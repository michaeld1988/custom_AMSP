"""
Tests for the optional calibration wizard.

Run with:  python3 tests/test_wizard.py
(No Siril required — sirilpy is stubbed and Qt runs offscreen.)
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

from fake_siril import install_stub_sirilpy   # noqa: E402
from make_fits import build_dataset, write_frame  # noqa: E402

install_stub_sirilpy()

import Custom_AMSP as amsp  # noqa: E402


def scan(root: Path) -> list[dict]:
    return [amsp.read_fits_info(p) for p in amsp.collect_fits([str(root)])]


class TestDarkFlatNameDetection(unittest.TestCase):
    """The file-name rule the user specified, spelled out case by case."""

    def test_all_requested_spellings_match(self):
        for name in ('darkflat_001.fits', 'flatdark_001.fits',
                     'dark_flat_001.fits', 'flat_dark_001.fits',
                     'dark-flat-001.fits', 'flat-dark-001.fits',
                     'M42_DarkFlat_300s.fit', 'session1.FLAT_DARK.fits',
                     'dark flat 01.fits', 'dark.flat.01.fits'):
            with self.subTest(name=name):
                self.assertTrue(amsp.name_suggests_darkflat(name), name)

    def test_plain_darks_and_flats_do_not_match(self):
        for name in ('dark_001.fits', 'flat_001.fits', 'masterdark.fit',
                     'light_M42_Ha.fits', 'bias_01.fits',
                     'darker_flatfield_note.txt'.replace('.txt', '.fits')):
            with self.subTest(name=name):
                self.assertFalse(amsp.name_suggests_darkflat(name), name)

    def test_only_the_file_name_counts_not_the_folder(self):
        """A folder called dark_flats must not retype the darks inside it."""
        self.assertFalse(
            amsp.name_suggests_darkflat('/data/dark_flats/dark_001.fits'))
        self.assertTrue(
            amsp.name_suggests_darkflat('/data/darks/dark_flat_001.fits'))

    def test_retyping_records_the_previous_type_and_is_reversible(self):
        infos = [{'name': 'dark_flat_1.fits', 'imgtype': 'dark',
                  'is_master': False},
                 {'name': 'dark_1.fits', 'imgtype': 'dark', 'is_master': False}]
        changed = amsp.apply_darkflat_name_hints(infos)
        self.assertEqual(len(changed), 1)
        self.assertEqual(infos[0]['imgtype'], 'darkflat')
        self.assertEqual(infos[0]['imgtype_before_hint'], 'dark')
        self.assertEqual(infos[1]['imgtype'], 'dark')

    def test_lights_and_masters_are_never_retyped(self):
        infos = [{'name': 'darkflat_light.fits', 'imgtype': 'light',
                  'is_master': False},
                 {'name': 'master_dark_flat.fit', 'imgtype': 'dark',
                  'is_master': True}]
        self.assertEqual(amsp.apply_darkflat_name_hints(infos), [])
        self.assertEqual(infos[0]['imgtype'], 'light')
        self.assertEqual(infos[1]['imgtype'], 'dark')


class TestSessionDelta(unittest.TestCase):
    def test_the_users_example(self):
        """A flat from 15.08 is two days off the night of the 13th→14th."""
        self.assertEqual(amsp.session_delta_days('2026-08-13', '2026-08-15'), 2)

    def test_next_afternoon_is_one_day(self):
        self.assertEqual(amsp.session_delta_days('2026-08-13', '2026-08-14'), 1)

    def test_same_night_is_zero_and_earlier_is_negative(self):
        self.assertEqual(amsp.session_delta_days('2026-08-13', '2026-08-13'), 0)
        self.assertEqual(amsp.session_delta_days('2026-08-13', '2026-08-11'), -2)

    def test_unknown_date_returns_none(self):
        self.assertIsNone(amsp.session_delta_days('2026-08-13', '????-??-??'))


class WizardCase(unittest.TestCase):
    """Shared Qt application and dataset."""

    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])
        cls.tmp = Path(tempfile.mkdtemp(prefix='amsp_wiz_'))
        cls.data = build_dataset(cls.tmp / 'data')
        cls.infos = scan(cls.data)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def wizard(self, infos=None, synthetic=''):
        # fresh dicts per test: the wizard mutates imgtype in place
        src = infos if infos is not None else scan(self.data)
        return amsp.CalibrationWizard(None, src, None, synthetic)


class TestWizardPages(WizardCase):
    def test_starts_on_page_one(self):
        w = self.wizard()
        self.assertEqual(w._stack.currentIndex(), 0)
        self.assertIn('Lights', w._step_lbl.text())

    def test_lights_page_lists_every_light_group(self):
        w = self.wizard()
        w._refresh_lights_page()
        # dataset: M42/Ha/300s on two nights
        self.assertEqual(w._lights_table.rowCount(), 2)
        nights = {w._lights_table.item(r, 0).text()
                  for r in range(w._lights_table.rowCount())}
        self.assertEqual(nights, {'2026-03-22', '2026-03-23'})

    def test_lights_page_reports_the_nights_it_found(self):
        w = self.wizard()
        self.assertIn('2 Nacht', w._lights_status.text().replace('Nächten', 'Nacht'))

    def test_calibration_page_groups_by_type(self):
        w = self.wizard()
        w._goto(1)
        rows = [w._calib_table.item(r, 0).text()
                for r in range(w._calib_table.rowCount())]
        self.assertTrue(any('Bias' in r for r in rows), rows)
        self.assertTrue(any('Darks' in r for r in rows), rows)
        self.assertTrue(any('Flats' in r for r in rows), rows)

    def test_assign_page_has_one_row_per_night(self):
        w = self.wizard()
        w._goto(2)
        self.assertEqual(len(w._night_rows), 2)
        self.assertEqual([n for n, _ in w._night_rows],
                         ['2026-03-22', '2026-03-23'])

    def test_next_is_blocked_until_lights_are_loaded(self):
        w = amsp.CalibrationWizard(None, [], None, '')
        self.assertFalse(w._btn_next.isEnabled())
        self.assertFalse(w._btn_finish.isEnabled())

    def test_navigation_clamps_at_both_ends(self):
        w = self.wizard()
        w._goto(-5)
        self.assertEqual(w._stack.currentIndex(), 0)
        w._goto(99)
        self.assertEqual(w._stack.currentIndex(), 3)


class TestWizardSuggestions(WizardCase):
    def test_dark_suggestion_matches_the_exposure_time(self):
        w = self.wizard()
        w._goto(2)
        for _, combos in w._night_rows:
            src = {s.sid: s for s in w._sources}[combos['dark'].currentData()]
            self.assertEqual(src.exptime, 300.0)

    def test_dark_suggestion_prefers_the_pooled_library(self):
        w = self.wizard()
        w._goto(2)
        for _, combos in w._night_rows:
            self.assertEqual(combos['dark'].currentData(),
                             amsp.subs_sid('dark', amsp.ANY_SESSION, '300s'))

    def test_flat_suggestion_picks_the_only_flat_group(self):
        w = self.wizard()
        w._goto(2)
        for _, combos in w._night_rows:
            self.assertEqual(combos['flat'].currentData(),
                             amsp.subs_sid('flat', '2026-03-25', 'Ha'))

    def test_flat_suggestion_prefers_the_closest_night(self):
        """Two flat nights: each light night gets the nearer one."""
        infos = scan(self.data)
        near = self.tmp / 'near'
        for i in range(4):
            write_frame(near / f'flat_near_{i}.fits', 'FLAT',
                        f'2026-03-22T18:0{i}:00', 3.0, filt='Ha')
        infos += scan(near)
        w = self.wizard(infos)
        w._goto(2)
        picked = {night: combos['flat'].currentData()
                  for night, combos in w._night_rows}
        self.assertEqual(picked['2026-03-22'],
                         amsp.subs_sid('flat', '2026-03-22', 'Ha'))

    def test_bias_suggestion_is_the_pooled_source(self):
        w = self.wizard()
        w._goto(2)
        for _, combos in w._night_rows:
            self.assertEqual(combos['bias'].currentData(),
                             amsp.subs_sid('bias', amsp.ANY_SESSION))

    def test_darkflat_suggestion_uses_real_dark_flats_when_present(self):
        infos = scan(self.data)
        df = self.tmp / 'df'
        for i in range(4):
            write_frame(df / f'dark_flat_{i}.fits', 'DARK',
                        f'2026-03-25T19:0{i}:00', 3.0)
        infos += scan(df)
        w = self.wizard(infos)
        w._goto(2)
        for _, combos in w._night_rows:
            sid = combos['darkflat'].currentData()
            self.assertTrue(sid.startswith('subs:darkflat:'), sid)


class TestWizardApplyToAll(WizardCase):
    def test_apply_to_all_copies_the_selected_row(self):
        infos = scan(self.data)
        extra = self.tmp / 'extra_darks'
        for i in range(4):
            write_frame(extra / f'dark_other_{i}.fits', 'DARK',
                        f'2026-02-02T20:0{i}:00', 300.0)
        infos += scan(extra)
        w = self.wizard(infos)
        w._goto(2)

        target = amsp.subs_sid('dark', '2026-02-02', '300s')
        first = w._night_rows[0][1]['dark']
        idx = first.findData(target)
        self.assertGreaterEqual(idx, 0, 'per-night dark source should exist')
        first.setCurrentIndex(idx)
        # the other night still has its own suggestion
        self.assertNotEqual(w._night_rows[1][1]['dark'].currentData(), target)

        w._apply_to_all_nights('dark')
        for _, combos in w._night_rows:
            self.assertEqual(combos['dark'].currentData(), target)

    def test_apply_to_all_leaves_other_kinds_untouched(self):
        w = self.wizard()
        w._goto(2)
        before = [c['flat'].currentData() for _, c in w._night_rows]
        w._apply_to_all_nights('dark')
        after = [c['flat'].currentData() for _, c in w._night_rows]
        self.assertEqual(before, after)


class TestWizardValidation(WizardCase):
    def _messages(self, w, severity=None):
        return [m for s, _, m in w._validate() if severity is None or s == severity]

    def test_clean_dataset_has_no_exposure_warning(self):
        w = self.wizard()
        w._goto(3)
        self.assertFalse([m for m in self._messages(w, 'warn')
                          if 'Belichtungszeit' in m])

    def test_dark_exposure_mismatch_beyond_5s_warns(self):
        infos = scan(self.data)
        bad = self.tmp / 'bad_darks'
        for i in range(4):
            write_frame(bad / f'dark_bad_{i}.fits', 'DARK',
                        f'2026-02-03T20:0{i}:00', 240.0)   # 60 s off
        infos += scan(bad)
        w = self.wizard(infos)
        w._goto(2)
        sid = amsp.subs_sid('dark', amsp.ANY_SESSION, '240s')
        for _, combos in w._night_rows:
            idx = combos['dark'].findData(sid)
            self.assertGreaterEqual(idx, 0, f'source {sid} not offered')
            combos['dark'].setCurrentIndex(idx)
        w._goto(3)
        warnings = [m for m in self._messages(w, 'warn') if m.startswith('Dark:')]
        self.assertTrue(warnings, self._messages(w))
        self.assertIn('60.0 s', warnings[0])

    def test_exposure_within_5s_is_accepted(self):
        infos = scan(self.data)
        close = self.tmp / 'close_darks'
        for i in range(4):
            write_frame(close / f'dark_close_{i}.fits', 'DARK',
                        f'2026-02-04T20:0{i}:00', 303.0)   # 3 s off
        infos += scan(close)
        w = self.wizard(infos)
        w._goto(2)
        sid = amsp.subs_sid('dark', amsp.ANY_SESSION, '303s')
        for _, combos in w._night_rows:
            idx = combos['dark'].findData(sid)
            self.assertGreaterEqual(idx, 0, f'source {sid} not offered')
            combos['dark'].setCurrentIndex(idx)
        w._goto(3)
        self.assertFalse([m for m in self._messages(w, 'warn')
                          if m.startswith('Dark:')])

    def test_exposure_tolerance_is_configurable(self):
        infos = scan(self.data)
        bad = self.tmp / 'tol_darks'
        for i in range(4):
            write_frame(bad / f'dark_tol_{i}.fits', 'DARK',
                        f'2026-02-05T20:0{i}:00', 310.0)   # 10 s off
        infos += scan(bad)
        w = self.wizard(infos)
        w._goto(2)
        sid = amsp.subs_sid('dark', amsp.ANY_SESSION, '310s')
        for _, combos in w._night_rows:
            idx = combos['dark'].findData(sid)
            self.assertGreaterEqual(idx, 0, f'source {sid} not offered')
            combos['dark'].setCurrentIndex(idx)
        w._goto(3)
        self.assertTrue([m for m in self._messages(w, 'warn')
                         if m.startswith('Dark:')])
        w._spin_exp_tol.setValue(15.0)
        self.assertFalse([m for m in self._messages(w, 'warn')
                          if m.startswith('Dark:')])

    def test_flat_from_a_distant_date_warns(self):
        """The user's rule: a flat from the 15th is not for the 13th→14th."""
        w = self.wizard()
        w._goto(3)   # flats are from 2026-03-25, lights from 03-22 / 03-23
        warnings = [m for m in self._messages(w, 'warn') if m.startswith('Flat')]
        self.assertTrue(warnings, self._messages(w))
        self.assertIn('Tage', warnings[0])

    def test_flat_from_the_next_afternoon_does_not_warn(self):
        infos = scan(self.data)
        nxt = self.tmp / 'next_day_flats'
        for i in range(4):
            write_frame(nxt / f'flat_next_{i}.fits', 'FLAT',
                        f'2026-03-23T16:0{i}:00', 3.0, filt='Ha')
        infos += scan(nxt)
        w = self.wizard(infos)
        w._goto(2)
        sid = amsp.subs_sid('flat', '2026-03-23', 'Ha')
        for night, combos in w._night_rows:
            idx = combos['flat'].findData(sid)
            self.assertGreaterEqual(idx, 0, f'source {sid} not offered')
            combos['flat'].setCurrentIndex(idx)
        w._goto(3)
        # 2026-03-22 → 2026-03-23 is one day: inside the default tolerance
        flat_warnings = [m for m in self._messages(w, 'warn')
                         if m.startswith('Flat')]
        self.assertFalse(flat_warnings, flat_warnings)

    def test_date_tolerance_is_configurable(self):
        w = self.wizard()
        w._goto(3)
        self.assertTrue([m for m in self._messages(w, 'warn')
                         if m.startswith('Flat')])
        w._spin_date_tol.setValue(200.0)   # hours, not days
        self.assertFalse([m for m in self._messages(w, 'warn')
                          if m.startswith('Flat')])

    def test_auto_left_in_a_row_is_reported(self):
        w = self.wizard()
        w._goto(2)
        w._night_rows[0][1]['dark'].setCurrentIndex(
            w._night_rows[0][1]['dark'].findData(amsp.SID_AUTO))
        w._goto(3)
        self.assertTrue([m for m in self._messages(w, 'warn') if 'Auto' in m])

    def test_synthetic_bias_without_expression_is_an_error(self):
        w = self.wizard(synthetic='')
        w._goto(2)
        cb = w._night_rows[0][1]['bias']
        cb.setCurrentIndex(cb.findData(amsp.SID_SYNTHETIC))
        w._goto(3)
        self.assertTrue([m for m in self._messages(w, 'error')])

    def test_finish_is_blocked_until_warnings_are_confirmed(self):
        w = self.wizard()
        w._goto(3)                       # flat date warning is present
        self.assertTrue(w._needs_confirm)
        self.assertFalse(w._btn_finish.isEnabled())
        w._chk_accept.setChecked(True)
        self.assertTrue(w._btn_finish.isEnabled())

    def test_none_is_reported_as_information_not_a_warning(self):
        w = self.wizard()
        w._goto(2)
        cb = w._night_rows[0][1]['dark']
        cb.setCurrentIndex(cb.findData(amsp.SID_NONE))
        w._goto(3)
        self.assertTrue([m for m in self._messages(w, 'info')
                         if 'bewusst keine' in m])
        self.assertFalse([m for m in self._messages(w, 'warn')
                          if m.startswith('Dark:')])


class TestWizardResult(WizardCase):
    def test_night_choice_expands_to_every_light_group(self):
        w = self.wizard()
        w._goto(2)
        result = w.assignments
        for night in ('2026-03-22', '2026-03-23'):
            gkey = amsp.light_group_key('M42', night, 'Ha', '300s')
            self.assertIn(gkey, result['lights'])
            self.assertEqual(result['lights'][gkey]['flat'],
                             amsp.subs_sid('flat', '2026-03-25', 'Ha'))

    def test_darkflat_lands_on_the_flat_group_of_the_chosen_flat(self):
        w = self.wizard()
        w._goto(2)
        result = w.assignments
        fkey = amsp.flat_group_key('2026-03-25', 'Ha')
        self.assertIn(fkey, result['flats'])
        self.assertTrue(result['flats'][fkey]['bias'])

    def test_auto_entries_are_not_written(self):
        w = self.wizard()
        w._goto(2)
        for _, combos in w._night_rows:
            for cb in combos.values():
                cb.setCurrentIndex(cb.findData(amsp.SID_AUTO))
        self.assertEqual(w.assignments, {'lights': {}, 'flats': {}})

    def test_result_is_accepted_by_the_engine(self):
        """End-to-end: what the wizard produces must actually calibrate."""
        from fake_siril import FakeSiril
        infos = scan(self.data)
        w = self.wizard(infos)
        w._goto(2)
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
        calls = [c for c in siril.calibrate_calls()
                 if 'light_M42_Ha_300s' in c[1]]
        self.assertEqual(len(calls), 2)
        for call in calls:
            flags = ' '.join(call)
            self.assertIn('-flat=', flags)
            self.assertIn('-dark=', flags)

    def test_wizard_infos_carry_the_darkflat_retyping(self):
        infos = scan(self.data)
        df = self.tmp / 'df2'
        for i in range(3):
            write_frame(df / f'flat_dark_{i}.fits', 'DARK',
                        f'2026-03-25T19:0{i}:00', 3.0)
        infos += scan(df)
        w = self.wizard(infos)
        w._goto(1)
        types = {fi['name']: fi['imgtype'] for fi in w.infos}
        self.assertEqual(types['flat_dark_0.fits'], 'darkflat')

    def test_disabling_the_name_rule_restores_the_header_type(self):
        infos = scan(self.data)
        df = self.tmp / 'df3'
        write_frame(df / 'dark-flat-9.fits', 'DARK',
                    '2026-03-25T19:00:00', 3.0)
        infos += scan(df)
        w = self.wizard(infos)
        w._goto(1)
        self.assertEqual(
            next(fi['imgtype'] for fi in w.infos
                 if fi['name'] == 'dark-flat-9.fits'), 'darkflat')
        w._chk_darkflat_names.setChecked(False)
        self.assertEqual(
            next(fi['imgtype'] for fi in w.infos
                 if fi['name'] == 'dark-flat-9.fits'), 'dark')


class TestWizardLoading(WizardCase):
    def test_folder_with_everything_is_split_into_lights_and_calibration(self):
        w = amsp.CalibrationWizard(None, [], None, '')
        w._add_paths([str(self.data)])
        self.assertTrue(w._scan_thread.wait(30000))
        self.app.processEvents()               # deliver the queued result signal
        self.assertEqual(w._lights_table.rowCount(), 2)
        w._goto(1)
        self.assertGreater(w._calib_table.rowCount(), 0)

    def test_already_loaded_files_are_not_added_twice(self):
        w = self.wizard()
        before = len(w.infos)
        w._add_paths([str(self.data)])
        self.assertEqual(len(w.infos), before)
        self.assertIn('bereits geladen', w._hint_lbl.text())


class TestDarkFlatFallback(WizardCase):
    def test_falls_back_to_bias_when_no_dark_matches_the_flat_exposure(self):
        """A 300 s dark is not a dark flat for 3 s flats — use the bias."""
        w = self.wizard()
        w._goto(2)
        for _, combos in w._night_rows:
            self.assertEqual(combos['darkflat'].currentData(),
                             amsp.subs_sid('bias', amsp.ANY_SESSION))

    def test_a_dark_matching_the_flat_exposure_is_preferred_over_bias(self):
        infos = scan(self.data)
        short = self.tmp / 'short_darks'
        for i in range(4):
            write_frame(short / f'dark_short_{i}.fits', 'DARK',
                        f'2026-03-25T19:0{i}:00', 3.0)
        infos += scan(short)
        w = self.wizard(infos)
        w._goto(2)
        for _, combos in w._night_rows:
            self.assertEqual(combos['darkflat'].currentData(),
                             amsp.subs_sid('dark', amsp.ANY_SESSION, '3s'))

    def test_the_fallback_produces_no_spurious_warning(self):
        w = self.wizard()
        w._goto(3)
        self.assertFalse([m for _, _, m in w._validate()
                          if m.startswith('Dark-Flat')])


class TestWizardInMainWindow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])
        cls.tmp = Path(tempfile.mkdtemp(prefix='amsp_wizwin_'))
        cls.data = build_dataset(cls.tmp / 'data')
        cls._real_cfg = amsp.CONFIG_PATH
        amsp.CONFIG_PATH = cls.tmp / 'config.json'

    @classmethod
    def tearDownClass(cls):
        amsp.CONFIG_PATH = cls._real_cfg
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_wizard_button_is_usable_on_an_empty_window(self):
        win = amsp.FITSOrganizerWindow()
        self.assertTrue(win.initialization_successful)
        self.assertTrue(win.wizard_btn.isEnabled())
        self.assertFalse(win.go_btn.isEnabled())

    def test_window_adopts_files_and_assignments_from_the_wizard(self):
        from PyQt6.QtWidgets import QDialog
        win = amsp.FITSOrganizerWindow()
        infos = scan(self.data)

        class Stub(amsp.CalibrationWizard):
            def exec(self):                  # accept without a UI round trip
                self._goto(2)
                return QDialog.DialogCode.Accepted

        real = amsp.CalibrationWizard
        amsp.CalibrationWizard = lambda *a, **kw: Stub(None, infos, None, '')
        try:
            win._run_wizard()
        finally:
            amsp.CalibrationWizard = real

        self.assertEqual(len(win._all_infos), len(infos))
        self.assertTrue(win.go_btn.isEnabled())
        self.assertTrue(win.assign_btn.isEnabled())
        gkey = amsp.light_group_key('M42', '2026-03-22', 'Ha', '300s')
        self.assertIn(gkey, win._assignments['lights'])

        # and it survived the config write
        again = amsp.FITSOrganizerWindow()
        self.assertIn(gkey, again._assignments['lights'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
