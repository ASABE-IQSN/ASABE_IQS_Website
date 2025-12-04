import gspread
import pandas as pd
import pickle
import mysql.connector
import local_secrets
gc=gspread.service_account(filename="nimble-equator-463901-k2-d0ff3569c345.json")

with open("team_dict.pkl","rb") as file:

    team_dict=pickle.load(file)
team_dict:dict
spreadsheet=gc.open_by_url("https://docs.google.com/spreadsheets/d/1X1loFtbkWdLxark5Fi8ASXUopkczHL2leleRrTouAUM/edit?gid=1900858676#gid=1900858676")

engine_sheet=spreadsheet.worksheet("Engine Distribution")
cnx = mysql.connector.connect(
    host=local_secrets.DB_IP,
    port=3306,
    user=local_secrets.ADMINUNAME,
    password=local_secrets.ADMINPWORD,
    database="IQS_Test_Environment")

cursor=cnx.cursor(dictionary=True)

data=engine_sheet.get_all_values()

df=pd.DataFrame(data[2:])
print(df.head())
for i,row in df.iterrows():
    team_name=row[1]
    team_id=team_dict.get(team_name,None)
    if team_id:
        pass#print(f"Team:{} team_id:{}")
    else:
        print(team_name)
    year=row[2]
    serial=row[3]
    model=row[4]
    print(year,serial,model,team_id)
    if(team_id):
        sql="INSERT INTO engines (engine_serial_number,team_id,distributed_year,engine_model) VALUES (%s,%s,%s,%s)"
        values=(serial,team_id,year,model)
        cursor.execute(sql,values)
cnx.commit()