import asyncio
import signal
from functools import wraps


def singer_to_str(singers: list[dict], sep: str = "&"):
    """
    将歌手列表转换为字符串

    Args:
        singers: 歌手列表
        sep: 分隔符
    """
    return "&".join(map(lambda x: x["name"], singers))


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
