import asyncio
import os
import signal
import sys
from functools import wraps
from typing import IO, TextIO, TypeVar

import httpx
from PIL import Image
from PIL._typing import StrOrBytesPath

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


def _resize_image_to_terminal(img: Image.Image, border: int) -> Image.Image:
    # 获取终端尺寸
    tsize = os.get_terminal_size()
    term_width = tsize.columns
    term_height = tsize.lines * 2  # 调整为终端字符的高度

    # 计算调整图像的尺寸
    img_width, img_height = img.size
    img_ratio = img_width / img_height
    term_ratio = (term_width - border * 2) / (term_height - border * 2)

    if img_ratio > term_ratio:
        new_width = term_width - border * 2
        new_height = int(new_width / img_ratio)
    else:
        new_height = term_height - border * 2
        new_width = int(new_height * img_ratio)

    # 调整图像大小
    return img.resize((new_width, new_height), Image.Resampling.LANCZOS)


def print_ascii(path: StrOrBytesPath | IO[bytes], out: TextIO = sys.stdout, tty=False, invert=True, border=4):  # noqa: C901
    """
    使用 ASCII 字符输出二维码图像.

    Args:
        path: 二维码文件的路径.
        out: 输出流.
        tty: 是否使用固定的 TTY 颜色代码(强制 invert=True).
        invert: 是否反转 ASCII 字符(实心 <-> 透明).
        border: 保留的边距大小.
    """
    # 如果需要 TTY 且输出流不是 TTY, 则抛出异常
    if tty and not out.isatty():
        raise OSError("Not a tty")

    # 打开图像
    img = _resize_image_to_terminal(Image.open(path).convert("L"), border)
    pixels = img.load()

    # 定义用于不同像素强度的 ASCII 字符
    codes = [bytes((code,)).decode("cp437") for code in (255, 223, 220, 219)]

    if tty:
        invert = True
    if invert:
        codes.reverse()

    def get_module(x, y) -> int:
        # 确保在边界内并应用反转逻辑
        if min(x, y) < 0 or max(x, y) >= img.size[0]:
            return 0  # 空白区域
        if pixels:
            return pixels[y, x] > 128  # 假设是灰度图像
        return 0

    # 打印顶部边距
    for _ in range(border // 2):
        out.write("\n")
    # 按行打印 ASCII 图像
    for r in range(0, img.size[1], 2):  # 每次处理两行高度
        if tty:
            if not invert or r < img.size[1] - 1:
                out.write("\x1b[48;5;232m")  # 背景黑色
            out.write("\x1b[38;5;255m")  # 前景白色
        # 打印左侧边距
        out.write(" " * (border // 2))
        # 打印当前行的每个列
        for c in range(img.size[0]):
            pos = get_module(c, r) + (get_module(c, r + 1) << 1)
            out.write(codes[pos])
        if tty:
            out.write("\x1b[0m")  # 重置颜色
        out.write("\n")
    # 打印底部边距
    for _ in range(border // 2):
        out.write("\n")
    out.flush()
