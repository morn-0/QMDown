import logging

from rich.console import Console
from rich.logging import RichHandler

__version__ = "0.1.1"

console = Console()

logging.getLogger("httpx").setLevel("CRITICAL")

logging.basicConfig(
    level="INFO",
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
