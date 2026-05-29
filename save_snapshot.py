"""
Standalone snapshot saver — รันโดย Windows Task Scheduler ทุก 2 ชม.
บันทึกข้อมูล Printhead จากทุกเครื่องลง SQLite DB
"""
import requests
import sqlite3
import json
import configparser
import concurrent.futures
from datetime import datetime
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, 'history.db')
INI_PATH = os.path.join(BASE_DIR, 'machines.ini')
LOG_PATH = os.path.join(BASE_DIR, 'snapshot.log')
MAX_LOG_LINES = 500   # ตัด log เก่าทิ้งถ้าเกิน


def log(msg):
    ts   = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f'[{ts}] {msg}'
    print(line)
    try:
        lines = []
        if os.path.exists(LOG_PATH):
            with open(LOG_PATH, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        lines.append(line + '\n')
        if len(lines) > MAX_LOG_LINES:
            lines = lines[-MAX_LOG_LINES:]
        with open(LOG_PATH, 'w', encoding='utf-8') as f:
            f.writelines(lines)
    except Exception:
        pass


def load_config():
    cfg = configparser.ConfigParser()
    cfg.read(INI_PATH, encoding='utf-8')
    machines = {k.upper(): f'http://{v}/json/heads' for k, v in cfg.items('machines')}
    timeout  = cfg.getint('settings', 'timeout', fallback=5)
    return machines, timeout


def fetch_machine(name, url, timeout):
    try:
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 200:
            return name, resp.json(), None
        return name, None, f'HTTP {resp.status_code}'
    except requests.exceptions.ConnectionError:
        return name, None, 'Connection refused'
    except requests.exceptions.Timeout:
        return name, None, 'Timeout'
    except Exception as e:
        return name, None, str(e)


def init_db(conn):
    c = conn.cursor()
    c.execute('BEGIN')
    c.execute('''CREATE TABLE IF NOT EXISTS head_history (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        date      TEXT NOT NULL,
        machine   TEXT NOT NULL,
        data      TEXT NOT NULL,
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
    c.execute('COMMIT')



def is_duplicate_snapshot(c, machine, data_json, date_str):
    """ไม่บันทึกถ้า snapshot ล่าสุดของวันนี้มีข้อมูลเหมือนกันทุกอย่าง"""
    c.execute('''SELECT data FROM head_snapshots
                 WHERE machine=? AND date=?
                 ORDER BY time DESC LIMIT 1''', (machine, date_str))
    row = c.fetchone()
    return row is not None and row[0] == data_json


def save_to_db(conn, now, machine, data):
    date_str  = now.strftime('%Y-%m-%d')
    time_str  = now.strftime('%H:%M:%S')
    ts        = now.isoformat()
    data_json = json.dumps(data, ensure_ascii=False)
    c = conn.cursor()

    # BEGIN IMMEDIATE locks the DB so check+insert is atomic (no race condition)
    c.execute('BEGIN IMMEDIATE')
    try:
        # Daily summary (upsert — ใช้กับหน้า History)
        c.execute('''INSERT INTO head_history (date, machine, data, timestamp)
                     VALUES (?, ?, ?, ?)
                     ON CONFLICT(date, machine)
                     DO UPDATE SET data=excluded.data, timestamp=excluded.timestamp''',
                  (date_str, machine, data_json, ts))

        # Append snapshot — บันทึกเฉพาะถ้าข้อมูลเปลี่ยนจาก snapshot ล่าสุด
        is_dup = is_duplicate_snapshot(c, machine, data_json, date_str)

        if not is_dup:
            c.execute('''INSERT INTO head_snapshots (date, time, machine, data, timestamp)
                         VALUES (?, ?, ?, ?, ?)''',
                      (date_str, time_str, machine, data_json, ts))
        c.execute('COMMIT')
        return 'skipped' if is_dup else 'saved'
    except Exception:
        c.execute('ROLLBACK')
        raise


def run():
    log('=' * 50)
    log('Snapshot started')
    machines, timeout = load_config()

    # isolation_level=None = autocommit — ทำให้ BEGIN IMMEDIATE ทำงานได้
    conn = sqlite3.connect(DB_PATH, isolation_level=None, timeout=30)
    try:
        init_db(conn)
        now = datetime.now()

        success, skipped, failed = 0, 0, []

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(machines)) as executor:
            futures = {executor.submit(fetch_machine, name, url, timeout): name
                       for name, url in machines.items()}
            for future in concurrent.futures.as_completed(futures):
                name, data, error = future.result()
                if data and data.get('Installed'):
                    heads  = len(data.get('Installed', []))
                    result = save_to_db(conn, now, name, data)
                    if result == 'saved':
                        log(f'  SAVED   {name}: {heads} heads')
                        success += 1
                    else:
                        log(f'  SKIP    {name}: no change')
                        skipped += 1
                else:
                    failed.append(name)
                    log(f'  FAIL    {name}: {error}')
    finally:
        conn.close()

    log(f'Done — saved:{success}  skipped:{skipped}  failed:{len(failed)} {failed or ""}')
    log('=' * 50)
    return success, skipped, failed


if __name__ == '__main__':
    run()
