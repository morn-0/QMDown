import asyncio
import logging
import os
from io import BytesIO
from pathlib import Path

import anyio
import typer
from pydantic import HttpUrl
from qqmusic_api import Credential
from qqmusic_api.login_utils import PhoneLogin, PhoneLoginEvents, QQLogin, QrCodeLoginEvents, WXLogin
from qqmusic_api.song import get_song_urls
from qqmusic_api.user import User

from QMDown import console
from QMDown.model import Song, SongUrl
from QMDown.utils.priority import get_priority
from QMDown.utils.utils import print_ascii


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
                print_ascii(qrcode)
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
        logging.info(f"[Cookies] euin: {user_info['EncryptedUin']} name: [red]{user_info['Name']}")

        return credential

    return None


async def handle_song_urls(
    data: dict[str, Song],
    max_quality: int,
    credential: Credential | None,
):
    qualities = get_priority(int(max_quality))
    mids = [song.mid for song in data.values()]
    song_urls: list[SongUrl] = []
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
        logging.info(f"[blue][{_quality.name}]:[/] 获取成功 {len(_urls)}")
        song_urls.extend(
            [SongUrl(id=data[mid].id, mid=mid, url=HttpUrl(url), type=_quality) for mid, url in _urls.items() if url]
        )
    return song_urls, mids
