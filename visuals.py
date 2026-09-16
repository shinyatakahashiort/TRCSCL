"""Interactive Plotly figure factories; independent of the Streamlit runtime."""
import math
import plotly.graph_objects as go
from optics import display_axis, residual_for_axis
from engine import Analysis, fmt_axis


def curve_figure(result: Analysis) -> go.Figure:
    c = result.case
    axes = list(range(181))
    values = [abs(residual_for_axis(result.target_vector, c.next_lens, a, c.next_rotation_cw).cylinder) for a in axes]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=axes, y=values, mode="lines", name="理論曲線",
                            hovertemplate="表示軸 %{x:.1f}°<br>残余 |C| %{y:.3f} D<extra></extra>"))
    ordered = sorted(result.candidates, key=lambda x: display_axis(x.axis))
    fig.add_trace(go.Scatter(x=[display_axis(x.axis) for x in ordered], y=[x.cylinder_abs for x in ordered],
                            mode="markers", name="入力した候補軸", marker={"size": 8},
                            hovertemplate="候補 %{x:.1f}°<br>残余 |C| %{y:.3f} D<extra></extra>"))
    if result.best:
        fig.add_trace(go.Scatter(x=[display_axis(result.best.axis)], y=[result.best.cylinder_abs], mode="markers",
                                name="候補内の最小", marker={"size": 16, "symbol": "star"}))
    fig.update_layout(height=385, margin={"l": 20, "r": 20, "t": 20, "b": 30},
                      xaxis_title="次に試すSCLの表示軸（°）", yaxis_title="予測残余 |C|（D・角膜面）",
                      xaxis={"range": [0, 180], "dtick": 30}, yaxis={"rangemode": "tozero"},
                      legend={"orientation": "h", "y": 1.12})
    return fig


def axis_figure(result: Analysis) -> go.Figure:
    fig = go.Figure()
    t = [math.radians(i) for i in range(361)]
    fig.add_trace(go.Scatter(x=[math.cos(v) for v in t], y=[math.sin(v) for v in t],
                            mode="lines", name="角度基準", showlegend=False, hoverinfo="skip",
                            line={"width": 1, "dash": "dot"}))
    entries = [("現在の眼上軸", result.current_actual.axis, "dash"),
               ("推定必要矯正の軸", result.inferred_target.axis, "dot")]
    if result.best:
        entries.append(("候補の予測眼上軸", result.best.on_eye_axis, "solid"))
    for name, a, dash in entries:
        if a is None:
            continue
        angle = math.radians(a)
        x, y = math.cos(angle), math.sin(angle)
        fig.add_trace(go.Scatter(x=[-x, x], y=[-y, y], mode="lines", name=f"{name} {fmt_axis(a)}",
                                line={"width": 3, "dash": dash}, hoverinfo="name"))
    for a in (0, 45, 90, 135, 180, 270):
        rad = math.radians(a)
        label = "0° = 180°" if a == 0 else ("6時" if a == 270 else f"{a}°")
        fig.add_annotation(x=1.17*math.cos(rad), y=1.17*math.sin(rad), text=label, showarrow=False)
    # Six-o'clock mark is illustrative only; it is NOT the cylinder axis.
    r = math.radians(result.case.rotation_cw)
    fig.add_trace(go.Scatter(x=[0, -math.sin(r)], y=[-1, -math.cos(r)], mode="markers",
                            name="6時マーク：基準 / 現在（例）", marker={"size": [8, 12], "symbol": ["circle-open", "diamond"]}))
    fig.update_layout(height=460, margin={"l": 20, "r": 20, "t": 10, "b": 30},
                      xaxis={"range": [-1.45, 1.45], "visible": False},
                      yaxis={"range": [-1.35, 1.35], "visible": False, "scaleanchor": "x"},
                      legend={"orientation": "h", "y": -0.02}, dragmode=False)
    return fig


