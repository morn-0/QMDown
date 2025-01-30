import logging
import os
import sys
from typing import IO, TextIO

import httpx
from PIL import Image
from PIL._typing import StrOrBytesPath
from qrcode import QRCode


def truncate(file_name: str, file_suffix: str, max_length: int = 255) -> str:
    """截断文件名以适应最大长度限制.

    Args:
        file_name: 文件全名.
        max_length: 最大允许长度.
    """
    encoded_name = file_name.encode()
    max_length -= len(file_suffix.encode())
    if len(encoded_name) <= max_length:
        return file_name
    ellipsis = "…"
    max_length -= len(ellipsis.encode())
    truncated_bytes = encoded_name[:max_length]
    while True:
        try:
            truncated_name = truncated_bytes.decode("utf-8")
            break
        except UnicodeDecodeError:
            truncated_bytes = truncated_bytes[:-1]
    return truncated_name + ellipsis


def substitute_with_fullwidth(input_string: str, substitutions: set[str] = set('\x00\\/:<>|?*".')) -> str:
    """
    将字符串中的指定字符替换为全角字符.

    Args:
        input_string: 输入的字符串.
        substitutions: 需要替换为全角字符的字符集合.
    """
    return "".join(chr(ord(char) + 0xFEE0) if char in substitutions else char for char in input_string)


def safe_filename(file_full_name: str, max_length: int = 255) -> str:
    """安全文件名处理.

    Args:
        file_full_name: 包含路径的完整文件名.
    """
    file_name, file_suffix = os.path.splitext(file_full_name)
    processed_name = truncate(substitute_with_fullwidth(file_name), file_suffix, max_length)
    return f"{processed_name}{file_suffix}"


async def get_real_url(url: str) -> str | None:
    """获取跳转后的URL.

    Args:
        url: URL.
    """
    async with httpx.AsyncClient(verify=False) as client:
        resp = await client.get(url)
        return resp.headers.get("Location", None)


def show_qrcode(
    path: StrOrBytesPath | IO[bytes],
    out: TextIO = sys.stdout,
    tty: bool = False,
    invert: bool = False,
    border: int = 4,
) -> None:
    """
    输出二维码的 ASCII 或通过备用方案显示/保存

    Args:
        path: 二维码文件路径或文件对象
        out: 输出流 (默认 stdout)
        tty: 是否使用 TTY 颜色代码
        invert: 是否反转颜色
        border: 二维码边界大小
    """
    try:
        # 尝试使用 pyzbar 解码
        from pyzbar.pyzbar import decode

        img = Image.open(path)
        decoded = decode(img)

        if decoded:
            url = decoded[0].data.decode("utf-8")
            qr = QRCode(border=border)
            qr.add_data(url)
            qr.print_ascii(out=out, tty=tty, invert=invert)
            return

    except Exception:
        img = Image.open(path)
        filename = "qrcode.png"
        img.save(filename)
        logging.warning(f"无法显示二维码,二维码已保存至: [blue]{filename}")
