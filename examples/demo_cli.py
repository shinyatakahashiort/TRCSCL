"""Run from any directory: python examples/demo_cli.py. Synthetic examples only."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from optics import Rx, axis_grid, to_vector, from_vector, lens_on_eye
from engine import Case, analyze, fmt_axis, fmt_rx


def main():
    target=Rx(-3,-1.25,180)
    for rotation in (10.0,-10.0):
        over=from_vector(to_vector(target)-to_vector(lens_on_eye(target,rotation)))
        result=analyze(Case(target,target,over,rotation,axis_grid(10),0,0,
                            stability="安定している",source="架空デモ"))
        print(f"rotation CW-positive: {rotation:+.1f} degrees")
        print("over-refraction at cornea:", fmt_rx(over))
        print("next LABEL axis:", fmt_axis(result.best.axis))
        print("predicted residual:", fmt_rx(result.best.residual_cornea))
        print()


if __name__ == '__main__':
    main()
