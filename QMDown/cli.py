from pathlib import Path
from typing import Annotated

import typer

from . import __version__

app = typer.Typer(add_completion=False)


def handle_version(value: bool):
    if value:
        typer.echo(f"QMDown {__version__}")
        raise typer.Exit()


@app.command()
def main(
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
    pass


if __name__ == "__main__":
    app()

