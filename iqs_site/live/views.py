from django.shortcuts import render
from events.models import Team, Event, EventTeam
from django.conf import settings
# Create your views here.


def live_landing(request):
    current_event=(Event.objects.filter(event_active=True).first())
    return render(request,"live_landing.html",{"active_event":current_event})

def live_pull(request):
    context={}
    context["api_url"]=settings.APIURL
    return render(request,"live_pull.html",context)

def live_maneuverability(request):
    context = {}
    context["api_url"] = settings.APIURL
    return render(request, "live_maneuverability.html", context)

def overlay(request):
    return render(request,"overlay.html")