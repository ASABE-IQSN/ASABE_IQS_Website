from functools import wraps


def log_view(func):
    """Deprecated — page-view recording is now handled by PageViewMiddleware."""
    return func
