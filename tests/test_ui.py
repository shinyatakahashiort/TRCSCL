"""Real Streamlit AppTest smoke tests (skipped when Streamlit is not installed).
CI installs requirements.txt before running these tests. A skip is NOT a pass.
"""
from pathlib import Path
import importlib.util
import unittest

HAS_STREAMLIT = importlib.util.find_spec("streamlit") is not None
if HAS_STREAMLIT:
    from streamlit.testing.v1 import AppTest
APP = Path(__file__).resolve().parents[1] / "app.py"


@unittest.skipUnless(HAS_STREAMLIT, "Streamlit is not installed; UI execution was NOT verified in this environment.")
class TestStreamlitUI(unittest.TestCase):
    def start(self):
        at = AppTest.from_file(str(APP), default_timeout=30).run()
        self.assertEqual(len(at.exception), 0)
        return at

    def click(self, at, label):
        next(x for x in at.button if x.label == label).click().run()
        self.assertEqual(len(at.exception), 0)
        return at

    def run_demo(self, label="時計回り10°のデモ"):
        at = self.start()
        self.click(at, label)
        at.checkbox(key="consent").check().run()
        self.click(at, "残余乱視が最小になる軸を計算")
        self.assertEqual(len(at.error), 0)
        return at

    def test_initial_ui(self):
        self.start()

    def test_consent_required(self):
        at = self.start()
        self.click(at, "残余乱視が最小になる軸を計算")
        self.assertTrue(any("確認欄" in x.value for x in at.error))

    def test_empty_values_produce_validation_message(self):
        at = self.start()
        at.checkbox(key="consent").check().run()
        self.click(at, "残余乱視が最小になる軸を計算")
        self.assertGreater(len(at.error), 0)

    def test_clockwise_demo(self):
        at = self.run_demo()
        self.assertAlmostEqual(at.session_state["_result"].best.axis, 10)
        self.assertGreater(len(at.metric), 0)

    def test_counterclockwise_demo(self):
        at = self.run_demo("反時計回り10°のデモ")
        self.assertAlmostEqual(at.session_state["_result"].best.axis, 170)

    def test_changed_input_hides_stale_result(self):
        at = self.run_demo()
        at.number_input(key="lens_a").set_value(170.0).run()
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(len(at.metric), 0)
        self.assertTrue(any("入力が変更" in x.value for x in at.info))

    def test_clear_removes_results(self):
        at = self.run_demo()
        self.click(at, "入力をクリア")
        self.assertEqual(len(at.metric), 0)
        self.assertIsNone(at.number_input(key="lens_s").value)

    def test_custom_candidates(self):
        at = self.run_demo()
        at.selectbox(key="grid_mode").select("使用可能な軸を手入力").run()
        at.text_area(key="axes_text").set_value("90, 180").run()
        self.click(at, "残余乱視が最小になる軸を計算")
        self.assertEqual(len(at.session_state["_result"].candidates), 2)
        self.assertEqual(at.session_state["_result"].best.axis, 0)

    def test_changed_next_power(self):
        at = self.run_demo()
        at.checkbox(key="change_power").check().run()
        at.number_input(key="next_s").set_value(-2.5).run()
        at.number_input(key="next_c").set_value(-1.25).run()
        self.click(at, "残余乱視が最小になる軸を計算")
        self.assertAlmostEqual(at.session_state["_result"].best.residual_cornea.m, -.5)


if __name__ == "__main__":
    unittest.main()
