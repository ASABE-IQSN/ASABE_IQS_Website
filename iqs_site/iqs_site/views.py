import logging

from django.shortcuts import render

from stats.models import CsrfFailure

logger = logging.getLogger("django.security.csrf")


def csrf_failure(request, reason=""):
    ip = (
        request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
        or request.META.get("REMOTE_ADDR", "")
    )
    user = request.user if hasattr(request, "user") and request.user.is_authenticated else None

    logger.warning(
        "CSRF failure | reason=%r | path=%s | referer=%s | user=%s | ua=%s",
        reason,
        request.path,
        request.META.get("HTTP_REFERER", "-"),
        user.username if user else "anonymous",
        request.META.get("HTTP_USER_AGENT", "-")[:120],
    )

    try:
        CsrfFailure.objects.create(
            ip=ip,
            path=request.path[:500],
            reason=reason[:255],
            referer=request.META.get("HTTP_REFERER", "")[:2048],
            user=user,
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
        )
    except Exception:
        logger.exception("Could not save CsrfFailure to database")

    return render(request, "403_csrf.html", status=403)
