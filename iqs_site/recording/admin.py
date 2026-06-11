from django.contrib import admin

from . import models

for _m in (models.PullStatusEvent, models.PullDataPoint,
           models.DurabilityStatusEvent, models.DurabilityDataPoint,
           models.ManeuverabilityStatusEvent, models.LoadToadDataPoint,
           models.EngineDataPoint):
    admin.site.register(_m)
