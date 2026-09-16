"""Print the new inverse-model demo without running Streamlit."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import estimate_rotation, analyze_case, summary_export
from optics import Rx, axis_grid
from engine import Case
b,l,o=Rx(-3,-1.25,180),Rx(-3,-1.25,180),Rx(.22,-.43,40)
e=estimate_rotation(b,l,o,0,0)
c=Case(b,l,o,e.clockwise_deg,axis_grid(10),baseline_vertex_mm=0,over_vertex_mm=0,source='架空デモ')
print(summary_export(analyze_case(c),e))
