import logging

from rich.console import Console

__version__ = "0.1.0"

console = Console()

logging.getLogger("httpx").setLevel("CRITICAL")
