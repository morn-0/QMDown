import gettext
import logging
from importlib import resources

from rich.console import Console

__version__ = "0.1.0"

console = Console()

logging.getLogger("httpx").setLevel("CRITICAL")

gettext.bindtextdomain("zh_CN", localedir=str(resources.files("QMDown") / "languages"))
gettext.textdomain("zh_CN")
