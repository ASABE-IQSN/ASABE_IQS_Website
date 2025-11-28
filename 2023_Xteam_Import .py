import os
import mysql.connector
import local_secrets
import re
import pandas as pd
# cnx = mysql.connector.connect(
#     host=local_secrets.DB_IP,
#     port=3306,
#     user=local_secrets.ADMINUNAME,
#     password=local_secrets.ADMINPWORD,
#     database="IQS_Test_Environment")
parent="sql_management/data/2023/Pulling Data/X-Team Data"
files=os.listdir(parent)

hook_ids={"Pull_1":10,"Pull_2":11}

#team_ids={"h":1}

team_ids={"Penn State X-Team":232,"Penn State":232,"Kentucky Re-pull":230,"Penn State X-Team Repull":232,"Iowa State":229,"Nebraska":212,"NDSU":231,"SDSU":227,"Mizzou":228,"Kentucky":230,"Kentucky":230,"SDSU":227,"Penn State":232,"Iowa State":229,"Mizzou":228,"NDSU":231}


teams=[]

#cursor=cnx.cursor()
hooks=[]
id=0
for file in files:
    #print(file)
    pulls=[]
    for pull in os.listdir(parent+"/"+file):
        if ".csv" in pull:
            #print(pull)
            pull_df={}
            patern=r"__\d+_(.+)\.csv$"
            match=re.search(patern,pull)
            team=match.group(1)
            #print(team)
            #print(f"Pull: {file} Team: {team}")
            #teams.append(team)
            team_id=team_ids.get(team,-1)
            #print(team_id)
            data=open(parent+"/"+file+"/"+pull)
            force=[]
            distance=[]
            speed=[]
            pull_df["Raw Team Name"]=team
            pull_df["Team ID"]=team_id
            pull_df["Raw Hook"]=file
            pull_df["Hook ID"]=hook_ids[file]
            pull_df["Event ID"]=23
            pull_df["Pull ID"]=id
            
            #sql="INSERT INTO pulls (event_id, team_id, hook_id) VALUES (%s,%s,%s)"
            #values=(23,team_id,hook_ids[file])
            if team_id>0:
                #cursor.execute(sql,values)
                #sql="SELECT LAST_INSERT_ID();"
                #cursor.execute(sql)
                #id=1#cursor.fetchone()
                
                pull_data=[]
                
                for i,fileline in enumerate(data):
                    if i>33:
                        di={}
                        dsp=fileline.split(",")
                        di["pull_time"]=float(dsp[1])
                        di["chain_force"]=float(dsp[2])
                        di["distance"]=float(dsp[3])
                        di["speed"]=float(dsp[4][:-1])
                        pull_data.append(di)
                        distance.append(float(dsp[3]))
                        speed.append(float(dsp[4][:-1]))
                        force.append(float(dsp[2]))
                        #sql="INSERT INTO pull_data (pull_id,pull_time,chain_force,speed,distance) VALUES (%s,%s,%s,%s,%s)"
                        #values=(id,di["pull_time"],di["chain_force"],di["speed"],di["distance"])
                        #cursor.execute(sql,values)
                
                pull_data_df=pd.DataFrame(pull_data)
                pull_data_df.to_hdf(parent+"/"+file+"/"+str(id)+'.h5', key='df', mode='w')

                max_force=max(force)
                max_speed=max(speed)
                max_distance=max(distance)
                pull_df["max_speed"]=max_speed
                pull_df["max_force"]=max_force
                pull_df["max_distance"]=max_distance
                pulls.append(pull_df)
                #sql="UPDATE pulls SET final_distance=%s WHERE pull_id=%s"
                #values=(max_distance,id)
                #cursor.execute(sql,values)

                #sql="UPDATE pulls SET top_speed=%s WHERE pull_id=%s"
                #values=(max_speed,id)
                #cursor.execute(sql,values)
                id+=1
            else:
                print(f"Tractor Not Found")
        #cnx.commit()
    pulls_df=pd.DataFrame(pulls)
    print(pulls_df.head())
    pulls_df.to_hdf(parent+"/"+file+"/"+'pulls.h5', key='df', mode='w')


                    
                    
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