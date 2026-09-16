"""Tests of v0.3 input lists, validation, state and inverse optics; no UI mocking claims."""
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


def fill_reference(rotation=10):
    target=Rx(-3,-1.25,180)
    over=from_vector(to_vector(target)-to_vector(lens_on_eye(target,rotation)))
    app.st.session_state.update({
        'baseline_s':'-3.00','baseline_c':'-1.25','baseline_a':'180','baseline_vertex':'0.0',
        'lens_s':'-3.00','lens_c':'-1.25','lens_a':'180',
        'over_s':str(over.sphere),'over_c':str(over.cylinder),
        'over_a':None if over.axis is None else str(display_axis(over.axis)),'over_vertex':'0.0',
    })


class InputSpecificationTests(unittest.TestCase):
    def test_requested_power_steps(self):
        self.assertEqual(app.INPUT_STEPS, {'baseline':('0.25','5'),'lens':('0.25','10'),'over':('0.25','5')})

    def test_lists_have_exact_steps_and_endpoints(self):
        for q, aq in app.INPUT_STEPS.values():
            for lo, hi in [('-30','25'),('-15','15'),('-15','0')]:
                values=[Decimal(v) for v in app.options_for(lo,hi,q,2)]
                self.assertEqual(values[0], Decimal(0))
                self.assertEqual(len(values), len(set(values)))
                self.assertEqual(min(values), Decimal(lo))
                self.assertEqual(max(values), Decimal(hi))
                ordered=sorted(values)
                self.assertTrue(all(b-a==Decimal(q) for a,b in zip(ordered,ordered[1:])))
                self.assertEqual(values[1], -Decimal(q))
            values=[int(v) for v in app.options_for('0','180',aq,0)]
            self.assertEqual(values, list(range(0,181,int(aq))))

    def test_all_auxiliary_numeric_lists_start_at_zero(self):
        for args in [('0','25','0.5',1),('0','30','1',0),('0','5','0.05',2),
                     ('0','180','1',0),('-30','25','0.25',2),('-15','0','0.25',2)]:
            values=app.options_for(*args)
            self.assertEqual(Decimal(values[0]), 0)

    def test_invalid_option_definitions_rejected(self):
        for args in [('0','1','0',2),('1','0','1',0),('0','NaN','1',0)]:
            with self.assertRaises(ValueError): app.options_for(*args)

    def test_direct_entry_normalized(self):
        for raw in ['-3.25','−3.25','－３．２５','-3.25 D','-3.250']:
            self.assertEqual(app.parse_value(raw,label='S',minimum=-30,maximum=25,step='0.25'),-3.25)

    def test_hundredth_entry(self):
        self.assertEqual(app.parse_value('-0.43',label='C',minimum=-15,maximum=15,step='0.01'),-.43)

    def test_invalid_values_not_silently_rounded(self):
        for raw in ['NaN','Infinity','abc','30','-31']:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                app.parse_value(raw,label='S',minimum=-30,maximum=25,step='0.25')

    def test_arbitrary_precision_entry_not_quantized(self):
        for raw in ['-3.26','0.001','-3.13789','+2.12345']:
            self.assertEqual(app.parse_value(raw,label='S',minimum=-30,maximum=25,step='0.25'),float(raw))

    def test_axis_zero_and_degree_suffix(self):
        self.assertEqual(app.parse_value('０°',label='Ax',minimum=0,maximum=180,step='5',axis=True),180)
        self.assertEqual(app.parse_value('175°',label='Ax',minimum=0,maximum=180,step='5',axis=True),175)

    def test_axis_step_not_enforced_for_direct_entry(self):
        for raw in ['175','37','37.5','17.1234']:
            self.assertEqual(app.parse_value(raw,label='Ax',minimum=0,maximum=180,step='10',axis=True),float(raw))

    def test_out_of_range_axes_still_rejected(self):
        for raw in ['-1','181','NaN','Infinity']:
            with self.assertRaises(ValueError):
                app.parse_value(raw,label='Ax',minimum=0,maximum=180,axis=True)

    def test_numbering_updated_everywhere(self):
        text=Path(app.__file__).read_text()
        self.assertIn('03｜装用後の屈折値',text)
        self.assertIn('04｜次に試せる軸の候補',text)
        for old in ['04｜装用後','04 装用後','05｜','01−04','01と04','と04を']:
            self.assertNotIn(old,text)

    def test_demo_function_and_labels_removed(self):
        text=Path(app.__file__).read_text()
        self.assertFalse(hasattr(app,'load_demo'))
        self.assertNotIn('デモ',text)
        self.assertFalse((Path(app.__file__).parent/'examples').exists())

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
        self.assertEqual(p['app_version'],'0.3.0')
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

    def test_arbitrary_values_preserve_reference_calculation(self):
        for rotation,axis in [(10,10),(-10,170),(0,180)]:
            fill_reference(rotation)
            c,e=app.build_case()
            a=app.analyze_case(c)
            self.assertAlmostEqual(display_axis(a.best.axis),axis)
            self.assertLess(a.best.cylinder_abs,1e-10)
            self.assertEqual(c.over_refraction.sphere,float(app.st.session_state['over_s']))
            self.assertEqual(c.over_refraction.cylinder,float(app.st.session_state['over_c']))

    def test_empty_inputs_rejected(self):
        with self.assertRaises(ValueError):app.build_case()

    def test_old_rotation_input_ignored(self):
        fill_reference(10)
        c1,e1=app.build_case()
        app.st.session_state['rotation_amount']=55
        app.st.session_state['rotation_direction']='反時計回り（−）'
        c2,e2=app.build_case()
        self.assertEqual(e1,e2)

    def test_blank_over_axis_allowed_when_c_zero(self):
        fill_reference(10)
        app.st.session_state.update(over_s='0.00',over_c='0.00',over_a=None)
        c,e=app.build_case()
        self.assertEqual(display_axis(app.analyze_case(c).best.axis),180)

    def test_arbitrary_baseline_step_accepted(self):
        fill_reference(10)
        app.st.session_state['baseline_s']='-3.13'
        c,e=app.build_case()
        self.assertEqual(c.baseline.sphere,-3.13)

    def test_arbitrary_values_in_all_nine_rx_fields(self):
        for prefix in ('baseline','lens','over'):
            app.st.session_state.update({f'{prefix}_s':'-3.13789',f'{prefix}_c':'-1.2345',f'{prefix}_a':'37.345'})
            rx=app.read_rx(prefix,prefix)
            self.assertEqual(rx.sphere,-3.13789)
            self.assertEqual(rx.cylinder,-1.2345)
            self.assertAlmostEqual(rx.axis,37.345)

    def test_arbitrary_auxiliary_values(self):
        fill_reference(10)
        app.st.session_state.update(baseline_vertex='12.35',over_vertex='11.17',
                                   rotation_half_width='2.37',discrepancy_threshold='0.017')
        c,e=app.build_case()
        self.assertEqual(c.baseline_vertex_mm,12.35)
        self.assertEqual(c.over_vertex_mm,11.17)
        self.assertEqual(c.rotation_half_width_deg,2.37)
        self.assertEqual(c.discrepancy_threshold_D,.017)

    def test_zero_threshold_is_valid(self):
        fill_reference(10)
        app.st.session_state['discrepancy_threshold']='0'
        c,e=app.build_case()
        self.assertEqual(c.discrepancy_threshold_D,0)
        self.assertIsNotNone(app.analyze_case(c).best)

    def test_old_demo_state_removed_by_schema_migration(self):
        app.st.session_state.update(_schema='2.0',_demo=True,_result='stale')
        app.init_state()
        self.assertNotIn('_demo',app.st.session_state)
        self.assertNotIn('_result',app.st.session_state)
        self.assertEqual(app.st.session_state['_schema'],'3.0')

    def test_export_uses_new_numbering_and_preserves_input_precision(self):
        fill_reference(10)
        app.st.session_state['over_s']='0.217060222'
        c,e=app.build_case()
        a=app.analyze_case(c)
        self.assertEqual(app.export_payload(a,e)['input']['over_refraction']['S_D'],0.217060222)
        self.assertIn('03 装用後',app.summary_export(a,e))
        self.assertNotIn('04 装用後',app.summary_export(a,e))

    def test_custom_axes(self):
        fill_reference(10)
        app.st.session_state.update(grid_mode=app.GRID_OPTIONS[3],available_axes=['90','180'])
        c,e=app.build_case()
        self.assertEqual(len(app.analyze_case(c).candidates),2)

    def test_empty_custom_axes_rejected(self):
        fill_reference(10)
        app.st.session_state.update(grid_mode=app.GRID_OPTIONS[3],available_axes=[])
        with self.assertRaises(ValueError):app.build_case()

    def test_custom_power(self):
        fill_reference(10)
        app.st.session_state.update(change_power=True,next_s='-2.513',next_c='-1.277')
        c,e=app.build_case()
        self.assertEqual(c.next_lens.sphere,-2.513)
        self.assertEqual(c.next_lens.cylinder,-1.277)

    def test_signature_changes_on_input(self):
        fill_reference(10)
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
