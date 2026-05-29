"""
create_sample_db.py
===================
สร้าง history_sample.db ที่มี Mock Data สำหรับ Demo / GitHub
ข้อมูลทั้งหมดเป็นข้อมูลจำลอง ไม่ใช่ข้อมูลจริง

รัน: python create_sample_db.py
ผล : history_sample.db (สร้างในโฟลเดอร์เดียวกัน)
"""

import sqlite3
import json
import os
import random
from datetime import datetime, timedelta

random.seed(42)   # fix seed → ได้ผลเหมือนกันทุกครั้ง

BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
SAMPLE_DB_PATH = os.path.join(BASE_DIR, 'history_sample.db')

# ── เครื่องและรุ่นสำหรับ sample (subset จาก machines.ini จริง) ──────────────
MACHINES = {
    'MS01': 'JP4',
    'MS02': 'JP4',
    'MS03': "JP4evo'17",
    'MS04': "JP4evo'17",
    'MS05': 'JPKevo',
    'MS06': 'MiniLario',
}

# จำนวน head ต่อเครื่อง (ตามรุ่น)
HEADS_PER_MACHINE = {
    'JP4':        8,
    "JP4evo'17":  8,
    'JPKevo':    32,
    'MiniLario': 64,
}

# สีหมึก
COLORS = ['Cyan', 'Magenta', 'Yellow', 'Black',
          'Light Cyan', 'Light Magenta', 'Grey', 'Black']

INK_TYPE = '[U] MS Universal'


# ── helpers ──────────────────────────────────────────────────────────────────

def fake_serial(prefix='SMP'):
    """Serial Number จำลอง เช่น SMP-4821-037"""
    return f'{prefix}-{random.randint(1000, 9999)}-{random.randint(10, 99)}'


def make_snapshot(machine: str, base_dt: datetime) -> dict:
    """
    สร้าง snapshot จำลองของเครื่อง ณ เวลา base_dt
    คืน dict  { 'Installed': [...], 'Uninstalled': [...] }
    """
    model     = MACHINES[machine]
    n_heads   = HEADS_PER_MACHINE[model]
    n_colors  = len(COLORS)

    installed = []
    for i in range(n_heads):
        color     = COLORS[i % n_colors]
        col       = (i // 2) + 1
        row       = (i % 2) + 1
        # ติดตั้งย้อนหลัง 0–180 วัน
        offset_s  = random.randint(0, 180 * 86400)
        install_ts = int(base_dt.timestamp()) - offset_s
        installed.append({
            'Column':   col,
            'Row':      row,
            'Serial':   fake_serial('SMP'),
            'Installed': install_ts,
            'Color':    color,
            'InkType':  INK_TYPE,
        })

    # ประวัติ uninstalled 2–4 รายการต่อเครื่อง
    uninstalled = []
    start_ts = int((base_dt - timedelta(days=365)).timestamp())
    for j in range(random.randint(2, 4)):
        color      = COLORS[j % n_colors]
        install_ts = start_ts + j * 90 * 86400
        remove_ts  = install_ts + random.randint(60, 180) * 86400
        uninstalled.append({
            'Serial':    fake_serial('OLD'),
            'Installed': install_ts,
            'Removed':   remove_ts,
            'Color':     color,
            'InkType':   INK_TYPE,
        })

    return {'Installed': installed, 'Uninstalled': uninstalled}


# ── DB setup ─────────────────────────────────────────────────────────────────

def init_db(conn: sqlite3.Connection):
    c = conn.cursor()
    c.executescript('''
        CREATE TABLE IF NOT EXISTS head_history (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            date      TEXT NOT NULL,
            machine   TEXT NOT NULL,
            data      TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            UNIQUE(date, machine)
        );
        CREATE TABLE IF NOT EXISTS head_snapshots (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            date      TEXT NOT NULL,
            time      TEXT NOT NULL,
            machine   TEXT NOT NULL,
            data      TEXT NOT NULL,
            timestamp TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_snap_machine ON head_snapshots(machine);
        CREATE INDEX IF NOT EXISTS idx_snap_date    ON head_snapshots(date);
    ''')
    conn.commit()


# ── main ─────────────────────────────────────────────────────────────────────

def build_sample_db():
    # ลบ DB เก่า (ถ้ามี) เพื่อ reproducibility
    if os.path.exists(SAMPLE_DB_PATH):
        os.remove(SAMPLE_DB_PATH)

    conn = sqlite3.connect(SAMPLE_DB_PATH)
    init_db(conn)
    c = conn.cursor()

    today = datetime(2026, 5, 28)    # วันที่จำลอง

    # สร้างข้อมูลย้อนหลัง 7 วัน
    snap_count   = 0
    hist_count   = 0

    for day_offset in range(7, -1, -1):          # วันที่ 7 → 0
        snap_dt  = today - timedelta(days=day_offset)
        date_str = snap_dt.strftime('%Y-%m-%d')

        # 2 snapshot ต่อวัน: เช้า (08:00) + บ่าย (14:00)
        for hour in (8, 14):
            snap_time = snap_dt.replace(hour=hour, minute=0, second=0)
            time_str  = snap_time.strftime('%H:%M:%S')
            ts_str    = snap_time.isoformat()

            for machine in MACHINES:
                data      = make_snapshot(machine, snap_time)
                data_json = json.dumps(data, ensure_ascii=False)

                # head_snapshots — ทุก snapshot
                c.execute(
                    '''INSERT INTO head_snapshots (date, time, machine, data, timestamp)
                       VALUES (?, ?, ?, ?, ?)''',
                    (date_str, time_str, machine, data_json, ts_str)
                )
                snap_count += 1

                # head_history — upsert daily summary (ใช้บ่ายเป็นตัวล่าสุดของวัน)
                c.execute(
                    '''INSERT INTO head_history (date, machine, data, timestamp)
                       VALUES (?, ?, ?, ?)
                       ON CONFLICT(date, machine)
                       DO UPDATE SET data=excluded.data, timestamp=excluded.timestamp''',
                    (date_str, machine, data_json, ts_str)
                )
                if hour == 14:
                    hist_count += 1

    conn.commit()
    conn.close()

    print(f'✅  สร้าง {SAMPLE_DB_PATH} สำเร็จ')
    print(f'   head_history  : {hist_count} rows  ({len(MACHINES)} machines × 8 days)')
    print(f'   head_snapshots: {snap_count} rows  ({len(MACHINES)} machines × 8 days × 2 snapshots/day)')
    print()
    print('💡  ใช้แทน history.db ได้เลยเพื่อ demo — ข้อมูลเป็น mock ทั้งหมด')


if __name__ == '__main__':
    build_sample_db()
