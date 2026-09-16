"""Real Streamlit AppTest coverage for v0.3. Skipped if Streamlit is absent.

No demos are exposed in the app. Test fixtures are entered by tests only.
"""
from decimal import Decimal
from pathlib import Path
import importlib.util
import unittest

HAS_STREAMLIT = importlib.util.find_spec("streamlit") is not None
if HAS_STREAMLIT:
    from streamlit.testing.v1 import AppTest
APP = Path(__file__).resolve().parents[1] / "app.py"


@unittest.skipUnless(HAS_STREAMLIT, "Streamlit is not installed: real UI execution not verified.")
class TestStreamlitUI(unittest.TestCase):
    def start(self):
        at = AppTest.from_file(str(APP), default_timeout=30).run()
        self.assertEqual(len(at.exception), 0)
        return at

    def click(self, at, label):
        next(x for x in at.button if x.label == label).click().run()
        self.assertEqual(len(at.exception), 0)
        return at

    def run_reference(self):
        at = self.start()
        fields = {
            'baseline_s': '-3.00', 'baseline_c': '-1.25', 'baseline_a': '180', 'baseline_vertex': '0.0',
            'lens_s': '-3.00', 'lens_c': '-1.25', 'lens_a': '180',
            'over_s': '0.00', 'over_c': '0.00', 'over_vertex': '0.0',
        }
        for key, value in fields.items():
            at.selectbox(key=key).select(value)
        at.run()
        at.checkbox(key='consent').check().run()
        self.click(at, '残余乱視が最小になる軸を計算')
        self.assertEqual(len(at.error), 0)
        return at

    def test_initial_ui_numbering(self):
        at = self.start()
        self.assertEqual([x.value for x in at.subheader], [
            '01｜装用前の矯正値', '02｜装用中SCLの表示度数',
            '03｜装用後の屈折値', '04｜次に試せる軸の候補',
        ])

    def test_no_demo_buttons_or_rotation_input(self):
        at = self.start()
        self.assertFalse(any('デモ' in x.label for x in at.button))
        self.assertFalse(any(x.key in ('rotation_amount','rotation_direction') for x in at.selectbox))

    def test_all_nine_rx_fields_are_editable_zero_first_lists(self):
        at = self.start()
        for p in ('baseline','lens','over'):
            for f in ('s','c','a'):
                widget = at.selectbox(key=f'{p}_{f}')
                self.assertTrue(widget.proto.accept_new_options)
                self.assertEqual(Decimal(widget.options[0]), 0)
                self.assertIsNone(widget.value)

    def test_requested_axis_choices(self):
        at = self.start()
        for p, step in [('baseline',5),('lens',10),('over',5)]:
            self.assertEqual(at.selectbox(key=f'{p}_a').options,[str(x) for x in range(0,181,step)])

    def test_requested_power_choices(self):
        at = self.start()
        for p in ('baseline','lens','over'):
            for f in ('s','c'):
                options = at.selectbox(key=f'{p}_{f}').options
                self.assertEqual(options[:3], ['0.00','-0.25','-0.50'])
                self.assertIn('-3.25',options)
                self.assertNotIn('-0.43',options)

    def test_all_advanced_numeric_lists_start_zero(self):
        at = self.start()
        at.checkbox(key='change_power').check().run()
        for key in ('baseline_vertex','over_vertex','next_s','next_c','rotation_half_width','discrepancy_threshold'):
            widget = at.selectbox(key=key)
            self.assertEqual(Decimal(widget.options[0]), 0)
            self.assertTrue(widget.proto.accept_new_options)

    def test_consent_required(self):
        at = self.start()
        self.click(at, '残余乱視が最小になる軸を計算')
        self.assertTrue(any('確認欄' in x.value for x in at.error))

    def test_empty_values_validation(self):
        at = self.start()
        at.checkbox(key='consent').check().run()
        self.click(at, '残余乱視が最小になる軸を計算')
        self.assertGreater(len(at.error),0)

    def test_reference_case_calculates(self):
        at = self.run_reference()
        self.assertAlmostEqual(at.session_state['_result'].best.cylinder_abs,0)

    def test_changed_input_hides_stale_result(self):
        at = self.run_reference()
        at.selectbox(key='lens_a').select('170').run()
        self.assertEqual(len(at.exception),0)
        self.assertEqual(len(at.metric),0)
        self.assertTrue(any('入力が変更' in x.value for x in at.info))

    def test_clear_removes_results(self):
        at = self.run_reference()
        self.click(at,'入力をクリア')
        self.assertEqual(len(at.metric),0)
        self.assertIsNone(at.selectbox(key='lens_s').value)

    def test_custom_candidate_selection_includes_zero(self):
        at = self.run_reference()
        at.selectbox(key='grid_mode').select('使用可能な軸を選択・入力').run()
        self.assertEqual(at.multiselect(key='available_axes').options[0], '0')
        at.multiselect(key='available_axes').set_value(['0','90','180']).run()
        self.click(at,'残余乱視が最小になる軸を計算')
        self.assertEqual(len(at.session_state['_result'].candidates),2)

    def test_changed_next_power(self):
        at = self.run_reference()
        at.checkbox(key='change_power').check().run()
        at.selectbox(key='next_s').select('-2.50').run()
        at.selectbox(key='next_c').select('-1.25').run()
        self.click(at,'残余乱視が最小になる軸を計算')
        self.assertEqual(at.session_state['_result'].case.next_lens.sphere,-2.5)

    def test_zero_threshold_accepted(self):
        at = self.run_reference()
        at.selectbox(key='discrepancy_threshold').select('0.00').run()
        self.click(at,'残余乱視が最小になる軸を計算')
        self.assertEqual(len(at.error),0)
        self.assertEqual(at.session_state['_result'].case.discrepancy_threshold_D,0)

    def test_undetermined_rotation_blocks_results(self):
        at = self.run_reference()
        at.selectbox(key='over_s').select('-3.00').run()
        at.selectbox(key='over_c').select('-1.25').run()
        at.selectbox(key='over_a').select('180').run()
        self.click(at,'残余乱視が最小になる軸を計算')
        self.assertTrue(any('推定できません' in x.value for x in at.error))
        self.assertEqual(len(at.metric),0)


if __name__=='__main__': unittest.main()
