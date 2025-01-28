import logging
from pathlib import Path
from typing import Annotated

import click
import typer
from qqmusic_api import Credential
from rich.table import Table
from typer import rich_utils

from QMDown import __version__, console
from QMDown.extractor import AlbumExtractor, SongExtractor, SonglistExtractor
from QMDown.model import Song
from QMDown.processor.downloader import AsyncDownloader
from QMDown.processor.handler import handle_login, handle_lyric, handle_song_urls, tag_audio
from QMDown.utils.async_typer import AsyncTyper
from QMDown.utils.priority import SongFileTypePriority
from QMDown.utils.tag import add_cover_to_audio
from QMDown.utils.utils import get_real_url

app = AsyncTyper(
    context_settings={"help_option_names": ["-h", "--help"]},
    add_completion=False,
    invoke_without_command=True,
)


def handle_version(value: bool):
    if value:
        console.print(f"[green bold]QMDown [blue bold]{__version__}")
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


def print_params(ctx: typer.Context):
    console.print("🌈 当前运行参数:", style="bold blue")
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("参数项", style="bold cyan", width=20)
    table.add_column("配置值", style="yellow", overflow="fold")
    sensitive_params = {"cookies"}
    for name, value in ctx.params.items():
        if value is None:
            continue

        if name in sensitive_params and value:
            display_value = f"{value[:4]}****{value[-4:]}" if isinstance(value, str) else "****"
        else:
            if isinstance(value, Path):
                display_value = f"{value.resolve()}"
            elif isinstance(value, list):
                display_value = "\n".join([f"{_}" for _ in value]) if value else "空列表"
            else:
                display_value = str(value)

        if isinstance(value, bool):
            display_value = f"[{'bold green' if value else 'bold red'}]{display_value}[/]"
        elif isinstance(value, int):
            display_value = f"[bold blue]{display_value}[/]"
        param_name = f"--{name.replace('_', '-')}"
        table.add_row(param_name, display_value)
    console.print(table)
    console.print("🚀 开始执行下载任务...", style="bold blue")


@app.command()
async def cli(  # noqa: C901
    ctx: typer.Context,
    urls: Annotated[
        list[str],
        typer.Argument(
            help="QQ 音乐链接(支持多个链接)",
            show_default=False,
        ),
    ],
    output_path: Annotated[
        Path,
        typer.Option(
            "-o",
            "--output",
            help="下载文件存储目录",
            resolve_path=True,
            file_okay=False,
            rich_help_panel="[blue bold]Download[/] [green bold]下载",
        ),
    ] = Path.cwd(),
    num_workers: Annotated[
        int,
        typer.Option(
            "-n",
            "--num-workers",
            help="并发下载协程数量",
            rich_help_panel="[blue bold]Download[/] [green bold]下载",
            min=1,
        ),
    ] = 8,
    max_quality: Annotated[
        str,
        typer.Option(
            "-q",
            "--quality",
            help="首选音频品质",
            click_type=click.Choice(
                [str(_.value) for _ in SongFileTypePriority],
            ),
            rich_help_panel="[blue bold]Download[/] [green bold]下载",
        ),
    ] = str(SongFileTypePriority.MP3_128.value),
    overwrite: Annotated[
        bool,
        typer.Option(
            "-w",
            "--overwrite",
            help="覆盖已存在文件",
            rich_help_panel="[blue bold]Download[/] [green bold]下载",
        ),
    ] = False,
    with_lyric: Annotated[
        bool,
        typer.Option(
            "--lyric",
            help="下载原始歌词文件",
            rich_help_panel="[blue bold]Lyric[/] [green bold]歌词选项",
        ),
    ] = False,
    with_trans: Annotated[
        bool,
        typer.Option(
            "--trans",
            help="下载双语翻译歌词(需配合`--lyric`使用)",
            rich_help_panel="[blue bold]Lyric[/] [green bold]歌词选项",
        ),
    ] = False,
    with_roma: Annotated[
        bool,
        typer.Option(
            "--roma",
            help="下载罗马音歌词(需配合`--lyric`使用)",
            rich_help_panel="[blue bold]Lyric[/] [green bold]歌词选项",
        ),
    ] = False,
    no_metadata: Annotated[
        bool,
        typer.Option(
            "--no-metadata",
            help="禁用元数据添加",
            rich_help_panel="[blue bold]Metadata[/] [green bold]元数据",
        ),
    ] = False,
    no_cover: Annotated[
        bool,
        typer.Option(
            "--no-cover",
            help="禁用专辑封面嵌入",
            rich_help_panel="[blue bold]Metadata[/] [green bold]元数据",
        ),
    ] = False,
    cookies: Annotated[
        str | None,
        typer.Option(
            "-c",
            "--cookies",
            help="QQ音乐Cookie凭证(从浏览器开发者工具获取 `musicid` 和 `musickey`,拼接为 `musicid:musickey` 格式)",
            metavar="MUSICID:MUSICKEY",
            show_default=False,
            rich_help_panel="[blue bold]Authentication[/] [green bold]认证管理",
        ),
    ] = None,
    login_type: Annotated[
        str | None,
        typer.Option(
            "--login",
            help="第三方登录方式",
            click_type=click.Choice(
                ["QQ", "WX", "PHONE"],
                case_sensitive=False,
            ),
            rich_help_panel="[blue bold]Authentication[/] [green bold]认证管理",
            show_default=False,
        ),
    ] = None,
    cookies_load_path: Annotated[
        Path | None,
        typer.Option(
            "--load",
            help="加载 Cookies 文件路径",
            rich_help_panel="[blue bold]Authentication[/] [green bold]认证管理",
            resolve_path=True,
            dir_okay=False,
            show_default=False,
        ),
    ] = None,
    cookies_save_path: Annotated[
        Path | None,
        typer.Option(
            "--save",
            help="持久化 Cookies 文件路径",
            rich_help_panel="[blue bold]Authentication[/] [green bold]认证管理",
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
            help="禁用进度条显示",
        ),
    ] = False,
    no_color: Annotated[
        bool,
        typer.Option(
            "--no-color",
            help="禁用彩色输出",
            is_eager=True,
            callback=handle_no_color,
        ),
    ] = False,
    debug: Annotated[
        bool | None,
        typer.Option(
            "--debug",
            help="启用调试日志输出",
            is_eager=True,
            callback=handle_debug,
        ),
    ] = None,
    version: Annotated[
        bool | None,
        typer.Option(
            "-v",
            "--version",
            help="输出版本信息",
            is_eager=True,
            callback=handle_version,
        ),
    ] = None,
):
    """
    QQ 音乐解析/下载工具
    """
    print_params(ctx)

    if (cookies, login_type, cookies_load_path).count(None) < 1:
        raise typer.BadParameter("选项 '--credential' , '--login' 或 '--load' 不能共用")

    # 登录
    credential = await handle_login(cookies, login_type, cookies_load_path, cookies_save_path)
    # 提取歌曲信息
    extractors = [SongExtractor(), SonglistExtractor(), AlbumExtractor()]
    song_data: list[Song] = []
    with console.status("解析链接中...") as status:
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
                    except Exception as e:
                        logging.error(f"[blue bold][{extractor.__class__.__name__}][/] {e}", exc_info=True)
                    break
            else:
                logging.info(f"Not Supported: {url}")
        # 歌曲去重
        data = {item.mid: item for item in song_data}

        if len(data) == 0:
            raise typer.Exit()

        # 获取歌曲链接
        status.update(f"[green bold]获取歌曲链接中[/] 共{len(data)}首...")
        song_urls, f_mids = await handle_song_urls(data, int(max_quality), credential)

        logging.info(f"[red]获取歌曲链接成功: {len(data) - len(f_mids)}/{len(data)}")

        if len(f_mids) > 0:
            logging.info(f"[red]获取歌曲链接失败: {[data[mid].get_full_name() for mid in f_mids]}")

    if len(song_urls) == 0:
        raise typer.Exit()

    # 下载歌曲
    logging.info(f"[blue bold][歌曲][/] 开始下载 总共 {len(song_urls)} 首")

    song_downloader = AsyncDownloader(
        save_dir=output_path,
        num_workers=num_workers,
        no_progress=no_progress,
        overwrite=overwrite,
    )

    tags: dict[Path, Song] = {}

    for url in song_urls:
        song = data[url.mid]
        path = await song_downloader.add_task(
            url=url.url.__str__(), file_name=song.get_full_name(), file_suffix=url.type.e
        )
        if song.album.mid or song.album.pmid:
            tags[path] = song

    await song_downloader.execute_tasks()

    logging.info("[blue bold][歌曲][green bold] 下载完成")

    if not no_metadata:
        logging.info("[blue bold][标签][/] 开始添加元数据")
        with console.status("添加元数据中..."):
            for path, song in tags.items():
                await tag_audio(song.mid, song.album.mid, path)
        logging.info("[blue bold][标签][green bold] 元数据添加完成")

    if not no_cover:
        # 下载封面
        logging.info("[blue bold][封面][/] 开始下载专辑封面")

        cover_downloader = AsyncDownloader(
            save_dir=output_path,
            num_workers=num_workers,
            overwrite=overwrite,
        )

        for song in tags.values():
            await cover_downloader.add_task(
                url=f"https://y.gtimg.cn/music/photo_new/T002R500x500M000{song.album.mid or song.album.pmid}.jpg",
                file_name=song.get_full_name(),
                file_suffix=".jpg",
            )

        await cover_downloader.execute_tasks()

        logging.info("[blue bold][封面][green bold] 专辑封面下载完成")

        logging.info("[blue bold][封面][/] 开始嵌入专辑封面")
        with console.status("嵌入封面中..."):
            for path, song in tags.items():
                cover_path = path.with_suffix(".jpg")
                await add_cover_to_audio(path, cover_path)
        logging.info("[blue bold][封面][green bold] 专辑封面嵌入完成")

    # 下载歌词
    if with_lyric:
        logging.info("[blue bold][歌词][/] 开始下载")
        await handle_lyric(
            {url.mid: data[url.mid] for url in song_urls},
            save_dir=output_path,
            num_workers=num_workers,
            overwrite=overwrite,
            trans=with_trans,
            roma=with_roma,
        )
        logging.info("[blue bold][歌词][green bold] 下载完成")


if __name__ == "__main__":
    app()
