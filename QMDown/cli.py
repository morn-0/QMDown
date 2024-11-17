import logging
from pathlib import Path
from typing import Annotated

import typer
from qqmusic_api.song import get_song_urls
from qqmusic_api.songlist import Songlist
from rich.prompt import Confirm
from rich.table import Table

from QMDown import __version__, console
from QMDown.downloader import AsyncDownloader
from QMDown.utils import cli_coro, singer_to_str

app = typer.Typer(add_completion=False)


def handle_version(value: bool):
    if value:
        typer.echo(f"QMDown {__version__}")
        raise typer.Exit()


@app.command()
@cli_coro()
async def main(
    id: Annotated[
        list[int],
        typer.Argument(
            help="歌单ID",
            show_default=False,
        ),
    ],
    output_path: Annotated[
        Path,
        typer.Option(
            "-o",
            "--output",
            help="歌曲保存路径。",
            show_default=False,
            exists=True,
            dir_okay=True,
            writable=True,
            resolve_path=True,
        ),
    ] = Path.cwd(),
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            "-v",
            help="显示版本信息。",
            is_flag=True,
            is_eager=True,
            callback=handle_version,
        ),
    ] = None,
):
    logging.info("解析歌单中...")
    info_table = Table(
        title="歌单信息",
        show_lines=True,
        expand=True,
    )
    info_table.add_column("歌单ID")
    info_table.add_column("歌单名称")
    info_table.add_column("歌单创建者")
    info_table.add_column("歌曲数量")

    songlist_data: list[Songlist] = []

    for songlist_id in set(id):
        songlist = Songlist(songlist_id)
        info = await songlist.get_detail()
        if not info["host_uin"]:
            logging.info(f"无法找到歌单：[red]{songlist_id}[/red]")
            continue

        songlist_data.append(songlist)
        info_table.add_row(
            str(songlist_id),
            info["title"],
            info["host_nick"],
            str(info["songnum"]),
        )

    console.print(info_table)

    if not Confirm.ask("是否确认下载歌单？", default=True, console=console):
        raise typer.Exit()

    logging.info("获取歌曲信息...")
    song_data = []
    for songlist in songlist_data:
        song_data.extend(await songlist.get_song())

    song_data = {song["mid"]: song for song in song_data}
    mids = list(map(lambda x: x["mid"], song_data.values()))

    info_table = Table(
        title="获取链接失败",
        show_lines=False,
        expand=True,
    )
    info_table.add_column("歌曲")
    info_table.add_column("歌手")

    downloader = AsyncDownloader(output_path)

    with console.status("获取歌曲文件链接..."):
        urls = await get_song_urls(mids)
        failed_num = 0

        for mid, url in urls.items():
            song = song_data[mid]
            if url:
                await downloader.add_task(url, song["title"] + ".mp3")
            else:
                failed_num += 1
                info_table.add_row(song["name"], singer_to_str(song["singer"]))

    console.print(info_table)
    logging.info(f"获取失败歌曲总数：{failed_num}/{len(mids)}")
    logging.info("开始下载歌曲")
    await downloader.run()
    logging.info("下载完成")


if __name__ == "__main__":
    app(prog_name="QMDown")
