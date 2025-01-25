import asyncio
import logging
import os
from io import BytesIO
from pathlib import Path

import anyio
import typer
from pydantic import HttpUrl
from qqmusic_api import Credential
from qqmusic_api.login import httpx
from qqmusic_api.login_utils import PhoneLogin, PhoneLoginEvents, QQLogin, QrCodeLoginEvents, WXLogin
from qqmusic_api.lyric import get_lyric
from qqmusic_api.song import get_song_urls
from qqmusic_api.user import User
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from QMDown import console
from QMDown.model import Song, SongUrl
from QMDown.utils.lrcparser import LrcParser
from QMDown.utils.priority import get_priority
from QMDown.utils.utils import show_qrcode


async def handle_login(  # noqa: C901
    cookies: str | None = None,
    login_type: str | None = None,
    cookies_load_path: Path | None = None,
    cookies_save_path: Path | None = None,
) -> Credential | None:
    credential = None
    if cookies:
        if ":" in cookies:
            data = cookies.split(":")
            credential = Credential(
                musicid=int(data[0]),
                musickey=data[1],
            )
        raise typer.BadParameter("格式错误,将'musicid'与'musickey'使用':'连接")

    if login_type:
        if login_type.lower() in ["qq", "wx"]:
            login = WXLogin() if login_type.lower() == "wx" else QQLogin()
            logging.info(f"二维码登录 [red]{login.__class__.__name__}")
            with console.status("获取二维码中...") as status:
                qrcode = BytesIO(await login.get_qrcode())
                status.stop()
                show_qrcode(qrcode)
                status.update(f"[red]请使用[blue] {login_type.upper()} [red]扫描二维码登录")
                status.start()
                while True:
                    state, credential = await login.check_qrcode_state()
                    if state == QrCodeLoginEvents.REFUSE:
                        logging.warning("[yellow]二维码登录被拒绝")
                        return None
                    if state == QrCodeLoginEvents.CONF:
                        status.update("[red]请确认登录")
                    if state == QrCodeLoginEvents.TIMEOUT:
                        logging.warning("[yellow]二维码登录超时")
                        return None
                    if state == QrCodeLoginEvents.DONE:
                        status.stop()
                        logging.info(f"[blue]{login_type.upper()}[green]登录成功")
                    await asyncio.sleep(1)
        else:
            phone = typer.prompt("请输入手机号", type=int)
            login = PhoneLogin(int(phone))
            with console.status("获取验证码中...") as status:
                while True:
                    state = await login.send_authcode()
                    if state == PhoneLoginEvents.SEND:
                        logging.info("[red]验证码发送成功")
                        break
                    if state == PhoneLoginEvents.CAPTCHA:
                        logging.info("[red]需要滑块验证")
                        if login.auth_url is None:
                            logging.warning("[yellow]获取验证链接失败")
                            return None
                        logging.info(f"请复制链接前往浏览器验证:{login.auth_url}")
                        status.stop()
                        typer.confirm("验证后请回车", prompt_suffix="", show_default=False)
                        status.start()
                    else:
                        logging.warning("[yellow]登录失败(未知情况)")
                        return None
            code = typer.prompt("请输入验证码", type=int)
            try:
                credential = await login.authorize(code)
            except Exception:
                logging.warning("[yellow]验证码错误或已过期")
                return None

    if cookies_load_path:
        credential = Credential.from_cookies_str(await (await anyio.open_file(cookies_load_path)).read())

    if credential:
        if await credential.is_expired():
            logging.warning("[yellow]Cookies 已过期,正在尝试刷新...")
            if await credential.refresh():
                logging.info("[green]Cookies 刷新成功")
                if cookies_load_path and os.access(cookies_load_path, os.W_OK):
                    cookies_save_path = cookies_load_path
                else:
                    logging.warning("[yellow]Cookies 刷新失败")

        # 保存 Cookies
        if cookies_save_path:
            logging.info(f"[green]保存 Cookies 到: {cookies_save_path}")
            await (await anyio.open_file(cookies_save_path, "w")).write(credential.as_json())

        user = User(euin=credential.encrypt_uin, credential=credential)
        user_info = (await user.get_homepage())["Info"]["BaseInfo"]
        logging.info(f"[blue][Cookies][/] 当前登录账号: [red bold]{user_info['Name']}({credential.musicid}) ")

        return credential

    return None


async def handle_song_urls(
    data: dict[str, Song],
    max_quality: int,
    credential: Credential | None,
):
    qualities = get_priority(int(max_quality))
    all_mids = [song.mid for song in data.values()]
    song_urls: list[SongUrl] = []
    mids = all_mids.copy()
    for _quality in qualities:
        if len(mids) == 0:
            break
        _urls = {}
        try:
            _urls = await get_song_urls(mids, _quality, credential=credential)
        except Exception:
            pass
        mids = list(filter(lambda mid: not _urls[mid], _urls))
        [_urls.pop(mid, None) for mid in mids]
        song_urls.extend(
            [SongUrl(id=data[mid].id, mid=mid, url=HttpUrl(url), type=_quality) for mid, url in _urls.items() if url]
        )
        logging.info(f"[blue][{_quality.name}]:[/] 获取成功数量: {len(_urls)}")
    return song_urls, [mid for mid in all_mids if mid not in mids], mids


async def handle_lyric(
    data: dict[str, Song],
    save_dir: str | Path = ".",
    num_workers: int = 3,
    overwrite: bool = False,
    trans: bool = False,
    roma: bool = False,
    qrc: bool = False,
):
    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.ReadTimeout, httpx.ConnectTimeout)),
    )
    async def download_lyric(client: httpx.AsyncClient, mid: str):
        song = data[mid]
        song_name = song.get_full_name()
        lyric_path = save_dir / f"{song_name}.lrc"

        if not overwrite and lyric_path.exists():
            logging.info(f"[blue][跳过][/] {lyric_path.name}")
            return

        try:
            lyric = await get_lyric(mid=mid, qrc=qrc, trans=trans, roma=roma)
        except Exception as e:
            logging.error(f"[red][错误][/] 下载歌词失败: {song_name} - {e}")
            return

        ori_data = lyric.get("lyric", "")

        if not ori_data:
            logging.warning(f"[yellow] {song_name} 无歌词")
            return

        trans_data = lyric.get("trans", "")
        roma_data = lyric.get("roma", "")

        lyrics = LrcParser(ori_data)
        lyrics.parse_lrc(trans_data)
        lyrics.parse_lrc(roma_data)

        if trans and not trans_data:
            logging.warning(f"[yellow] {song_name} 无翻译歌词")

        if roma and not roma_data:
            logging.warning(f"[yellow] {song_name} 无罗马歌词")

        async with await anyio.open_file(lyric_path, "w") as f:
            await f.write(lyrics.dump())

        logging.info(f"[blue][完成][/] {lyric_path.name}")

    async with httpx.AsyncClient() as client:
        semaphore = asyncio.Semaphore(num_workers)

        async def safe_download(mid: str):
            async with semaphore:
                await download_lyric(client, mid)

        with console.status("下载歌词中..."):
            await asyncio.gather(*(safe_download(song.mid) for song in data.values()))
