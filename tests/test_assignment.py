"""
Tests for the manual calibration assignment added by Custom AMSP.

Run with:  python3 tests/test_assignment.py
(No Siril required — sirilpy is stubbed and the Qt widgets run offscreen.)
"""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from fake_siril import FakeSiril, install_stub_sirilpy  # noqa: E402
from make_fits import build_dataset                     # noqa: E402

install_stub_sirilpy()

import Custom_AMSP as amsp  # noqa: E402


def scan(root: Path) -> list[dict]:
    return [amsp.read_fits_info(p) for p in amsp.collect_fits([str(root)])]


def run_engine(infos, tmp: Path, assignments=None, strict=False, **kw):
    siril = FakeSiril(tmp / 'wd')
    (tmp / 'wd').mkdir(parents=True, exist_ok=True)
    engine = amsp.PreprocessingEngine(
        siril=siril, all_infos=infos, wd=tmp / 'wd',
        output_dir=tmp / 'out', synthetic_bias='', external_darks=None,
        use_disto=False, keep_masters=False,
        assignments=assignments, strict_assignment=strict, **kw)
    engine.run()
    return siril, engine


def calib_args(siril, needle: str) -> list[list[str]]:
    """calibrate calls whose sequence name contains `needle`."""
    return [c for c in siril.calibrate_calls() if needle in c[1]]


def flag_value(call: list[str], flag: str):
    for tok in call:
        tok = tok.strip('"')
        if tok.startswith(flag + '='):
            return tok[len(flag) + 1:]
    return None


class TestSourceEnumeration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix='amsp_src_'))
        cls.infos = scan(build_dataset(cls.tmp / 'data'))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_dataset_is_read_correctly(self):
        kinds = {}
        for fi in self.infos:
            kinds[fi['imgtype']] = kinds.get(fi['imgtype'], 0) + 1
        self.assertEqual(kinds, {'light': 8, 'flat': 5, 'dark': 6, 'bias': 6})

    def test_sources_cover_every_calibration_kind(self):
        sids = {s.sid for s in amsp.enumerate_cal_sources(self.infos)}
        self.assertIn(amsp.subs_sid('bias', amsp.ANY_SESSION), sids)
        self.assertIn(amsp.subs_sid('dark', amsp.ANY_SESSION, '300s'), sids)
        self.assertIn(amsp.subs_sid('flat', '2026-03-25', 'Ha'), sids)

    def test_source_ids_are_date_independent_for_pooled_groups(self):
        """The pooled dark source must not carry a capture date."""
        sid = amsp.subs_sid('dark', amsp.ANY_SESSION, '300s')
        self.assertNotIn('2026', sid)

    def test_enumeration_is_stable_across_calls(self):
        a = [s.sid for s in amsp.enumerate_cal_sources(self.infos)]
        b = [s.sid for s in amsp.enumerate_cal_sources(self.infos)]
        self.assertEqual(a, b)

    def test_external_files_are_offered_as_dark_sources(self):
        ext = self.tmp / 'ext'
        ext.mkdir(exist_ok=True)
        shutil.copy2(self.tmp / 'data' / 'darks' / 'dark_0.fits',
                     ext / 'library_dark.fits')
        srcs = amsp.enumerate_cal_sources(self.infos, ext)
        labels = [s.label for s in srcs if s.kind == 'dark' and s.is_file]
        self.assertTrue(any('library_dark.fits' in x for x in labels), labels)


class TestAutomaticBaseline(unittest.TestCase):
    """The behaviour this fork has to preserve when nothing is assigned."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix='amsp_auto_'))
        cls.infos = scan(build_dataset(cls.tmp / 'data'))
        cls.siril, _ = run_engine(cls.infos, cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_lights_are_calibrated_for_both_nights(self):
        self.assertEqual(len(calib_args(self.siril, 'light_M42_Ha_300s')), 2)

    def test_dark_is_matched_across_sessions(self):
        """Upstream already matches darks by exposure, whatever the night."""
        for call in calib_args(self.siril, 'light_M42_Ha_300s'):
            self.assertIsNotNone(flag_value(call, '-dark'), call)

    def test_flat_from_another_night_is_NOT_found_automatically(self):
        """This is the failure the fork exists to fix — documented, not fixed."""
        for call in calib_args(self.siril, 'light_M42_Ha_300s'):
            self.assertIsNone(flag_value(call, '-flat'), call)


class TestManualAssignment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix='amsp_manual_'))
        cls.infos = scan(build_dataset(cls.tmp / 'data'))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _assign_flat_to_both_nights(self):
        flat_sid = amsp.subs_sid('flat', '2026-03-25', 'Ha')
        dark_sid = amsp.subs_sid('dark', amsp.ANY_SESSION, '300s')
        return {
            'lights': {
                amsp.light_group_key('M42', night, 'Ha', '300s'):
                    {'flat': flat_sid, 'dark': dark_sid}
                for night in ('2026-03-22', '2026-03-23')
            },
            'flats': {},
        }

    def test_assigned_flat_is_applied_to_both_nights(self):
        siril, _ = run_engine(self.infos, self.tmp / 'r1',
                              self._assign_flat_to_both_nights())
        calls = calib_args(siril, 'light_M42_Ha_300s')
        self.assertEqual(len(calls), 2)
        for call in calls:
            flat = flag_value(call, '-flat')
            self.assertIsNotNone(flat, call)
            self.assertIn('Ha', Path(flat).name)

    def test_assigned_dark_is_applied(self):
        siril, _ = run_engine(self.infos, self.tmp / 'r2',
                              self._assign_flat_to_both_nights())
        for call in calib_args(siril, 'light_M42_Ha_300s'):
            self.assertIsNotNone(flag_value(call, '-dark'), call)

    def test_pooled_dark_reuses_the_existing_master(self):
        """All 300 s darks come from one night → no second stack of the same frames."""
        siril, engine = run_engine(self.infos, self.tmp / 'r3',
                                   self._assign_flat_to_both_nights())
        pooled = engine._registry[amsp.subs_sid('dark', amsp.ANY_SESSION, '300s')]
        per_night = engine._registry[amsp.subs_sid('dark', '2026-01-05', '300s')]
        self.assertEqual(pooled, per_night)

    def test_none_disables_a_calibration_kind(self):
        assign = {
            'lights': {
                amsp.light_group_key('M42', '2026-03-22', 'Ha', '300s'):
                    {'dark': amsp.SID_NONE},
            },
            'flats': {},
        }
        siril, _ = run_engine(self.infos, self.tmp / 'r4', assign)
        by_night = {}
        for call in calib_args(siril, 'light_M42_Ha_300s'):
            by_night[flag_value(call, '-dark') is None] = call
        # the assigned night has no dark, the other one still gets the auto match
        self.assertIn(True, by_night)
        self.assertIn(False, by_night)

    def test_strict_mode_applies_only_what_was_assigned(self):
        flat_sid = amsp.subs_sid('flat', '2026-03-25', 'Ha')
        assign = {
            'lights': {
                amsp.light_group_key('M42', '2026-03-22', 'Ha', '300s'):
                    {'flat': flat_sid},
            },
            'flats': {},
        }
        siril, _ = run_engine(self.infos, self.tmp / 'r5', assign, strict=True)
        calls = calib_args(siril, 'light_M42_Ha_300s')
        self.assertEqual(len(calls), 2)
        assigned = [c for c in calls if flag_value(c, '-flat')]
        self.assertEqual(len(assigned), 1)
        # strict mode must not invent a dark for either night
        for call in calls:
            self.assertIsNone(flag_value(call, '-dark'), call)

    def test_missing_source_falls_back_and_warns(self):
        assign = {
            'lights': {
                amsp.light_group_key('M42', '2026-03-22', 'Ha', '300s'):
                    {'dark': 'file:/nowhere/does-not-exist.fit'},
            },
            'flats': {},
        }
        siril, _ = run_engine(self.infos, self.tmp / 'r6', assign)
        self.assertTrue(any('unavailable' in m for m in siril.logs), siril.logs)
        # still calibrated, via the automatic match
        for call in calib_args(siril, 'light_M42_Ha_300s'):
            self.assertIsNotNone(flag_value(call, '-dark'), call)

    def test_flat_group_bias_assignment_is_used(self):
        bias_sid = amsp.subs_sid('bias', amsp.ANY_SESSION)
        assign = {
            'lights': {},
            'flats': {amsp.flat_group_key('2026-03-25', 'Ha'): {'bias': bias_sid}},
        }
        siril, _ = run_engine(self.infos, self.tmp / 'r7', assign)
        flat_calls = calib_args(siril, 'flat_Ha_')
        self.assertTrue(flat_calls)
        for call in flat_calls:
            self.assertIsNotNone(flag_value(call, '-bias'), call)

    def test_flat_group_bias_none_skips_bias(self):
        assign = {
            'lights': {},
            'flats': {amsp.flat_group_key('2026-03-25', 'Ha'):
                      {'bias': amsp.SID_NONE}},
        }
        siril, _ = run_engine(self.infos, self.tmp / 'r8', assign)
        for call in calib_args(siril, 'flat_Ha_'):
            self.assertIsNone(flag_value(call, '-bias'), call)

    def test_assigned_masters_never_pollute_automatic_lookups(self):
        """'cal_*' names must not match the master-bias*/master-dark_* globs."""
        src = amsp.CalSource(sid='x', kind='dark', label='l',
                             session=amsp.ANY_SESSION, exptime=300.0,
                             files=[{'path': Path('/tmp/x.fit')}])
        siril, engine = run_engine(self.infos, self.tmp / 'r9')
        stem = engine._sid_stem(src)
        self.assertTrue(stem.startswith('cal_'))
        self.assertFalse(stem.startswith('master'))


class TestWorkingDirectoryInvariant(unittest.TestCase):
    """
    Every convert/calibrate/stack must run in the directory that holds its
    sequence.  Resolving an assignment can build another master, which cd's
    elsewhere — so the resolution has to happen before the cd, not after.
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix='amsp_cwd_'))
        cls.infos = scan(build_dataset(cls.tmp / 'data'))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_automatic_run_keeps_the_working_directory_correct(self):
        siril, _ = run_engine(self.infos, self.tmp / 'a')
        self.assertEqual(siril.violations, [])

    def test_assigned_run_keeps_the_working_directory_correct(self):
        flat_sid = amsp.subs_sid('flat', '2026-03-25', 'Ha')
        bias_sid = amsp.subs_sid('bias', amsp.ANY_SESSION)
        dark_sid = amsp.subs_sid('dark', amsp.ANY_SESSION, '300s')
        assign = {
            'lights': {
                amsp.light_group_key('M42', night, 'Ha', '300s'):
                    {'flat': flat_sid, 'dark': dark_sid, 'bias': bias_sid}
                for night in ('2026-03-22', '2026-03-23')
            },
            'flats': {amsp.flat_group_key('2026-03-25', 'Ha'): {'bias': bias_sid}},
        }
        siril, _ = run_engine(self.infos, self.tmp / 'b', assign)
        self.assertEqual(siril.violations, [])

    def test_optional_pipeline_steps_still_line_up(self):
        """Background extraction and drizzle change the sequence names."""
        siril, _ = run_engine(self.infos, self.tmp / 'c', use_bkg=True,
                              use_drizzle=True, drizzle_scale=2.0)
        self.assertEqual(siril.violations, [])


class TestKeyHelpers(unittest.TestCase):
    def test_group_keys_survive_a_json_round_trip(self):
        import json
        key = amsp.light_group_key("NGC 7000 | East", '2026-03-22', 'Hα', '300s')
        restored = json.loads(json.dumps({key: {'dark': 'x'}}))
        self.assertIn(key, restored)

    def test_object_and_filter_stay_separable(self):
        a = amsp.light_group_key('A', 'S', 'B', 'E')
        b = amsp.light_group_key('A', 'S', 'B', 'E')
        c = amsp.light_group_key('A', 'S', 'B2', 'E')
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)


class TestAssignmentDialog(unittest.TestCase):
    """Offscreen Qt smoke test of the dialog itself."""

    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])
        cls.tmp = Path(tempfile.mkdtemp(prefix='amsp_ui_'))
        cls.infos = scan(build_dataset(cls.tmp / 'data'))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _dialog(self, assignments=None):
        return amsp.CalibrationAssignmentDialog(
            None, self.infos, None, assignments or {'lights': {}, 'flats': {}},
            '=10*$OFFSET')

    def test_rows_match_the_light_and_flat_groups(self):
        dlg = self._dialog()
        self.assertEqual(len(dlg._light_rows), 2)   # two nights, one filter/exp
        self.assertEqual(len(dlg._flat_rows), 1)    # one flat night/filter

    def test_untouched_dialog_assigns_nothing(self):
        dlg = self._dialog()
        self.assertEqual(dlg.assignments, {'lights': {}, 'flats': {}})

    def test_selecting_a_source_is_returned(self):
        dlg = self._dialog()
        gkey, combos = dlg._light_rows[0]
        sid = amsp.subs_sid('flat', '2026-03-25', 'Ha')
        combos['flat'].setCurrentIndex(combos['flat'].findData(sid))
        self.assertEqual(dlg.assignments['lights'][gkey], {'flat': sid})

    def test_copy_first_row_applies_to_all_rows(self):
        dlg = self._dialog()
        sid = amsp.subs_sid('flat', '2026-03-25', 'Ha')
        _, first = dlg._light_rows[0]
        first['flat'].setCurrentIndex(first['flat'].findData(sid))
        dlg._copy_first_row()
        self.assertEqual(len(dlg.assignments['lights']), 2)
        for _, combos in dlg._light_rows:
            self.assertEqual(combos['flat'].currentData(), sid)

    def test_reset_tab_clears_the_active_tab(self):
        dlg = self._dialog()
        sid = amsp.subs_sid('flat', '2026-03-25', 'Ha')
        _, first = dlg._light_rows[0]
        first['flat'].setCurrentIndex(first['flat'].findData(sid))
        dlg._reset_tab()
        self.assertEqual(dlg.assignments['lights'], {})

    def test_stored_assignment_is_preselected(self):
        sid = amsp.subs_sid('flat', '2026-03-25', 'Ha')
        gkey = amsp.light_group_key('M42', '2026-03-22', 'Ha', '300s')
        dlg = self._dialog({'lights': {gkey: {'flat': sid}}, 'flats': {}})
        found = dict(dlg._light_rows)[gkey]
        self.assertEqual(found['flat'].currentData(), sid)

    def test_unavailable_stored_source_is_kept_not_silently_dropped(self):
        gkey = amsp.light_group_key('M42', '2026-03-22', 'Ha', '300s')
        dlg = self._dialog(
            {'lights': {gkey: {'dark': 'file:/gone/master.fit'}}, 'flats': {}})
        combo = dict(dlg._light_rows)[gkey]['dark']
        self.assertEqual(combo.currentData(), 'file:/gone/master.fit')
        self.assertIn('unavailable', combo.currentText())

    def test_synthetic_bias_is_offered_for_lights_and_flats(self):
        dlg = self._dialog()
        _, light = dlg._light_rows[0]
        _, flat = dlg._flat_rows[0]
        self.assertGreaterEqual(light['bias'].findData(amsp.SID_SYNTHETIC), 0)
        self.assertGreaterEqual(flat['bias'].findData(amsp.SID_SYNTHETIC), 0)

    def test_dark_combo_lists_the_pooled_library(self):
        dlg = self._dialog()
        _, combos = dlg._light_rows[0]
        sid = amsp.subs_sid('dark', amsp.ANY_SESSION, '300s')
        self.assertGreaterEqual(combos['dark'].findData(sid), 0)


class TestMainWindow(unittest.TestCase):
    """Offscreen smoke test of the window wiring and config round trip."""

    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])
        cls.tmp = Path(tempfile.mkdtemp(prefix='amsp_win_'))
        cls.infos = scan(build_dataset(cls.tmp / 'data'))
        # never touch the real user config while testing
        cls._real_cfg = amsp.CONFIG_PATH
        amsp.CONFIG_PATH = cls.tmp / 'config.json'

    @classmethod
    def tearDownClass(cls):
        amsp.CONFIG_PATH = cls._real_cfg
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _window(self):
        win = amsp.FITSOrganizerWindow()
        self.assertTrue(win.initialization_successful)
        return win

    def test_assignment_button_follows_the_loaded_files(self):
        win = self._window()
        self.assertFalse(win.assign_btn.isEnabled())
        win._on_scan_done(list(self.infos))
        self.assertTrue(win.assign_btn.isEnabled())
        win._clear()
        self.assertFalse(win.assign_btn.isEnabled())

    def test_button_label_shows_the_assignment_count(self):
        win = self._window()
        win._on_scan_done(list(self.infos))
        gkey = amsp.light_group_key('M42', '2026-03-22', 'Ha', '300s')
        win._assignments = {'lights': {gkey: {'dark': 'x'}}, 'flats': {}}
        win._update_assign_button()
        self.assertIn('(1)', win.assign_btn.text())

    def test_assignments_survive_a_config_round_trip(self):
        gkey = amsp.light_group_key('M42', '2026-03-22', 'Ha', '300s')
        sid = amsp.subs_sid('flat', '2026-03-25', 'Ha')

        win = self._window()
        win._assignments = {'lights': {gkey: {'flat': sid}}, 'flats': {}}
        win._strict_assignment = True
        win._save_config()

        other = self._window()
        self.assertEqual(other._assignments['lights'][gkey], {'flat': sid})
        self.assertTrue(other._strict_assignment)

    def test_corrupt_assignments_in_config_are_ignored(self):
        amsp.CONFIG_PATH.write_text(
            '{"assignments": {"lights": {"k": "not-a-dict"}, "flats": 42}}')
        win = self._window()
        self.assertEqual(win._assignments, {'lights': {}, 'flats': {}})

    def test_master_flag_override_moves_a_file_between_buckets(self):
        win = self._window()
        win._on_scan_done(list(self.infos))
        target = next(fi for fi in win._all_infos if fi['imgtype'] == 'dark')
        win._selected_paths = lambda: {str(target['path'].resolve())}

        win._change_master_flag(True)
        self.assertTrue(target['is_master'])
        self.assertGreaterEqual(target['stackcnt'], 2)

        win._change_master_flag(False)
        self.assertFalse(target['is_master'])
        self.assertEqual(target['stackcnt'], 0)

    def test_type_override_now_also_applies_to_masters(self):
        win = self._window()
        win._on_scan_done(list(self.infos))
        target = next(fi for fi in win._all_infos if fi['imgtype'] == 'dark')
        win._selected_paths = lambda: {str(target['path'].resolve())}
        win._change_master_flag(True)
        win._change_file_type('flat')
        self.assertEqual(target['imgtype'], 'flat')

    def test_engine_receives_the_assignments_from_the_window(self):
        captured = {}
        real_engine = amsp.PreprocessingEngine

        class Spy(real_engine):
            def __init__(self, **kw):
                captured.update(kw)
                super().__init__(**kw)

            def run(self):
                pass

        win = self._window()
        win._on_scan_done(list(self.infos))
        gkey = amsp.light_group_key('M42', '2026-03-22', 'Ha', '300s')
        win._assignments = {'lights': {gkey: {'dark': 'x'}}, 'flats': {}}
        win._strict_assignment = True
        win._keep_masters = False
        amsp.PreprocessingEngine = Spy
        try:
            win._on_go()
            win._proc_worker.wait(5000)
        finally:
            amsp.PreprocessingEngine = real_engine

        self.assertEqual(captured['assignments']['lights'][gkey], {'dark': 'x'})
        self.assertTrue(captured['strict_assignment'])
        # upstream never forwarded this one, so the checkbox had no effect
        self.assertFalse(captured['keep_masters'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
