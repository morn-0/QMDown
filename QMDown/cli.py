import asyncio
import logging
import os
from io import BytesIO
from pathlib import Path
from typing import Annotated

import anyio
import click
import typer
from pydantic import HttpUrl
from qqmusic_api import Credential
from qqmusic_api.exceptions import ResponseCodeError
from qqmusic_api.login import QrCodeLoginEvents
from qqmusic_api.login_utils import QQLogin, WXLogin
from qqmusic_api.song import get_song_urls
from typer import rich_utils

from QMDown import __version__, console
from QMDown.downloader import AsyncDownloader
from QMDown.extractor import SongExtractor, SonglistExtractor
from QMDown.extractor.album import AlbumExtractor
from QMDown.model import Song, SongUrl
from QMDown.quality import SongFileTypePriority, get_priority
from QMDown.utils import cli_coro, get_real_url, print_ascii

app = typer.Typer(
    context_settings={"help_option_names": ["-h", "--help"]},
    add_completion=False,
)
logger = logging.getLogger("QMDown.main")


def handle_version(value: bool):
    if value:
        console.print(f"[green]QMDown [blue]{__version__}")
        raise typer.Exit()


def handle_no_color(value: bool):
    if value:
        console.no_color = value
        rich_utils.COLOR_SYSTEM = None


def handle_debug(value: bool):
    if value:
        logging.getLogger().setLevel(logging.DEBUG)


def parse_cookies(value: str | None) -> Credential | None:
    if value:
        if ":" in value:
            data = value.split(":")
            return Credential(
                musicid=int(data[0]),
                musickey=data[1],
            )
        raise typer.BadParameter("格式错误")
    return None


async def handle_login_qr(value: str | None) -> Credential | None:
    if value:
        login = WXLogin() if value == "wx" else QQLogin()
        logger.info(f"二维码登录 [red]{login.__class__.__name__}")
        with console.status("获取二维码中...") as status:
            qrcode = BytesIO(await login.get_qrcode())
            status.stop()
            print_ascii(qrcode)
            status.update(f"[red]请使用[blue] {value.upper()} [red]扫描二维码登录")
            status.start()
            while True:
                state, credential = await login.check_qrcode_state()
                if state == QrCodeLoginEvents.REFUSE:
                    logger.warning("[yellow]二维码登录被拒绝")
                    return None
                if state == QrCodeLoginEvents.CONF:
                    status.update("[red]请确认登录")
                if state == QrCodeLoginEvents.TIMEOUT:
                    logger.warning("[yellow]二维码登录超时")
                    return None
                if state == QrCodeLoginEvents.DONE:
                    status.stop()
                    logger.info(f"[blue]{value.upper()}[green]登录成功")
                    break
                await asyncio.sleep(1)

        return credential

    return None


@app.command()
@cli_coro()
async def main(  # noqa: C901
    urls: Annotated[
        list[str],
        typer.Argument(
            help="链接",
        ),
    ],
    output_path: Annotated[
        Path,
        typer.Option(
            "-o",
            "--output",
            help="歌曲保存路径",
            resolve_path=True,
            file_okay=False,
            rich_help_panel="[blue]Download [green]下载",
        ),
    ] = Path.cwd(),
    num_workers: Annotated[
        int,
        typer.Option(
            "-n",
            "--num-workers",
            help="最大并发下载数",
            rich_help_panel="[blue]Download [green]下载",
            min=1,
        ),
    ] = 8,
    max_quality: Annotated[
        str,
        typer.Option(
            "-q",
            "--quality",
            help="最大下载音质",
            click_type=click.Choice(
                [str(_.value) for _ in SongFileTypePriority],
            ),
            rich_help_panel="[blue]Download [green]下载",
        ),
    ] = str(SongFileTypePriority.MP3_128.value),
    no_progress: Annotated[
        bool,
        typer.Option(
            "--no-progress",
            help="不显示进度条",
        ),
    ] = False,
    no_color: Annotated[
        bool,
        typer.Option(
            "--no-color",
            help="不显示颜色",
            is_eager=True,
            callback=handle_no_color,
        ),
    ] = False,
    cookies: Annotated[
        str | None,
        typer.Option(
            "-c",
            "--cookies",
            help="QQ 音乐 Cookie",
            metavar="musicid:musickey",
            show_default=False,
            rich_help_panel="[blue]Login [green]登录",
        ),
    ] = None,
    login_qr: Annotated[
        str | None,
        typer.Option(
            "--login-qr",
            help="二维码登录",
            click_type=click.Choice(["qq", "wx"], case_sensitive=False),
            rich_help_panel="[blue]Login [green]登录",
            show_default=False,
        ),
    ] = None,
    c_load_path: Annotated[
        Path | None,
        typer.Option(
            "--load",
            help="从文件读取 Cookies 信息",
            rich_help_panel="[blue]Login [green]登录",
            resolve_path=True,
            dir_okay=False,
            show_default=False,
        ),
    ] = None,
    c_save_path: Annotated[
        Path | None,
        typer.Option(
            "--save",
            help="保存 Cookies 信息到文件",
            rich_help_panel="[blue]Login [green]登录",
            resolve_path=True,
            dir_okay=False,
            writable=True,
            show_default=False,
        ),
    ] = None,
    debug: Annotated[
        bool | None,
        typer.Option(
            "--debug",
            help="启用调试模式",
            is_eager=True,
            callback=handle_debug,
        ),
    ] = None,
    version: Annotated[
        bool | None,
        typer.Option(
            "-v",
            "--version",
            help="显示版本信息",
            is_eager=True,
            callback=handle_version,
        ),
    ] = None,
):
    """
    QQ 音乐解析/下载工具
    """
    # 登录
    if (cookies, login_qr, c_load_path).count(None) < 1:
        raise typer.BadParameter("选项 '--credential' , '--login-qr' 或 '--load' 不能共用")

    credential = parse_cookies(cookies) or await handle_login_qr(login_qr)
    if c_load_path:
        credential = Credential.from_cookies_str(await (await anyio.open_file(c_load_path)).read())

    if credential:
        if await credential.is_expired():
            logger.warning("[yellow]Cookies 已过期,正在尝试刷新...")
            if await credential.refresh():
                logger.info("[green]Cookies 刷新成功")
                if c_load_path and os.access(c_load_path, os.W_OK):
                    c_save_path = c_load_path
            else:
                logger.warning("[yellow]Cookies 刷新失败")

        # 保存 Cookies
        if c_save_path:
            logger.info(f"[green]保存 Cookies 到: {c_save_path}")
            await (await anyio.open_file(c_save_path, "w")).write(credential.as_json())

    # 初始化提取器
    extractors = [SongExtractor(), SonglistExtractor(), AlbumExtractor()]

    # 提取歌曲数据
    song_data: list[Song] = []
    status = console.status("解析链接中...")
    status.start()
    for url in urls:
        if "c6.y.qq.com/base/fcgi-bin" in url:
            _url = url
            url = await get_real_url(url)
            if not url:
                logger.info(f"获取真实链接失败: {_url}")
                continue
            logger.info(f"{_url} -> {url}")
        data = None
        for extractor in extractors:
            if extractor.suitable(url):
                try:
                    data = await extractor.extract(url)
                except ResponseCodeError:
                    pass
                finally:
                    break
        if not data:
            logger.info(f"Not Supported: {url}")
            break
        if isinstance(data, list):
            song_data.extend(data)
        else:
            song_data.append(data)

    # 歌曲去重
    data = {item.mid: item for item in song_data}
    # 获取歌曲链接
    status.update(f"获取歌曲链接([red]{len(data)}[/])...")

    qualities = get_priority(int(max_quality))
    mids = [song.mid for song in data.values()]
    song_urls: list[SongUrl] = []
    for _quality in qualities:
        if len(mids) == 0:
            break
        _urls = {}
        try:
            _urls = await get_song_urls(mids, _quality, credential=credential)
        except ResponseCodeError as e:
            logger.error(f"[red]获取歌曲链接失败: {e.message}")
        mids = list(filter(lambda mid: not _urls[mid], _urls))
        [_urls.pop(mid, None) for mid in mids]
        logger.info(f"[blue][{_quality.name}]:[/] 获取成功 {len(_urls)}")
        song_urls.extend(
            [SongUrl(id=data[mid].id, mid=mid, url=HttpUrl(url), type=_quality) for mid, url in _urls.items() if url]
        )

    logger.info(f"[red]获取歌曲链接成功: {len(data) - len(mids)}/{len(data)}")

    if len(mids) > 0:
        logger.info(f"[red]获取歌曲链接失败: {[data[mid].get_full_name() for mid in mids]}")

    status.stop()

    if len(song_urls) == 0:
        raise typer.Exit()

    # 开始下载歌曲
    downloader = AsyncDownloader(save_dir=output_path, num_workers=num_workers, no_progress=no_progress)
    for _url in song_urls:
        song = data[_url.mid]
        await downloader.add_task(url=_url.url.__str__(), filename=song.get_full_name() + _url.type.e)

    await downloader.run()


if __name__ == "__main__":
    app(prog_name="QMDown")
