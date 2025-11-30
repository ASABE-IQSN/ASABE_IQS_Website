import os
import mysql.connector
import local_secrets
import re
import pandas as pd
cnx = mysql.connector.connect(
    host=local_secrets.DB_IP,
    port=3306,
    user=local_secrets.ADMINUNAME,
    password=local_secrets.ADMINPWORD,
    database="IQS_Test_Environment")
parent="sql_management/data/2025/2025_Pull_Data"
files=os.listdir(parent)

local_db=mysql.connector.connect(
    host=local_secrets.LOCAL_DB_IP,
    port=3306,
    user=local_secrets.LOCALADMINUNAME,
    password=local_secrets.LOCALADMINPWORD,
    database="2025_IQS_Testing")

hook_converter={1:12,2:13,3:14}
team_tractor_converter={16:(5,69),12:(5,13),13:(5,34),24:(7,70),25:(7,72),27:(7,20),28:(7,41),22:(7,73),23:(7,74),21:(7,75),}


remote_cursor=cnx.cursor()
local_cursor=local_db.cursor(dictionary=True)

sql="SELECT * FROM pulls WHERE final_distance IS NOT NULL"
local_cursor.execute(sql)
res=local_cursor.fetchall()
for x in res:
    print(x)