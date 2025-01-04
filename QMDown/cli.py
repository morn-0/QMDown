import logging
from pathlib import Path
from typing import Annotated

import click
import typer
from pydantic import HttpUrl
from qqmusic_api.exceptions import ResponseCodeError
from qqmusic_api.song import get_song_urls
from rich.logging import RichHandler

from QMDown import __version__, console
from QMDown.downloader import AsyncDownloader
from QMDown.extractor import SongExtractor, SonglistExtractor
from QMDown.extractor.album import AlbumExtractor
from QMDown.model import Song, SongUrl
from QMDown.quality import SongFileTypePriority, get_priority
from QMDown.utils import cli_coro, get_real_url

app = typer.Typer(context_settings={"help_option_names": ["-h", "--help"]})
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
        ),
    ] = Path.cwd(),
    max_quality: Annotated[
        str,
        typer.Option(
            "--quality",
            help="最大下载音质",
            click_type=click.Choice(
                [str(_.value) for _ in SongFileTypePriority],
            ),
        ),
    ] = str(SongFileTypePriority.MP3_128.value),
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
    """
    QQ 音乐解析/下载工具
    """
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

        _urls = await get_song_urls(mids, _quality)
        mids = list(filter(lambda mid: not _urls[mid], _urls))
        [_urls.pop(mid, None) for mid in mids]
        logger.info(f"[blue][{_quality.name}]:[/] 获取成功 {len(_urls)}")
        song_urls.extend(
            [SongUrl(id=data[mid].id, mid=mid, url=HttpUrl(url), quality=_quality) for mid, url in _urls.items() if url]
        )

    logger.info(f"[red]获取歌曲链接成功: {len(data) -len(mids)}/{len(data)}")

    if len(mids) > 0:
        logger.info(f"[red]获取歌曲链接失败: {[data[mid].get_full_name() for mid in mids]}")

    status.stop()

    if len(song_urls) == 0:
        raise typer.Exit()

    # 开始下载歌曲
    downloader = AsyncDownloader(save_dir=output_path, num_workers=num_workers, no_progress=no_progress)
    for _url in song_urls:
        song = data[_url.mid]
        await downloader.add_task(url=_url.url.__str__(), filename=song.get_full_name() + _url.quality.e)

    await downloader.run()


if __name__ == "__main__":
    app(prog_name="QMDown")
