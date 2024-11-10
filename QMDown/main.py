import asyncio
import signal
from enum import Enum
from functools import wraps
from pathlib import Path

import aiofiles
import httpx
import typer
from qqmusic_api import Credential
from qqmusic_api.song import SongFileType, get_song_urls
from qqmusic_api.songlist import Songlist
from rich.align import Align
from rich.console import Console
from rich.progress import BarColumn, DownloadColumn, Progress, TextColumn
from rich.prompt import Confirm
from rich.table import Table
from typing_extensions import Annotated

console = Console(log_path=False)
app = typer.Typer()


def cli_coro(
    signals=(signal.SIGHUP, signal.SIGTERM, signal.SIGINT),
    shutdown_func=None,
):
    """Decorator function that allows defining coroutines with click."""

    def decorator_cli_coro(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            loop = asyncio.get_event_loop()
            if shutdown_func:
                for ss in signals:
                    loop.add_signal_handler(ss, shutdown_func, ss, loop)
            return loop.run_until_complete(f(*args, **kwargs))

        return wrapper

    return decorator_cli_coro


def singer_to_str(singers: list[dict], sep: str = "&"):
    """
    将歌手列表转换为字符串

    Args:
        singers: 歌手列表
        sep: 分隔符
    """
    return "&".join(map(lambda x: x["name"], singers))


async def download(
    client: httpx.AsyncClient,
    url: str,
    file_name: str,
    file_suffix: str,
    base_path: str,
    progress: Progress,
):
    """
    下载文件

    Args:
        client: httpx.AsyncClient
        url: 文件下载链接
        file_name: 文件名
        file_suffix: 文件后缀
        base_path: 文件保存路径
        progress: 进度
    """
    file_path = f"{base_path}/{file_name}.{file_suffix}"

    async with client.stream("GET", url) as response:
        response.raise_for_status()
        total = int(response.headers.get("Content-Length", 0))

        task = progress.add_task("Downloading", total=total, file_name=file_name)

        async with aiofiles.open(file_path, "wb") as f:
            async for chunk in response.aiter_bytes(chunk_size=1024 * 5):
                await f.write(chunk)
                progress.update(task, advance=len(chunk))


@app.command()
@cli_coro()
async def main(
    songlist_id: Annotated[int, typer.Option("--songlist", help="歌单ID")],
    base_path: Annotated[
        Path,
        typer.Option(
            "--dir",
            help="歌曲保存路径",
            exists=True,
            dir_okay=True,
            writable=True,
            resolve_path=True,
        ),
    ] = Path.cwd(),
):
    songlist = Songlist(songlist_id)
    info = await songlist.get_detail()
    if not info["host_uin"]:
        console.print(f"无法找到歌单：[red]{songlist_id}[/red]")
        raise typer.Exit()
    info_table = Table(
        title="歌单信息",
        show_header=False,
        show_lines=True,
        expand=True,
    )
    info_table.add_row("歌单ID", str(songlist_id))
    info_table.add_row("歌单名称", info["title"])
    info_table.add_row("歌单创建者", info["host_nick"])
    info_table.add_row(Align("歌单描述", vertical="middle"), info["desc"])
    info_table.add_row("歌曲数量", str(info["songnum"]))
    console.print(info_table)

    if not Confirm.ask("是否下载歌曲？", default=True):
        raise typer.Exit()

    song_file_type = SongFileType.MP3_320

    data = await songlist.get_song()
    mids = map(lambda x: x["mid"], data)
    with console.status("获取歌曲文件链接..."):
        urls = await get_song_urls(list(mids), file_type=song_file_type)

    async with httpx.AsyncClient() as client:
        with Progress(
            TextColumn("[bold blue]{task.fields[file_name]}", justify="right"),
            BarColumn(),
            DownloadColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=console,
        ) as progress:
            for song in data:
                full_name = f"{song['title']} - {singer_to_str(song['singer'])}"
                if not urls.get(song["mid"], ""):
                    console.log(f"下载链接获取失败：[red]{full_name}[/red]")
                    continue

                await download(
                    client=client,
                    url=urls[song["mid"]],
                    file_name=full_name,
                    file_suffix=song_file_type.e.replace(".",""),
                    base_path=str(base_path),
                    progress=progress,
                )


if __name__ == "__main__":
    app()
