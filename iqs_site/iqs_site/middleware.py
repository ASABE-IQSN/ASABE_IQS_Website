import queue
import traceback as tb
import threading
import time

from users.models import View

_view_queue: queue.Queue = queue.Queue(5000)

_SKIP_PREFIXES = (
    "/static/",
    "/media/",
    "/health/",
    "/stats/pv/",   # page-session tracking endpoints — no need to log the logger
)


def _worker() -> None:
    while True:
        try:
            user_id, url, ip, response_time, code = _view_queue.get(timeout=100)
            View.objects.create(
                user_id=user_id,
                url=url,
                ip=ip,
                response_time_s=response_time,
                response_code=code,
            )
        except Exception:
            pass


_thread = threading.Thread(target=_worker, daemon=True)
_thread.start()


def _enqueue(request, ip: str, status_code: int, elapsed: float) -> None:
    user_id = None
    if hasattr(request, "user") and request.user.is_authenticated:
        user_id = request.user.pk
    try:
        _view_queue.put_nowait(
            [user_id, request.get_full_path()[:255], ip, elapsed, status_code]
        )
    except queue.Full:
        pass


def _save_server_error(request, ip: str, exc: BaseException) -> None:
    """Persist the full traceback to ServerError. Import deferred to avoid circular imports."""
    try:
        from stats.models import ServerError
        user = None
        if hasattr(request, "user") and request.user.is_authenticated:
            user = request.user
        ServerError.objects.create(
            url=request.get_full_path()[:500],
            method=request.method,
            ip=ip,
            user=user,
            exception_type=type(exc).__name__,
            traceback=tb.format_exc(),
        )
    except Exception:
        pass


class PageViewMiddleware:
    """
    Records every Django-handled request to the `views` table.
    Catches unhandled exceptions so that real 500 crashes are recorded and
    their full tracebacks are stored in `server_error_log`.
    Uses a background thread queue to avoid adding DB latency to responses.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if any(request.path.startswith(p) for p in _SKIP_PREFIXES):
            return self.get_response(request)

        ip = (
            request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
            or request.META.get("REMOTE_ADDR", "")
        )
        start = time.time()
        response = self.get_response(request)
        _enqueue(request, ip, response.status_code, time.time() - start)
        return response

    def process_exception(self, request, exception):
        """
        Called by Django before it converts an unhandled exception to a 500
        response — this is the only reliable place to capture the traceback.
        Returning None lets Django's normal 500 handling continue.
        """
        ip = (
            request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
            or request.META.get("REMOTE_ADDR", "")
        )
        _save_server_error(request, ip, exception)
        return None
