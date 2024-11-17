import gettext
import logging
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler

__version__ = "0.1.0"

console = Console()

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
logging.getLogger("httpx").setLevel("CRITICAL")

logging.info(f"QMDown {__version__}")


gettext.bindtextdomain("zh_CN", localedir=str(Path(__file__).parent / "languages"))
gettext.textdomain("zh_CN")
