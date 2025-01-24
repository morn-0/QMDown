import logging
import sys
from typing import IO, TextIO

import httpx
from PIL import Image
from PIL._typing import StrOrBytesPath
from qrcode import QRCode


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
