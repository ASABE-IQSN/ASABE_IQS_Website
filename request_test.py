import requests
from requests import Session
import time
REMOTE_URL="https://internationalquarterscale.com"

session=Session()

for i in range(1000):
    start_time=time.time()
    resp=session.post(REMOTE_URL)
    #print(resp.text)
    dt=time.time()-start_time
    print(dt)