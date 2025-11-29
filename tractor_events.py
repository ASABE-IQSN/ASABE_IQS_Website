import mysql.connector
import local_secrets

cnx = mysql.connector.connect(
     host=local_secrets.DB_IP,
     port=3306,
     user=local_secrets.ADMINUNAME,
     password=local_secrets.ADMINPWORD,
     database="IQS_Test_Environment")

cursor=cnx.cursor(dictionary=True)

# sql="SELECT * FROM teams"
# cursor.execute(sql)
# teams={}
# x=cursor.fetchall()
# for res in x:
#     teams[res["team_id"]]=res
    

sql="SELECT * FROM event_teams"
cursor.execute(sql)
event_teams={}
x=cursor.fetchall()
for res in x:
    team_id=res["team_id"]
    event_id=res["event_id"]
    sql="SELECT tractor_id FROM tractors WHERE original_team_id=%s AND year=%s"
    values=(res["team_id"],res["event_id"])
    cursor.execute(sql,values)
    res=cursor.fetchone()
    if(res):
        tractor_id=res["tractor_id"]
        print(f"Tractor: {tractor_id} Team:{team_id}, Event: {event_id}")
        sql="INSERT INTO tractor_events (tractor_id,event_id,team_id) VALUES(%s,%s,%s)"
        values=(tractor_id,event_id,team_id)
        cursor.execute(sql,values)
    else:
        print(f"Tractor Not Found {team_id} {event_id}")
cnx.commit()
# sql="SELECT * FROM tractors"
# cursor.execute(sql)
# x=cursor.fetchall()
# for res in x:
#     team=teams[res["team_id"]]
#     name=team["team_abbreviation"]+" 20"+str(res["year"])
#     sql="UPDATE tractors SET tractor_name=%s WHERE tractor_id=%s"
#     values=(name,res["tractor_id"])
#     cursor.execute(sql,values)
# cnx.commit()