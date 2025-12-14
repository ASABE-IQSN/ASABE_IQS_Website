from functools import wraps
from django.http import HttpRequest, HttpResponse, Http404
from users.models import View

import time

def log_view(func):
    @wraps(func)
    def wrapped(*args,**kwargs):
        #print(f"Running logger with {args[0]}")
        request=args[0]
        request:HttpRequest
        #print(request.get_full_path())
        #print(request.user.id)
        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        if xff:
            ip = xff.split(",")[0].strip()
        else:
            ip = request.META.get("REMOTE_ADDR")
        start_time=time.time()
        ret=func(*args,**kwargs)
        ret:HttpResponse
        code=ret.status_code
        response_time=time.time()-start_time
        View.objects.create(user_id=request.user.id,url=request.get_full_path(),ip=ip,response_time_s=response_time,response_code=code)
        return ret
    return wrapped
