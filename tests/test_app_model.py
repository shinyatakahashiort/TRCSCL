"""Tests of v0.2 input lists, validation, state and inverse optics; no UI mocking claims."""
import ast
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import random
from types import SimpleNamespace
import unittest

import app
from optics import Rx, axis_distance, axis_grid, display_axis, from_vector, lens_on_eye, to_vector, to_spectacle
from engine import Case


class InputSpecificationTests(unittest.TestCase):
    def test_requested_power_steps(self):
        self.assertEqual(app.INPUT_STEPS, {'baseline':('0.25','5'),'lens':('0.25','10'),'over':('0.01','1')})

    def test_lists_have_exact_steps_and_endpoints(self):
        for q, aq in app.INPUT_STEPS.values():
            for lo, hi in [('-30','25'),('-15','15'),('-15','0')]:
                values=[Decimal(v) for v in app.options_for(lo,hi,q,2)]
                self.assertEqual(values[0],Decimal(lo))
                self.assertEqual(values[-1],Decimal(hi))
                self.assertTrue(all(b-a==Decimal(q) for a,b in zip(values,values[1:])))
            values=[int(v) for v in app.options_for(aq,'180',aq,0)]
            self.assertEqual(values[-1],180)
            self.assertEqual(len(values),180//int(aq))

    def test_direct_entry_normalized(self):
        for raw in ['-3.25','−3.25','－３．２５','-3.25 D','-3.250']:
            self.assertEqual(app.parse_value(raw,label='S',minimum=-30,maximum=25,step='0.25'),-3.25)

    def test_hundredth_entry(self):
        self.assertEqual(app.parse_value('-0.43',label='C',minimum=-15,maximum=15,step='0.01'),-.43)

    def test_invalid_values_not_silently_rounded(self):
        for raw in ['NaN','Infinity','abc','30','-31','-3.26']:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                app.parse_value(raw,label='S',minimum=-30,maximum=25,step='0.25')

    def test_invalid_fine_precision(self):
        with self.assertRaises(ValueError):
            app.parse_value('0.001',label='C',minimum=-15,maximum=15,step='0.01')

    def test_axis_zero_and_degree_suffix(self):
        self.assertEqual(app.parse_value('０°',label='Ax',minimum=0,maximum=180,step='5',axis=True),180)
        self.assertEqual(app.parse_value('175°',label='Ax',minimum=0,maximum=180,step='5',axis=True),175)

    def test_axis_step_enforced(self):
        with self.assertRaises(ValueError):
            app.parse_value('175',label='Ax',minimum=0,maximum=180,step='10',axis=True)

    def test_empty_values(self):
        for v in (None,'','   '):
            self.assertIsNone(app.parse_value(v,label='S',minimum=-30,maximum=25,step='0.25'))

    def test_no_rotation_input_widget_in_source(self):
        tree=ast.parse(Path(app.__file__).read_text())
        keys=[]
        for node in ast.walk(tree):
            if isinstance(node,ast.Call):
                for kw in node.keywords:
                    if kw.arg=='key' and isinstance(kw.value,ast.Constant):keys.append(kw.value.value)
        self.assertNotIn('rotation_direction',keys)
        self.assertNotIn('rotation_amount',keys)
        self.assertNotIn('next_rotation_amount',keys)
        self.assertNotIn('03｜装用中SCLの回転',Path(app.__file__).read_text())


class InverseModelTests(unittest.TestCase):
    def case(self,rotation=10,base=None,lens=None,bvd=0,ovd=0):
        base=base or Rx(-3,-1.25,180)
        lens=lens or Rx(-3,-1.25,180)
        over=from_vector(to_vector(base)-to_vector(lens_on_eye(lens,rotation)))
        b=to_spectacle(base,bvd)
        o=to_spectacle(over,ovd)
        e=app.estimate_rotation(b,lens,o,bvd,ovd)
        c=Case(b,lens,o,e.clockwise_deg,axis_grid(10),baseline_vertex_mm=bvd,over_vertex_mm=ovd)
        return app.analyze_case(c),e

    def test_clockwise_inverse(self):
        a,e=self.case()
        self.assertAlmostEqual(e.clockwise_deg,10)
        self.assertAlmostEqual(display_axis(a.best.axis),10)
        self.assertAlmostEqual(a.best.cylinder_abs,0)

    def test_counterclockwise_inverse(self):
        a,e=self.case(-10)
        self.assertAlmostEqual(e.clockwise_deg,-10)
        self.assertAlmostEqual(display_axis(a.best.axis),170)
        self.assertAlmostEqual(a.best.cylinder_abs,0)

    def test_nonzero_vertex_planes(self):
        a,e=self.case(10,bvd=12,ovd=10)
        self.assertAlmostEqual(e.clockwise_deg,10)
        self.assertAlmostEqual(a.best.cylinder_abs,0)

    def test_plus_cylinder_baseline_and_over(self):
        b=Rx(-4.25,1.25,90)
        lens=Rx(-3,-1.25,180)
        over=from_vector(to_vector(b)-to_vector(lens_on_eye(lens,10)))
        over_plus=Rx(over.sphere+over.cylinder,-over.cylinder,over.axis+90)
        e=app.estimate_rotation(b,lens,over_plus,0,0)
        self.assertAlmostEqual(e.clockwise_deg,10)

    def test_1000_random_rotations(self):
        rng=random.Random(20260917)
        for _ in range(1000):
            lens=Rx(rng.uniform(-10,5),-rng.uniform(.25,6),rng.uniform(0,180))
            base=Rx(rng.uniform(-8,3),-rng.uniform(.25,5),rng.uniform(0,180))
            r=rng.uniform(-89.9,89.9)
            over=from_vector(to_vector(base)-to_vector(lens_on_eye(lens,r)))
            e=app.estimate_rotation(base,lens,over,0,0)
            self.assertLess(axis_distance(e.clockwise_deg,r),1e-8)
            self.assertAlmostEqual(e.delta_M,0,places=8)
            self.assertAlmostEqual(e.delta_C,0,places=8)

    def test_zero_signal_does_not_assume_zero_rotation(self):
        b=Rx(-3,-1.25,180)
        with self.assertRaisesRegex(ValueError,'推定できません'):
            app.estimate_rotation(b,b,b,0,0)

    def test_low_signal_suppressed(self):
        b=Rx(0,0,None)
        o=Rx(.02,-.04,40)
        with self.assertRaises(ValueError):
            app.estimate_rotation(b,Rx(-3,-1.25,180),o,0,0)

    def test_cannot_use_spherical_or_positive_current_lens(self):
        for lens in [Rx(-3,0,None),Rx(-4.25,1.25,90)]:
            with self.assertRaises(ValueError):
                app.estimate_rotation(Rx(-3,-1.25,180),lens,Rx(0,0,None),0,0)

    def test_zero_residual_preserves_current_axis(self):
        # Baseline differs from lens axis, but OR=0; do NOT double-correct.
        b,l=Rx(-3,-1.25,180),Rx(-3,-1.25,170)
        e=app.estimate_rotation(b,l,Rx(0,0,None),0,0)
        c=Case(b,l,Rx(0,0,None),e.clockwise_deg,axis_grid(10),baseline_vertex_mm=0,over_vertex_mm=0)
        a=app.analyze_case(c)
        self.assertAlmostEqual(display_axis(a.best.axis),170)
        self.assertAlmostEqual(a.best.cylinder_abs,0)

    def test_model_mismatch_is_disclosed(self):
        # Lens magnitude 1.25 vs effect inferred as 3.00 D.
        b,l,o=Rx(-3,-3,180),Rx(-3,-1.25,180),Rx(0,0,None)
        e=app.estimate_rotation(b,l,o,0,0)
        a=app.analyze_case(Case(b,l,o,e.clockwise_deg,axis_grid(10),baseline_vertex_mm=0,over_vertex_mm=0))
        self.assertAlmostEqual(e.delta_C,-1.75)
        self.assertTrue(any('回転だけでは' in w for w in a.warnings))

    def test_export_does_not_report_measured_rotation(self):
        a,e=self.case()
        p=app.export_payload(a,e)
        self.assertEqual(p['app_version'],'0.2.0')
        self.assertNotIn('current_rotation_cw_deg',p['input'])
        self.assertFalse(p['assumptions']['rotation_was_measured'])
        self.assertIn('NOT_observed',p['rotation_estimation']['source'])
        self.assertIn('estimated_current_on_eye_SCL',p['derived'])
        self.assertIn('実測ではない',app.summary_export(a,e))


class StateTests(unittest.TestCase):
    def setUp(self):
        self.previous=getattr(app,'st',None)
        app.st=SimpleNamespace(session_state={})
        app.clear_inputs()
    def tearDown(self):
        if self.previous is not None:app.st=self.previous

    def test_rounded_demos_use_displayed_values_only(self):
        for rotation,axis in [(10,10),(-10,170),(0,180)]:
            app.load_demo(rotation)
            c,e=app.build_case()
            a=app.analyze_case(c)
            self.assertEqual(display_axis(a.best.axis),axis)
            self.assertLess(a.best.cylinder_abs,.01)
            self.assertEqual(Decimal(app.st.session_state['over_c']) % Decimal('.01'),0)

    def test_empty_inputs_rejected(self):
        with self.assertRaises(ValueError):app.build_case()

    def test_old_rotation_input_ignored(self):
        app.load_demo(10)
        c1,e1=app.build_case()
        app.st.session_state['rotation_amount']=55
        app.st.session_state['rotation_direction']='反時計回り（−）'
        c2,e2=app.build_case()
        self.assertEqual(e1,e2)

    def test_blank_over_axis_allowed_when_c_zero(self):
        app.load_demo(10)
        app.st.session_state.update(over_s='0.00',over_c='0.00',over_a=None)
        c,e=app.build_case()
        self.assertEqual(display_axis(app.analyze_case(c).best.axis),180)

    def test_invalid_baseline_step_rejected(self):
        app.load_demo(10)
        app.st.session_state['baseline_s']='-3.13'
        with self.assertRaisesRegex(ValueError,'0.25'):app.build_case()

    def test_custom_axes(self):
        app.load_demo(10)
        app.st.session_state.update(grid_mode=app.GRID_OPTIONS[3],available_axes=['90','180'])
        c,e=app.build_case()
        self.assertEqual(len(app.analyze_case(c).candidates),2)

    def test_empty_custom_axes_rejected(self):
        app.load_demo(10)
        app.st.session_state.update(grid_mode=app.GRID_OPTIONS[3],available_axes=[])
        with self.assertRaises(ValueError):app.build_case()

    def test_custom_power(self):
        app.load_demo(10)
        app.st.session_state.update(change_power=True,next_s='-2.50',next_c='-1.25')
        c,e=app.build_case()
        self.assertEqual(c.next_lens.sphere,-2.5)

    def test_signature_changes_on_input(self):
        app.load_demo(10)
        old=app.input_signature()
        app.st.session_state['over_s']='0.23'
        self.assertNotEqual(old,app.input_signature())

    def test_clear_removes_results_and_rotation_keys(self):
        app.st.session_state.update(_result='obsolete',rotation_amount=33)
        app.clear_inputs()
        self.assertNotIn('_result',app.st.session_state)
        self.assertNotIn('rotation_amount',app.st.session_state)
        self.assertIsNone(app.st.session_state['baseline_s'])


if __name__=='__main__': unittest.main()
