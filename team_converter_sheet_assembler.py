import pickle
import mysql.connector
import gspread
import pandas as pd
import time
import local_secrets

gc=gspread.service_account(filename="nimble-equator-463901-k2-d0ff3569c345.json")

cnx = mysql.connector.connect(
    host=local_secrets.DB_IP,
    port=3306,
    user=local_secrets.ADMINUNAME,
    password=local_secrets.ADMINPWORD,
    database="IQS_Test_Environment")

cursor=cnx.cursor(dictionary=True)

spreadsheet=gc.open_by_url("https://docs.google.com/spreadsheets/d/13r_0bjps-od1AAgb6TL0KdOOv7Y1zQ0nVcxvsxcnJ6w/edit?gid=0#gid=0")
sheet=spreadsheet.worksheet("Sheet1")

data=sheet.get_all_values()



for i,da in enumerate(data):
    if i>=25:
        print(da)
        sql="SELECT * FROM teams WHERE team_id=%s"
        values=(da[0],)
        cursor.execute(sql,values)
        x=cursor.fetchone()
        print(x)
        if x:
            sheet.update_cell(i+1,2,x["team_name"])
            sheet.update_cell(i+1,3,x["team_abbreviation"])
            sheet.update_cell(i+1,4,x["team_all_caps_abbreviation"])
            sheet.update_cell(i+1,5,x["team_really_short"])
            sheet.update_cell(i+1,6,x["team_really_short_all_caps"])
            time.sleep(5)