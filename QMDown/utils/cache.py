import hashlib
import inspect
import logging
import os
import pickle
import platform
import shutil
import time
from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any, ParamSpec, TypeVar

import anyio
from anyio import Lock, Path, to_thread
from anyio.lowlevel import RunVar
from anyio.streams.file import FileReadStream, FileWriteStream

from QMDown import __version__

RetT = TypeVar("RetT")
P = ParamSpec("P")


async def get_system_cache_dir() -> Path:
    """获取系统标准缓存目录"""
    system = platform.system()
    try:
        if system == "Linux":
            return Path(os.environ.get("XDG_CACHE_HOME", await Path.home() / ".cache"))
        if system == "Darwin":
            return await Path.home() / "Library" / "Caches"
        if system == "Windows":
            return Path(os.environ["LOCALAPPDATA"]) / "Cache"
        return await Path.home() / ".cache"
    except KeyError:
        return await Path.home() / ".cache"


async def get_cache_path(cache_key: str) -> Path:
    """生成带哈希的文件路径"""
    cache_root = await get_system_cache_dir() / "QMDown" / __version__
    hashed = hashlib.sha256(cache_key.encode()).hexdigest()
    return cache_root / f"{hashed[:2]}/{hashed[2:4]}/{hashed}.cache"


async def save_to_disk(cache_key: str, value: Any, expiry: float) -> None:
    cache_path = await get_cache_path(cache_key)
    temp_path = cache_path.with_suffix(".tmp")
    try:
        # 异步创建目录结构
        await cache_path.parent.mkdir(parents=True, exist_ok=True)

        async with await FileWriteStream.from_path(temp_path) as stream:
            serialized = await to_thread.run_sync(lambda: pickle.dumps((value, expiry)), cancellable=True)
            await stream.send(serialized)

        # 原子替换文件
        await temp_path.rename(cache_path)

    except Exception as e:
        await temp_path.unlink(missing_ok=True)
        logging.debug(f"Cache save failed: {e}")


async def clean_old_caches():
    cache_root = await get_system_cache_dir() / "QMDown"
    if not await cache_root.exists():
        return

    async for entry in cache_root.iterdir():
        if await entry.is_dir() and entry.name != __version__:
            try:
                await to_thread.run_sync(shutil.rmtree, entry)
                logging.debug(f"Removed old cache directory: {entry}")
            except Exception as e:
                logging.debug(f"Failed to remove {entry}: {e}")


async def load_from_disk(cache_key: str) -> tuple[Any, float] | None:
    cache_path = await get_cache_path(cache_key)
    try:
        if not await cache_path.exists():
            return None

        async with await FileReadStream.from_path(cache_path) as stream:
            data = await stream.receive()
        return await to_thread.run_sync(lambda: pickle.loads(data), cancellable=True)
    except (pickle.UnpicklingError, EOFError, anyio.ClosedResourceError) as e:
        await cache_path.unlink(missing_ok=True)
        logging.debug(f"Invalid cache removed: {e}")
        return None


async def delete_disk_cache(cache_key: str) -> None:
    cache_path = await get_cache_path(cache_key)
    await cache_path.unlink(missing_ok=True)
    # 自动清理空目录
    for parent in [cache_path.parent, cache_path.parent.parent]:
        if await parent.is_dir():
            await parent.rmdir()


def cached(
    args_to_cache_key: Callable[[inspect.BoundArguments], str], ttl: int = 36000
) -> Callable[[Callable[P, Coroutine[Any, Any, RetT]]], Callable[P, Coroutine[Any, Any, RetT]]]:
    CACHE: dict[str, tuple[RetT, float]] = {}
    run_lock = RunVar("cache_lock", Lock())

    def decorator(fn: Callable[P, Coroutine[Any, Any, RetT]]):
        @wraps(fn)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> RetT:
            sig = inspect.signature(fn)
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()
            cache_key = f"{fn.__module__}:{fn.__name__}:{args_to_cache_key(bound_args)}"

            lock = run_lock.get()
            async with lock:
                current_time = time.time()

                # 内存缓存检查
                if (cache_data := CACHE.get(cache_key)) and cache_data[1] > current_time:
                    logging.debug(f"[Memory Hit] {cache_key}")
                    return cache_data[0]

                # 磁盘缓存检查
                if (disk_data := await load_from_disk(cache_key)) and disk_data[1] > current_time:
                    CACHE[cache_key] = disk_data
                    logging.debug(f"[Disk Hit] {cache_key}")
                    return disk_data[0]

                # 执行实际函数
                logging.debug(f"[Cache Miss] {cache_key}")
                result = await fn(*args, **kwargs)

                # 异步并行更新缓存
                async with anyio.create_task_group() as tg:
                    CACHE[cache_key] = (result, current_time + ttl)
                    tg.start_soon(save_to_disk, cache_key, result, current_time + ttl)

                return result

        return wrapper

    return decorator
