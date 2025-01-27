import base64
import logging
import mimetypes
from pathlib import Path

import anyio
from anyio import to_thread
from mutagen._file import File
from mutagen.flac import FLAC, Picture
from mutagen.id3 import ID3
from mutagen.id3._frames import APIC
from mutagen.id3._util import ID3NoHeaderError
from mutagen.mp4 import MP4, MP4Cover
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis


async def add_cover_to_audio(audio_path: str | Path, cover_path: str | Path, remove: bool = True) -> None:
    """
    为音频文件添加封面 (支持 MP3/FLAC/OGG/AAC)

    Args:
        audio_path: 音频文件路径
        cover_path: 封面图片路径
        remove: 是否在成功后删除封面文件
    """
    audio_path = Path(audio_path)
    cover_path = Path(cover_path)

    # 检查封面文件是否存在
    if not await to_thread.run_sync(cover_path.exists):
        logging.warning(f"[blue][封面][/] 封面文件不存在: {cover_path}")
        return

    try:
        # 异步读取封面数据
        async with await anyio.open_file(cover_path, "rb") as f:
            cover_data = await f.read()

        # 检测 MIME 类型
        mime_type, _ = await to_thread.run_sync(mimetypes.guess_type, cover_path)
        if mime_type not in ("image/jpeg", "image/png", "image/webp"):
            raise ValueError(f"不支持的图片格式: {mime_type}")

        # 根据文件后缀选择处理方式
        ext = audio_path.suffix.lower()
        if ext == ".mp3":
            await _handle_mp3_cover(audio_path, cover_data, mime_type)
        elif ext in (".flac", ".oga"):
            await _handle_flac_cover(audio_path, cover_data, mime_type)
        elif ext in (".ogg", ".opus"):
            await _handle_ogg_cover(audio_path, cover_data, mime_type)
        elif ext in (".m4a", ".aac", ".mp4"):
            await _handle_aac_cover(audio_path, cover_data, mime_type)
        else:
            raise ValueError(f"不支持的音频格式: {ext}")

        # 删除封面文件
        if remove:
            await to_thread.run_sync(cover_path.unlink, True)

        logging.debug(f"[blue][封面][/] 成功添加封面到 {audio_path}")

    except Exception as e:
        logging.error(f"[blue][封面][/] 处理 {audio_path} 失败: {e!s}")
        if remove and await to_thread.run_sync(cover_path.exists):
            await to_thread.run_sync(cover_path.unlink, True)


async def _handle_mp3_cover(path: Path, data: bytes, mime: str) -> None:
    try:
        # 强制加载为 ID3v2.3
        audio = await to_thread.run_sync(
            lambda: ID3(path) if path.exists() else ID3(),
        )
    except ID3NoHeaderError:
        audio = ID3()

    # 清理旧封面
    audio.delall("APIC")

    # 添加 APIC 帧
    audio.add(
        APIC(
            encoding=0,  # Latin-1
            mime=mime,
            type=3,  # 3 = 封面图片
            desc="Cover",
            data=data,
        )
    )

    # 保存为 ID3v2.3
    await to_thread.run_sync(lambda: audio.save(path, v2_version=3))


async def _handle_flac_cover(path: Path, data: bytes, mime: str) -> None:
    audio = await to_thread.run_sync(FLAC, path)

    # 创建 Picture 对象
    pic = Picture()
    pic.type = 3
    pic.mime = mime
    pic.data = data
    pic.desc = "Cover"

    # 清除旧图片并添加新图片
    audio.clear_pictures()
    audio.add_picture(pic)

    await to_thread.run_sync(audio.save)


async def _handle_ogg_cover(path: Path, data: bytes, mime: str) -> None:
    audio = await to_thread.run_sync(File, path)

    if isinstance(audio, OggOpus):
        audio = OggOpus(path)
    elif isinstance(audio, OggVorbis):
        audio = OggVorbis(path)
    else:
        raise ValueError("不支持的 Ogg 格式")

    pic = Picture()
    pic.type = 3
    pic.mime = mime
    pic.data = data
    pic.desc = "Cover"

    audio["metadata_block_picture"] = [base64.b64encode(pic.write()).decode("utf-8")]

    await to_thread.run_sync(audio.save)


async def _handle_aac_cover(path: Path, data: bytes, mime: str) -> None:
    audio = await to_thread.run_sync(MP4, path)

    # 转换图片格式
    cover_format = MP4Cover.FORMAT_JPEG if mime == "image/jpeg" else MP4Cover.FORMAT_PNG
    cover = MP4Cover(data, cover_format)

    # 设置 covr 原子
    audio["covr"] = [cover]

    await to_thread.run_sync(audio.save)
