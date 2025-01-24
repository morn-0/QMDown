import asyncio
import logging
import signal
import sys
from collections.abc import Callable, Sequence
from functools import wraps
from typing import IO, TextIO

import httpx
from PIL import Image
from PIL._typing import StrOrBytesPath
from pyzbar import pyzbar
from qrcode import QRCode


def cli_coro(
    signals: Sequence[int] | None = None,
    shutdown_func: Callable[[int, asyncio.AbstractEventLoop], None] | None = None,
):
    """Decorator function that allows defining coroutines with click."""
    if signals is None:
        # 根据平台设置默认信号
        if sys.platform == "win32":
            signals = (signal.SIGINT,)  # Windows通常支持SIGINT
        else:
            signals = (signal.SIGHUP, signal.SIGTERM, signal.SIGINT)

    def decorator_cli_coro(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            loop = asyncio.get_event_loop()
            if shutdown_func:
                for ss in signals:
                    try:
                        loop.add_signal_handler(ss, shutdown_func, ss, loop)
                    except NotImplementedError:
                        # 平台不支持该信号c静默跳过
                        pass
                    except RuntimeError as e:
                        # 处理其他可能的运行时错误)如信号无效)
                        logging.warning(f"Could not register signal {ss}: {e}")
            return loop.run_until_complete(f(*args, **kwargs))

        return wrapper

    return decorator_cli_coro


async def get_real_url(url: str) -> str | None:
    """获取跳转后的URL.

    Args:
        url: URL.
    """
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
