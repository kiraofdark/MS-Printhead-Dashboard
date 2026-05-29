from flask import Flask, render_template, jsonify, request
import requests
import sqlite3
import json
import configparser
from datetime import datetime, date
import concurrent.futures
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)
DB_PATH = os.path.join(BASE_DIR, 'history.db')
INI_PATH = os.path.join(BASE_DIR, 'machines.ini')


def _safe_json(text, fallback=None):
    """Parse JSON อย่างปลอดภัย — คืน fallback แทน crash ถ้าข้อมูลเสีย"""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return fallback


def load_machines():
    cfg = configparser.ConfigParser()
    cfg.read(INI_PATH, encoding='utf-8')
    if not cfg.has_section('machines'):
        return {}
    machines = {}
    for name, ip in cfg.items('machines'):
        machines[name.upper()] = f'http://{ip}/json/heads'
    return machines


def load_timeout():
    cfg = configparser.ConfigParser()
    cfg.read(INI_PATH, encoding='utf-8')
    return cfg.getint('settings', 'timeout', fallback=5)


def load_port():
    cfg = configparser.ConfigParser()
    cfg.read(INI_PATH, encoding='utf-8')
    return cfg.getint('settings', 'port', fallback=5000)


def load_models():
    cfg = configparser.ConfigParser()
    cfg.read(INI_PATH, encoding='utf-8')
    if not cfg.has_section('models'):
        return {}
    return {k.upper(): v for k, v in cfg.items('models')}


def init_db():
    conn = sqlite3.connect(DB_PATH)
    try:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS head_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            machine TEXT NOT NULL,
            data TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            UNIQUE(date, machine)
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS head_snapshots (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            date      TEXT NOT NULL,
            time      TEXT NOT NULL,
            machine   TEXT NOT NULL,
            data      TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )''')
        c.execute('CREATE INDEX IF NOT EXISTS idx_snap_machine ON head_snapshots(machine)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_snap_date    ON head_snapshots(date)')
        conn.commit()
    finally:
        conn.close()


def get_latest_snapshot(machine):
    """ดึง snapshot ล่าสุดจาก DB สำหรับเครื่องที่ offline"""
    conn = sqlite3.connect(DB_PATH)
    try:
        c = conn.cursor()
        c.execute('''SELECT data, date, time FROM head_snapshots
                     WHERE machine=? ORDER BY date DESC, time DESC LIMIT 1''',
                  (machine,))
        row = c.fetchone()
    finally:
        conn.close()
    if row:
        data = _safe_json(row[0])
        return data, row[1], row[2]
    return None, None, None


def fetch_machine(name, url, timeout=5):
    try:
        response = requests.get(url, timeout=timeout)
        if response.status_code == 200:
            return name, response.json(), None
        return name, None, f'HTTP {response.status_code}'
    except requests.exceptions.ConnectionError:
        return name, None, 'Connection refused'
    except requests.exceptions.Timeout:
        return name, None, 'Timeout'
    except (ValueError, requests.exceptions.JSONDecodeError):
        return name, None, 'Invalid JSON response'
    except Exception as e:
        return name, None, str(e)


def parse_heads(data):
    """Return the Installed list from the printer JSON response."""
    if data is None:
        return []
    if isinstance(data, dict):
        if 'Installed' in data and isinstance(data['Installed'], list):
            return data['Installed']
        # fallback for other possible structures
        for key in ['heads', 'data', 'printheads', 'result', 'installed_heads', 'items']:
            if key in data and isinstance(data[key], list):
                return data[key]
    if isinstance(data, list):
        return data
    return []


def save_history(date_str, machine, raw_data):
    """Save full raw_data (Installed + Uninstalled) keyed by date+machine."""
    conn = sqlite3.connect(DB_PATH)
    try:
        c = conn.cursor()
        c.execute(
            '''INSERT INTO head_history (date, machine, data, timestamp)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(date, machine) DO UPDATE SET data=excluded.data, timestamp=excluded.timestamp''',
            (date_str, machine, json.dumps(raw_data), datetime.now().isoformat())
        )
        conn.commit()
    finally:
        conn.close()


@app.route('/')
def index():
    return render_template('index.html',
                           machines=list(load_machines().keys()),
                           models=load_models())


@app.route('/api/heads')
def api_heads():
    machines = load_machines()   # reload ทุกครั้ง ถ้าแก้ ini ไม่ต้อง restart
    today = date.today().isoformat()
    results = {}

    if not machines:
        return jsonify({})

    timeout = load_timeout()   # อ่าน ini แค่ครั้งเดียวต่อ request
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(machines)) as executor:
        futures = {executor.submit(fetch_machine, name, url, timeout): name
                   for name, url in machines.items()}
        for future in concurrent.futures.as_completed(futures):
            name, data, error = future.result()
            heads = parse_heads(data)
            results[name] = {
                'heads': heads,
                'uninstalled': data.get('Uninstalled', []) if isinstance(data, dict) else [],
                'error': error,
            }
            if heads:
                save_history(today, name, data)

    # Return sorted by machine name
    return jsonify(dict(sorted(results.items())))


@app.route('/api/history')
def api_history():
    date_filter = request.args.get('date')
    machine_filter = request.args.get('machine')

    conn = sqlite3.connect(DB_PATH)
    try:
        c = conn.cursor()
        query = 'SELECT date, machine, data, timestamp FROM head_history WHERE 1=1'
        params = []
        if date_filter:
            query += ' AND date=?'
            params.append(date_filter)
        if machine_filter:
            query += ' AND machine=?'
            params.append(machine_filter)
        query += ' ORDER BY date DESC, machine ASC'
        c.execute(query, params)
        rows = c.fetchall()
    finally:
        conn.close()

    result = []
    for r in rows:
        raw = _safe_json(r[2])
        if raw is None:
            continue
        installed   = raw.get('Installed',   []) if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
        uninstalled = raw.get('Uninstalled', [])  if isinstance(raw, dict) else []
        result.append({
            'date': r[0], 'machine': r[1],
            'data': installed, 'uninstalled': uninstalled,
            'timestamp': r[3],
        })
    return jsonify(result)


@app.route('/api/history/dates')
def api_history_dates():
    conn = sqlite3.connect(DB_PATH)
    try:
        c = conn.cursor()
        c.execute('SELECT DISTINCT date FROM head_history ORDER BY date DESC')
        dates = [r[0] for r in c.fetchall()]
    finally:
        conn.close()
    return jsonify(dates)


@app.route('/history')
def history_page():
    return render_template('history.html',
                           machines=list(load_machines().keys()),
                           models=load_models())


@app.route('/serial')
def serial_page():
    return render_template('serial.html')


@app.route('/serials')
def serials_page():
    return render_template('serials.html')


@app.route('/api/serials')
def api_serials():
    machines = load_machines()
    timeout  = load_timeout()
    serials  = {}   # key = serial.upper()

    if not machines:
        return jsonify([])

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(machines)) as executor:
        futures = {executor.submit(fetch_machine, name, url, timeout): name
                   for name, url in machines.items()}
        for future in concurrent.futures.as_completed(futures):
            name, data, error = future.result()
            if not data:
                continue

            for h in data.get('Installed', []):
                sn = str(h.get('Serial') or '').strip()
                if not sn:
                    continue
                key = sn.upper()
                serials[key] = {
                    'serial':           sn,
                    'color':            h.get('Color', ''),
                    'ink_type':         h.get('InkType', ''),
                    'status':           'installed',
                    'machine':          name,
                    'col':              h.get('Column'),
                    'row':              h.get('Row'),
                    'installed_ts':     h.get('Installed'),
                    'removed_ts':       None,
                    'machines_history': serials.get(key, {}).get('machines_history', set()),
                }
                serials[key]['machines_history'].add(name)

            for h in data.get('Uninstalled', []):
                sn = str(h.get('Serial') or '').strip()
                if not sn:
                    continue
                key = sn.upper()
                existing = serials.get(key)
                hist = existing.get('machines_history', set()) if existing else set()
                hist.add(name)
                # อัปเดตเฉพาะถ้ายังไม่มี หรือถ้าเป็น uninstalled ที่ใหม่กว่า
                if not existing or (existing['status'] == 'uninstalled'
                                    and (h.get('Removed') or 0) > (existing.get('removed_ts') or 0)):
                    serials[key] = {
                        'serial':           sn,
                        'color':            h.get('Color', ''),
                        'ink_type':         h.get('InkType', ''),
                        'status':           'uninstalled',
                        'machine':          name,
                        'col':              None,
                        'row':              None,
                        'installed_ts':     h.get('Installed'),
                        'removed_ts':       h.get('Removed'),
                        'machines_history': hist,
                    }
                else:
                    serials[key]['machines_history'] = hist

    # แปลง set → list ก่อน jsonify
    result = []
    for v in serials.values():
        v['machines_history'] = sorted(v['machines_history'])
        result.append(v)

    result.sort(key=lambda x: (x['status'] != 'installed', x['color'], x['serial']))
    return jsonify(result)


def extract_entries(name, data, q, entries, source='live'):
    """แยก Installed/Uninstalled ที่ตรงกับ q แล้วใส่ลง entries dict"""
    q = q.upper().strip()
    for h in data.get('Uninstalled', []):
        sn = str(h.get('Serial') or '').upper().strip()
        if q in sn or sn in q:
            key = (name, h.get('Installed'), (h.get('Color') or '').lower())
            if key not in entries:
                entries[key] = {
                    'machine':      name,
                    'serial':       str(h.get('Serial') or ''),
                    'color':        h.get('Color', ''),
                    'ink_type':     h.get('InkType', ''),
                    'col':          None,
                    'row':          None,
                    'installed_ts': h.get('Installed'),
                    'removed_ts':   h.get('Removed'),
                    'status':       'uninstalled',
                    'source':       source,
                }
    for h in data.get('Installed', []):
        sn = str(h.get('Serial') or '').upper().strip()
        if q in sn or sn in q:
            key = (name, h.get('Installed'), (h.get('Color') or '').lower())
            entries[key] = {          # live installed ชนะ fallback เสมอ
                'machine':      name,
                'serial':       str(h.get('Serial') or ''),
                'color':        h.get('Color', ''),
                'ink_type':     h.get('InkType', ''),
                'col':          h.get('Column'),
                'row':          h.get('Row'),
                'installed_ts': h.get('Installed'),
                'removed_ts':   None,
                'status':       'installed',
                'source':       source,
            }


def merge_db_uninstalled(name, q, entries):
    """Merge Uninstalled history จากทุก snapshot ของเครื่อง
    ป้องกันข้อมูลหายเมื่อ printer log ถูก reset — live data จะไม่ถูกทับ"""
    conn = sqlite3.connect(DB_PATH)
    try:
        c = conn.cursor()
        c.execute('SELECT data FROM head_snapshots WHERE machine=? ORDER BY date ASC, time ASC',
                  (name,))
        rows = c.fetchall()
    finally:
        conn.close()

    q_upper = q.upper().strip()
    for row in rows:
        data = _safe_json(row[0])
        if data is None:
            continue
        for h in data.get('Uninstalled', []):
            sn = str(h.get('Serial') or '').upper().strip()
            if q_upper in sn or sn in q_upper:
                key = (name, h.get('Installed'), (h.get('Color') or '').lower())
                if key not in entries:   # ไม่ทับ live data
                    entries[key] = {
                        'machine':      name,
                        'serial':       str(h.get('Serial') or ''),
                        'color':        h.get('Color', ''),
                        'ink_type':     h.get('InkType', ''),
                        'col':          None,
                        'row':          None,
                        'installed_ts': h.get('Installed'),
                        'removed_ts':   h.get('Removed'),
                        'status':       'uninstalled',
                        'source':       'db_history',
                    }


@app.route('/api/serial')
def api_serial():
    q = request.args.get('q', '').upper().strip()
    if not q:
        return jsonify({'serial': '', 'entries': [], 'error': 'กรุณาระบุ Serial No.'})
    if len(q) < 2:
        return jsonify({'serial': q, 'entries': [], 'error': 'กรุณาระบุอย่างน้อย 2 ตัวอักษร'})

    machines = load_machines()
    timeout  = load_timeout()
    entries  = {}
    offline  = []

    if not machines:
        return jsonify({'serial': q, 'entries': [], 'offline': [], 'fallback_used': {}})

    # Step 1: live fetch
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(machines)) as executor:
        futures = {executor.submit(fetch_machine, name, url, timeout): name
                   for name, url in machines.items()}
        for future in concurrent.futures.as_completed(futures):
            name, data, error = future.result()
            if data:
                extract_entries(name, data, q, entries, source='live')
            else:
                offline.append(name)

    # Step 2: DB fallback สำหรับ Installed[] ของเครื่องที่ offline
    fallback_info = {}
    for name in offline:
        fb_data, fb_date, fb_time = get_latest_snapshot(name)
        if fb_data:
            extract_entries(name, fb_data, q, entries, source='db')
            fallback_info[name] = f'{fb_date} {fb_time}'

    # Step 3: merge Uninstalled history จาก snapshot ทุกอัน (ทุกเครื่อง)
    # ป้องกันข้อมูลหายกรณี printer log reset
    for name in machines:
        merge_db_uninstalled(name, q, entries)

    result = sorted(entries.values(), key=lambda x: x['installed_ts'] or 0)
    return jsonify({
        'serial':        q,
        'entries':       result,
        'offline':       offline,
        'fallback_used': fallback_info,
    })


if __name__ == '__main__':
    init_db()
    app.run(debug=False, host='0.0.0.0', port=load_port())
