from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from events.models import Team, Event, EventTeam
from django.conf import settings
from iqs_site.utilities import log_view
# Create your views here.


@log_view
def live_landing(request):
    current_event=(Event.objects.filter(event_active=True).first())
    return render(request,"live_landing.html",{"active_event":current_event})

@log_view
def live_pull(request):
    context={}
    context["api_url"]=settings.APIURL
    return render(request,"live_pull.html",context)

@log_view
def live_maneuverability(request):
    context = {}
    context["api_url"] = settings.APIURL
    return render(request, "live_maneuverability.html", context)

@log_view
def live_durability(request):
    context = {}
    context["api_url"] = settings.APIURL
    return render(request, "live_durability.html", context)

@log_view
def overlay(request):
    return render(request,"overlay.html")


@staff_member_required
@log_view
def announcer_pull(request):
    context = {"api_url": settings.APIURL}
    return render(request, "announcer_pull.html", context)


@staff_member_required
@log_view
def announcer_maneuverability(request):
    context = {"api_url": settings.APIURL}
    return render(request, "announcer_maneuverability.html", context)


@staff_member_required
@log_view
def announcer_durability(request):
    context = {"api_url": settings.APIURL}
    return render(request, "announcer_durability.html", context)