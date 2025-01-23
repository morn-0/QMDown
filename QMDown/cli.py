import logging
from pathlib import Path
from typing import Annotated

import click
import typer
from qqmusic_api import Credential
from typer import rich_utils

from QMDown import __version__, console
from QMDown.extractor import AlbumExtractor, SongExtractor, SonglistExtractor
from QMDown.model import Song
from QMDown.processor.downloader import AsyncDownloader
from QMDown.processor.handler import handle_login, handle_song_urls
from QMDown.utils.priority import SongFileTypePriority
from QMDown.utils.utils import cli_coro, get_real_url

app = typer.Typer(
    context_settings={"help_option_names": ["-h", "--help"]},
    add_completion=False,
    invoke_without_command=True,
)


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
        raise typer.BadParameter("格式错误,将'musicid'与'musickey'使用':'连接")
    return None


@app.command()
@cli_coro()
async def cli(  # noqa: C901
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
    login_type: Annotated[
        str | None,
        typer.Option(
            "--login",
            help="登录获取 Cookies",
            click_type=click.Choice(
                ["QQ", "WX", "PHONE"],
                case_sensitive=False,
            ),
            rich_help_panel="[blue]Login [green]登录",
            show_default=False,
        ),
    ] = None,
    cookies_load_path: Annotated[
        Path | None,
        typer.Option(
            "--load",
            help="从文件读取 Cookies",
            rich_help_panel="[blue]Login [green]登录",
            resolve_path=True,
            dir_okay=False,
            show_default=False,
        ),
    ] = None,
    cookies_save_path: Annotated[
        Path | None,
        typer.Option(
            "--save",
            help="保存 Cookies 到文件",
            rich_help_panel="[blue]Login [green]登录",
            resolve_path=True,
            dir_okay=False,
            writable=True,
            show_default=False,
        ),
    ] = None,
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
    if (cookies, login_type, cookies_load_path).count(None) < 1:
        raise typer.BadParameter("选项 '--credential' , '--login' 或 '--load' 不能共用")

    # 登录
    credential = await handle_login(cookies, login_type, cookies_load_path, cookies_save_path)
    # 提取歌曲信息
    extractors = [SongExtractor(), SonglistExtractor(), AlbumExtractor()]
    song_data: list[Song] = []
    status = console.status("解析链接中...")
    status.start()

    for url in urls:
        # 获取真实链接(如果适用)
        original_url = url
        if "c6.y.qq.com/base/fcgi-bin" in url:
            url = await get_real_url(url) or url
            if url == original_url:
                logging.info(f"获取真实链接失败: {original_url}")
                continue
            logging.info(f"{original_url} -> {url}")

        # 尝试用提取器解析链接
        for extractor in extractors:
            if extractor.suitable(url):
                try:
                    data = await extractor.extract(url)
                    if isinstance(data, list):
                        song_data.extend(data)
                    else:
                        song_data.append(data)
                except Exception:
                    pass
                break
        else:
            logging.info(f"Not Supported: {url}")

    # 歌曲去重
    data = {item.mid: item for item in song_data}
    # 获取歌曲链接
    status.update(f"[green]获取歌曲链接中[/] 共{len(data)}首...")
    song_urls, mids = await handle_song_urls(data, int(max_quality), credential)
    logging.info(f"[red]获取歌曲链接成功: {len(data) - len(mids)}/{len(data)}")
    if len(mids) > 0:
        logging.info(f"[red]获取歌曲链接失败: {[data[mid].get_full_name() for mid in mids]}")
    status.stop()

    if len(song_urls) == 0:
        raise typer.Exit()

    # 开始下载歌曲
    downloader = AsyncDownloader(save_dir=output_path, num_workers=num_workers, no_progress=no_progress)
    for _url in song_urls:
        song = data[_url.mid]
        await downloader.add_task(url=_url.url.__str__(), file_name=song.get_full_name(), file_suffix=_url.type.e)

    await downloader.execute_tasks()


if __name__ == "__main__":
    app()
