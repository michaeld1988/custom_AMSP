"""
Tests for capture-series detection.

Built around the dataset from the bug report: two flat runs — one at 18:54 on
2026-08-14, one at 06:12 on 2026-08-15 — that both fall into the noon-to-noon
night 2026-08-14 and were therefore treated as a single set.

Run with:  python3 tests/test_series.py
"""

import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from fake_siril import FakeSiril, install_stub_sirilpy   # noqa: E402
from make_fits import write_frame                        # noqa: E402

install_stub_sirilpy()

import Custom_AMSP as amsp  # noqa: E402


def scan(root: Path) -> list[dict]:
    return [amsp.read_fits_info(p) for p in amsp.collect_fits([str(root)])]


def build_report_dataset(root: Path) -> Path:
    """
    Reproduces the reported layout:

      lights  night 2026-08-13  (31 frames, 13th 21:00 → 14th 02:00)
      lights  night 2026-08-14  (41 frames, 14th 21:00 → 15th 02:00)
      flats   30 frames on 2026-08-14 18:54  (evening, 5.7 s)
      flats   30 frames on 2026-08-15 06:12  (next morning, 5.8 s)

    Both flat runs share the night key 2026-08-14.
    """
    root.mkdir(parents=True, exist_ok=True)

    # real time arithmetic: these runs cross midnight
    for tag, start, count, step in (('A', '2026-08-13T21:00:00', 31, 10),
                                    ('B', '2026-08-14T21:00:00', 41, 7)):
        t0 = datetime.fromisoformat(start)
        for i in range(count):
            stamp = (t0 + timedelta(minutes=i * step)).isoformat()
            write_frame(root / 'lights' / f'light_{tag}_{i:03d}.fits', 'LIGHT',
                        stamp, 300.0, obj='NGC7000')

    for i in range(30):
        write_frame(root / 'flats' / f'Flat_20260814_{i:04d}_5.7s.fits', 'FLAT',
                    f'2026-08-14T18:{54 + i // 6:02d}:{(i * 10) % 60:02d}', 5.7)
    for i in range(30):
        write_frame(root / 'flats' / f'Flat_20260815_{i:04d}_5.8s.fits', 'FLAT',
                    f'2026-08-15T06:{12 + i // 6:02d}:{(i * 10) % 60:02d}', 5.8)

    return root


class TestClustering(unittest.TestCase):
    def _frames(self, *stamps):
        return [{'date_obs': s} for s in stamps]

    def test_a_continuous_run_stays_one_series(self):
        frames = self._frames('2026-08-14T18:54:00', '2026-08-14T18:55:00',
                              '2026-08-14T18:56:00')
        self.assertEqual(len(amsp.cluster_by_time(frames)), 1)

    def test_the_reported_eleven_hour_gap_splits(self):
        frames = self._frames('2026-08-14T18:54:00', '2026-08-15T06:12:00')
        self.assertEqual(len(amsp.cluster_by_time(frames)), 2)

    def test_the_gap_threshold_is_honoured(self):
        frames = self._frames('2026-08-14T18:00:00', '2026-08-14T21:00:00')
        self.assertEqual(len(amsp.cluster_by_time(frames, 2.0)), 2)
        self.assertEqual(len(amsp.cluster_by_time(frames, 4.0)), 1)

    def test_frames_are_sorted_before_splitting(self):
        frames = self._frames('2026-08-15T06:12:00', '2026-08-14T18:54:00',
                              '2026-08-14T18:55:00')
        batches = amsp.cluster_by_time(frames)
        self.assertEqual([len(b) for b in batches], [2, 1])

    def test_undated_frames_form_their_own_series_and_are_never_lost(self):
        frames = self._frames('2026-08-14T18:54:00', '') + [{'date_obs': 'kaputt'}]
        batches = amsp.cluster_by_time(frames)
        self.assertEqual(sum(len(b) for b in batches), 3)
        self.assertEqual(len(batches), 2)

    def test_empty_input_gives_no_series(self):
        self.assertEqual(amsp.cluster_by_time([]), [])


class TestIntervalGap(unittest.TestCase):
    def _dt(self, s):
        return datetime.fromisoformat(s)

    def test_overlapping_intervals_have_no_gap(self):
        self.assertEqual(
            amsp.interval_gap_hours(self._dt('2026-08-14T21:00:00'),
                                    self._dt('2026-08-15T02:00:00'),
                                    self._dt('2026-08-14T22:00:00'),
                                    self._dt('2026-08-14T23:00:00')), 0.0)

    def test_gap_is_measured_edge_to_edge_in_both_directions(self):
        night = (self._dt('2026-08-14T21:00:00'), self._dt('2026-08-15T02:00:00'))
        after = amsp.interval_gap_hours(*night,
                                        self._dt('2026-08-15T06:00:00'),
                                        self._dt('2026-08-15T06:10:00'))
        before = amsp.interval_gap_hours(*night,
                                         self._dt('2026-08-14T18:00:00'),
                                         self._dt('2026-08-14T18:10:00'))
        self.assertAlmostEqual(after, 4.0)
        self.assertAlmostEqual(before, 2 + 50 / 60)   # 21:00 minus 18:10

    def test_missing_timestamps_give_none(self):
        self.assertIsNone(amsp.interval_gap_hours(
            None, None, self._dt('2026-08-14T18:00:00'),
            self._dt('2026-08-14T18:10:00')))


class ReportCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])
        cls.tmp = Path(tempfile.mkdtemp(prefix='amsp_series_'))
        cls.data = build_report_dataset(cls.tmp / 'data')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def infos(self):
        return scan(self.data)


class TestReportedDataset(ReportCase):
    def test_both_flat_runs_really_do_share_one_night_key(self):
        """The premise: this is why they were treated as one set."""
        flats = [fi for fi in self.infos() if fi['imgtype'] == 'flat']
        self.assertEqual({fi['session'] for fi in flats}, {'2026-08-14'})
        self.assertEqual(len(flats), 60)

    def test_lights_are_split_over_two_nights(self):
        lights = [fi for fi in self.infos() if fi['imgtype'] == 'light']
        self.assertEqual({fi['session'] for fi in lights},
                         {'2026-08-13', '2026-08-14'})

    def test_the_flats_are_offered_as_two_separate_series(self):
        sources = amsp.enumerate_cal_sources(self.infos())
        series = [s for s in sources if s.kind == 'flat' and s.is_batch]
        self.assertEqual(len(series), 2)
        self.assertEqual(sorted(len(s.files) for s in series), [30, 30])

    def test_series_labels_name_the_actual_times(self):
        sources = amsp.enumerate_cal_sources(self.infos())
        labels = [s.label for s in sources if s.kind == 'flat' and s.is_batch]
        self.assertTrue(any('2026-08-14 18:54' in x for x in labels), labels)
        self.assertTrue(any('2026-08-15 06:12' in x for x in labels), labels)

    def test_the_whole_night_entry_is_still_offered(self):
        """Series are added, nothing is taken away."""
        sources = amsp.enumerate_cal_sources(self.infos())
        whole = [s for s in sources
                 if s.kind == 'flat' and not s.is_batch and not s.is_file]
        self.assertEqual(len(whole), 1)
        self.assertEqual(len(whole[0].files), 60)

    def test_series_ids_are_distinct_and_carry_the_start_time(self):
        sources = amsp.enumerate_cal_sources(self.infos())
        sids = [s.sid for s in sources if s.kind == 'flat' and s.is_batch]
        self.assertEqual(len(set(sids)), 2)
        self.assertIn(amsp.batch_sid('flat', '2026-08-14T18:54', 'nofilter'), sids)
        self.assertIn(amsp.batch_sid('flat', '2026-08-15T06:12', 'nofilter'), sids)

    def test_series_ids_are_stable_across_runs(self):
        a = [s.sid for s in amsp.enumerate_cal_sources(self.infos())]
        b = [s.sid for s in amsp.enumerate_cal_sources(self.infos())]
        self.assertEqual(a, b)

    def test_a_single_run_produces_no_series_entries(self):
        """Simple projects must see exactly the list they saw before."""
        one = self.tmp / 'one_run'
        for i in range(10):
            write_frame(one / f'flat_{i}.fits', 'FLAT',
                        f'2026-09-01T18:{i:02d}:00', 3.0)
        sources = amsp.enumerate_cal_sources(scan(one))
        self.assertFalse([s for s in sources if s.is_batch])


class TestWizardWithReportedDataset(ReportCase):
    def wizard(self):
        return amsp.CalibrationWizard(None, self.infos(), None, '')

    def test_both_series_are_selectable_per_night(self):
        w = self.wizard()
        w._goto(2)
        self.assertEqual(len(w._night_rows), 2)
        for _, combos in w._night_rows:
            cb = combos['flat']
            offered = [cb.itemData(i) for i in range(cb.count())]
            self.assertIn(amsp.batch_sid('flat', '2026-08-14T18:54', 'nofilter'),
                          offered)
            self.assertIn(amsp.batch_sid('flat', '2026-08-15T06:12', 'nofilter'),
                          offered)

    def test_the_suggestion_is_a_series_not_the_whole_night(self):
        w = self.wizard()
        w._goto(2)
        for _, combos in w._night_rows:
            sid = combos['flat'].currentData()
            self.assertTrue(sid.startswith('batch:flat:'), sid)

    def test_the_nearer_series_wins_for_the_second_night(self):
        """Night 14→15: the evening run is 2 h away, the morning run 4 h."""
        w = self.wizard()
        w._goto(2)
        picked = dict((n, c['flat'].currentData()) for n, c in w._night_rows)
        self.assertEqual(picked['2026-08-14'],
                         amsp.batch_sid('flat', '2026-08-14T18:54', 'nofilter'))

    def test_the_first_night_borrows_a_flat_series_from_the_next_evening(self):
        """
        Night 13→14 has no flats of its own.  The nearest series is the
        evening of the 14th, ~17 h later — the "flats the next evening" case,
        which stays inside the 24 h default but shows up once it is tightened.
        """
        w = self.wizard()
        w._goto(2)
        rows = dict(w._night_rows)
        src = {s.sid: s for s in w._sources}[rows['2026-08-13']['flat'].currentData()]
        gap = w._gap_to_night(src, '2026-08-13')
        self.assertGreater(gap, 12.0)
        self.assertLess(gap, 24.0)

        w._goto(3)
        self.assertFalse([m for _, n, m in w._validate()
                          if n == '2026-08-13' and m.startswith('Flat-Serie')])
        w._spin_date_tol.setValue(12.0)
        flagged = [m for _, n, m in w._validate()
                   if n == '2026-08-13' and m.startswith('Flat-Serie')]
        self.assertTrue(flagged, 'tightening the tolerance must surface it')
        self.assertIn('entfernt', flagged[0])

    def test_a_flat_series_two_days_later_warns_at_the_default(self):
        """The user's rule: a flat from the 15th is not for the 13th→14th."""
        extra = self.tmp / 'late_flats'
        for i in range(10):
            write_frame(extra / f'Flat_20260816_{i:04d}.fits', 'FLAT',
                        f'2026-08-16T19:{i:02d}:00', 5.7)
        w = amsp.CalibrationWizard(None, self.infos() + scan(extra), None, '')
        w._goto(2)
        rows = dict(w._night_rows)
        cb = rows['2026-08-13']['flat']
        late = amsp.subs_sid('flat', '2026-08-16', 'nofilter')
        idx = cb.findData(late)
        self.assertGreaterEqual(idx, 0, 'the late flats must be selectable')
        cb.setCurrentIndex(idx)

        w._goto(3)
        flagged = [m for _, n, m in w._validate()
                   if n == '2026-08-13' and m.startswith('Flat-Serie')]
        self.assertTrue(flagged, w._validate())
        self.assertIn('Tage', flagged[0])

    def test_the_second_night_is_not_flagged(self):
        w = self.wizard()
        w._goto(3)
        warnings = [m for s, n, m in w._validate()
                    if n == '2026-08-14' and m.startswith('Flat-Serie')]
        self.assertFalse(warnings, warnings)

    def test_each_night_can_be_given_its_own_series(self):
        w = self.wizard()
        w._goto(2)
        evening = amsp.batch_sid('flat', '2026-08-14T18:54', 'nofilter')
        morning = amsp.batch_sid('flat', '2026-08-15T06:12', 'nofilter')
        rows = dict(w._night_rows)
        rows['2026-08-13']['flat'].setCurrentIndex(
            rows['2026-08-13']['flat'].findData(evening))
        rows['2026-08-14']['flat'].setCurrentIndex(
            rows['2026-08-14']['flat'].findData(morning))

        result = w.assignments
        gk13 = amsp.light_group_key('NGC7000', '2026-08-13', amsp.NO_FILTER, '300s')
        gk14 = amsp.light_group_key('NGC7000', '2026-08-14', amsp.NO_FILTER, '300s')
        self.assertEqual(result['lights'][gk13]['flat'], evening)
        self.assertEqual(result['lights'][gk14]['flat'], morning)

    def test_the_table_shows_the_distance_per_night(self):
        w = self.wizard()
        w._goto(2)
        cells = [w._assign_table.item(r, 6).text()
                 for r in range(w._assign_table.rowCount())]
        self.assertEqual(len(cells), 2)
        self.assertTrue(all('h' in c for c in cells), cells)
        # night 13 borrows a series ~17 h away, night 14 has one ~2 h away
        self.assertNotEqual(cells[0], cells[1])

    def test_the_distance_updates_when_another_series_is_picked(self):
        w = self.wizard()
        w._goto(2)
        before = w._assign_table.item(0, 6).text()
        cb = dict(w._night_rows)['2026-08-13']['flat']
        morning = amsp.batch_sid('flat', '2026-08-15T06:12', 'nofilter')
        cb.setCurrentIndex(cb.findData(morning))
        self.assertNotEqual(w._assign_table.item(0, 6).text(), before)

    def test_step_two_lists_both_series(self):
        w = self.wizard()
        w._goto(1)
        spans = [w._calib_table.item(r, 1).text()
                 for r in range(w._calib_table.rowCount())]
        self.assertTrue(any('2026-08-14 18:54' in s for s in spans), spans)
        self.assertTrue(any('2026-08-15 06:12' in s for s in spans), spans)


class TestEngineWithSeries(ReportCase):
    def test_two_series_produce_two_different_master_flats(self):
        infos = self.infos()
        w = amsp.CalibrationWizard(None, infos, None, '')
        w._goto(2)
        evening = amsp.batch_sid('flat', '2026-08-14T18:54', 'nofilter')
        morning = amsp.batch_sid('flat', '2026-08-15T06:12', 'nofilter')
        rows = dict(w._night_rows)
        rows['2026-08-13']['flat'].setCurrentIndex(
            rows['2026-08-13']['flat'].findData(evening))
        rows['2026-08-14']['flat'].setCurrentIndex(
            rows['2026-08-14']['flat'].findData(morning))
        assignments = w.assignments

        tmp = self.tmp / 'engine'
        (tmp / 'wd').mkdir(parents=True, exist_ok=True)
        siril = FakeSiril(tmp / 'wd')
        engine = amsp.PreprocessingEngine(
            siril=siril, all_infos=w.infos, wd=tmp / 'wd',
            output_dir=tmp / 'out', synthetic_bias='', external_darks=None,
            use_disto=False, keep_masters=False, assignments=assignments)
        engine.run()

        self.assertEqual(siril.violations, [])
        flats_used = set()
        for call in siril.calibrate_calls():
            if 'light_' not in call[1]:
                continue
            for tok in call:
                tok = tok.strip('"')
                if tok.startswith('-flat='):
                    flats_used.add(Path(tok[len('-flat='):]).name)
        self.assertEqual(len(flats_used), 2, flats_used)

    def test_series_masters_do_not_collide_on_disk(self):
        sources = amsp.enumerate_cal_sources(self.infos())
        series = [s for s in sources if s.kind == 'flat' and s.is_batch]
        tmp = self.tmp / 'stems'
        (tmp / 'wd').mkdir(parents=True, exist_ok=True)
        engine = amsp.PreprocessingEngine(
            siril=FakeSiril(tmp / 'wd'), all_infos=self.infos(), wd=tmp / 'wd',
            output_dir=tmp / 'out', synthetic_bias='', external_darks=None)
        stems = {engine._sid_stem(s) for s in series}
        self.assertEqual(len(stems), 2, stems)
        for stem in stems:
            self.assertTrue(stem.startswith('cal_'), stem)


class TestTreeShowsSeries(ReportCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._real_cfg = amsp.CONFIG_PATH
        amsp.CONFIG_PATH = cls.tmp / 'tree_config.json'

    @classmethod
    def tearDownClass(cls):
        amsp.CONFIG_PATH = cls._real_cfg
        super().tearDownClass()

    def _labels(self, item, out):
        out.append(item.text(0))
        for i in range(item.childCount()):
            self._labels(item.child(i), out)

    def test_the_tree_shows_two_flat_series(self):
        win = amsp.FITSOrganizerWindow()
        win._on_scan_done(self.infos())
        labels: list[str] = []
        for i in range(win.tree.topLevelItemCount()):
            self._labels(win.tree.topLevelItem(i), labels)
        series = [x for x in labels if x.startswith('🕘')]
        self.assertEqual(len(series), 2, series)
        self.assertTrue(any('18:54' in x for x in series), series)
        self.assertTrue(any('06:12' in x for x in series), series)

    def test_no_series_level_when_frames_form_one_run(self):
        one = self.tmp / 'tree_one'
        for i in range(6):
            write_frame(one / f'bias_{i}.fits', 'BIAS',
                        f'2026-09-02T20:{i:02d}:00', 0.0)
        win = amsp.FITSOrganizerWindow()
        win._on_scan_done(scan(one))
        labels: list[str] = []
        for i in range(win.tree.topLevelItemCount()):
            self._labels(win.tree.topLevelItem(i), labels)
        self.assertFalse([x for x in labels if x.startswith('🕘')], labels)


if __name__ == '__main__':
    unittest.main(verbosity=2)
