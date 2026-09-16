"""Verify chart construction with real Plotly, independent of Streamlit UI."""
import importlib.util
import json
import unittest
from optics import Rx, axis_grid, from_vector, lens_on_eye, to_vector
from engine import Case, analyze

HAS_PLOTLY = importlib.util.find_spec("plotly") is not None
if HAS_PLOTLY:
    from visuals import curve_figure, axis_figure


@unittest.skipUnless(HAS_PLOTLY, "Plotly is not installed.")
class TestVisuals(unittest.TestCase):
    def result(self):
        target=Rx(-3,-1.25,180)
        over=from_vector(to_vector(target)-to_vector(lens_on_eye(target,10)))
        return analyze(Case(target,target,over,10,axis_grid(10),0,0))

    def test_curve_endpoints_periodic(self):
        fig=curve_figure(self.result())
        self.assertEqual(len(fig.data[0].x),181)
        self.assertAlmostEqual(fig.data[0].y[0],fig.data[0].y[-1])

    def test_candidate_and_best_marker_counts(self):
        fig=curve_figure(self.result())
        self.assertEqual(len(fig.data[1].x),18)
        self.assertAlmostEqual(fig.data[2].x[0],10)
        self.assertAlmostEqual(fig.data[2].y[0],0)

    def test_frontal_clockwise_marker_moves_left(self):
        fig=axis_figure(self.result())
        marker=fig.data[-1]
        self.assertLess(marker.x[1],0)
        self.assertGreater(marker.y[1],-1)

    def test_figures_serialize_without_non_finite_values(self):
        for fig in (axis_figure(self.result()),curve_figure(self.result())):
            content=fig.to_json()
            self.assertNotIn('NaN',content)
            self.assertNotIn('Infinity',content)
            json.loads(content)


if __name__ == '__main__':
    unittest.main()
