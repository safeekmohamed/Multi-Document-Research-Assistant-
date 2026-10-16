from functools import lru_cache, wraps
from threading import RLock


def synchronized_lru_cache(maxsize=1):
    """Serialize cache misses so one model is initialized only once per process."""
    def decorate(function):
        cached = lru_cache(maxsize=maxsize)(function)
        lock = RLock()

        @wraps(function)
        def wrapped(*args, **kwargs):
            with lock:
                return cached(*args, **kwargs)

        wrapped.cache_clear = cached.cache_clear
        wrapped.cache_info = cached.cache_info
        return wrapped

    return decorate
