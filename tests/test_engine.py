import csv
import io
import json
import unittest
from dataclasses import replace
from optics import Rx, axis_grid, to_vector, from_vector, lens_on_eye, to_cornea, to_spectacle, axis_distance
from engine import Case, analyze, csv_export, json_export, text_export, fmt_rx, fmt_axis


def demo(rotation=10, **kwargs):
    target = Rx(-3, -1.25, 180)
    over = from_vector(to_vector(target)-to_vector(lens_on_eye(target, rotation)))
    fields = dict(baseline=target, lens=target, over_refraction=over,
                  rotation_cw=rotation, axes=axis_grid(10), baseline_vertex_mm=0,
                  over_vertex_mm=0, stability="安定している", source="架空の検算データ")
    fields.update(kwargs)
    return Case(**fields)


class TestEngine(unittest.TestCase):
    def test_clockwise_ten_demo(self):
        r = analyze(demo())
        self.assertAlmostEqual(r.best.axis, 10)
        self.assertAlmostEqual(r.best.on_eye_axis, 0)
        self.assertAlmostEqual(r.best.cylinder_abs, 0)
        self.assertAlmostEqual(r.best.residual_cornea.sphere, 0)
        self.assertAlmostEqual(r.discrepancy.norm, 0)

    def test_counterclockwise_ten_demo(self):
        r = analyze(demo(-10))
        self.assertAlmostEqual(r.best.axis, 170)
        self.assertAlmostEqual(r.best.on_eye_axis, 0)
        self.assertAlmostEqual(r.best.cylinder_abs, 0)
        self.assertAlmostEqual(r.case.over_refraction.axis, 140)

    def test_eye_side_does_not_invert_sign(self):
        od = analyze(demo(10, eye="OD"))
        os = analyze(demo(10, eye="OS"))
        self.assertEqual(od.best, os.best)

    def test_no_rotation_no_residual(self):
        r = analyze(demo(0))
        self.assertEqual(r.best.axis, 0)
        self.assertAlmostEqual(r.best.cylinder_abs, 0)

    def test_zero_over_refraction_does_not_apply_rotation_twice(self):
        r = analyze(demo(10, over_refraction=Rx(0,0,None)))
        self.assertEqual(r.best.axis, 0)  # label 180 is already correct for measured zero residual
        self.assertAlmostEqual(r.best.cylinder_abs, 0)
        self.assertAlmostEqual(r.baseline_continuous_axis, 10)

    def test_baseline_is_not_added_to_primary_target(self):
        good = analyze(demo())
        conflicting = analyze(demo(baseline=Rx(-10,-4,60)))
        self.assertEqual(good.best, conflicting.best)
        self.assertGreater(conflicting.discrepancy.norm, 1)
        self.assertTrue(any("不一致" in x for x in conflicting.warnings))

    def test_plus_cylinder_over_refraction_equivalent(self):
        case = demo()
        rx = case.over_refraction
        plus = Rx(rx.sphere+rx.cylinder, -rx.cylinder, rx.axis+90)
        a, b = analyze(case), analyze(replace(case, over_refraction=plus))
        self.assertAlmostEqual(axis_distance(a.best.axis, b.best.axis), 0)
        self.assertAlmostEqual(a.best.cylinder_abs, b.best.cylinder_abs)

    def test_high_power_with_separate_vertex_distances(self):
        baseline = Rx(-8, -2, 40)
        target = to_cornea(baseline, 14)
        lens = Rx(-7.25, -1.75, 40)
        current = lens_on_eye(lens, -12)
        over_cornea = from_vector(to_vector(target)-to_vector(current))
        over_measured = to_spectacle(over_cornea, 12)
        r = analyze(Case(baseline, lens, over_measured, -12, axis_grid(1), 14, 12))
        self.assertAlmostEqual(r.discrepancy.norm, 0, delta=1e-9)
        self.assertAlmostEqual(r.continuous.axis, 28, delta=1e-9)
        self.assertAlmostEqual(r.best.axis, 28, delta=1e-9)

    def test_cylinder_mismatch_leaves_nonzero_lower_bound(self):
        target = Rx(-3, -2, 90)
        lens = Rx(-3,-1,90)
        over = from_vector(to_vector(target)-to_vector(lens))
        r = analyze(Case(target,lens,over,0,axis_grid(10),0,0))
        self.assertAlmostEqual(r.lower_bound_C, 1)
        self.assertAlmostEqual(r.best.cylinder_abs, 1)

    def test_axis_change_does_not_change_mean_power(self):
        r = analyze(demo())
        for row in r.candidates:
            self.assertAlmostEqual(row.residual_cornea.m, r.over_cornea.m, delta=1e-10)

    def test_sphere_change_affects_mean_not_axis_optimum(self):
        a = analyze(demo())
        b = analyze(demo(next_lens=Rx(-2.5,-1.25,180)))
        self.assertEqual(a.best.axis,b.best.axis)
        self.assertAlmostEqual(b.best.residual_cornea.m,-.5)

    def test_separate_next_rotation(self):
        r = analyze(demo(next_rotation_cw=20))
        self.assertAlmostEqual(r.best.axis,20)
        self.assertAlmostEqual(r.best.cylinder_abs,0)

    def test_no_target_astigmatism_no_axis_recommendation(self):
        lens = Rx(-3,-1.25,180)
        target = Rx(-3.625,0,None)
        over = from_vector(to_vector(target)-to_vector(lens))
        r = analyze(demo(0,baseline=target,over_refraction=over))
        self.assertIsNone(r.best)
        self.assertIsNone(r.continuous)
        for row in r.candidates:
            self.assertAlmostEqual(row.cylinder_abs,1.25)

    def test_next_spherical_lens_no_axis_recommendation(self):
        r = analyze(demo(next_lens=Rx(-3.625,0,None)))
        self.assertIsNone(r.best)
        self.assertAlmostEqual(r.candidates[0].cylinder_abs,1.25)

    def test_current_spherical_lens_rejected(self):
        with self.assertRaises(ValueError):
            demo(lens=Rx(-3,0,None))

    def test_unstable_case_warns(self):
        r = analyze(demo(stability="不安定"))
        self.assertTrue(any("安定・再現性" in x for x in r.warnings))

    def test_available_axis_constraint(self):
        r = analyze(demo(10,axes=(90,180)))
        self.assertIn(r.best.axis,(90,0))
        self.assertEqual(r.best.axis,0)
        self.assertGreater(r.best.cylinder_abs,0)
        self.assertAlmostEqual(r.continuous.axis,10)

    def test_half_step_tie_prefers_current_label(self):
        lens = Rx(-3,-1.25,180)
        target = Rx(-3,-1.25,5)
        over = from_vector(to_vector(target)-to_vector(lens))
        r = analyze(demo(0,baseline=target,over_refraction=over))
        self.assertEqual(r.best.axis,0)
        self.assertEqual(set(r.tied_best_axes),{0,10})

    def test_invalid_case_parameters(self):
        for kwargs in [{"eye":"OU"},{"rotation_cw":91},{"next_rotation_cw":-91},
                       {"rotation_half_width_deg":31},{"axes":()},
                       {"discrepancy_threshold_D":0},{"rotation_cw":float("nan")}]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                demo(**kwargs)

    def test_json_export_contains_inputs_assumptions_and_candidates(self):
        d = json.loads(json_export(analyze(demo())))
        self.assertEqual(d["app_version"],"0.1.0")
        self.assertEqual(d["input"]["eye"],"OD")
        self.assertEqual(len(d["result"]["all_candidates"]),18)
        self.assertAlmostEqual(d["result"]["best_available_candidate"]["label_axis_deg"],10)
        self.assertIn("NOT",d["sensitivity_scope"])
        self.assertIn("未臨床検証",d["model_warning"])
        self.assertAlmostEqual(d["derived"]["over_refraction_cornea"]["axis_deg"],40)

    def test_csv_has_bom_and_all_rows(self):
        data = csv_export(analyze(demo()))
        self.assertTrue(data.startswith(b"\xef\xbb\xbf"))
        rows = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
        self.assertEqual(len(rows),18)
        self.assertEqual(float(rows[0]["axis_label_deg"]),10)
        self.assertEqual(float(rows[0]["overref_vertex_mm"]),0)

    def test_text_export_is_self_contained(self):
        text = text_export(analyze(demo()))
        for term in ["頂点間距離", "時計回り", "残余", "未臨床検証", "SCL", "信頼区間"]:
            self.assertIn(term,text)

    def test_formatted_zero_cylinder_hides_axis(self):
        self.assertIn("C=0",fmt_rx(Rx(0,-.001,40)))
        self.assertEqual(fmt_axis(0),"180.0°")
        self.assertEqual(fmt_axis(179.99999),"180.0°")
        self.assertEqual(fmt_axis(.00001),"180.0°")


if __name__ == "__main__":
    unittest.main()
