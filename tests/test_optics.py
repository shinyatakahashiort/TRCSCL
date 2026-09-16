"""Deterministic optical tests. Run with python -m unittest discover -s tests -v."""
import math
import random
import unittest
from optics import (
    Rx, PowerVector, normalize_axis, display_axis, signed_axis_difference,
    axis_distance, to_vector, from_vector, to_cornea, to_spectacle, on_eye_axis,
    order_axis, lens_on_eye, residual_for_axis, optimal_order_axis, axis_grid,
    parse_axes, clean_axes, cylinder_range,
)


def matrix(rx):
    """Independent meridional power matrix, not calling vector conversion."""
    a = math.radians(rx.axis or 0)
    s, c = rx.sphere, rx.cylinder
    return (s+c*math.sin(a)**2, -c*math.sin(a)*math.cos(a), s+c*math.cos(a)**2)


class TestOptics(unittest.TestCase):
    def assertRxEqual(self, a, b, tol=1e-9):
        for x, y in zip(matrix(a), matrix(b)):
            self.assertAlmostEqual(x, y, delta=tol)

    def test_zero_and_180_are_identical(self):
        self.assertEqual(normalize_axis(180), 0)
        self.assertEqual(normalize_axis(360), 0)
        self.assertEqual(normalize_axis(-10), 170)
        self.assertEqual(display_axis(0), 180)
        self.assertRxEqual(Rx(-3, -1, 0), Rx(-3, -1, 180))

    def test_smallest_axis_difference_crosses_boundary(self):
        self.assertEqual(signed_axis_difference(10, 170), 20)
        self.assertEqual(signed_axis_difference(170, 10), -20)
        self.assertEqual(axis_distance(179, 1), 2)

    def test_transpose_plus_cylinder(self):
        original = Rx(-4, 1.25, 90)
        equivalent = Rx(-2.75, -1.25, 180)
        self.assertEqual(original.minus_cylinder(), equivalent)
        self.assertRxEqual(original, equivalent)

    def test_sphere_has_no_axis(self):
        self.assertIsNone(Rx(-3, 0, 90).axis)
        self.assertIsNone(from_vector(PowerVector(-3, 0, 0)).axis)

    def test_cylinder_requires_axis(self):
        with self.assertRaises(ValueError):
            Rx(0, -1, None)

    def test_known_power_vectors(self):
        for a, expected in [(180, (1, 0)), (45, (0, 1)), (90, (-1, 0)), (135, (0, -1))]:
            p = to_vector(Rx(-2, -2, a))
            self.assertAlmostEqual(p.m, -3)
            self.assertAlmostEqual(p.j0, expected[0])
            self.assertAlmostEqual(p.j45, expected[1])

    def test_round_trip_1000_random_spherocylinders(self):
        rng = random.Random(71023)
        for _ in range(1000):
            rx = Rx(rng.uniform(-15, 10), rng.uniform(-6, 6), rng.uniform(0, 180))
            self.assertRxEqual(rx, from_vector(to_vector(rx)))

    def test_vector_addition_matches_independent_matrix_500_cases(self):
        rng = random.Random(8455)
        for _ in range(500):
            a = Rx(rng.uniform(-10, 5), rng.uniform(-5, 5), rng.uniform(0, 180))
            b = Rx(rng.uniform(-4, 4), rng.uniform(-5, 5), rng.uniform(0, 180))
            out = matrix(from_vector(to_vector(a) + to_vector(b)))
            expected = [x + y for x, y in zip(matrix(a), matrix(b))]
            for x, y in zip(out, expected):
                self.assertAlmostEqual(x, y, delta=1e-9)

    def test_vertex_both_meridians(self):
        out = to_cornea(Rx(-8, -2, 30), 12)
        self.assertAlmostEqual(out.sphere, -8 / 1.096)
        self.assertAlmostEqual(out.sphere + out.cylinder, -10 / 1.12)
        self.assertEqual(out.axis, 30)
        self.assertNotAlmostEqual(out.cylinder, -2 / 1.024, places=3)

    def test_vertex_round_trip(self):
        rng = random.Random(830)
        for _ in range(500):
            rx = Rx(rng.uniform(-20, 15), rng.uniform(-6, 6), rng.uniform(0, 180))
            d = rng.uniform(0, 20)
            self.assertRxEqual(rx, to_spectacle(to_cornea(rx, d), d), tol=1e-8)

    def test_zero_vertex_preserves_power(self):
        rx = Rx(-3, 1.5, 45)
        self.assertRxEqual(rx, to_cornea(rx, 0))

    def test_vertex_pole_rejected(self):
        with self.assertRaises(ValueError):
            to_cornea(Rx(50, 0, None), 20)
        with self.assertRaises(ValueError):
            to_spectacle(Rx(-50, 0, None), 20)
        with self.assertRaises(ValueError):
            to_cornea(Rx(-3, 0, None), -1)

    def test_clockwise_causes_decreasing_on_eye_axis(self):
        self.assertEqual(on_eye_axis(90, 10), 80)
        self.assertEqual(on_eye_axis(180, 10), 170)
        self.assertEqual(on_eye_axis(10, 20), 170)

    def test_counterclockwise_causes_increasing_on_eye_axis(self):
        self.assertEqual(on_eye_axis(90, -10), 100)
        self.assertEqual(on_eye_axis(180, -10), 10)

    def test_manufacturer_caas_examples(self):
        self.assertEqual(order_axis(180, 20), 20)
        self.assertEqual(order_axis(180, -30), 150)

    def test_rotation_order_inverse(self):
        rng = random.Random(8371)
        for _ in range(500):
            target, r = rng.uniform(0, 180), rng.uniform(-90, 90)
            self.assertAlmostEqual(axis_distance(on_eye_axis(order_axis(target, r), r), target), 0, delta=1e-10)

    def test_residual_cylinder_rotation_law(self):
        lens = Rx(-3, -1.25, 180)
        for rotation in [0, 1, 5, 10, 20, 30, 45, 90, -10, -45]:
            over = from_vector(to_vector(lens) - to_vector(lens_on_eye(lens, rotation)))
            expected = 2 * 1.25 * abs(math.sin(math.radians(rotation)))
            self.assertAlmostEqual(abs(over.cylinder), expected, delta=1e-9)
            self.assertAlmostEqual(over.m, 0, delta=1e-9)

    def test_clockwise_demo_over_refraction(self):
        target = Rx(-3, -1.25, 180)
        over = from_vector(to_vector(target)-to_vector(lens_on_eye(target, 10)))
        self.assertAlmostEqual(over.sphere, 0.217060222083663, places=12)
        self.assertAlmostEqual(over.cylinder, -0.434120444167326, places=12)
        self.assertAlmostEqual(over.axis, 40, places=10)

    def test_analytic_optimum_matches_dense_search_100_cases(self):
        rng = random.Random(7815)
        for _ in range(100):
            target = to_vector(Rx(rng.uniform(-5, 1), -rng.uniform(.1, 4), rng.uniform(0, 180)))
            lens = Rx(-3, -rng.uniform(.25, 4), 180)
            rotation = rng.uniform(-45, 45)
            optimum = optimal_order_axis(target, lens, rotation)
            theoretical = abs(residual_for_axis(target, lens, optimum, rotation).cylinder)
            brute = min(abs(residual_for_axis(target, lens, a/10, rotation).cylinder) for a in range(1800))
            self.assertLessEqual(theoretical, brute+1e-9)
            self.assertAlmostEqual(theoretical, abs(target.cylinder_magnitude - abs(lens.cylinder)), delta=1e-9)

    def test_sphere_or_no_target_astigmatism_has_no_unique_optimum(self):
        self.assertIsNone(optimal_order_axis(to_vector(Rx(-3, -1, 180)), Rx(-3, 0, None), 10))
        self.assertIsNone(optimal_order_axis(to_vector(Rx(-3, 0, None)), Rx(-3, -1, 180), 10))

    def test_plus_cylinder_lens_is_rejected(self):
        with self.assertRaises(ValueError):
            lens_on_eye(Rx(-3, 1, 90), 10)
        with self.assertRaises(ValueError):
            optimal_order_axis(to_vector(Rx(-3, -1, 180)), Rx(-3, 1, 90), 10)

    def test_candidate_grids_unique_periodic(self):
        for step, count in [(1, 180), (5, 36), (10, 18)]:
            axes = axis_grid(step)
            self.assertEqual(len(axes), count)
            self.assertEqual(len(set(axes)), count)
            self.assertIn(0, axes)
            self.assertNotIn(180, axes)
        with self.assertRaises(ValueError):
            axis_grid(7)

    def test_custom_axes_japanese_and_duplicates(self):
        self.assertEqual(parse_axes("１０、２０，９０,１８０,0\n10"), (10, 20, 90, 0))
        self.assertEqual(parse_axes("5.5; 15.5\n180"), (5.5, 15.5, 0))
        self.assertEqual(clean_axes([180, 0, 180]), (0,))

    def test_invalid_axes(self):
        for text in ["", "abc", "10, -1", "181", "nan", "inf", "20-90"]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_axes(text)

    def test_non_finite_input_rejected(self):
        for value in [float("nan"), float("inf"), float("-inf")]:
            with self.assertRaises(ValueError): Rx(value, 0, None)
            with self.assertRaises(ValueError): Rx(0, value, 180)
            with self.assertRaises(ValueError): Rx(0, -1, value)
            with self.assertRaises(ValueError): PowerVector(0, value, 0)

    def test_rotation_range_finds_interior_minimum(self):
        target = to_vector(Rx(-3, -1, 180))
        lo, hi = cylinder_range(target, Rx(-3, -1, 180), 180, 0, 10)
        self.assertAlmostEqual(lo, 0)
        self.assertAlmostEqual(hi, 2*math.sin(math.radians(10)))

    def test_rotation_range_finds_interior_maximum(self):
        target = to_vector(Rx(-3, -1, 180))
        lo, hi = cylinder_range(target, Rx(-3, -1, 180), 90, 0, 10)
        self.assertAlmostEqual(hi, 2)
        self.assertAlmostEqual(lo, 2*math.cos(math.radians(10)))

    def test_rotation_range_contains_sampled_values_200_cases(self):
        rng = random.Random(6145)
        for _ in range(200):
            target = to_vector(Rx(-3, -rng.uniform(.1, 4), rng.uniform(0, 180)))
            lens = Rx(-3, -rng.uniform(.1, 4), 0)
            a, r, h = rng.uniform(0,180), rng.uniform(-90,90), rng.uniform(0,30)
            lo, hi = cylinder_range(target, lens, a, r, h)
            values = [abs(residual_for_axis(target, lens, a, r-h+2*h*i/100).cylinder) for i in range(101)]
            self.assertLessEqual(lo, min(values)+1e-9)
            self.assertGreaterEqual(hi, max(values)-1e-9)
            self.assertLessEqual(min(values)-lo, .03)
            self.assertLessEqual(hi-max(values), .03)

    def test_zero_rotation_range_width(self):
        target = to_vector(Rx(-3, -1.75, 140))
        lens = Rx(-2, -1.25, 130)
        lo, hi = cylinder_range(target, lens, 130, 15, 0)
        self.assertAlmostEqual(lo, hi)


if __name__ == "__main__":
    unittest.main()
