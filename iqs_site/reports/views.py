from django.conf import settings
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404

from events.models import Report


def report_download(request, report_id):
    report = get_object_or_404(Report, pk=report_id)

    # Internal Celery task access: bypass user auth when a valid token is present.
    internal_token = getattr(settings, "INTERNAL_REPORT_TOKEN", "")
    if internal_token and request.headers.get("X-Internal-Token") == internal_token:
        pass  # allow
    elif not request.user.is_authenticated or not request.user.is_staff:
        raise Http404()

    response = HttpResponse(content_type="application/pdf")
    response["X-Accel-Redirect"] = f"/_reports/{report.report_link}"
    response["Content-Disposition"] = f'inline; filename="{report.report_link}"'
    return response
