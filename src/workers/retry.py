"""重试装饰器 — 指数退避"""
import functools
import time
from typing import Tuple, Type


def retry(exceptions: Tuple[Type[BaseException], ...], tries: int = 3,
          delay: float = 1.0, backoff: float = 2.0):
    """对指定异常进行指数退避重试"""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            _delay = delay
            _tries = tries
            while _tries > 1:
                try:
                    return fn(*args, **kwargs)
                except exceptions:
                    time.sleep(_delay)
                    _delay *= backoff
                    _tries -= 1
            return fn(*args, **kwargs)  # 最后一次直接抛
        return wrapper
    return decorator
