from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from events.models import Team, Event, EventTeam
from django.conf import settings
from compforms.models import OverlayScene
import json
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

def live_durability(request):
    context = {}
    context["api_url"] = settings.APIURL
    return render(request, "live_durability.html", context)

def overlay(request):
    context = {"api_url": settings.APIURL}
    return render(request, "overlay.html", context)


@staff_member_required
def overlay_producer(request):
    context = {"api_url": settings.APIURL}
    return render(request, "overlay_producer.html", context)


@staff_member_required
def announcer_pull(request):
    context = {"api_url": settings.APIURL}
    return render(request, "announcer_pull.html", context)


@staff_member_required
def announcer_maneuverability(request):
    context = {"api_url": settings.APIURL}
    return render(request, "announcer_maneuverability.html", context)


@staff_member_required
def announcer_durability(request):
    context = {"api_url": settings.APIURL}
    return render(request, "announcer_durability.html", context)


@staff_member_required
def overlay_scene_list(request):
    if request.method == 'POST':
        name = request.POST.get('name', 'New Scene').strip() or 'New Scene'
        canvas_width = int(request.POST.get('canvas_width', 1920))
        canvas_height = int(request.POST.get('canvas_height', 1080))
        scene = OverlayScene.objects.create(name=name, canvas_width=canvas_width, canvas_height=canvas_height)
        from django.shortcuts import redirect
        return redirect('live:overlay_scene_editor', scene_id=scene.scene_id)
    scenes = OverlayScene.objects.all().order_by('-updated_at')
    return render(request, 'overlay_scene_list.html', {'scenes': scenes})


@staff_member_required
def overlay_scene_editor(request, scene_id):
    from django.shortcuts import get_object_or_404
    scene = get_object_or_404(OverlayScene, pk=scene_id)
    scene_json = json.dumps({
        'name': scene.name,
        'canvas_width': scene.canvas_width,
        'canvas_height': scene.canvas_height,
        'elements': scene.elements,
    })
    return render(request, 'overlay_scene_editor.html', {
        'scene': scene,
        'scene_json': scene_json,
    })


@staff_member_required
def overlay_scene_save(request, scene_id):
    from django.shortcuts import get_object_or_404
    from django.http import JsonResponse
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    scene = get_object_or_404(OverlayScene, pk=scene_id)
    try:
        data = json.loads(request.body)
        if 'name' in data:
            scene.name = data['name'].strip() or scene.name
        if 'elements' in data:
            scene.elements = data['elements']
        scene.save(update_fields=['name', 'elements', 'updated_at'])
        return JsonResponse({'ok': True, 'name': scene.name})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)