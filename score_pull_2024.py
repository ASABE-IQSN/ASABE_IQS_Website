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

df=pd.read_excel("sql_management/data/2024/2024 Master Score Spreadsheet.xlsx",sheet_name="Overall Ranking & Scores",header=2,usecols="M,O:W")
print(df.head())
team_ids={"Cal Poly State University":20,"Iowa State University":7,"Kansas State University":2,"McGill University":18,"North Carolina State University":1,"North Dakota State University":9,"Oklahoma State University":16,"Oregon State University":22,"Penn State University":11,"Purdue University":4,"South Dakota State University":3,"Texas A&M University":23,"University of Georgia ":19,"University of Guelph":19,"University of Illinois":10,"University of Kentucky":8,"University of Laval":24,"University of Manitoba":17,"University of Missouri":5,"University of Nebraska":12,"University of Saskatchewan":15,"University of Tennessee - Martin":13,"University of Wisconsin Madison":6,"University of Wisconsin Platteville":14}
for i,row in df.iterrows():
    #print(row["Unnamed: 12"])
    team_name=row["Unnamed: 12"]
    team_id=team_ids.get(team_name,-1)
    row["team_id"]=team_id

    if team_id==-1:
        print(f"Team Name not found: {team_name} {team_id}")
    else:
        sql="INSERT INTO event_teams (event_id,team_id,total_score) VALUES (%s,%s,%s)"
        values=(24,team_id,row["TOTAL"])
        #cursor.execute(sql,values)

        sql="INSERT INTO tractors (year,team_id) VALUES (%s,%s)"
        values=(24,team_id)
        cursor.execute(sql,values)
print(df.head())
team_ids={}
cnx.commit()