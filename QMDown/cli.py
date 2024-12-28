import logging
from pathlib import Path
from typing import Annotated

import click
import typer
from qqmusic_api.song import SongFileType, get_song_urls
from rich.logging import RichHandler

from QMDown import __version__, console
from QMDown.downloader import AsyncDownloader
from QMDown.extractor import SongExtractor, SonglistExtractor
from QMDown.model import Song
from QMDown.utils import cli_coro

app = typer.Typer()
logger = logging.getLogger("QMDown.main")


def handle_version(value: bool):
    if value:
        typer.echo(f"QMDown {__version__}")
        raise typer.Exit()


def handle_debug(value: bool):
    logging.basicConfig(
        level="DEBUG" if value else "INFO",
        format="%(message)s",
        datefmt="[%X]",
        handlers=[
            RichHandler(
                show_path=False,
                markup=True,
                rich_tracebacks=True,
                console=console,
            )
        ],
    )


def handle_no_color(value: bool):
    if value:
        console.no_color = True


@app.command()
@cli_coro()
async def main(
    urls: Annotated[
        list[str],
        typer.Argument(
            help="链接。",
        ),
    ],
    output_path: Annotated[
        Path,
        typer.Option(
            "-o",
            "--output",
            help="歌曲保存路径",
            resolve_path=True,
        ),
    ] = Path.cwd(),
    quality: Annotated[
        str,
        typer.Option(
            "--quality",
            help="下载音质",
            click_type=click.Choice(
                list(SongFileType.__members__.keys()),
                case_sensitive=False,
            ),
        ),
    ] = SongFileType.MP3_128.name,
    num_workers: Annotated[
        int,
        typer.Option(
            "-n",
            "--num-workers",
            help="最大并发下载数",
        ),
    ] = 8,
    no_progress: Annotated[
        bool,
        typer.Option(
            "--no-progress",
            help="不显示进度条",
            is_flag=True,
        ),
    ] = False,
    no_color: Annotated[
        bool,
        typer.Option(
            "--no-color",
            help="不显示颜色",
            is_flag=True,
            callback=handle_no_color,
        ),
    ] = False,
    debug: Annotated[
        bool,
        typer.Option(
            "--debug",
            help="启用调试模式",
            is_flag=True,
            callback=handle_debug,
        ),
    ] = False,
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            "-v",
            help="显示版本信息",
            is_flag=True,
            is_eager=True,
            callback=handle_version,
        ),
    ] = None,
):
    # 初始化提取器
    extractors = [SongExtractor(), SonglistExtractor()]

    # 提取歌曲数据
    song_data: list[Song] = []

    status = console.status("解析链接中...")

    status.start()

    for url in urls:
        data = None
        for extractor in extractors:
            if extractor.suitable(url):
                data = await extractor.extract(url)
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

    file_type = SongFileType[quality]
    song_urls = await get_song_urls(list(data.keys()), file_type=file_type)

    logger.info(f"获取歌曲链接成功: [red]{len(list(filter(None,song_urls.values())))}/{len(data)}")
    status.stop()

    # 开始下载歌曲
    downloader = AsyncDownloader(save_dir=output_path, num_workers=num_workers, no_progress=no_progress)
    for mid, url in song_urls.items():
        song = data[mid]
        full_name = f"{song.title} - {song.signer_to_str()}"
        if url:
            await downloader.add_task(url=url, filename=full_name + file_type.e)
        else:
            logger.warning(f"[red]获取歌曲链接失败:[/] {full_name}")

    await downloader.run()


if __name__ == "__main__":
    app(prog_name="QMDown")
