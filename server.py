import json
import csv
import os
import sqlite3
import threading
import hmac
import re
import time
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get('BLITZ_DATA_DIR', '/tmp/blitz4-lab-data'))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / 'rounds.sqlite3'
LOCK = threading.Lock()

HISTORY_FILE = ROOT / 'historico_7dias.csv'
def archived_history():
    if not HISTORY_FILE.exists():
        return []
    results = []
    with HISTORY_FILE.open(encoding='utf-8-sig', newline='') as file:
        for n, item in enumerate(csv.DictReader(file)):
            try:
                stone = int(item['number'])
                stamp = item['timestamp'].strip()
                if not 0 <= stone <= 14 or not re.fullmatch(r'20\\d{2}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}', stamp):
                    continue
                color = 'branco' if stone == 0 else 'amarelo' if stone < 8 else 'escuro'
                if item['color'].strip() != color:
                    continue
                results.append({'id': 'archive-'+str(n), 'timestamp_utc': stamp+'-03:00', 'number': stone, 'color':color, 'source':'historico-7dias'})
            except (ValueError, TypeError, KeyError):
                continue
    return results
ARCHIVED = archived_history()

INGEST_KEY = os.environ.get('BLITZ_INGEST_KEY', '').strip()
EXTENSION_KEY = os.environ.get('BLITZ_EXTENSION_KEY', '').strip()
COLORS = {'amarelo': 'amarelo', 'escuro': 'escuro', 'branco': 'branco'}


REPLAY_START = time.time()
def load_demo():
    content = (ROOT / 'index.html').read_text(encoding='utf-8')
    match = re.search(r'const initialData=(\[.*?\]);\s*let data=', content, re.S)
    return json.loads(match.group(1)) if match else []
try:
    DEMO_ROUNDS = load_demo()
except (ValueError, OSError):
    DEMO_ROUNDS = []

def replay_state():
    end = min(len(DEMO_ROUNDS), max(0, int(time.time() - REPLAY_START)))
    wins = losses = sg = g1 = g2 = 0
    active = None
    recent = []
    for i in range(end):
        # Choose before observing this round: no future data enters the signal.
        if active is None and i >= 50:
            prior = DEMO_ROUNDS[i-50:i]
            black = sum(1 for x in prior if x['c']=='preto')
            yellow = sum(1 for x in prior if x['c']=='vermelho')
            total = black + yellow
            if total >= 25:
                color = 'preto' if black >= yellow else 'vermelho'
                quality = max(black, yellow)/total
                if quality >= .56:
                    active = {'color':color, 'at':i, 'quality':round(quality, 3)}
        stone = DEMO_ROUNDS[i]
        if active is not None:
            phase = i - active['at']
            if stone['c'] == active['color']:
                wins += 1
                if phase == 0: sg += 1
                elif phase == 1: g1 += 1
                else: g2 += 1
                recent.append({'time':stone['t'], 'color':active['color'], 'result':('SG','G1','G2')[phase]})
                active = None
            elif phase == 2:
                losses += 1
                recent.append({'time':stone['t'], 'color':active['color'], 'result':'LOSS'})
                active = None
    return {
      'mode':'SERVER_HISTORICAL_REPLAY', 'live_connected':False,
      'processed':end, 'total':len(DEMO_ROUNDS), 'finished':end==len(DEMO_ROUNDS),
      'last_round':DEMO_ROUNDS[end-1] if end else None,
      'stones':DEMO_ROUNDS[max(0,end-30):end],
      'signal':active, 'greens':wins,'loss':losses,'sg':sg,'g1':g1,'g2':g2,
      'recent':recent[-12:][::-1],
      'disclaimer':'Accelerated historical simulation only. No live feed or bets.'
    }

def db():
    connection = sqlite3.connect(DB_PATH, timeout=15)
    connection.execute('PRAGMA busy_timeout=15000')
    connection.execute('''CREATE TABLE IF NOT EXISTS rounds (
        id TEXT PRIMARY KEY, ts TEXT NOT NULL UNIQUE,
        number INTEGER NOT NULL, color TEXT NOT NULL,
        source TEXT NOT NULL, received TEXT NOT NULL
    )''')
    connection.commit()
    return connection

with db() as conn:
    pass

def now_iso():
    return datetime.now(timezone.utc).isoformat()

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def json_response(self, status, body):
        raw = json.dumps(body, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        p = urlsplit(self.path).path
        if p == '/health':
            return self.json_response(200, {'status': 'ok', 'app': 'double-insight-blitz4-lab'})
        if p == '/api/historical/7days':
            return self.json_response(200, {'loaded': bool(ARCHIVED), 'count':len(ARCHIVED),'whites':sum(r['number']==0 for r in ARCHIVED),'rounds':ARCHIVED})
        if p == '/api/replay/state':
            return self.json_response(200, replay_state())
        if p == '/api/status':
            with db() as conn:
                count = conn.execute('SELECT COUNT(*) FROM rounds').fetchone()[0]
                latest = conn.execute('SELECT ts FROM rounds ORDER BY ts DESC LIMIT 1').fetchone()
            return self.json_response(200, {
                'mode': 'historical_lab', 'live_connected': False,
                'ingestion_enabled': bool(INGEST_KEY),
                'stored_rounds': count, 'latest_round_utc': latest[0] if latest else None,
                'source': 'none', 'note': 'No external results feed is connected.'
            })
        if p == '/api/live/state':
            with db() as conn:
                count = conn.execute('SELECT COUNT(*) FROM rounds').fetchone()[0]
                last = conn.execute('SELECT id,ts,number,color,source,received FROM rounds ORDER BY ts DESC LIMIT 1').fetchone()
            fresh = False
            age = None
            if last:
                try:
                    dt = datetime.fromisoformat(last[1].replace('Z','+00:00'))
                    age = round((datetime.now(timezone.utc)-dt).total_seconds(), 1)
                    fresh = -10 <= age <= 90
                except (ValueError,TypeError):
                    pass
            return self.json_response(200, {
              'mode': 'OBSERVATION_ONLY',
              'connected': bool(fresh), 'fresh': bool(fresh),
              'round_age_seconds': age, 'count': count,
              'last_round': dict(zip(('id','timestamp_utc','number','color','source','received_at_utc'),last)) if last else None,
              'message':'Recent incoming rounds observed; not a verified continuous feed.' if fresh else 'No fresh external results. Historical replay is separate.'
            })
        if p == '/api/rounds':
            raw_limit = parse_qs(urlsplit(self.path).query).get('limit', ['100'])[0]
            try: limit = min(3000, max(1, int(raw_limit)))
            except ValueError: limit = 100
            with db() as conn:
                rows = conn.execute('SELECT id, ts, number, color, source FROM rounds ORDER BY ts DESC LIMIT ?', (limit,)).fetchall()
            return self.json_response(200, {
                'live_connected': False,
                'rounds': [dict(zip(('id','timestamp_utc','number','color','source'), r)) for r in reversed(rows)]
            })
        if p == '/':
            self.path = '/index.html'
            return super().do_GET()
        if p in ('/index.html','/painel.html','/monitor.html','/operacao.html','/comparativo.html','/ao-vivo.html','/estrategias.html','/prospectivo.html','/multihorizonte.html','/motor-lab.html'):
            return super().do_GET()
        return self.json_response(404, {'error':'not_found'})

    def do_POST(self):
        if urlsplit(self.path).path != '/api/ingest':
            return self.json_response(404, {'error': 'not_found'})
        supplied = self.headers.get('X-Ingest-Key', '')
        extension_supplied = self.headers.get('X-Extension-Key', '')
        extension_auth = bool(EXTENSION_KEY and extension_supplied and hmac.compare_digest(extension_supplied, EXTENSION_KEY))
        master_auth = bool(INGEST_KEY and supplied and hmac.compare_digest(supplied, INGEST_KEY))
        if not INGEST_KEY and not EXTENSION_KEY:
            return self.json_response(503, {'error': 'ingestion_disabled'})
        if not extension_auth and not master_auth:
            return self.json_response(401, {'error': 'unauthorized'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if size < 2 or size > 4096:
                return self.json_response(413, {'error': 'payload_size_invalid'})
            payload = json.loads(self.rfile.read(size))
            rid = str(payload['id']).strip()
            num = payload['number']
            stamp = str(payload['timestamp_utc']).strip()
            src = 'tipminer_dom_observation_not_game_time' if extension_auth else str(payload.get('source','approved_feed')).strip()
            parsed = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
            if parsed.tzinfo is None: raise ValueError('Timezone required')
            stamp = parsed.astimezone(timezone.utc).isoformat()
            if not rid or len(rid) > 100 or not isinstance(num,int) or isinstance(num,bool) or not 0 <= num <= 14 or len(src)>80 or not src:
                raise ValueError('Invalid fields')
            # Prevent fake future timestamps from marking the feed as healthy.
            skew = (parsed.astimezone(timezone.utc) - datetime.now(timezone.utc)).total_seconds()
            if skew > 10 or skew < -86400:
                return self.json_response(422, {'error':'timestamp_outside_allowed_window'})
            if extension_auth and (num == 0 or not rid.startswith('dom-')):
                return self.json_response(422, {'error':'extension_non_numeric_or_invalid_id'})
            color = 'branco' if num == 0 else 'amarelo' if num <= 7 else 'escuro'
            if payload.get('color', color) != color:
                raise ValueError('Color mismatch')
            with LOCK:
                with db() as conn:
                    last = conn.execute('SELECT id, ts FROM rounds ORDER BY ts DESC LIMIT 1').fetchone()
                    if last and stamp < last[1]:
                        return self.json_response(409, {'error':'out_of_order', 'last_round_utc':last[1]})
                    present = conn.execute('SELECT id,ts,number FROM rounds WHERE id=? OR ts=?',(rid,stamp)).fetchone()
                    if present:
                        return self.json_response(200 if present==(rid,stamp,num) else 409, {'status':'duplicate' if present==(rid,stamp,num) else 'conflict'})
                    conn.execute('INSERT INTO rounds VALUES (?,?,?,?,?,?)', (rid,stamp,num,color,src,now_iso()))
            return self.json_response(201, {'status':'accepted','id':rid,'color':color})
        except (ValueError,KeyError,TypeError,json.JSONDecodeError):
            return self.json_response(400, {'error':'invalid_round'})

    def end_headers(self):
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        super().end_headers()

if __name__ == '__main__':
    port = int(os.environ.get('PORT','8080'))
    ThreadingHTTPServer(('0.0.0.0',port),Handler).serve_forever()
