import inspect
import logging
import time
from asyncio import Lock
from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any, ParamSpec, TypeVar

RetT = TypeVar("RetT")
P = ParamSpec("P")


def cached(
    args_to_cache_key: Callable[[inspect.BoundArguments], str], ttl: int = 120
) -> Callable[[Callable[P, Coroutine[Any, Any, RetT]]], Callable[P, Coroutine[Any, Any, RetT]]]:
    CACHE: dict[str, tuple[RetT, float]] = {}
    lock = Lock()

    def decorator(fn: Callable[P, Coroutine[Any, Any, RetT]]):
        @wraps(fn)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> RetT:
            sig = inspect.signature(fn)
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()
            cache_key = f"{fn.__name__}_{args_to_cache_key(bound_args)}"

            async with lock:
                current_time = time.time()
                if cache_key in CACHE:
                    value, expiry = CACHE[cache_key]
                    if expiry > current_time:
                        logging.debug(f"[blue][Cache][/] {fn.__name__} cache hit: {cache_key}")
                        return value
                    del CACHE[cache_key]
                logging.debug(
                    f"[blue][Cache][/] {fn.__name__} cache miss: {cache_key}, all cache keys: {list(CACHE.keys())}"
                )
                result = await fn(*args, **kwargs)
                CACHE[cache_key] = (result, current_time + ttl)
                return result

        return wrapper

    return decorator
