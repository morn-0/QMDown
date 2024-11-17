import gettext
from pathlib import Path

from rich.console import Console

__version__ = "0.1.0"

console = Console()

gettext.bindtextdomain("zh_CN", localedir=str(Path(__file__).parent / "languages"))
gettext.textdomain("zh_CN")

