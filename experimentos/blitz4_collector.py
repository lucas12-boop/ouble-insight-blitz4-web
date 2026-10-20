"""Coletor Blitz4 24H experimental: requires a documented, authorized JSON results URL.
No automatic deployment. Never accepts future/unverified or other-game round feeds.
"""
import json, os, time, sqlite3
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

SOURCE_URL=os.getenv("BLITZ4_RESULTS_URL","").strip()
TARGET=os.getenv("BLITZ4_INGEST_URL","").strip()
KEY=os.getenv("BLITZ_INGEST_KEY","").strip()
INTERVAL=max(2,float(os.getenv("BLITZ4_POLL_SECONDS","3")))
STATE_DB=os.getenv("BLITZ4_COLLECTOR_DB","./blitz4_collector_state.sqlite3")
def connect_db():
    conn=sqlite3.connect(STATE_DB, timeout=15)
    conn.execute("CREATE TABLE IF NOT EXISTS delivered (id TEXT PRIMARY KEY, number INTEGER NOT NULL, official_time TEXT NOT NULL, delivered_at TEXT NOT NULL)")
    conn.commit()
    return conn
def is_delivered(conn,rid):
    return conn.execute("SELECT 1 FROM delivered WHERE id=?",(rid,)).fetchone() is not None
def remember(conn,item):
    conn.execute("INSERT OR IGNORE INTO delivered (id,number,official_time,delivered_at) VALUES (?,?,?,?)",
        (item["id"],item["number"],item["timestamp_utc"],datetime.now(timezone.utc).isoformat()))
    conn.commit()
def parse_rounds(doc):
    """Exact contract: {game:'blitz4-double', rounds:[{id,number,created_at}]}, no guessed aliases."""
    if not isinstance(doc,dict) or doc.get("game")!="blitz4-double" or not isinstance(doc.get("rounds"),list):
        raise ValueError("Feed not verified as blitz4-double")
    parsed=[]
    for item in doc["rounds"]:
        if not isinstance(item,dict): continue
        ident=item.get("id")
        n=item.get("number")
        stamp=item.get("created_at")
        if not isinstance(ident,(str,int)) or not isinstance(n,int) or isinstance(n,bool) or not 0<=n<=14 or not isinstance(stamp,str):
            continue
        try:
            dt=datetime.fromisoformat(stamp.replace("Z","+00:00"))
        except ValueError:
            continue
        if dt.tzinfo is None:continue
        dt=dt.astimezone(timezone.utc)
        if abs((datetime.now(timezone.utc)-dt).total_seconds())>3600:continue
        rid="blitz4-direct-"+str(ident)
        parsed.append(dict(id=rid,number=n,color="branco" if n==0 else "amarelo" if n<=7 else "escuro",timestamp_utc=dt.isoformat(),source="blitz4-direct-verified"))
    return sorted(parsed,key=lambda x:x["timestamp_utc"])
def send(item):
    body=json.dumps(item).encode()
    req=Request(TARGET,data=body,headers={"Content-Type":"application/json","X-Ingest-Key":KEY},method="POST")
    with urlopen(req,timeout=10) as response:
        return response.status,response.read().decode()[:500]
def run():
    if not (SOURCE_URL.startswith("https://") and TARGET.startswith("https://") and KEY):
        raise SystemExit("Collector inactive: set authorized BLITZ4_RESULTS_URL, BLITZ4_INGEST_URL, BLITZ_INGEST_KEY")
    conn=connect_db()
    print("experimental collector starting; source must be verified independently",flush=True)
    while True:
        try:
            with urlopen(Request(SOURCE_URL,headers={"Accept":"application/json"}),timeout=8) as response:
                doc=json.load(response)
            for item in parse_rounds(doc):
                if is_delivered(conn,item["id"]):continue
                status,reply=send(item)
                if status in (200,201):
                    remember(conn,item)
                    print("received",item["id"],item["number"],status,flush=True)
                else:
                    print("not accepted",status,reply,flush=True)
                    break
            # Successful delivery is persisted; restart will not resend acknowledged IDs.
        except (ValueError,URLError,HTTPError,TimeoutError,KeyError) as exc:
            print("feed or transmission issue:",str(exc)[:200],flush=True)
        time.sleep(INTERVAL)
if __name__=="__main__":run()
