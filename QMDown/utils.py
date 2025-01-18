import asyncio
import signal
import sys
from functools import wraps
from typing import IO, TextIO, TypeVar

import httpx
from PIL import Image
from PIL._typing import StrOrBytesPath
from pyzbar import pyzbar
from qrcode import QRCode

T = TypeVar("T")


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


def find_by_attribute(models: list[T], attribute_name: str, value: str) -> T:
    for model in models:
        if hasattr(model, attribute_name) and getattr(model, attribute_name) == value:
            return model
    raise ValueError(f"{value} not found in {models}")


async def get_real_url(url: str) -> str | None:
    async with httpx.AsyncClient(verify=False) as client:
        resp = await client.get(url)
        return resp.headers.get("Location", None)


def print_ascii(path: StrOrBytesPath | IO[bytes], out: TextIO = sys.stdout, tty=False, invert=False, border=4):
    """
    使用 ASCII 字符输出二维码图像.

    Args:
        path: 二维码文件的路径.
        out: 输出流.
        tty: 是否使用固定的 TTY 颜色代码(强制 invert=True).
        invert: 是否反转 ASCII 字符(实心 <-> 透明).
        border: 保留的边距大小.
    """
    img = Image.open(path)
    url = pyzbar.decode(img)[0].data.decode("utf-8")
    qr = QRCode(border=border)
    qr.add_data(url)
    qr.print_ascii(out=out, tty=tty, invert=invert)
