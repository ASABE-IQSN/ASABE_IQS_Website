from functools import wraps
from django.http import HttpRequest, HttpResponse, Http404
from users.models import View
import threading
import time
import queue

view_queue=queue.Queue(1000)

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
        view=[request.user.id,request.get_full_path(),ip,response_time,code]
        view_queue.put(view,block=False)
        #print("Put value in queue")
        #View.objects.create(user_id=request.user.id,url=request.get_full_path(),ip=ip,response_time_s=response_time,response_code=code)
        return ret
    return wrapped

def view_thread_func():
    while True:
        try:
            view=view_queue.get(timeout=100)
            user,url,ip,response_time,code=view
            View.objects.create(user_id=user,url=url,ip=ip,response_time_s=response_time,response_code=code)
            #print("Put object into sql")
        except Exception:
            pass


view_thread=threading.Thread(target=view_thread_func,daemon=True)
view_thread.start()