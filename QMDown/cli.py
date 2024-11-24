import logging
from pathlib import Path
from typing import Annotated

import click
import typer
from qqmusic_api.song import SongFileType
from rich.logging import RichHandler

from QMDown import __version__, console
from QMDown.utils import cli_coro

app = typer.Typer(add_completion=False)
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


@app.command()
@cli_coro()
async def main(
    url: Annotated[list[str], typer.Argument(help="链接")],
    output_path: Annotated[
        Path,
        typer.Option(
            "-o",
            "--output",
            help="歌曲保存路径。",
            show_default=False,
            resolve_path=True,
        ),
    ] = Path.cwd(),
    quality: Annotated[
        str,
        typer.Option(
            "--quality",
            help="下载音质。",
            click_type=click.Choice(
                list(SongFileType.__members__.keys()),
                case_sensitive=False,
            ),
        ),
    ] = SongFileType.MP3_128.name,
    max_workers: Annotated[
        int,
        typer.Option(
            "--max-workers",
            help="最大并发下载数。",
            show_default=False,
        ),
    ] = 5,
    debug: Annotated[
        bool,
        typer.Option(
            "--debug",
            help="启用调试模式。",
            show_default=False,
            callback=handle_debug,
        ),
    ] = False,
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
    logger.debug("s")


if __name__ == "__main__":
    app(prog_name="QMDown")
