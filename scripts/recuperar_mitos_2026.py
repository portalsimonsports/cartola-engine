import csv
import json
import time
from pathlib import Path
import requests

MITOS={1:24137264,2:46095320,3:24807770,4:48921295,5:28933900,6:45564289,7:17950024,8:2275569,9:361314,10:13356680,11:44851575,12:5461035,13:14013757,14:9533445,15:51001311,16:2425397,17:45146407,18:51030023,19:44621481,20:49149324,21:14650635,22:19572648,23:50198965,24:44759774}
BASES=["https://api.cartolafc.globo.com/time/id/{time_id}/{rodada}","https://api.cartola.globo.com/time/id/{time_id}/{rodada}"]
HEADERS={"User-Agent":"Mozilla/5.0 (compatible; SimonSportsCartola/1.0)","Accept":"application/json,text/plain,*/*"}
FIELDS=["ANO","RODADA","MITO_TIME_ID","MITO_NOME_TIME","MITO_PONTOS","MITO_PONTOS_CAMPEONATO","ATLETA_ID","APELIDO","NOME","POSICAO_ID","CLUBE_ID","PRECO","PONTOS_ATLETA","SCOUTS","CAPITAO","RESERVA","TECNICO","ESQUEMA_ID","PATRIMONIO","VALOR_TIME","FONTE","CAPTURADO_EM","RAW_JSON_ATLETA"]

def buscar(rodada,time_id):
    erros=[]
    for tpl in BASES:
        url=tpl.format(time_id=time_id,rodada=rodada)
        try:
            r=requests.get(url,headers=HEADERS,timeout=30)
            if r.ok:return {"ok":True,"url":url,"data":r.json()}
            erros.append(f"{url} HTTP {r.status_code}")
        except Exception as e:erros.append(f"{url} {e}")
        time.sleep(.4)
    return {"ok":False,"erros":erros}

def linhas(rodada,time_id,res,ts):
    d=res["data"]; t=d.get("time") or {}; cap=d.get("capitao_id"); out=[]
    def add(a,reserva):
        aid=a.get("atleta_id")
        out.append({"ANO":2026,"RODADA":rodada,"MITO_TIME_ID":time_id,"MITO_NOME_TIME":t.get("nome","") or "","MITO_PONTOS":d.get("pontos"),"MITO_PONTOS_CAMPEONATO":d.get("pontos_campeonato"),"ATLETA_ID":aid,"APELIDO":a.get("apelido","") or "","NOME":a.get("nome","") or "","POSICAO_ID":a.get("posicao_id"),"CLUBE_ID":a.get("clube_id"),"PRECO":a.get("preco_num"),"PONTOS_ATLETA":a.get("pontos_num"),"SCOUTS":json.dumps(a.get("scout") or {},ensure_ascii=False,separators=(",",":")),"CAPITAO":"SIM" if aid==cap else "NAO","RESERVA":"SIM" if reserva else "NAO","TECNICO":"SIM" if a.get("posicao_id")==6 else "NAO","ESQUEMA_ID":d.get("esquema_id"),"PATRIMONIO":d.get("patrimonio"),"VALOR_TIME":d.get("valor_time"),"FONTE":res.get("url","") or "","CAPTURADO_EM":ts,"RAW_JSON_ATLETA":""})
    for a in d.get("atletas") or []: add(a,False)
    reservas=d.get("reservas") or []
    if isinstance(reservas,dict): reservas=list(reservas.values())
    for a in reservas: add(a,True)
    return out

def main():
    ts=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()); base=Path("data/mitos_2026_por_rodada"); base.mkdir(parents=True,exist_ok=True); falhas=0
    for rodada,time_id in MITOS.items():
        print(f"Rodada {rodada}",flush=True); res=buscar(rodada,time_id)
        if not res.get("ok"):
            falhas+=1; continue
        rows=linhas(rodada,time_id,res,ts)
        p=base/f"rodada_{rodada:02d}.csv"
        with p.open("w",encoding="utf-8",newline="") as f:
            w=csv.DictWriter(f,fieldnames=FIELDS); w.writeheader(); w.writerows(rows)
        print(f"{p}: {len(rows)} linhas",flush=True)
    if falhas: raise SystemExit(2)

if __name__=="__main__":main()
