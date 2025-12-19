"""
URL configuration for iqs_site project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings

if getattr(settings, "SITE_VARIANT", "normal") == "testing":
    root_prefix = "testing/"   
else:
    root_prefix = ""           

urlpatterns = [
    path(root_prefix+'admin/', admin.site.urls),
    path(root_prefix, include("events.urls", namespace="events")),
    path(root_prefix+"live/",include("live.urls",namespace="live")),
    path(root_prefix+"techin/",include("techin.urls",namespace="techin")),
    path(root_prefix+"accounts/", include("django.contrib.auth.urls")),
    path(root_prefix+"user/", include("users.urls",namespace="user")),
    path("stats/", include("stats.urls", namespace="stats")),
]
