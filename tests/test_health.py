import sqlite3
import tempfile
import unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
import health
from db import Database

class Health(unittest.IsolatedAsyncioTestCase):
    async def test_backup_is_consistent_and_retention_is_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'gate.db';db=Database(path);await db.connect();await db.begin(1,42)
            for n in range(10):health.run_backup(str(path),keep=3,when=datetime(2026,10,1,tzinfo=timezone.utc)+timedelta(seconds=n))
            backups=health.list_backups(str(path));self.assertEqual(len(backups),3)
            with sqlite3.connect(backups[-1]) as c:
                self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
                self.assertEqual(c.execute('SELECT COUNT(*) FROM sessions').fetchone()[0],1)
            await db.close()
    async def test_database_failure_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Database(Path(tmp)/'gate.db');await db.connect()
            self.assertTrue((await health.db_probe(db))[0]);await db.close()
            self.assertFalse((await health.db_probe(db))[0])
    def test_errors_have_unique_ids_and_recent_counts(self):
        log=health.ErrorLog(size=2)
        first=log.record('test',ValueError('one'));second=log.record('test',ValueError('two'))
        self.assertNotEqual(first['id'],second['id']);self.assertTrue(first['id'].startswith('RCG-'))
        self.assertEqual(log.since(24),2)
        log.record('test',ValueError('three'));self.assertEqual(len(log.recent()),2);self.assertEqual(log.total,3)
    def test_startup_latency_does_not_report_nan_as_healthy(self):
        self.assertIsNone(health.latency_ms(float('nan')));self.assertIsNone(health.latency_ms(float('inf')))
        self.assertEqual(health.latency_ms(0.1),100)

if __name__=='__main__':unittest.main()
