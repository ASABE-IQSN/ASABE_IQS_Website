import pandas as pd
import mysql.connector
import local_secrets

cnx = mysql.connector.connect(
     host=local_secrets.DB_IP,
     port=3306,
     user=local_secrets.ADMINUNAME,
     password=local_secrets.ADMINPWORD,
     database="IQS_Test_Environment")

cursor=cnx.cursor()

team_ids={"Cal Poly State University":220,"Iowa State University":207,"ITAQ":225,"Penn State University":211,"North Carolina State University":201,"North Dakota State University":209,"South Dakota State University":203,"University of Kentucky":208,"University of Nebraska":212,"University of Missouri":205,"University of Wisconsin-Platteville":214}


df=pd.read_excel("sql_management/data/2025/2025 X_Team_Scoring_Master.xlsx",sheet_name="Overall Scores",header=8,usecols="A,AB")
print(df.head())

for i,row in df.iterrows():
    #print(row["Team"])
    team_name=row["Team"]
    team_id=team_ids.get(team_name,None)
    score=row["Unnamed: 27"]
    sql="SELECT tractor_id FROM tractors WHERE original_team_id=%s AND year=%s"
    values=(team_id-200,24)
    cursor.execute(sql,values)
    res=cursor.fetchone()
    if res:
        tractor_id=res[0]
    else:
        tractor_id=1
        print(f"Tractor not found {team_id}")
    if tractor_id and team_id:
        print(f"Team: {team_id} Tractor {tractor_id} score: {score}")
        sql="INSERT INTO tractor_events (tractor_id,team_id,event_id) VALUES (%s,%s,%s)"
        values=(tractor_id,team_id,25)
        #cursor.execute(sql,values)

        sql="INSERT INTO event_teams (team_id,event_id,total_score) VALUES (%s,%s,%s)"
        values=(team_id,25,int(score))
        #cursor.execute(sql,values)

#cnx.commit()
# team_ids={"Cal Poly State University":20,"Iowa State University":7,"Kansas State University":2,"McGill University":18,"North Carolina State University":1,"North Dakota State University":9,"Oklahoma State University":16,"Oregon State University":22,"Penn State University":11,"Purdue University":4,"South Dakota State University":3,"Texas A&M University":23,"University of Georgia ":19,"University of Guelph":19,"University of Illinois":10,"University of Kentucky":8,"University of Laval":24,"University of Manitoba":17,"University of Missouri":5,"University of Nebraska":12,"University of Saskatchewan":15,"University of Tennessee - Martin":13,"University of Wisconsin Madison":6}
# for i,row in df.iterrows():
#     #print(row["Unnamed: 12"])
#     team_name=row["Unnamed: 12"]
#     team_id=team_ids.get(team_name,-1)
#     row["team_id"]=team_id

#     if team_id==-1:
#         print(f"Team Name not found: {team_name} {team_id}")
#     else:
#         sql="INSERT INTO event_teams (event_id,team_id,total_score) VALUES (%s,%s,%s)"
#         values=(25,team_id,row["TOTAL"])
#         cursor.execute(sql,values)
#         sql="INSERT INTO tractors (year,team_id) VALUES (%s,%s)"
#         values=(25,team_id)
#         cursor.execute(sql,values)
# print(df.head())
# team_ids={}
