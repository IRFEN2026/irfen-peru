"""Regression for the August replay/400-newest eviction loop."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from archive_imerg_early_probe import retain_recent_and_replay, retention_summary

CASE = {'case_id': 'finite-research-replay', 'target_id': 'event',
        'start_utc': '2026-08-15T10:00:00Z', 'end_utc': '2026-08-16T10:00:00Z'}


def row(stamp, tid='live', value=0.0):
    return {'time_utc': stamp.isoformat(), 'granule': stamp.isoformat()+'.HDF5',
            'targets': [{'target_id': tid, 'accum_30min_mm': value}]}


class ReplayRetentionTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 8, 15, 10, tzinfo=timezone.utc)
        now = datetime(2026, 9, 21, tzinfo=timezone.utc)
        self.live = [row(now + timedelta(minutes=30*i)) for i in range(410)]

    def test_preserves_requested_old_rows_instead_of_repeated_eviction(self):
        replay = [row(self.start + timedelta(minutes=30*i), 'event', i/10) for i in range(6)]
        result = retain_recent_and_replay(self.live + replay, [CASE], 400)
        self.assertEqual(len(result), 406)
        self.assertEqual(result[:6], replay)
        self.assertEqual(result[-400:], self.live[-400:])
        self.assertEqual(retention_summary(result, [CASE], 400)['retained_replay_granules'], 6)

    def test_repeated_backfill_makes_finite_progress(self):
        records = self.live
        for batch in range(8):
            incoming = [row(self.start + timedelta(minutes=30*i), 'event')
                        for i in range(batch*6, (batch+1)*6)]
            records = retain_recent_and_replay(records + incoming, [CASE], 400)
            self.assertEqual(sum(r['targets'][0]['target_id']=='event' for r in records), (batch+1)*6)
        self.assertEqual(len(records), 448)

    def test_no_case_means_unchanged_hot_tail_policy(self):
        self.assertEqual(retain_recent_and_replay(self.live, [], 400), self.live[-400:])

    def test_wrong_target_outside_interval_and_missing_value_not_pinned(self):
        invalid = [row(self.start, 'wrong'), row(self.start-timedelta(minutes=30), 'event'),
                   row(self.start+timedelta(days=1), 'event'), row(self.start, 'event', None),
                   row(self.start, 'event', float('nan'))]
        self.assertEqual(retain_recent_and_replay(self.live+invalid, [CASE], 400), self.live[-400:])

    def test_exact_half_open_last_slot_is_retained(self):
        last = row(self.start+timedelta(hours=23,minutes=30), 'event', 1.2)
        self.assertIn(last, retain_recent_and_replay(self.live+[last], [CASE], 400))

    def test_replay_budget_is_bounded_and_rejects_excess_versions(self):
        repeated = [dict(row(self.start,'event'), granule=str(i)) for i in range(49)]
        with self.assertRaises(ValueError):
            retain_recent_and_replay(self.live+repeated, [CASE], 400)

    def test_retention_does_not_modify_values(self):
        record = row(self.start,'event',2.345)
        result = retain_recent_and_replay(self.live+[record], [CASE], 400)
        self.assertIs(result[0], record)
        self.assertEqual(result[0]['targets'][0]['accum_30min_mm'], 2.345)


if __name__ == '__main__':
    unittest.main()
