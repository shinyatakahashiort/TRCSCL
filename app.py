"""Toric SCL Axis Planner 0.4.0.

Run: python -m streamlit run app.py
UI update: sections 01/03 SPH lists ascend from -20 D to +20 D around 0.
Only these two fields default to 0.00 D. Direct entry remains unrestricted by list step.
Rotation is ESTIMATED from baseline minus over-refraction, never assumed zero.
Clinical validity of this inverse model has NOT been established.
Replace only app.py in the preceding 0.3.1 installation.
Adds an independent baseline-only, two-meridian vertex conversion panel.
Theoretical powers and explicitly rounded 0.25 D reference powers are separate.
Existing input lists and the axis/rotation inference calculation are unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import lru_cache
import json
import unicodedata

import pandas as pd

from optics import (
    Rx, axis_grid, display_axis, from_vector, lens_on_eye, parse_axes,
    signed_axis_difference, to_cornea, to_vector,
)
from engine import (
    Analysis, Case, REFERENCES, analyze, csv_export, fmt_axis, fmt_rx,
)
from visuals import curve_figure, axis_figure

VERSION = "0.4.0"
SCHEMA_VERSION = "3.0"
# A conservative numerical guard, NOT a validated clinical cutoff.
MIN_INFERENCE_C = 0.05
INFERENCE_NOTE = (
    "回転の実測値は使用していません。装用前と装用後の屈折値から眼上軸を推定し、"
    "次レンズでも同じ回転が生じると仮定した参考計算です。"
    "屈折状態が変わらず、レンズの効果を同一角膜面の薄レンズとして表せることを仮定します。"
    "この推定方式は臨床未検証で、実測した回転量の代用を保証するものではありません。"
)
GRID_OPTIONS = ["10°刻み（仮の候補）", "5°刻み（仮の候補）", "1°刻み（理論比較）", "使用可能な軸を選択・入力"]
INPUT_STEPS = {"baseline": ("0.25", "5"), "lens": ("0.25", "10"), "over": ("0.25", "5")}
STATE_DEFAULTS = {
    "eye": "右眼 OD",
    "baseline_s": "0.00", "baseline_c": None, "baseline_a": None,
    "baseline_vertex": "12.0",
    "lens_s": None, "lens_c": None, "lens_a": None,
    "over_s": "0.00", "over_c": None, "over_a": None, "over_vertex": "12.0",
    "measurement": "他覚的屈折（SCL装用下）", "grid_mode": GRID_OPTIONS[0],
    "available_axes": ["10", "20", "30", "40", "50", "60", "70", "80", "90", "100", "110", "120", "130", "140", "150", "160", "170", "180"],
    "change_power": False, "next_s": None, "next_c": None,
    "rotation_half_width": "5", "discrepancy_threshold": "0.50", "consent": False,
}


VERTEX_REFERENCE = {
    "title": "J&J Vision Professional：Fitting Calculator（両主経線の頂点間距離補正）",
    "url": "https://www.acuvue.com/en-au/professionals/simplifit-fitting-calculator/",
}
VERTEX_NOTE = (
    "01の自覚的屈折値を角膜面へ換算した、初回試験装用の度数選択の目安です。"
    "S・Cの0.25 D丸め候補は製品の製作範囲・乱視度数・軸規格・在庫と未照合です。"
    "レンズ回転・フィッティングを補正した最終処方ではありません。"
    "実際の製品規格に合わせ、装用後の視力・追加矯正・フィッティングで確認してください。"
)
VERTEX_ROUNDING_NOTE = (
    "理論値を求めた後にSとCをそれぞれ最も近い0.25 Dへ丸めます。"
    "ちょうど中間の値は絶対値が大きい側へ丸めます。"
    "Axは丸めず、マイナス円柱表記に統一した軸を保持します。"
    "これは数値上の丸め候補で、残余屈折を最小化した製品選択ではありません。"
)


@dataclass(frozen=True)
class VertexSCLRecommendation:
    """Baseline-only conversion; never uses the current lens or over-refraction."""
    original: Rx
    vertex_mm: float
    theoretical: Rx
    quarter_diopter: Rx
    rounding_residual: Rx

    def to_dict(self) -> dict:
        return {
            "source": "01_subjective_refraction_only",
            "spectacle_refraction": self.original.to_dict(),
            "vertex_distance_mm": self.vertex_mm,
            "theoretical_corneal_minus_cylinder": self.theoretical.to_dict(),
            "reference_S_C_rounded_to_0_25_D": self.quarter_diopter.to_dict(),
            "rounding_residual_cornea_no_rotation": self.rounding_residual.to_dict(),
            "rounding_rule": VERTEX_ROUNDING_NOTE,
            "rotation_compensated": False,
            "product_specifications_checked": False,
            "written_back_to_02": False,
            "note": VERTEX_NOTE,
        }


def round_quarter_diopter(value: float) -> float:
    """Nearest 0.25 D, ties away from zero; never round a source input in place."""
    try:
        d = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("丸め対象の度数には数値を指定してください。") from exc
    if not d.is_finite():
        raise ValueError("丸め対象の度数には有限の数値を指定してください。")
    q = Decimal("0.25")
    rounded = (d / q).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * q
    return 0.0 if rounded == 0 else float(rounded)


def recommend_scl_from_baseline(baseline: Rx, vertex_mm: float) -> VertexSCLRecommendation:
    """Vertex BOTH principal powers S and S+C, then reconstruct S/C/Axis.

    Reuses the established optics.to_cornea helper, including its singularity
    checks and plus-to-minus-cylinder transposition. Rounding is a display-only
    reference and is never fed into the existing rotation inference model.
    """
    exact = to_cornea(baseline, vertex_mm)
    rounded = Rx(round_quarter_diopter(exact.sphere),
                 round_quarter_diopter(exact.cylinder), exact.axis)
    residual = from_vector(to_vector(exact) - to_vector(rounded))
    return VertexSCLRecommendation(baseline, float(vertex_mm), exact, rounded, residual)


def baseline_recommendation_from_state() -> VertexSCLRecommendation | None:
    """Incomplete 01 gives no result; malformed input raises, never reuses a cache."""
    state = st.session_state
    raw = [state.get(k) for k in ("baseline_s", "baseline_c", "baseline_vertex")]
    if any(v is None or str(v).strip() == "" for v in raw):
        return None
    c = parse_value(state["baseline_c"], label="01 自覚 C", minimum=-15, maximum=15)
    if c != 0 and (state.get("baseline_a") is None or str(state["baseline_a"]).strip() == ""):
        return None
    baseline = read_rx("baseline", "01 自覚")
    vd = required_value("baseline_vertex", "装用前の頂点間距離", 0, 25, "0.5")
    return recommend_scl_from_baseline(baseline, vd)


def vertex_power_text(value: float, digits: int = 3) -> str:
    """Avoid showing a negative zero caused solely by numeric presentation."""
    if abs(value) < 0.5 * 10 ** (-digits):
        value = 0.0
    return f"{value:+.{digits}f}"


def vertex_axis_text(axis: float | None) -> str:
    """Retain non-grid axes for this conversion instead of rounding to product axes."""
    if axis is None:
        return "—（C=0）"
    return f"{display_axis(axis):.10f}".rstrip("0").rstrip(".") + "°"


def vertex_rx_text(rx: Rx, digits: int = 3) -> str:
    return (f"S {vertex_power_text(rx.sphere, digits)} D / "
            f"C {vertex_power_text(rx.cylinder, digits)} D / Ax {vertex_axis_text(rx.axis)}")


def vertex_summary(rec: VertexSCLRecommendation, eye: str = "") -> str:
    return "\n".join([
        f"トーリックSCL 軸選択 v{VERSION}｜01の頂点間距離補正",
        f"対象眼：{eye}" if eye else "対象眼：未指定",
        f"01 自覚的屈折値：{vertex_rx_text(rec.original, 6)}",
        f"頂点間距離：{rec.vertex_mm:g} mm → 角膜面 0 mm",
        f"理論値（マイナス円柱）：{vertex_rx_text(rec.theoretical, 6)}",
        f"S・Cを0.25 Dへ丸めた参考候補：{vertex_rx_text(rec.quarter_diopter, 2)}",
        f"丸めのみの理論残余（角膜面・回転なし）：{vertex_rx_text(rec.rounding_residual, 6)}",
        VERTEX_ROUNDING_NOTE, VERTEX_NOTE,
        "02・03の値はこの換算に使用せず、02へ自動入力もしません。",
        f"参照（両主経線の補正）：{VERTEX_REFERENCE['url']}",
    ]) + "\n"


def show_baseline_scl_recommendation() -> None:
    """Live 01-only panel, refreshed at every committed widget edit."""
    st.divider()
    st.markdown("#### 頂点間距離補正後のSCL度数")
    try:
        rec = baseline_recommendation_from_state()
    except ValueError as exc:
        st.warning(f"SCL度数を計算できません：{exc}")
        return
    if rec is None:
        st.caption("01のS・C・Axと頂点間距離を入力すると自動表示します。C=0ではAx不要です。02・03の入力は不要です。")
        return
    exact, rounded = rec.theoretical, rec.quarter_diopter
    st.caption(f"01の入力を使用 ／ VD {rec.vertex_mm:g} mm → 0 mm ／ マイナス円柱表記")
    st.markdown("**① 角膜面での理論値（0.25 Dへの丸め前）**")
    s_col, c_col, a_col = st.columns(3)
    s_col.metric("理論 S（D）", vertex_power_text(exact.sphere))
    c_col.metric("理論 C（D）", vertex_power_text(exact.cylinder))
    a_col.metric("理論 Ax", vertex_axis_text(exact.axis))
    st.markdown("**② 初回SCL度数の参考候補（S・C：0.25 D単位）**")
    st.success(vertex_rx_text(rounded, 2))
    st.caption("回転補正なし・製品規格未照合の参考候補です。入力値と02のSCL度数は変更しません。")
    if rec.original.cylinder > 0:
        st.caption("プラス円柱入力は、等価なマイナス円柱表記へ換算しています（軸は90°転換）。")
    if rounded.cylinder == 0:
        st.caption("この丸め候補はC=0のため軸指定はありません。球面候補の表示は可能ですが、下段のトーリック軸比較はC≠0のSCLが対象です。")
    with st.expander("補正の内訳・丸め方法・注意点"):
        original_minus = rec.original.minus_cylinder()
        st.write("SとS＋Cの両主経線をそれぞれ換算し、換算後の差からCを求めます。Cだけを単独で補正しません。")
        st.latex(r"F'_1=\frac{S}{1-dS},\quad F'_2=\frac{S+C}{1-d(S+C)}")
        st.latex(r"S_{CL}=F'_1,\quad C_{CL}=F'_2-F'_1,\quad d=\mathrm{VD(mm)}/1000")
        st.table(pd.DataFrame([
            {"主経線": "軸方向（S）", "補正前（D）": f"{original_minus.sphere:+.4f}",
             "角膜面（D）": f"{exact.sphere:+.4f}"},
            {"主経線": "直交方向（S＋C）", "補正前（D）": f"{original_minus.sphere + original_minus.cylinder:+.4f}",
             "角膜面（D）": f"{exact.sphere + exact.cylinder:+.4f}"},
        ]))
        st.caption("内訳はマイナス円柱表記です。理論値の内部計算は丸めず、表示のみ小数桁数を整えています。")
        st.write(VERTEX_ROUNDING_NOTE)
        st.write("丸めのみの理論残余（角膜面・回転なし）：" + vertex_rx_text(rec.rounding_residual))
        st.caption("この残余は丸めの影響だけを示します。実際の装用後残余屈折の予測ではありません。")
        st.warning(VERTEX_NOTE)
        st.caption("VD=0 mmでは再補正しません。VDの初期値12 mmは実測値ではないので、自覚検査時の値を確認してください。")
        st.markdown(f"[{VERTEX_REFERENCE['title']}]({VERTEX_REFERENCE['url']})")
        st.download_button(
            "頂点間距離補正メモを保存", vertex_summary(rec, st.session_state.get("eye", "")),
            file_name="scl_vertex_conversion.txt", mime="text/plain", key="vertex_memo_download",
        )


@dataclass(frozen=True)
class RotationEstimate:
    clockwise_deg: float
    on_eye_axis_deg: float
    implied_lens: Rx
    fitted_lens: Rx
    delta_M: float
    delta_C: float

    def to_dict(self) -> dict:
        return {
            "source": "inferred_from_baseline_minus_over_refraction_NOT_observed",
            "clockwise_deg": self.clockwise_deg,
            "on_eye_axis_deg": display_axis(self.on_eye_axis_deg),
            "implied_lens_cornea": self.implied_lens.to_dict(),
            "nominal_lens_fitted_to_inferred_axis": self.fitted_lens.to_dict(),
            "nominal_minus_implied_M_D": self.delta_M,
            "nominal_minus_implied_abs_C_D": self.delta_C,
            "note": INFERENCE_NOTE,
        }


def estimate_rotation(baseline: Rx, lens: Rx, over: Rx, baseline_vd: float, over_vd: float) -> RotationEstimate:
    """Inverse thin-lens model, with nominal minus cylinder constrained in magnitude.

    L_implied = B_cornea - R_cornea. Its J0/J45 direction estimates the on-eye
    minus-cylinder axis. Fit the nominal S/C at that axis, then use fitted L + R
    as the target. This projects inconsistent data instead of pretending they
    fit exactly. The fit discrepancies are exposed; they are NOT independent
    validation against baseline (baseline participates in this estimate).
    """
    if lens.cylinder >= 0 or lens.axis is None:
        raise ValueError("02のSCLには、Cが0でないマイナス円柱のトーリックSCLを入力してください。")
    implied_p = to_vector(to_cornea(baseline, baseline_vd)) - to_vector(to_cornea(over, over_vd))
    if implied_p.cylinder_magnitude < MIN_INFERENCE_C:
        raise ValueError(
            "01と03の差から得られる乱視補正成分が小さく、眼上軸を推定できません。"
            "入力値・測定面を再確認してください。回転を0°に置き換えた計算は行いません。"
            f"（推定を保留する便宜的な閾値：{MIN_INFERENCE_C:.2f} D未満）"
        )
    implied = from_vector(implied_p)
    rotation = signed_axis_difference(lens.axis, implied.axis)
    fitted = lens_on_eye(lens, rotation)
    return RotationEstimate(rotation, fitted.axis, implied, fitted,
                            fitted.m - implied.m, abs(lens.cylinder) - abs(implied.cylinder))


def parse_value(raw: object, *, label: str, minimum: float, maximum: float,
                step: str | None = None, axis: bool = False) -> float | None:
    """Parse finite in-range numbers without enforcing dropdown increments.

    ``step`` is retained for call compatibility only: it describes list options,
    not restrictions on a manually entered value. No grid quantization occurs.
    """
    if raw is None or str(raw).strip() == "":
        return None
    s = unicodedata.normalize("NFKC", str(raw)).strip()
    s = s.translate(str.maketrans({"−": "-", "–": "-", "—": "-", "﹣": "-"}))
    for suffix in ("mm", "MM", "D", "d", "°", "度"):
        if s.endswith(suffix):
            s = s[:-len(suffix)].strip()
            break
    try:
        d = Decimal(s)
    except InvalidOperation as exc:
        raise ValueError(f"{label}には数値を入力してください。") from exc
    if not d.is_finite():
        raise ValueError(f"{label}には有限の数値を入力してください。")
    if not Decimal(str(minimum)) <= d <= Decimal(str(maximum)):
        raise ValueError(f"{label}は{minimum:g}〜{maximum:g}の範囲で入力してください。")
    return 180.0 if axis and d == 0 else float(d)


@lru_cache(maxsize=32)
def options_for(minimum: str, maximum: str, step: str, decimals: int) -> tuple[str, ...]:
    """Exact dropdown grid: 0, negatives towards the minimum, then positives.

    For nonnegative lists (e.g. axes and VD), this is 0, step, 2*step, ... .
    This ordering changes the UI only and never changes calculation values.
    """
    lo, hi, q = Decimal(minimum), Decimal(maximum), Decimal(step)
    if not all(x.is_finite() for x in (lo, hi, q)) or q <= 0 or lo > hi:
        raise ValueError("選択肢の範囲・刻みが不正です。")
    if not 0 <= decimals <= 10:
        raise ValueError("選択肢の小数桁数が不正です。")
    values = [lo + i*q for i in range(int((hi-lo)/q)+1)]
    if lo <= 0 <= hi:
        values = [Decimal(0),
                  *sorted((v for v in values if v < 0), reverse=True),
                  *sorted(v for v in values if v > 0)]
    return tuple(f"{v:.{decimals}f}" for v in values)


def numeric_choice(label: str, key: str, minimum: str, maximum: str, step: str,
                   decimals: int = 2, help_text: str | None = None) -> None:
    st.selectbox(label, options_for(minimum, maximum, step, decimals), index=None,
                 key=key, accept_new_options=True,
                 placeholder="選択、または入力してEnter", help=help_text)


@lru_cache(maxsize=1)
def refraction_s_options() -> tuple[str, ...]:
    """Ascending 0.25 D list for 01/03 SPH only; 0 is the central entry.

    The dropdown contains 161 exact values from -20.00 to +20.00 D.
    Direct entries are still checked against read_rx's original numeric limits,
    not this convenience list, and are never rounded to its 0.25 D grid.
    """
    return tuple(f"{Decimal(i) / Decimal(4):.2f}" for i in range(-80, 81))


def signed_s_label(value: object) -> str:
    """Show + on positive built-in options without modifying returned values."""
    text = str(value)
    if text in refraction_s_options() and Decimal(text) > 0:
        return "+" + text
    return text


def refraction_s_choice(key: str) -> None:
    """Keep existing values; start an empty 01/03 SPH at the central 0 option."""
    if key not in ("baseline_s", "over_s"):
        raise ValueError("0中心のSリストは01・03専用です。")
    # This runs before the widget is rendered. It also migrates an unset value
    # from v0.3.0 without replacing a nonempty or manually entered value.
    if st.session_state.get(key) is None:
        st.session_state[key] = "0.00"
    st.selectbox(
        "S / SPH（D）", refraction_s_options(), index=None, key=key,
        format_func=signed_s_label, accept_new_options=True,
        placeholder="選択、または入力してEnter",
        help=("リストは−20.00〜＋20.00 D、0.25 D刻みです。"
              "0.00 Dの上がマイナス、下がプラスです。"
              "初期値は0.00 Dですので、測定値に合わせて変更してください。"
              "直接入力は従来の範囲（−30〜＋25 D）内で刻み制限なく入力できます。"),
    )


def init_state() -> None:
    # A schema change clears obsolete rotation keys and previously displayed results.
    if st.session_state.get("_schema") != SCHEMA_VERSION:
        clear_inputs()
    for key, value in STATE_DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = list(value) if isinstance(value, list) else value


def clear_inputs() -> None:
    for key in ("rotation_direction", "rotation_amount", "stability", "change_rotation",
                "next_rotation_direction", "next_rotation_amount", "axes_text",
                "_result", "_estimate", "_result_signature", "_demo"):
        st.session_state.pop(key, None)
    for key, value in STATE_DEFAULTS.items():
        st.session_state[key] = list(value) if isinstance(value, list) else value
    st.session_state["_schema"] = SCHEMA_VERSION


def input_signature() -> str:
    data = {k: st.session_state.get(k) for k in STATE_DEFAULTS}
    if not data["change_power"]:
        data.pop("next_s", None)
        data.pop("next_c", None)
    if data["grid_mode"] != GRID_OPTIONS[3]:
        data.pop("available_axes", None)
    return json.dumps(data, ensure_ascii=False, sort_keys=True, allow_nan=False)


def rx_inputs(prefix: str) -> None:
    power_step, axis_step = INPUT_STEPS[prefix]
    c1, c2, c3 = st.columns(3)
    with c1:
        if prefix in ("baseline", "over"):
            refraction_s_choice(f"{prefix}_s")
        else:
            numeric_choice("S / SPH（D）", f"{prefix}_s", "-30", "25", power_step)
    with c2:
        numeric_choice("C / CYL（D）", f"{prefix}_c", "-15", "0" if prefix == "lens" else "15", power_step)
    with c3:
        numeric_choice("Ax（°）", f"{prefix}_a", "0", "180", axis_step, 0,
                       "リストは0°から始まります。0°と180°は同じ軸です。直接入力は刻みに関係なく、小数の軸も入力できます。")
    st.caption(f"リスト：S・C {power_step} D刻み ／ Ax {axis_step}°刻み。直接入力は範囲内の任意の値を使えます（刻み制限・自動丸めなし）。")
    if prefix == "lens":
        st.caption("容器・処方に記載されたSCLの表示度数です。マイナス円柱表記で入力してください。")
    else:
        st.caption("Sのリスト：−20.00〜＋20.00 D。初期値0.00 Dから、上がマイナス・下がプラスです。")
        st.caption("プラス円柱も入力できます。C=0のとき、Axは空欄で構いません。")


def read_rx(prefix: str, label: str) -> Rx:
    q, aq = INPUT_STEPS[prefix]
    s = parse_value(st.session_state[f"{prefix}_s"], label=f"{label} S", minimum=-30, maximum=25, step=q)
    c = parse_value(st.session_state[f"{prefix}_c"], label=f"{label} C", minimum=-15,
                    maximum=0 if prefix == "lens" else 15, step=q)
    if s is None or c is None:
        raise ValueError(f"{label}のSとCを入力してください。")
    # Do not validate an irrelevant axis for a spherical refraction.
    a = None if c == 0 else parse_value(st.session_state[f"{prefix}_a"], label=f"{label} Ax",
                                       minimum=0, maximum=180, step=aq, axis=True)
    if c != 0 and a is None:
        raise ValueError(f"{label}のAxを入力してください。")
    return Rx(s, c, a)


def required_value(key: str, label: str, minimum: float, maximum: float, step: str) -> float:
    value = parse_value(st.session_state[key], label=label, minimum=minimum, maximum=maximum, step=step)
    if value is None:
        raise ValueError(f"{label}を入力してください。")
    return value


def build_case() -> tuple[Case, RotationEstimate]:
    baseline, lens, over = (read_rx(p, label) for p, label in
                            (("baseline", "01 装用前"), ("lens", "02 SCL"), ("over", "03 装用後")))
    bvd = required_value("baseline_vertex", "装用前の頂点間距離", 0, 25, "0.5")
    ovd = required_value("over_vertex", "装用後の頂点間距離", 0, 25, "0.5")
    estimate = estimate_rotation(baseline, lens, over, bvd, ovd)
    next_lens = None
    if st.session_state["change_power"]:
        ns = required_value("next_s", "次レンズ S", -30, 25, "0.25")
        nc = required_value("next_c", "次レンズ C", -15, 0, "0.25")
        next_lens = Rx(ns, nc, lens.axis)
    mode = st.session_state["grid_mode"]
    if mode == GRID_OPTIONS[3]:
        axes = parse_axes(",".join(st.session_state["available_axes"]))
    else:
        axes = axis_grid([10, 5, 1][GRID_OPTIONS.index(mode)])
    case = Case(
        baseline=baseline, lens=lens, over_refraction=over, rotation_cw=estimate.clockwise_deg,
        axes=axes, baseline_vertex_mm=bvd, over_vertex_mm=ovd, next_lens=next_lens,
        next_rotation_cw=None,
        rotation_half_width_deg=required_value("rotation_half_width", "変動幅", 0, 30, "1"),
        eye="OD" if st.session_state["eye"] == "右眼 OD" else "OS",
        stability="未確認（屈折値からの推定）", measurement=st.session_state["measurement"],
        source="選択・直接入力",
        discrepancy_threshold_D=required_value("discrepancy_threshold", "不一致確認閾値", 0, 5, "0.05"),
    )
    return case, estimate


def analyze_case(case: Case) -> Analysis:
    result = analyze(case)
    warnings = []
    for warning in result.warnings:
        if warning.startswith("回転の安定"):
            continue  # Replaced by a prominent inference disclosure in the UI/exports.
        if warning.startswith("装用前の矯正値と装用後"):
            warning = ("入力したSCLのS/Cと、01−03から求めたレンズ効果が設定閾値を超えて一致しません。"
                       "回転だけでは入力値を説明できないため、この結果で処方を決定しないでください。"
                       "測定値・頂点間距離・屈折状態を再確認してください。")
        warnings.append(warning)
    return replace(result, warnings=tuple(warnings))


def export_payload(result: Analysis, estimate: RotationEstimate) -> dict:
    data = result.to_dict()
    data["app_version"] = VERSION
    data["schema_version"] = SCHEMA_VERSION
    data["model_warning"] = INFERENCE_NOTE
    data["basis"] = "baseline minus over-refraction estimates lens orientation; fitted nominal SCL plus over-refraction estimates target"
    data["rotation_estimation"] = estimate.to_dict()
    # Older engine exports a known-rotation model. Relabel it explicitly here.
    inputs = data.get("input", data.get("inputs", {}))
    inputs.pop("current_rotation_cw_deg", None)
    inputs.pop("assumed_next_rotation_cw_deg", None)
    data["derived"]["estimated_current_on_eye_SCL"] = data["derived"].pop("current_on_eye_SCL")
    # These comparisons use the same inferred rotation; they are not independent.
    for key in ("baseline_only_optimal_label_axis_deg", "baseline_only_best_available",
                "baseline_predicted_residual_at_primary_best_cornea"):
        data["result"].pop(key, None)
    data["assumptions"] = {"rotation_was_measured": False,
                           "next_rotation_equals_estimated_current_rotation": True,
                           "estimated_next_rotation_cw_deg": estimate.clockwise_deg,
                           "baseline_used_in_estimation_not_independent_validation": True}
    data["result"]["warnings"] = [INFERENCE_NOTE, *result.warnings]
    data["initial_scl_from_baseline"] = recommend_scl_from_baseline(
        result.case.baseline, result.case.baseline_vertex_mm).to_dict()
    data["sensitivity_scope"] = "Next-rotation scenarios only; excludes estimation/refraction error. NOT a confidence interval."
    return data


def summary_export(result: Analysis, estimate: RotationEstimate) -> str:
    c = result.case
    lines = [f"トーリックSCL 軸選択 v{VERSION}", "回転未測定・屈折値からの推定モデル", INFERENCE_NOTE,
             f"対象眼：{c.eye} / {c.source}", f"01 装用前：{fmt_rx(c.baseline)} / VD {c.baseline_vertex_mm:g} mm",
             f"02 SCL表示度数：{fmt_rx(c.lens)}", f"03 装用後：{fmt_rx(c.over_refraction)} / VD {c.over_vertex_mm:g} mm",
             f"眼上軸の推定：{fmt_axis(estimate.on_eye_axis_deg)}",
             f"回転の推定（実測ではない、時計回り正）：{estimate.clockwise_deg:+.2f}°",
             f"次レンズ固定度数：S {c.next_lens.sphere:+.2f} D / C {c.next_lens.cylinder:+.2f} D",
             f"モデル不一致：ΔM {estimate.delta_M:+.3f} D / Δ|C| {estimate.delta_C:+.3f} D"]
    if result.best:
        lines += [f"最小となる候補表示軸：{fmt_axis(result.best.axis)}",
                  f"予測残余屈折（角膜面）：{fmt_rx(result.best.residual_cornea)}"]
    else:
        lines += ["最適軸は一意に決定できません。"]
    vertex = recommend_scl_from_baseline(c.baseline, c.baseline_vertex_mm)
    lines += ["01からの頂点間距離補正（下記は回転補正と別計算）：",
              "角膜面理論値：" + vertex_rx_text(vertex.theoretical, 6),
              "0.25 D参考候補：" + vertex_rx_text(vertex.quarter_diopter, 2),
              VERTEX_NOTE]
    lines += ["注意：" + x for x in result.warnings]
    return "\n".join(lines) + "\n"


def candidate_frame(result: Analysis) -> pd.DataFrame:
    return pd.DataFrame([{
        "順位": i+1, "表示軸（°）": display_axis(x.axis), "予測眼上軸（°）": display_axis(x.on_eye_axis),
        "残余 |C|（D）": x.cylinder_abs, "残余 S（D）": x.residual_cornea.sphere,
        "残余 C（D）": x.residual_cornea.cylinder,
        "残余軸（°）": display_axis(x.residual_cornea.axis) if x.cylinder_abs >= .005 else None,
        "回転変動時の最大 |C|（D）": x.maximum_C,
    } for i, x in enumerate(result.candidates)])


def show_results(result: Analysis, estimate: RotationEstimate) -> None:
    c, best = result.case, result.best
    st.divider()
    st.subheader("計算結果｜次に試すレンズの比較（推定モデル）")
    st.info(INFERENCE_NOTE)
    st.caption(f"{c.eye} / {c.source} / 残余屈折は角膜面で比較")
    for warning in result.warnings:
        st.warning(warning)
    if best:
        a, b, d = st.columns(3)
        a.metric("候補内で残余乱視が最小の表示軸", fmt_axis(best.axis))
        b.metric("そのレンズの予測眼上軸", fmt_axis(best.on_eye_axis))
        d.metric("予測残余 |C|（角膜面）", f"{best.cylinder_abs:.2f} D")
        st.markdown(f"**次に試す候補：S {c.next_lens.sphere:+.2f} D / C {c.next_lens.cylinder:+.2f} D × {fmt_axis(best.axis)}**")
        st.write(f"予測残余屈折（角膜面）：{fmt_rx(best.residual_cornea)}")
        st.caption(f"装用後の測定面（VD {c.over_vertex_mm:g} mm）：{fmt_rx(best.residual_spectacle)}")
        st.caption(f"連続値の理論最適表示軸：{fmt_axis(result.continuous.axis)}。現在の表示軸からの変更：{best.label_change:+.1f}°。眼上のレンズを手で回す指示ではありません。")
        if len(result.tied_best_axes) > 1:
            st.caption("同率最小：" + " / ".join(fmt_axis(a) for a in result.tied_best_axes))
    else:
        st.info("どの軸でも同じ評価となるため、最適軸を1つに選べません。")
    a, b = st.columns(2)
    a.metric("軸だけを変えた場合の理論最小 |C|", f"{result.lower_bound_C:.2f} D")
    b.metric("予測残余球面等価 M", f"{result.target_vector.m-c.next_lens.m:+.2f} D")
    t1, t2, t3, t4 = st.tabs(["候補軸と残余乱視", "軸の図（推定）", "推定条件と不一致", "計算式・結果保存"])
    with t1:
        st.plotly_chart(curve_figure(result), use_container_width=True, config={"displayModeBar": False}, key="curve")
        st.dataframe(candidate_frame(result), hide_index=True, use_container_width=True,
                     column_config={key: st.column_config.NumberColumn(format="%.2f") for key in
                                    ["表示軸（°）", "予測眼上軸（°）", "残余 |C|（D）", "残余 S（D）", "残余 C（D）", "残余軸（°）", "回転変動時の最大 |C|（D）"]})
        if best:
            st.caption(f"次レンズの回転が推定値から±{c.rotation_half_width_deg:g}°変動する仮想条件では、残余 |C| は{best.minimum_C:.3f}〜{best.maximum_C:.3f} Dです。")
        st.caption("変動幅は信頼区間ではありません。屈折値から回転を推定する際の誤差は含みません。製品規格・在庫は別途確認してください。")
    with t2:
        fig = axis_figure(result)
        for trace in fig.data:
            if trace.name:
                trace.name = trace.name.replace("現在の眼上軸", "現在の推定眼上軸").replace("基準 / 現在（例）", "基準 / 推定位置（例）")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False}, key="axes_diagram")
        st.caption("図中の眼上軸・マーク位置は屈折値からの推定図で、実際に観察したものではありません。")
    with t3:
        st.write(f"現在の推定眼上軸：**{fmt_axis(estimate.on_eye_axis_deg)}** ／ 回転の推定値：{estimate.clockwise_deg:+.2f}°（検者正面・時計回り正、実測ではありません）")
        st.dataframe(pd.DataFrame([
            {"項目": "01 装用前（角膜面）", "S/C/Axis": fmt_rx(result.baseline_cornea)},
            {"項目": "03 装用後（角膜面）", "S/C/Axis": fmt_rx(result.over_cornea)},
            {"項目": "01−03から得られるレンズ効果", "S/C/Axis": fmt_rx(estimate.implied_lens)},
            {"項目": "02のS/Cを推定眼上軸に配置", "S/C/Axis": fmt_rx(result.current_actual)},
            {"項目": "計算に使用する必要矯正の推定", "S/C/Axis": fmt_rx(result.inferred_target)},
        ]), hide_index=True, use_container_width=True)
        a, b = st.columns(2)
        a.metric("02と推定レンズ効果の差 ΔM", f"{estimate.delta_M:+.3f} D")
        b.metric("02と推定レンズ効果の差 Δ|C|", f"{estimate.delta_C:+.3f} D")
        st.warning("01は眼上軸の推定にも使用しています。この不一致評価は独立した検証ではありません。差が小さくても推定回転が正しいことは保証されません。")
        st.caption(f"不一致の注意表示：|ΔM|または|Δ|C||が{c.discrepancy_threshold_D:g} Dを超える場合。臨床的な合否基準ではなく便宜的な設定です。")
    with t4:
        st.markdown("**両主経線を角膜面に換算し、パワーベクトルで計算します。**")
        st.latex(r"F_c=F_s/(1-dF_s)\quad(F_s=S,\;S+C)")
        st.latex(r"M=S+C/2,\quad J_0=-(C/2)\cos(2A),\quad J_{45}=-(C/2)\sin(2A)")
        st.latex(r"\mathbf L_{implied}=\mathbf B_{cornea}-\mathbf R_{cornea}")
        st.latex(r"A_{eye}=\tfrac12\operatorname{atan2}(J_{45,L},J_{0,L}),\quad r=A_{label}-A_{eye}\pmod{180^\circ}")
        st.write("この方向に02のS/Cを配置した推定レンズ効果と03を加えて必要矯正を再構成し、各候補レンズの効果を差し引きます。01をさらに加算することはありません。")
        st.latex(r"\mathbf T=\mathbf L_{nominal}(A_{eye})+\mathbf R_{cornea},\quad \mathbf P_{res}(a)=\mathbf T-\mathbf L_{next}(a-r)")
        st.caption("屈折値から回転を推定する逆計算は本アプリ独自のモデルで、下記資料がその臨床的妥当性を保証するものではありません。")
        a, b, d = st.columns(3)
        a.download_button("入力・全結果 JSON", json.dumps(export_payload(result, estimate), ensure_ascii=False, indent=2, allow_nan=False), file_name=f"toric_result_{c.eye}.json", mime="application/json", use_container_width=True)
        b.download_button("候補一覧 CSV", csv_export(result), file_name=f"toric_candidates_{c.eye}.csv", mime="text/csv", use_container_width=True)
        d.download_button("計算メモ TXT", summary_export(result, estimate), file_name=f"toric_summary_{c.eye}.txt", mime="text/plain", use_container_width=True)
        for ref in REFERENCES:
            st.markdown(f"[{ref['title']}]({ref['url']})")


def main() -> None:
    # Lazy import makes the input-validation and inverse-optics functions testable
    # without a Streamlit installation. It is still required to run the UI.
    global st
    import streamlit as st

    st.set_page_config(page_title="Toric SCL Axis Planner", page_icon="◉", layout="wide")
    init_state()
    st.markdown("""<style>.block-container {max-width:1160px;padding-top:2rem;}
        h1 {letter-spacing:-.035em;} [data-testid="stMetricValue"] {font-variant-numeric:tabular-nums;}
        </style>""", unsafe_allow_html=True)
    st.caption(f"TORIC SCL · AXIS PLANNER · v{VERSION}")
    st.title("トーリックSCL 軸選択シミュレーター")
    st.write("01の自覚的屈折値から、頂点間距離を補正した **SCL度数の目安** を表示します。02・03も入力すると、次に試す **表示軸** を比較できます。回転の入力は不要です。")
    st.warning("教育・研究用／臨床未検証です。回転は屈折値からの推定であり、結果だけで処方を確定しないでください。")
    st.caption("01・03のSは0.00 Dを中心に、上がマイナス・下がプラスです。その他の数値リストは0から始まります。直接入力してEnterで確定することもでき、刻み制限・自動丸めはありません。")
    controls, eye_column = st.columns([3, 1])
    with controls:
        st.button("入力をクリア", on_click=clear_inputs)
    with eye_column:
        st.selectbox("対象眼", ["右眼 OD", "左眼 OS"], key="eye")
    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            st.subheader("01｜装用前の自覚的屈折値")
            rx_inputs("baseline")
            numeric_choice("装用前屈折値の頂点間距離（mm）", "baseline_vertex", "0", "25", "0.5", 1)
            st.caption("自覚検査時の頂点間距離を設定してください。角膜面換算済みなら0 mmです。")
            show_baseline_scl_recommendation()
    with right:
        with st.container(border=True):
            st.subheader("02｜装用中SCLの表示度数")
            rx_inputs("lens")
            st.caption("初期設定は同じS・Cを維持した軸変更です。次レンズも同じ回転挙動を示すと仮定します。")
    with st.container(border=True):
        st.subheader("03｜装用後の屈折値")
        rx_inputs("over")
        x, y = st.columns(2)
        with x:
            st.selectbox("測定方法", ["他覚的屈折（SCL装用下）", "自覚的追加矯正（SCL装用下）"], key="measurement")
        with y:
            numeric_choice("装用後屈折値の頂点間距離（mm）", "over_vertex", "0", "25", "0.5", 1)
        st.caption("SCL装用下の残余屈折／追加矯正を入力します。裸眼時やSCL度数を合算済みの値は入力しません。")
    with st.container(border=True):
        st.subheader("04｜次に試せる軸の候補")
        st.selectbox("候補軸の指定方法", GRID_OPTIONS, key="grid_mode")
        if st.session_state["grid_mode"] == GRID_OPTIONS[3]:
            st.multiselect("使用可能な表示軸（°）", options_for("0", "180", "1", 0),
                           key="available_axes", accept_new_options=True,
                           placeholder="候補を選択、または軸を入力してEnter")
        st.caption("候補は製品規格・在庫を保証するものではありません。実際に使用できる表示軸を設定してください。")
    with st.expander("詳細設定｜次レンズのS/C、変動シナリオ"):
        st.checkbox("次レンズのS/Cを変更した場合を仮想比較する", key="change_power")
        if st.session_state["change_power"]:
            x, y = st.columns(2)
            with x:
                numeric_choice("次レンズ S（D）", "next_s", "-30", "25", "0.25")
            with y:
                numeric_choice("次レンズ C（D・マイナス円柱）", "next_c", "-15", "0", "0.25")
        numeric_choice("次レンズの回転変動シナリオ（±°）", "rotation_half_width", "0", "30", "1", 0)
        st.caption("実測回転の入力ではなく、予測回転が変わった場合の仮想比較です。±5°は信頼区間ではありません。")
        numeric_choice("モデル不一致の確認閾値（D・便宜的）", "discrepancy_threshold", "0", "5", "0.05",
                       help_text="0 Dを選ぶと、ごく小さい不一致でも注意を表示します。計算結果を変更する設定ではありません。")
    st.checkbox("測定面を確認し、回転は推定値で結果は処方確定値ではないことを理解した", key="consent")
    if st.button("残余乱視が最小になる軸を計算", type="primary", use_container_width=True):
        for key in ("_result", "_estimate", "_result_signature", "_demo"):
            st.session_state.pop(key, None)
        if not st.session_state["consent"]:
            st.error("上の確認欄にチェックしてから計算してください。")
        else:
            try:
                case, estimate = build_case()
                st.session_state["_result"] = analyze_case(case)
                st.session_state["_estimate"] = estimate
                st.session_state["_result_signature"] = input_signature()
            except ValueError as exc:
                st.error(str(exc))
    if "_result" in st.session_state:
        if st.session_state.get("_result_signature") != input_signature():
            st.info("入力が変更されました。古い結果は非表示です。計算ボタンで更新してください。")
        else:
            show_results(st.session_state["_result"], st.session_state["_estimate"])
    with st.expander("適用範囲・計算の仮定・データの扱い"):
        st.write(INFERENCE_NOTE)
        st.write("01と03の差が十分に得られず眼上軸を推定できない場合は、計算を保留します。SCLの変形・偏心・涙液・不正乱視・高次収差・調節変化などはモデル化していません。")
        st.write("入力はStreamlitサーバーで処理されます。本コードはDB保存・外部API送信・患者名やIDの収集を行いません。実データの扱いは施設の情報管理方針に従ってください。")
        for ref in REFERENCES:
            st.markdown(f"[{ref['title']}]({ref['url']})")


if __name__ == "__main__":
    main()
