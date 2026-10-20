import json
import csv
import os
import sqlite3
import threading
import hmac
import re
import time
import hashlib
import base64
from http.cookies import SimpleCookie
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get('BLITZ_DATA_DIR', '/tmp/blitz4-lab-data'))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / 'rounds.sqlite3'
LOCK = threading.Lock()

HISTORY_FILE = DATA_DIR / 'historico_7dias.csv'
if not HISTORY_FILE.exists() and (ROOT / 'historico_7dias.csv').exists():
    import shutil
    shutil.copyfile(ROOT / 'historico_7dias.csv', HISTORY_FILE)
def archived_history():
    if not HISTORY_FILE.exists():
        return []
    results = []
    with HISTORY_FILE.open(encoding='utf-8-sig', newline='') as file:
        for n, item in enumerate(csv.DictReader(file)):
            try:
                stone = int(item['number'])
                stamp = item['timestamp'].strip()
                if not 0 <= stone <= 14 or not re.fullmatch(r'20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', stamp):
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
OWNER_USER = os.environ.get('BLITZ_OWNER_USER','').strip()
OWNER_PASS_HASH = os.environ.get('BLITZ_OWNER_PASS_HASH','').strip()
OWNER_SESSION_SECRET = os.environ.get('BLITZ_OWNER_SESSION_SECRET','').strip()
OWNER_LOGIN_ATTEMPTS = {}
def owner_token_valid(token):
    if not (token and OWNER_SESSION_SECRET):
        return False
    try:
        encoded, mac = token.rsplit('.',1)
        expected=hmac.new(OWNER_SESSION_SECRET.encode(),encoded.encode(),'sha256').hexdigest()
        if not hmac.compare_digest(expected,mac):
            return False
        raw=base64.urlsafe_b64decode(encoded+'='*((-len(encoded))%4)).decode()
        user,expires=raw.split('|',1)
        return user==OWNER_USER and int(expires)>int(time.time())
    except (ValueError,TypeError,UnicodeError):
        return False
def owner_password_valid(username,password):
    if not (OWNER_USER and OWNER_PASS_HASH and username==OWNER_USER and isinstance(password,str)):
        return False
    try:
        salt,digest=OWNER_PASS_HASH.split(':',1)
        calculated=hashlib.pbkdf2_hmac('sha256',password.encode('utf-8'),bytes.fromhex(salt),240000)
        return hmac.compare_digest(calculated.hex(),digest)
    except (ValueError,TypeError):
        return False

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
    connection.execute("""CREATE TABLE IF NOT EXISTS rounds (
        id TEXT PRIMARY KEY, ts TEXT NOT NULL,
        number INTEGER NOT NULL, color TEXT NOT NULL,
        source TEXT NOT NULL, received TEXT NOT NULL
    )""")
    connection.commit()
    return connection

def ensure_round_schema():
    # Older builds applied UNIQUE(ts). Observation timestamps are not round IDs.
    # Rebuild transactionally; existing records survive and no new timestamp constraint is created.
    with db() as conn:
        indexes = conn.execute("PRAGMA index_list('rounds')").fetchall()
        has_unique_ts = any(row[2] and
            [c[2] for c in conn.execute("PRAGMA index_info('"+row[1]+"')").fetchall()] == ['ts']
            for row in indexes)
        if not has_unique_ts:
            return
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute("ALTER TABLE rounds RENAME TO rounds_before_ts_migration")
            conn.execute("""CREATE TABLE rounds (
                id TEXT PRIMARY KEY, ts TEXT NOT NULL,
                number INTEGER NOT NULL, color TEXT NOT NULL,
                source TEXT NOT NULL, received TEXT NOT NULL
            )""")
            conn.execute("""INSERT INTO rounds (id,ts,number,color,source,received)
                         SELECT id,ts,number,color,source,received FROM rounds_before_ts_migration""")
            conn.execute("DROP TABLE rounds_before_ts_migration")
            conn.commit()
        except Exception:
            conn.rollback()
            raise

ensure_round_schema()

def now_iso():
    return datetime.now(timezone.utc).isoformat()

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def json_response(self, status, body):
        raw = json.dumps(body, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        if getattr(self,'_rounds_etag',None): self.send_header('ETag',self._rounds_etag)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def owner_authorized(self):
        try:
            cookies=SimpleCookie();cookies.load(self.headers.get('Cookie',''))
            return owner_token_valid(cookies['blitz_owner'].value) if 'blitz_owner' in cookies else False
        except Exception:
            return False

    def do_GET(self):
        p = urlsplit(self.path).path
        if p == '/proprietario.html' and not self.owner_authorized():
            self.send_response(302)
            self.send_header('Location','/login.html')
            self.send_header('Cache-Control','no-store')
            self.end_headers()
            return
        if p == '/api/owner/session':
            return self.json_response(200, {'authenticated':self.owner_authorized(),'configured':bool(OWNER_USER and OWNER_PASS_HASH and OWNER_SESSION_SECRET)})
        if p == '/api/owner/overview':
            if not self.owner_authorized(): return self.json_response(401,{'error':'unauthorized'})
            with db() as conn:
                count=conn.execute('SELECT COUNT(*) FROM rounds').fetchone()[0]
                whites=conn.execute('SELECT COUNT(*) FROM rounds WHERE number=0').fetchone()[0]
                latest=conn.execute('SELECT number,color,ts,received FROM rounds ORDER BY received DESC LIMIT 1').fetchone()
            return self.json_response(200, {'observed_rounds':count,'observed_whites':whites,'archive_rounds':len(ARCHIVED),'archive_whites':sum(r['number']==0 for r in ARCHIVED),'latest':dict(zip(('number','color','observed_utc','received_utc'),latest)) if latest else None})
        if p == '/api/extension/version':
            package = ROOT / 'Insight-Blitz4-TipMiner-Extensao.zip'
            return self.json_response(200, {'version': '0.11.0' if package.exists() else None, 'download': '/Insight-Blitz4-TipMiner-Extensao.zip' if package.exists() else None, 'auto_update':False})
        if p == '/health':
            return self.json_response(200, {'status': 'ok', 'app': 'double-insight-blitz4-lab'})
        if p == '/api/historical/7days':
            return self.json_response(200, {'loaded': bool(ARCHIVED), 'count':len(ARCHIVED),'whites':sum(r['number']==0 for r in ARCHIVED),'rounds':ARCHIVED})
        if p == '/api/history/status':
            return self.json_response(200, {'installed':bool(ARCHIVED),'count':len(ARCHIVED),'whites':sum(r['number']==0 for r in ARCHIVED),'persistent':str(HISTORY_FILE).startswith(str(DATA_DIR))})
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
        if p == '/api/capture/health':
            with db() as conn:
                recent = conn.execute('SELECT ts,received,number,color,source FROM rounds ORDER BY received DESC LIMIT 120').fetchall()
                white_count = conn.execute('SELECT COUNT(*) FROM rounds WHERE number=0').fetchone()[0]
                last_white = conn.execute('SELECT ts,received FROM rounds WHERE number=0 ORDER BY received DESC LIMIT 1').fetchone()
            age = None
            if recent:
                try: age = max(0,round((datetime.now(timezone.utc)-datetime.fromisoformat(recent[0][1])).total_seconds(),1))
                except (ValueError,TypeError): pass
            delays=[]
            for ts,received,*_ in recent:
                try: delays.append(max(0,(datetime.fromisoformat(received)-datetime.fromisoformat(ts)).total_seconds()))
                except (ValueError,TypeError): continue
            return self.json_response(200, {'status': 'waiting' if age is None else ('stale' if age>90 else 'receiving'), 'last_received_age_seconds':age, 'latest_number':recent[0][2] if recent else None,'latest_color':recent[0][3] if recent else None,'latest_source':recent[0][4] if recent else None,'recent_count':len(recent),'live_white_count':white_count,'last_live_white_received_utc':last_white[1] if last_white else None,'receive_lag_seconds_median':round(sorted(delays)[len(delays)//2],1) if delays else None,'note':'Timestamps from extension are observation times, not official game round times.'})
        if p == '/api/capture/recent':
            with db() as conn:
                rows = conn.execute('SELECT id,ts,received,number,color,source FROM rounds ORDER BY received DESC LIMIT 30').fetchall()
            entries = []
            for rid,ts,received,num,color,source in rows:
                try:
                    lag = round((datetime.fromisoformat(received)-datetime.fromisoformat(ts)).total_seconds(),2)
                except (ValueError,TypeError):
                    lag = None
                entries.append({'id':rid,'observed_utc':ts,'received_utc':received,'number':num,'color':color,'source':source,'transport_lag_seconds':lag})
            return self.json_response(200,{'count':len(entries),'rounds':entries,'warning':'Observed timestamp is not verified official round time.'})
        if p == '/api/rounds':
            raw_limit = parse_qs(urlsplit(self.path).query).get('limit', ['100'])[0]
            try: limit = min(3000, max(1, int(raw_limit)))
            except ValueError: limit = 100
            with db() as conn:
                latest = conn.execute('SELECT id,received FROM rounds ORDER BY received DESC, rowid DESC LIMIT 1').fetchone()
                latest_id = latest[0] if latest else ''
                latest_received = latest[1] if latest else None
                if latest_id and self.headers.get('If-None-Match','') == '"'+latest_id+'"':
                    self.send_response(304)
                    self.send_header('Cache-Control','no-store')
                    self.send_header('ETag','"'+latest_id+'"')
                    self.end_headers()
                    return
                rows = conn.execute('SELECT id, ts, number, color, source, received FROM rounds ORDER BY ts DESC LIMIT ?', (limit,)).fetchall()
            self._rounds_etag = '"'+latest_id+'"'
            return self.json_response(200, {
                'live_connected': False,
                'last_received_utc': latest_received,
                'rounds': [dict(zip(('id','timestamp_utc','number','color','source','received_utc'), r)) for r in reversed(rows)]
            })
        if p == '/':
            self.path = '/index.html'
            return super().do_GET()
        if p in ('/login.html','/proprietario.html','/index.html','/painel.html','/monitor.html','/operacao.html','/comparativo.html','/ao-vivo.html','/estrategias.html','/prospectivo.html','/multihorizonte.html','/motor-lab.html','/extensao.html','/historico-servidor.html','/Insight-Blitz4-TipMiner-Extensao.zip'):
            return super().do_GET()
        return self.json_response(404, {'error':'not_found'})

    def do_POST(self):
        target=urlsplit(self.path).path
        if target == '/api/owner/logout':
            self.send_response(204)
            self.send_header('Set-Cookie','blitz_owner=; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=0')
            self.send_header('Cache-Control','no-store')
            self.end_headers()
            return
        if target == '/api/owner/login':
            try:
                size=int(self.headers.get('Content-Length','0'))
                if size<2 or size>2048: return self.json_response(400,{'error':'invalid_input'})
                data=json.loads(self.rfile.read(size))
                ip=self.client_address[0]; now=time.time()
                with LOCK:
                    attempts=[t for t in OWNER_LOGIN_ATTEMPTS.get(ip,[]) if now-t<900]
                    if len(attempts)>=8: return self.json_response(429,{'error':'too_many_attempts'})
                    attempts.append(now);OWNER_LOGIN_ATTEMPTS[ip]=attempts
                if not owner_password_valid(data.get('username',''),data.get('password','')) or not OWNER_SESSION_SECRET:
                    return self.json_response(401,{'error':'invalid_credentials'})
                with LOCK: OWNER_LOGIN_ATTEMPTS.pop(ip,None)
                encoded=base64.urlsafe_b64encode((OWNER_USER+'|'+str(int(now)+8*3600)).encode()).decode().rstrip('=')
                sig=hmac.new(OWNER_SESSION_SECRET.encode(),encoded.encode(),'sha256').hexdigest()
                raw=json.dumps({'authenticated':True},ensure_ascii=False).encode()
                self.send_response(200)
                self.send_header('Content-Type','application/json')
                self.send_header('Set-Cookie','blitz_owner='+encoded+'.'+sig+'; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=28800')
                self.send_header('Cache-Control','no-store')
                self.send_header('Content-Length',str(len(raw)))
                self.end_headers();self.wfile.write(raw)
                return
            except (ValueError,KeyError,TypeError,json.JSONDecodeError):
                return self.json_response(400,{'error':'invalid_input'})
        if target == '/api/history/import':
            auth = self.headers.get('X-Extension-Key','')
            master = self.headers.get('X-Ingest-Key','')
            authorized = bool((EXTENSION_KEY and hmac.compare_digest(auth,EXTENSION_KEY)) or (INGEST_KEY and hmac.compare_digest(master,INGEST_KEY)))
            if not authorized:
                return self.json_response(401, {'error':'unauthorized'})
            try:
                size = int(self.headers.get('Content-Length','0'))
                if size < 1000 or size > 1500000:
                    return self.json_response(413, {'error':'csv_size_invalid'})
                body = self.rfile.read(size).decode('utf-8-sig')
                parsed = list(csv.DictReader(body.splitlines()))
                if not 1000 <= len(parsed) <= 50000:
                    raise ValueError('row_count_invalid')
                valid = []
                for item in parsed:
                    n = int(item['number'])
                    stamp = item['timestamp'].strip()
                    color = 'branco' if n == 0 else 'amarelo' if n <= 7 else 'escuro'
                    if n < 0 or n > 14 or item['color'].strip() != color or not re.fullmatch(r'20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}',stamp):
                        raise ValueError('csv_data_invalid')
                    valid.append(item)
                with LOCK:
                    temporary=HISTORY_FILE.with_suffix('.tmp')
                    temporary.write_text(body,encoding='utf-8')
                    temporary.replace(HISTORY_FILE)
                    global ARCHIVED
                    ARCHIVED = archived_history()
                return self.json_response(201, {'installed':True,'count':len(ARCHIVED),'whites':sum(r['number']==0 for r in ARCHIVED)})
            except (ValueError,KeyError,UnicodeError,TypeError):
                return self.json_response(400, {'error':'invalid_historical_csv'})
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
            if extension_auth and not rid.startswith('dom-'):
                return self.json_response(422, {'error':'extension_invalid_id'})
            color = 'branco' if num == 0 else 'amarelo' if num <= 7 else 'escuro'
            if payload.get('color', color) != color:
                raise ValueError('Color mismatch')
            with LOCK:
                with db() as conn:
                    last = conn.execute('SELECT id, ts FROM rounds ORDER BY ts DESC LIMIT 1').fetchone()
                    # Backfill may arrive late from the extension. Store it without treating it as the latest live round.
                    # The live endpoint orders by observation time; delayed/batched stones never create retroactive GREENs.
                    delayed = bool(last and stamp < last[1])
                    present = conn.execute('SELECT id,ts,number FROM rounds WHERE id=?',(rid,)).fetchone()
                    if present:
                        return self.json_response(200 if present==(rid,stamp,num) else 409, {'status':'duplicate' if present==(rid,stamp,num) else 'conflict'})
                    conn.execute('INSERT INTO rounds VALUES (?,?,?,?,?,?)', (rid,stamp,num,color,src,now_iso()))
            return self.json_response(201, {'status':'accepted','id':rid,'color':color,'backfill':delayed})
        except (ValueError,KeyError,TypeError,json.JSONDecodeError):
            return self.json_response(400, {'error':'invalid_round'})

    def end_headers(self):
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        super().end_headers()

if __name__ == '__main__':
    port = int(os.environ.get('PORT','8080'))
    ThreadingHTTPServer(('0.0.0.0',port),Handler).serve_forever()
