import mysql.connector
import local_secrets

cnx = mysql.connector.connect(
     host=local_secrets.DB_IP,
     port=3306,
     user=local_secrets.ADMINUNAME,
     password=local_secrets.ADMINPWORD,
     database="IQS_Test_Environment")

cursor=cnx.cursor(dictionary=True)

sql="SELECT * FROM teams"
cursor.execute(sql)
teams={}
x=cursor.fetchall()
for res in x:
    teams[res["team_id"]]=res

sql="SELECT * FROM tractors"
cursor.execute(sql)
x=cursor.fetchall()
for res in x:
    team=teams[res["team_id"]]
    name=team["team_abbreviation"]+" 20"+str(res["year"])
    sql="UPDATE tractors SET tractor_name=%s WHERE tractor_id=%s"
    values=(name,res["tractor_id"])
    cursor.execute(sql,values)
cnx.commit()