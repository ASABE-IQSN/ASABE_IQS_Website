import os
import mysql.connector
import local_secrets
import re
import pandas as pd
import pickle
cnx = mysql.connector.connect(
    host=local_secrets.DB_IP,
    port=3306,
    user=local_secrets.ADMINUNAME,
    password=local_secrets.ADMINPWORD,
    database="IQS_Test_Environment")
parent="sql_management/data/2025/2025_Pull_Data"
files=os.listdir(parent)

hook_ids={"A-Team Pull 1- 1100lb, High Hook":3,"A-Team Pull 2- 1600lb, High Hook":4,"A-Team Pull 3- 1600lb, Low Hook":5}

with open("team_dict.pkl","rb") as file:

    team_dict=pickle.load(file)
team_dict:dict
print(team_dict)
file_filter=["A-Team Pull 1- 1100lb, High Hook","A-Team Pull 2- 1600lb, High Hook","A-Team Pull 3- 1600lb, Low Hook"]
#team_ids={'Caly Poly':20,'UT-Martin':13,'Kansas State':2,'Kentucky':8,'UW-Platteville':14,'Saskatc':15,'Iowa State':7,'Purdue':4,'NDSU':9,'Illinois':10,'Nebraska':12,'Mizzou':5,'Illinois Re-pull':10,'UW-Madison':6,'NC State':1,'Penn State':11,'SDSU':3,'Laval':24,'Wisconsin-Mad':6,'Cal Poly':20,'U of Sask':15,'NCSU':1,'UW-Platt':14,'Saskatch':15,'Penn State Repull':11,'UW Platteville':14,'Old Iowa State Tractor':-1,'NC_State':1}

teams=[]

cursor=cnx.cursor()
hooks=[]
id=0
for file in files:
    print(file)
    if file in file_filter:
        pulls=[]
        for pull in os.listdir(parent+"/"+file):
            if ".csv" in pull:
                #print(pull)
                pull_df={}
                patern=r"Hook_\d{4}_([^\.]+)(?=\.csv$)"
                match=re.search(patern,pull)
                #print(pull)
                team=match.group(1)
                #print(f"Pull: {file} Team: {team}")
                #teams.append(team)
                team_id=team_dict.get(team,-1)
                #print(team_id)
                data=open(parent+"/"+file+"/"+pull)
                force=[]
                distance=[]
                speed=[]

                # pull_df["Raw Team Name"]=team
                # pull_df["Team ID"]=team_id
                # pull_df["Raw Hook"]=file
                # pull_df["Hook ID"]=hook_ids.get(file,None)
                # pull_df["Event ID"]=23
                # pull_df["Pull ID"]=id
                if team_id>0:
                    pass
                else:
                    print(team)
                    print(pull)
                
                
                if team_id>0:

                    sql="SELECT tractor_id FROM tractors WHERE original_team_id = %s AND year = %s"
                    values=(team_id,25)
                    cursor.execute(sql,values)
                    x=cursor.fetchone()
                    if x:
                        tractor_id=x[0]
                        sql="INSERT INTO pulls (event_id, team_id, hook_id, tractor_id) VALUES (%s,%s,%s,%s)"
                        values=(25,team_id,hook_ids[file],tractor_id)
                        cursor.execute(sql,values)
                    else:
                        print(team)
                    sql="SELECT LAST_INSERT_ID();"
                    cursor.execute(sql)
                    id=cursor.fetchone()
                    id=id[0]
                    
                    pull_data=[]
                    vals=[]
                    for i,fileline in enumerate(data):
                        if i>33:
                            di={}
                            dsp=fileline.split(",")
                            di["pull_time"]=float(dsp[0])
                            di["chain_force"]=float(dsp[1])
                            di["distance"]=float(dsp[3])
                            di["speed"]=float(dsp[2])
                            pull_data.append(di)
                            distance.append(float(dsp[3]))
                            speed.append(float(dsp[2]))
                            force.append(float(dsp[1]))
                            sql="INSERT INTO pull_data (pull_id,pull_time,chain_force,speed,distance) VALUES (%s,%s,%s,%s,%s)"
                            values=(id,di["pull_time"],di["chain_force"],di["speed"],di["distance"])
                            #print(sql)
                            #print(values)
                            vals.append(values)
                            #cursor.execute(sql,values)
                    print(id)

                    cursor.executemany(sql,vals)
                    #pull_data_df=pd.DataFrame(pull_data)
                    #print(pull_data_df.head())
                    #pull_data_df.to_hdf("sql_management/data/2023/Pulling Data/A-Team Data/"+file+"/"+str(id)+'.h5', key='df', mode='w')

                    max_force=max(force)
                    max_speed=max(speed)
                    max_distance=max(distance)
                    pull_df["max_speed"]=max_speed
                    pull_df["max_force"]=max_force
                    pull_df["max_distance"]=max_distance
                    pulls.append(pull_df)
                    sql="UPDATE pulls SET final_distance=%s WHERE pull_id=%s"
                    values=(max_distance,id)
                    cursor.execute(sql,values)

                    sql="UPDATE pulls SET top_speed=%s WHERE pull_id=%s"
                    values=(max_speed,id)
                    cursor.execute(sql,values)
                    id+=1
        cnx.commit()
        #pulls_df=pd.DataFrame(pulls)
        #pulls_df.to_hdf("sql_management/data/2023/Pulling Data/A-Team Data/"+file+"/"+'pulls.h5', key='df', mode='w')


                    
                    
# dedupe=[]
# for team in teams:
#     if team not in dedupe:
#         dedupe.append(team)
# print(dedupe)
# st="{"
# for line in dedupe:
#     st+=f"'{line}':,"
# print(st[:-1]+"}")

    #print(file.split("_")[1][:-4])