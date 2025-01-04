import asyncio
import signal
from functools import wraps
from typing import TypeVar

import httpx

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
