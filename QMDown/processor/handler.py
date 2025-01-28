import asyncio
import logging
import os
from io import BytesIO
from pathlib import Path

import anyio
import typer
from qqmusic_api import Credential
from qqmusic_api.login import httpx
from qqmusic_api.login_utils import PhoneLogin, PhoneLoginEvents, QQLogin, QrCodeLoginEvents, WXLogin
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from QMDown import api, console
from QMDown.model import Song, SongUrl
from QMDown.utils.priority import get_priority
from QMDown.utils.tag import Metadata, write_metadata
from QMDown.utils.utils import show_qrcode, substitute_with_fullwidth


async def tag_audio(mid: str, album_mid: str, file: Path):
    """给音频文件添加元数据

    Args:
        mid: 歌曲 mid
        album_mid: 专辑 mid
        file: 音频文件路径
    """
    song_task = asyncio.create_task(api.get_song_detail(mid))
    album_task = asyncio.create_task(api.get_album_detail(mid=album_mid)) if album_mid else None

    # 处理歌曲信息
    song = await song_task
    track_info = song.track_info

    metadata: Metadata = {
        "title": [track_info.title],
        "artist": [s.name for s in track_info.singer],
    }
    if song.company:
        metadata["copyright"] = song.company
    if song.genre:
        metadata["genre"] = song.genre

    if track_info.index_album:
        metadata["tracknumber"] = [str(track_info.index_album)]
    if track_info.index_cd:
        metadata["discnumber"] = [str(track_info.index_cd)]

    # 处理专辑信息
    if album_task:
        album = await album_task
        metadata.update(
            {
                "album": [album.info.name],
                "albumartist": [s.name for s in album.singer],
            }
        )

    # 处理发行时间
    if song.time_public and song.time_public[0]:
        metadata["date"] = [str(song.time_public[0])]
    logging.debug(f"[blue][标签][/] {file}: {metadata}")
    await write_metadata(file, metadata)


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

    logging.info("[blue][Cookies][/] 登录账号中...")
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

        user = await api.get_user_detail(euin=credential.encrypt_uin, credential=credential)
        user_info = user["Info"]["BaseInfo"]
        logging.info(f"[blue][Cookies][/] 当前登录账号: [red bold]{user_info['Name']}({credential.musicid}) ")

        return credential

    return None


async def handle_song_urls(
    data: dict[str, Song],
    max_quality: int,
    credential: Credential | None,
) -> tuple[list[SongUrl], list[str]]:
    qualities = get_priority(max_quality)
    all_mids = [song.mid for song in data.values()]
    success_urls: list[SongUrl] = []
    pending_mids = all_mids.copy()
    for current_quality in qualities:
        if not pending_mids:
            break
        try:
            batch_urls = await api.get_download_url(mids=pending_mids, quality=current_quality, credential=credential)
            url_map = {url.mid: url for url in batch_urls if url.url}
            succeeded = []
            remaining = []
            for mid in pending_mids:
                if mid in url_map:
                    succeeded.append(url_map[mid])
                else:
                    remaining.append(mid)
            success_urls.extend(succeeded)
            pending_mids = remaining

            logging.info(f"[blue][{current_quality.name}]:[/] 获取成功数量: {len(succeeded)}")
        except Exception as e:
            logging.error(f"[blue][{current_quality.name}]:[/] {e}")
            continue

    return success_urls, pending_mids


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
    async def download_lyric(mid: str):
        song = data[mid]
        song_name = song.get_full_name()
        lyric_path = save_dir / f"{substitute_with_fullwidth(song_name)}.lrc"

        if not overwrite and lyric_path.exists():
            logging.info(f"[blue][跳过][/] {lyric_path.name}")
            return

        try:
            lyric = await api.get_lyric(mid=mid, qrc=qrc, trans=trans, roma=roma)
        except Exception as e:
            logging.error(f"[red][错误][/] 下载歌词失败: {song_name} - {e}")
            return

        if not lyric.lyric:
            logging.warning(f"[yellow] {song_name} 无歌词")
            return

        parser = lyric.get_parser()

        async with await anyio.open_file(lyric_path, "w") as f:
            await f.write(parser.dump())

        logging.info(f"[blue][完成][/] {lyric_path.name}")

    semaphore = asyncio.Semaphore(num_workers)

    async def safe_download(mid: str):
        async with semaphore:
            await download_lyric(mid)

    with console.status("下载歌词中..."):
        await asyncio.gather(*(safe_download(song.mid) for song in data.values()))
