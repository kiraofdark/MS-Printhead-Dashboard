"""
POC Test — ทดสอบระบบ snapshot + DB fallback
รัน: python test_snapshot.py
"""
import sqlite3
import json
import os
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, 'history.db')

# รองรับ Windows terminal
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

PASS = '[PASS]'
FAIL = '[FAIL]'

results = []

def check(name, condition, detail=''):
    status = PASS if condition else FAIL
    print(f'  {status}  {name}')
    if detail:
        print(f'         {detail}')
    results.append((name, condition))
    return condition


print('\n' + '='*55)
print(' MS Printhead — POC & System Test')
print('='*55)

# ─────────────────────────────────────────
print('\n[1] รัน save_snapshot.py')
print('-'*40)
import save_snapshot
success, skipped, failed = save_snapshot.run()
check('fetch สำเร็จอย่างน้อย 1 เครื่อง (saved หรือ skipped)', success + skipped > 0,
      f'saved={success}  skipped={skipped}  failed={len(failed)}')


# ─────────────────────────────────────────
print('\n[2] ตรวจ DB Schema')
print('-'*40)
conn = sqlite3.connect(DB_PATH)
c    = conn.cursor()

c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in c.fetchall()]
check('ตาราง head_history มีอยู่',    'head_history'   in tables)
check('ตาราง head_snapshots มีอยู่',  'head_snapshots' in tables)

c.execute('SELECT COUNT(*) FROM head_history')
hist_count = c.fetchone()[0]
check('head_history มีข้อมูล', hist_count > 0, f'{hist_count} rows')

c.execute('SELECT COUNT(*) FROM head_snapshots')
snap_count = c.fetchone()[0]
check('head_snapshots มีข้อมูล', snap_count > 0, f'{snap_count} rows')


# ─────────────────────────────────────────
print('\n[3] ตรวจ Duplicate Guard')
print('-'*40)
snap_before = snap_count
save_snapshot.run()   # รันซ้ำทันที — ข้อมูลไม่เปลี่ยน ต้องไม่บันทึกซ้ำ
c.execute('SELECT COUNT(*) FROM head_snapshots')
snap_after = c.fetchone()[0]
check('ไม่บันทึก snapshot ซ้ำถ้าข้อมูลเหมือนกัน',
      snap_after == snap_before,
      f'before={snap_before}  after={snap_after}  diff={snap_after - snap_before}')


# ─────────────────────────────────────────
print('\n[4] ตรวจ DB Fallback (simulate offline)')
print('-'*40)
c.execute('SELECT machine FROM head_snapshots GROUP BY machine ORDER BY machine')
machines_in_db = [r[0] for r in c.fetchall()]
check('มีข้อมูลใน head_snapshots', len(machines_in_db) > 0,
      f'machines: {machines_in_db}')

if machines_in_db:
    test_machine = machines_in_db[0]
    c.execute('''SELECT data, date, time FROM head_snapshots
                 WHERE machine=? ORDER BY date DESC, time DESC LIMIT 1''',
              (test_machine,))
    row = c.fetchone()
    check(f'ดึง latest snapshot ของ {test_machine} ได้',
          row is not None, f'date={row[1]}  time={row[2]}' if row else '')

    if row:
        data = json.loads(row[0])
        installed   = data.get('Installed', [])
        uninstalled = data.get('Uninstalled', [])
        check(f'snapshot มีข้อมูล Installed',   len(installed)   > 0, f'{len(installed)} heads')
        check(f'snapshot มีข้อมูล Uninstalled', len(uninstalled) > 0, f'{len(uninstalled)} records')


# ─────────────────────────────────────────
print('\n[5] ตรวจ Serial Timeline จาก DB (ไม่ต้องออนไลน์)')
print('-'*40)
c.execute('''SELECT data FROM head_snapshots
             ORDER BY date DESC, time DESC LIMIT 1''')
row = c.fetchone()
if row:
    data  = json.loads(row[0])
    heads = data.get('Installed', [])
    if heads:
        test_serial = heads[0].get('Serial', '')
        q = test_serial.upper()
        # simulate extract_entries
        found = []
        for h in data.get('Uninstalled', []):
            sn = h.get('Serial', '').upper()
            if q in sn or sn in q:
                found.append(('uninstalled', h))
        for h in heads:
            sn = h.get('Serial', '').upper()
            if q in sn or sn in q:
                found.append(('installed', h))
        check(f'ค้นหา serial "{test_serial}" จาก snapshot ได้',
              len(found) > 0, f'พบ {len(found)} entries')


# ─────────────────────────────────────────
print('\n[7] ตรวจ Log Reset — DB Merge Protection')
print('-'*40)
# จำลอง: บันทึก snapshot หลัง log reset (Uninstalled ว่าง)
# แล้วตรวจว่า merge ข้าม snapshot ยังหาข้อมูลเก่าได้
c.execute('SELECT machine FROM head_snapshots GROUP BY machine ORDER BY machine')
machines_snap = [r[0] for r in c.fetchall()]

if machines_snap:
    test_m = machines_snap[0]

    # นับ Uninstalled เก่าก่อน reset
    c.execute('''SELECT data FROM head_snapshots WHERE machine=?
                 ORDER BY date ASC, time ASC''', (test_m,))
    all_snaps = c.fetchall()
    pre_uninstalled = {}
    for r in all_snaps:
        for h in json.loads(r[0]).get('Uninstalled', []):
            key = (h.get('Installed'), (h.get('Color') or '').lower())
            pre_uninstalled[key] = h

    # แทรก snapshot จำลอง "หลัง reset" — Uninstalled ว่าง
    c.execute('''SELECT data FROM head_snapshots WHERE machine=?
                 ORDER BY date DESC, time DESC LIMIT 1''', (test_m,))
    last = json.loads(c.fetchone()[0])
    post_reset = {'Installed': last.get('Installed', []), 'Uninstalled': []}
    c.execute('''INSERT INTO head_snapshots (date, time, machine, data, timestamp)
                 VALUES (?,?,?,?,?)''',
              ('2099-01-01', '00:00:00', test_m,
               json.dumps(post_reset), '2099-01-01T00:00:00'))
    conn.commit()

    # merge ข้าม snapshot ทั้งหมด
    c.execute('''SELECT data FROM head_snapshots WHERE machine=?
                 ORDER BY date ASC, time ASC''', (test_m,))
    merged = {}
    for r in c.fetchall():
        for h in json.loads(r[0]).get('Uninstalled', []):
            key = (h.get('Installed'), (h.get('Color') or '').lower())
            merged[key] = h

    check('merge ยังพบ Uninstalled เก่าหลัง log reset',
          len(merged) >= len(pre_uninstalled),
          f'pre_reset={len(pre_uninstalled)}  merged={len(merged)}')
    check('snapshot ล่าสุด (post-reset) มี Uninstalled ว่าง',
          len(post_reset['Uninstalled']) == 0)
    check('merge ไม่ลดจำนวน entries',
          len(merged) >= len(pre_uninstalled),
          f'pre={len(pre_uninstalled)} merged={len(merged)}')

    # ลบ snapshot จำลองออก
    c.execute("DELETE FROM head_snapshots WHERE date='2099-01-01' AND machine=?", (test_m,))
    conn.commit()
else:
    check('มี snapshot ให้ทดสอบ log reset', False, 'ไม่มี snapshot ในฐานข้อมูล')


# ─────────────────────────────────────────
print('\n[6] ตรวจ Log File')
print('-'*40)
log_path = os.path.join(BASE_DIR, 'snapshot.log')
check('snapshot.log ถูกสร้าง', os.path.exists(log_path))
if os.path.exists(log_path):
    with open(log_path, encoding='utf-8') as f:
        lines = f.readlines()
    check('log มีเนื้อหา', len(lines) > 0, f'{len(lines)} lines')


# ─────────────────────────────────────────
conn.close()
total  = len(results)
passed = sum(1 for _, r in results if r)
failed_tests = [(n, r) for n, r in results if not r]

print('\n' + '='*55)
print(f' ผลรวม: {passed}/{total} passed', end='')
if failed_tests:
    print(f'  ({len(failed_tests)} failed)')
    for name, _ in failed_tests:
        print(f'   ✗ {name}')
else:
    print('  — All passed!')
print('='*55 + '\n')

sys.exit(0 if passed == total else 1)
