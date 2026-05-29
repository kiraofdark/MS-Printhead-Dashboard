"""
Unit Tests — MS Printhead Dashboard
รัน: python test_unit.py -v
"""
import unittest
import unittest.mock as mock
import sqlite3
import json
import configparser
import tempfile
import os
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Fixtures ──────────────────────────────────────────────────
SAMPLE_INSTALLED = [
    {'Column': 1, 'Row': 1, 'Serial': 'AAA1-0001', 'Installed': 1627380641,
     'Color': 'Cyan',    'InkType': '[U] MS Universal'},
    {'Column': 2, 'Row': 1, 'Serial': 'AAA1-0001', 'Installed': 1627380641,
     'Color': 'Magenta', 'InkType': '[U] MS Universal'},
    {'Column': 3, 'Row': 1, 'Serial': 'BBB2-0002', 'Installed': 1743529382,
     'Color': 'Yellow',  'InkType': '[U] MS Universal'},
]
SAMPLE_UNINSTALLED = [
    {'Serial': 'OLD1-0001', 'Installed': 1474526593, 'Removed': 1627380000,
     'Color': 'Cyan',    'InkType': '[U] MS Universal'},
    {'Serial': 'OLD2-0002', 'Installed': 1500000000, 'Removed': 1743529000,
     'Color': 'Yellow',  'InkType': '[U] MS Universal'},
    {'Serial': 'SPEC-*001', 'Installed': 1600000000, 'Removed': 1700000000,
     'Color': 'Grey',    'InkType': '[U] MS Universal'},
]
SAMPLE_DATA = {'Installed': SAMPLE_INSTALLED, 'Uninstalled': SAMPLE_UNINSTALLED}

def make_ini(machines=None, timeout=5, port=5000, models=None):
    """สร้าง temp ini file สำหรับทดสอบ"""
    cfg = configparser.ConfigParser()
    cfg['machines'] = machines or {'MS01': '192.168.1.1', 'MS02': '192.168.1.2'}
    cfg['settings'] = {'timeout': str(timeout), 'port': str(port)}
    if models:
        cfg['models'] = models
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.ini',
                                     delete=False, encoding='utf-8')
    cfg.write(tmp)
    tmp.close()
    return tmp.name

def make_db():
    """สร้าง in-memory SQLite สำหรับทดสอบ"""
    conn = sqlite3.connect(':memory:')
    c = conn.cursor()
    c.execute('''CREATE TABLE head_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT, machine TEXT, data TEXT, timestamp TEXT,
        UNIQUE(date, machine))''')
    c.execute('''CREATE TABLE head_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT, time TEXT, machine TEXT, data TEXT, timestamp TEXT)''')
    c.execute('CREATE INDEX idx_m ON head_snapshots(machine)')
    conn.commit()
    return conn


# ══════════════════════════════════════════════════════════════
# 1. load_config / load_machines / load_models
# ══════════════════════════════════════════════════════════════
class TestLoadConfig(unittest.TestCase):

    def setUp(self):
        self.ini = make_ini(
            machines={'ms01': '192.168.1.1', 'ms02': '192.168.1.2'},
            timeout=8, port=8080,
            models={'ms01': 'JP4', 'ms02': 'JPKevo'}
        )

    def tearDown(self):
        os.unlink(self.ini)

    def _load(self):
        import save_snapshot as ss
        cfg = configparser.ConfigParser()
        cfg.read(self.ini, encoding='utf-8')
        return cfg

    def test_machine_keys_are_uppercased(self):
        cfg = self._load()
        machines = {k.upper(): v for k, v in cfg.items('machines')}
        self.assertIn('MS01', machines)
        self.assertIn('MS02', machines)
        self.assertNotIn('ms01', machines)

    def test_machine_url_format(self):
        cfg = self._load()
        machines = {k.upper(): f'http://{v}/json/heads'
                    for k, v in cfg.items('machines')}
        self.assertEqual(machines['MS01'], 'http://192.168.1.1/json/heads')

    def test_timeout_value(self):
        cfg = self._load()
        self.assertEqual(cfg.getint('settings', 'timeout', fallback=5), 8)

    def test_port_value(self):
        cfg = self._load()
        self.assertEqual(cfg.getint('settings', 'port', fallback=5000), 8080)

    def test_models_section(self):
        cfg = self._load()
        models = {k.upper(): v for k, v in cfg.items('models')}
        self.assertEqual(models['MS01'], 'JP4')
        self.assertEqual(models['MS02'], 'JPKevo')

    def test_missing_models_section_returns_empty(self):
        ini2 = make_ini()   # no models section
        cfg = configparser.ConfigParser()
        cfg.read(ini2, encoding='utf-8')
        models = {k.upper(): v for k, v in cfg.items('models')} \
                 if cfg.has_section('models') else {}
        self.assertEqual(models, {})
        os.unlink(ini2)


# ══════════════════════════════════════════════════════════════
# 2. fetch_machine
# ══════════════════════════════════════════════════════════════
class TestFetchMachine(unittest.TestCase):

    def _fetch(self, name, url, timeout=5):
        import save_snapshot as ss
        return ss.fetch_machine(name, url, timeout)

    @mock.patch('requests.get')
    def test_success_returns_json(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = SAMPLE_DATA
        name, data, error = self._fetch('MS01', 'http://x/json/heads')
        self.assertEqual(name, 'MS01')
        self.assertEqual(data, SAMPLE_DATA)
        self.assertIsNone(error)

    @mock.patch('requests.get', side_effect=__import__('requests').exceptions.ConnectionError)
    def test_connection_refused(self, _):
        name, data, error = self._fetch('MS01', 'http://x/json/heads')
        self.assertIsNone(data)
        self.assertEqual(error, 'Connection refused')

    @mock.patch('requests.get', side_effect=__import__('requests').exceptions.Timeout)
    def test_timeout(self, _):
        name, data, error = self._fetch('MS01', 'http://x/json/heads')
        self.assertIsNone(data)
        self.assertEqual(error, 'Timeout')

    @mock.patch('requests.get')
    def test_http_500(self, mock_get):
        mock_get.return_value.status_code = 500
        name, data, error = self._fetch('MS01', 'http://x/json/heads')
        self.assertIsNone(data)
        self.assertEqual(error, 'HTTP 500')

    @mock.patch('requests.get')
    def test_invalid_json_raises_caught(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.side_effect = ValueError('Bad JSON')
        name, data, error = self._fetch('MS01', 'http://x/json/heads')
        self.assertIsNone(data)
        self.assertIsNotNone(error)


# ══════════════════════════════════════════════════════════════
# 3. parse_heads (จาก app.py)
# ══════════════════════════════════════════════════════════════
class TestParseHeads(unittest.TestCase):

    def _parse(self, data):
        # inline implementation ตรงกับ app.py
        if data is None:
            return []
        if isinstance(data, dict):
            if 'Installed' in data and isinstance(data['Installed'], list):
                return data['Installed']
            for key in ['heads', 'data', 'printheads', 'result']:
                if key in data and isinstance(data[key], list):
                    return data[key]
        if isinstance(data, list):
            return data
        return []

    def test_installed_key(self):
        result = self._parse(SAMPLE_DATA)
        self.assertEqual(result, SAMPLE_INSTALLED)

    def test_list_input(self):
        result = self._parse(SAMPLE_INSTALLED)
        self.assertEqual(result, SAMPLE_INSTALLED)

    def test_none_returns_empty(self):
        self.assertEqual(self._parse(None), [])

    def test_empty_dict_returns_empty(self):
        self.assertEqual(self._parse({}), [])

    def test_fallback_key_heads(self):
        data = {'heads': SAMPLE_INSTALLED}
        self.assertEqual(self._parse(data), SAMPLE_INSTALLED)

    def test_fallback_key_data(self):
        data = {'data': SAMPLE_INSTALLED}
        self.assertEqual(self._parse(data), SAMPLE_INSTALLED)

    def test_installed_key_takes_priority(self):
        data = {'Installed': SAMPLE_INSTALLED, 'heads': []}
        self.assertEqual(self._parse(data), SAMPLE_INSTALLED)


# ══════════════════════════════════════════════════════════════
# 4. is_duplicate_snapshot
# ══════════════════════════════════════════════════════════════
class TestDuplicateGuard(unittest.TestCase):

    def setUp(self):
        self.conn = make_db()

    def tearDown(self):
        self.conn.close()

    def _is_dup(self, machine, data_json, date_str):
        import save_snapshot as ss
        return ss.is_duplicate_snapshot(self.conn.cursor(), machine,
                                        data_json, date_str)

    def _insert(self, machine, data_json, date='2026-05-12', time='10:00:00'):
        self.conn.execute(
            'INSERT INTO head_snapshots (date,time,machine,data,timestamp) VALUES (?,?,?,?,?)',
            (date, time, machine, data_json, datetime.now().isoformat()))
        self.conn.commit()

    def test_no_previous_is_not_duplicate(self):
        self.assertFalse(self._is_dup('MS01', '{"x":1}', '2026-05-12'))

    def test_same_data_is_duplicate(self):
        self._insert('MS01', '{"x":1}')
        self.assertTrue(self._is_dup('MS01', '{"x":1}', '2026-05-12'))

    def test_different_data_is_not_duplicate(self):
        self._insert('MS01', '{"x":1}')
        self.assertFalse(self._is_dup('MS01', '{"x":2}', '2026-05-12'))

    def test_different_machine_is_not_duplicate(self):
        self._insert('MS01', '{"x":1}')
        self.assertFalse(self._is_dup('MS02', '{"x":1}', '2026-05-12'))

    def test_different_date_is_not_duplicate(self):
        self._insert('MS01', '{"x":1}', date='2026-05-11')
        self.assertFalse(self._is_dup('MS01', '{"x":1}', '2026-05-12'))


# ══════════════════════════════════════════════════════════════
# 5. save_to_db
# ══════════════════════════════════════════════════════════════
class TestSaveToDB(unittest.TestCase):

    def setUp(self):
        self.conn = make_db()
        self.now  = datetime(2026, 5, 12, 10, 0, 0)

    def tearDown(self):
        self.conn.close()

    def _save(self, machine, data):
        import save_snapshot as ss
        return ss.save_to_db(self.conn, self.now, machine, data)

    def test_first_save_returns_saved(self):
        result = self._save('MS01', SAMPLE_DATA)
        self.assertEqual(result, 'saved')

    def test_same_data_returns_skipped(self):
        self._save('MS01', SAMPLE_DATA)
        result = self._save('MS01', SAMPLE_DATA)
        self.assertEqual(result, 'skipped')

    def test_changed_data_returns_saved(self):
        self._save('MS01', SAMPLE_DATA)
        changed = dict(SAMPLE_DATA)
        changed['Installed'] = SAMPLE_INSTALLED[:2]   # เหลือ 2 heads
        result = self._save('MS01', changed)
        self.assertEqual(result, 'saved')

    def test_saves_to_head_history(self):
        self._save('MS01', SAMPLE_DATA)
        c = self.conn.cursor()
        c.execute('SELECT COUNT(*) FROM head_history WHERE machine=?', ('MS01',))
        self.assertEqual(c.fetchone()[0], 1)

    def test_saves_to_head_snapshots(self):
        self._save('MS01', SAMPLE_DATA)
        c = self.conn.cursor()
        c.execute('SELECT COUNT(*) FROM head_snapshots WHERE machine=?', ('MS01',))
        self.assertEqual(c.fetchone()[0], 1)

    def test_head_history_upsert(self):
        self._save('MS01', SAMPLE_DATA)
        changed = dict(SAMPLE_DATA, Installed=SAMPLE_INSTALLED[:1])
        self._save('MS01', changed)
        c = self.conn.cursor()
        c.execute('SELECT COUNT(*) FROM head_history WHERE machine=?', ('MS01',))
        self.assertEqual(c.fetchone()[0], 1)   # ยังมีแค่ 1 row (upsert)

    def test_multiple_machines_saved_independently(self):
        self._save('MS01', SAMPLE_DATA)
        self._save('MS02', SAMPLE_DATA)
        c = self.conn.cursor()
        c.execute('SELECT COUNT(*) FROM head_snapshots')
        self.assertEqual(c.fetchone()[0], 2)


# ══════════════════════════════════════════════════════════════
# 6. extract_entries (จาก app.py)
# ══════════════════════════════════════════════════════════════
class TestExtractEntries(unittest.TestCase):

    def _extract(self, name, data, q, source='live'):
        entries = {}
        # inline ตรงกับ app.py extract_entries logic
        q = q.upper().strip()
        for h in data.get('Uninstalled', []):
            sn = h.get('Serial', '').upper().strip()
            if q in sn or sn in q:
                key = (name, h.get('Installed'), (h.get('Color') or '').lower())
                if key not in entries:
                    entries[key] = {
                        'machine': name, 'serial': h.get('Serial', ''),
                        'color': h.get('Color', ''), 'ink_type': h.get('InkType', ''),
                        'col': None, 'row': None,
                        'installed_ts': h.get('Installed'),
                        'removed_ts': h.get('Removed'),
                        'status': 'uninstalled', 'source': source,
                    }
        for h in data.get('Installed', []):
            sn = h.get('Serial', '').upper().strip()
            if q in sn or sn in q:
                key = (name, h.get('Installed'), (h.get('Color') or '').lower())
                entries[key] = {
                    'machine': name, 'serial': h.get('Serial', ''),
                    'color': h.get('Color', ''), 'ink_type': h.get('InkType', ''),
                    'col': h.get('Column'), 'row': h.get('Row'),
                    'installed_ts': h.get('Installed'),
                    'removed_ts': None,
                    'status': 'installed', 'source': source,
                }
        return entries

    def test_exact_serial_match(self):
        entries = self._extract('MS01', SAMPLE_DATA, 'AAA1-0001')
        self.assertEqual(len(entries), 2)   # Cyan + Magenta

    def test_partial_serial_match(self):
        entries = self._extract('MS01', SAMPLE_DATA, 'AAA1')
        self.assertGreater(len(entries), 0)

    def test_partial_matches_uninstalled(self):
        entries = self._extract('MS01', SAMPLE_DATA, 'OLD1')
        self.assertEqual(len(entries), 1)
        e = list(entries.values())[0]
        self.assertEqual(e['status'], 'uninstalled')

    def test_installed_overwrites_uninstalled_same_key(self):
        """ถ้า Serial เดียวกัน Installed ต้องชนะ Uninstalled"""
        data = {
            'Installed':   [{'Column': 1, 'Row': 1, 'Serial': 'X-001',
                             'Installed': 100, 'Color': 'Cyan', 'InkType': ''}],
            'Uninstalled': [{'Serial': 'X-001', 'Installed': 100,
                             'Removed': 200, 'Color': 'Cyan', 'InkType': ''}],
        }
        entries = self._extract('MS01', data, 'X-001')
        # key เดียวกัน (MS01, 100) → Installed ชนะ
        e = list(entries.values())[0]
        self.assertEqual(e['status'], 'installed')

    def test_special_chars_in_serial(self):
        entries = self._extract('MS01', SAMPLE_DATA, 'SPEC-*001')
        self.assertEqual(len(entries), 1)

    def test_no_match_returns_empty(self):
        entries = self._extract('MS01', SAMPLE_DATA, 'ZZZ-9999')
        self.assertEqual(entries, {})

    def test_case_insensitive(self):
        entries_upper = self._extract('MS01', SAMPLE_DATA, 'AAA1-0001')
        entries_lower = self._extract('MS01', SAMPLE_DATA, 'aaa1-0001')
        self.assertEqual(len(entries_upper), len(entries_lower))

    def test_empty_data(self):
        entries = self._extract('MS01', {}, 'AAA1')
        self.assertEqual(entries, {})

    def test_source_tag_preserved(self):
        entries = self._extract('MS01', SAMPLE_DATA, 'OLD1', source='db')
        e = list(entries.values())[0]
        self.assertEqual(e['source'], 'db')


# ══════════════════════════════════════════════════════════════
# 7. get_latest_snapshot
# ══════════════════════════════════════════════════════════════
class TestGetLatestSnapshot(unittest.TestCase):

    def setUp(self):
        self.conn = make_db()

    def tearDown(self):
        self.conn.close()

    def _insert(self, machine, data, date, time):
        self.conn.execute(
            'INSERT INTO head_snapshots (date,time,machine,data,timestamp) VALUES (?,?,?,?,?)',
            (date, time, machine, json.dumps(data), datetime.now().isoformat()))
        self.conn.commit()

    def _get(self, machine):
        c = self.conn.cursor()
        c.execute('''SELECT data, date, time FROM head_snapshots
                     WHERE machine=? ORDER BY date DESC, time DESC LIMIT 1''',
                  (machine,))
        row = c.fetchone()
        if row:
            return json.loads(row[0]), row[1], row[2]
        return None, None, None

    def test_returns_none_when_no_data(self):
        data, date, time = self._get('MS99')
        self.assertIsNone(data)

    def test_returns_latest_snapshot(self):
        self._insert('MS01', {'v': 1}, '2026-05-10', '10:00:00')
        self._insert('MS01', {'v': 2}, '2026-05-12', '08:00:00')
        self._insert('MS01', {'v': 3}, '2026-05-12', '10:00:00')
        data, date, time = self._get('MS01')
        self.assertEqual(data['v'], 3)
        self.assertEqual(date, '2026-05-12')
        self.assertEqual(time, '10:00:00')

    def test_does_not_mix_machines(self):
        self._insert('MS01', {'machine': 'MS01'}, '2026-05-12', '10:00:00')
        self._insert('MS02', {'machine': 'MS02'}, '2026-05-12', '12:00:00')
        data, _, _ = self._get('MS01')
        self.assertEqual(data['machine'], 'MS01')

    def test_prefers_later_time_same_date(self):
        self._insert('MS01', {'v': 'morning'}, '2026-05-12', '06:00:00')
        self._insert('MS01', {'v': 'evening'}, '2026-05-12', '18:00:00')
        data, _, _ = self._get('MS01')
        self.assertEqual(data['v'], 'evening')


# ══════════════════════════════════════════════════════════════
# 8. Log Reset — merge_db_uninstalled
# ══════════════════════════════════════════════════════════════
class TestLogResetMerge(unittest.TestCase):
    """ทดสอบ merge_db_uninstalled: ข้อมูลต้องอยู่หลัง printer log reset"""

    PRE_RESET = {
        'Installed':   [{'Column': 1, 'Row': 1, 'Serial': 'NEW-001',
                          'Installed': 200, 'Color': 'Cyan', 'InkType': ''}],
        'Uninstalled': [{'Serial': 'OLD-001', 'Installed': 100,
                          'Removed': 180, 'Color': 'Cyan', 'InkType': ''}],
    }
    POST_RESET = {
        'Installed':   [{'Column': 1, 'Row': 1, 'Serial': 'NEW-001',
                          'Installed': 200, 'Color': 'Cyan', 'InkType': ''}],
        'Uninstalled': [],   # log ถูก reset
    }

    def setUp(self):
        self.conn = make_db()
        self.conn.execute(
            'INSERT INTO head_snapshots (date,time,machine,data,timestamp) VALUES (?,?,?,?,?)',
            ('2025-01-01', '08:00:00', 'MS01', json.dumps(self.PRE_RESET), ''))
        self.conn.execute(
            'INSERT INTO head_snapshots (date,time,machine,data,timestamp) VALUES (?,?,?,?,?)',
            ('2025-01-02', '08:00:00', 'MS01', json.dumps(self.POST_RESET), ''))
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def _merge(self, machine, q, entries):
        """inline merge_db_uninstalled using test DB"""
        q_upper = q.upper().strip()
        c = self.conn.cursor()
        c.execute('SELECT data FROM head_snapshots WHERE machine=? ORDER BY date ASC, time ASC',
                  (machine,))
        for row in c.fetchall():
            data = json.loads(row[0])
            for h in data.get('Uninstalled', []):
                sn = h.get('Serial', '').upper().strip()
                if q_upper in sn or sn in q_upper:
                    key = (machine, h.get('Installed'), (h.get('Color') or '').lower())
                    if key not in entries:
                        entries[key] = {
                            'machine':      machine,
                            'serial':       h.get('Serial', ''),
                            'color':        h.get('Color', ''),
                            'ink_type':     h.get('InkType', ''),
                            'col':          None, 'row': None,
                            'installed_ts': h.get('Installed'),
                            'removed_ts':   h.get('Removed'),
                            'status':       'uninstalled',
                            'source':       'db_history',
                        }

    def test_old_serial_found_after_reset(self):
        """serial เก่าต้องหาได้จาก snapshot ก่อน reset"""
        entries = {}
        self._merge('MS01', 'OLD-001', entries)
        self.assertEqual(len(entries), 1)
        e = list(entries.values())[0]
        self.assertEqual(e['status'], 'uninstalled')
        self.assertEqual(e['source'], 'db_history')

    def test_live_data_not_overwritten_by_db_history(self):
        """live entry ต้องไม่ถูก db_history ทับ"""
        live_key = ('MS01', 100, 'cyan')
        entries = {live_key: {'source': 'live', 'status': 'installed'}}
        self._merge('MS01', 'OLD-001', entries)
        self.assertEqual(entries[live_key]['source'], 'live')

    def test_no_duplicate_from_multiple_snapshots(self):
        """snapshot หลายอัน ต้องไม่ทำให้ entry ซ้ำ"""
        entries = {}
        self._merge('MS01', 'OLD-001', entries)
        self.assertEqual(len(entries), 1)

    def test_new_serial_not_in_merge(self):
        """merge ดูแค่ Uninstalled[] — Installed[] ต้องไม่ถูก merge"""
        entries = {}
        self._merge('MS01', 'NEW-001', entries)
        self.assertEqual(len(entries), 0)

    def test_empty_db_returns_nothing(self):
        """DB ว่าง ต้องไม่ error"""
        empty_conn = make_db()
        q_upper = 'OLD-001'
        c = empty_conn.cursor()
        c.execute('SELECT data FROM head_snapshots WHERE machine=?', ('MS99',))
        self.assertEqual(c.fetchall(), [])
        empty_conn.close()

    def test_partial_query_finds_old_serial(self):
        """ค้นหาแบบ partial ต้องเจอ serial เก่าด้วย"""
        entries = {}
        self._merge('MS01', 'OLD', entries)
        self.assertGreater(len(entries), 0)

    def test_wrong_machine_returns_nothing(self):
        """ค้นหาเครื่องที่ไม่มี snapshot ต้องได้ entries ว่าง"""
        entries = {}
        self._merge('MS99', 'OLD-001', entries)
        self.assertEqual(len(entries), 0)


# ══════════════════════════════════════════════════════════════
# 9. Timestamp conversion
# ══════════════════════════════════════════════════════════════
class TestTimestamp(unittest.TestCase):

    def _ts_to_date(self, ts):
        if not ts:
            return '—'
        if isinstance(ts, (int, float)):
            d = datetime.fromtimestamp(ts)
            return f'{d.day:02d}/{d.month:02d}/{str(d.year)[2:]}'
        return str(ts)

    def test_known_timestamp(self):
        # 1627380641 = 27 Jul 2021
        result = self._ts_to_date(1627380641)
        self.assertIn('07', result)   # month
        self.assertIn('21', result)   # year

    def test_zero_returns_dash(self):
        self.assertEqual(self._ts_to_date(0), '—')

    def test_none_returns_dash(self):
        self.assertEqual(self._ts_to_date(None), '—')

    def test_string_passthrough(self):
        self.assertEqual(self._ts_to_date('01/01/25'), '01/01/25')


# ══════════════════════════════════════════════════════════════
# Runner
# ══════════════════════════════════════════════════════════════
if __name__ == '__main__':
    loader = unittest.TestLoader()
    suite  = unittest.TestSuite()

    test_classes = [
        TestLoadConfig, TestFetchMachine, TestParseHeads,
        TestDuplicateGuard, TestSaveToDB, TestExtractEntries,
        TestGetLatestSnapshot, TestLogResetMerge, TestTimestamp,
    ]
    for cls in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
