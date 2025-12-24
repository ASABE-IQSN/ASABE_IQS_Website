from django.shortcuts import render
from events.models import Team, Event, EventTeam
# Create your views here.


def live_landing(request):
    current_event=(Event.objects.filter(event_active=True).first())
    return render(request,"live_landing.html",{"active_event":current_event})

def live_pull(request):
    return render(request,"live_pull.html")

def overlay(request):
    return render(request,"overlay.html")