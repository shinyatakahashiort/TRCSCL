"""Application model and reproducible exports. Streamlit-independent."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
import csv
import io
import json
from optics import (
    EPS, Rx, PowerVector, axis_distance, clean_axes, cylinder_range, display_axis,
    finite, from_vector, lens_on_eye, on_eye_axis, optimal_order_axis,
    residual_for_axis, signed_axis_difference, to_cornea, to_spectacle, to_vector,
)

VERSION = "0.1.0"
SCHEMA_VERSION = "1.0"
CONVENTION = "検者が患者の正面から見た時計回りを正とする。眼上軸=表示軸−回転量（180°周期）。右眼・左眼で符号を反転しない。"
MODEL_WARNING = (
    "教育・研究用の未臨床検証プロトタイプ。薄レンズ・同一角膜面でのベクトル和を仮定。"
    "次レンズの回転が入力どおり再現することを仮定し、視力・フィッティング・安全性は予測しない。"
    "結果は処方確定値ではない。自覚的追加矯正、装用状態および再装用後の評価が必要。"
)
REFERENCES = [
    {"title": "Thibos LN, Wheeler W, Horner D. Power vectors. Optom Vis Sci. 1997;74(6):367–375.",
     "url": "https://pubmed.ncbi.nlm.nih.gov/9255814/", "doi": "10.1097/00006324-199706000-00019"},
    {"title": "CooperVision Australia. Toric Fitting Guidelines (LARS/CAAS).",
     "url": "https://coopervision.net.au/practitioner/fitting-tips-and-tools/toolkits/biofinity/toric-fitting-guidelines"},
]


@dataclass(frozen=True)
class Case:
    baseline: Rx
    lens: Rx
    over_refraction: Rx
    rotation_cw: float
    axes: tuple[float, ...]
    baseline_vertex_mm: float = 12.0
    over_vertex_mm: float = 12.0
    next_lens: Rx | None = None
    next_rotation_cw: float | None = None
    rotation_half_width_deg: float = 5.0
    eye: str = "OD"
    stability: str = "未確認"
    measurement: str = "他覚的屈折（SCL装用下）"
    source: str = "手入力"
    discrepancy_threshold_D: float = 0.50

    def __post_init__(self) -> None:
        if self.eye not in ("OD", "OS"):
            raise ValueError("眼はODまたはOSで指定してください。")
        if self.lens.cylinder > EPS or (self.next_lens and self.next_lens.cylinder > EPS):
            raise ValueError("SCLはマイナス円柱表記で入力してください。")
        if self.lens.axis is None:
            raise ValueError("このアプリは装用中レンズのCが0でないトーリックSCLを対象とします。")
        for name in ("rotation_cw", "rotation_half_width_deg", "discrepancy_threshold_D"):
            object.__setattr__(self, name, finite(getattr(self, name), name))
        nr = self.rotation_cw if self.next_rotation_cw is None else finite(self.next_rotation_cw, "次の回転量")
        if abs(self.rotation_cw) > 90 or abs(nr) > 90:
            raise ValueError("回転量は−90〜+90°で設定してください。")
        if not 0 <= self.rotation_half_width_deg <= 30:
            raise ValueError("回転変動幅は0〜30°で設定してください。")
        if not 0.05 <= self.discrepancy_threshold_D <= 5:
            raise ValueError("確認閾値は0.05〜5.00 Dで設定してください。")
        object.__setattr__(self, "next_rotation_cw", nr)
        object.__setattr__(self, "next_lens", self.next_lens or self.lens)
        object.__setattr__(self, "axes", clean_axes(self.axes))


@dataclass(frozen=True)
class Candidate:
    axis: float
    on_eye_axis: float
    residual_cornea: Rx
    residual_spectacle: Rx
    minimum_C: float
    maximum_C: float
    label_change: float

    @property
    def cylinder_abs(self) -> float:
        return abs(self.residual_cornea.cylinder)

    def to_dict(self) -> dict:
        return {
            "label_axis_deg": display_axis(self.axis),
            "predicted_on_eye_axis_deg": display_axis(self.on_eye_axis),
            "residual_cornea": self.residual_cornea.to_dict(),
            "residual_over_refraction_plane": self.residual_spectacle.to_dict(),
            "residual_cornea_M_D": self.residual_cornea.m,
            "rotation_scenario_min_abs_C_D": self.minimum_C,
            "rotation_scenario_max_abs_C_D": self.maximum_C,
            "signed_label_axis_change_deg": self.label_change,
        }


@dataclass(frozen=True)
class Analysis:
    case: Case
    baseline_cornea: Rx
    over_cornea: Rx
    current_actual: Rx
    inferred_target: Rx
    target_vector: PowerVector
    discrepancy: PowerVector
    candidates: tuple[Candidate, ...]
    best: Candidate | None
    tied_best_axes: tuple[float, ...]
    continuous: Candidate | None
    baseline_continuous_axis: float | None
    baseline_best: Candidate | None
    baseline_predicted_current: Rx
    baseline_predicted_at_primary_best: Rx | None
    lower_bound_C: float
    warnings: tuple[str, ...]

    def to_dict(self) -> dict:
        c = self.case
        return {
            "schema_version": SCHEMA_VERSION,
            "app_version": VERSION,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "purpose": "unvalidated research / education simulation, not a prescription",
            "model_warning": MODEL_WARNING,
            "convention": CONVENTION,
            "objective": "Minimize corneal-plane residual |C|; keep selected next S/C fixed.",
            "basis": "on-eye current SCL vector + vertex-corrected OVER-refraction vector",
            "input": {
                "eye": c.eye, "source": c.source, "rotation_stability": c.stability,
                "over_refraction_measurement_type": c.measurement,
                "baseline": c.baseline.to_dict(), "baseline_vertex_mm": c.baseline_vertex_mm,
                "current_SCL": c.lens.to_dict(), "current_rotation_cw_deg": c.rotation_cw,
                "over_refraction": c.over_refraction.to_dict(), "over_refraction_vertex_mm": c.over_vertex_mm,
                "next_SCL_S_C_fixed": {"S_D": c.next_lens.sphere, "C_D": c.next_lens.cylinder},
                "assumed_next_rotation_cw_deg": c.next_rotation_cw,
                "candidate_axes_deg": [display_axis(a) for a in c.axes],
                "next_rotation_scenario_half_width_deg": c.rotation_half_width_deg,
                "discrepancy_check_threshold_D_unvalidated": c.discrepancy_threshold_D,
            },
            "derived": {
                "baseline_cornea": self.baseline_cornea.to_dict(),
                "over_refraction_cornea": self.over_cornea.to_dict(),
                "current_on_eye_SCL": self.current_actual.to_dict(),
                "inferred_total_required_correction_cornea": self.inferred_target.to_dict(),
                "inferred_total_power_vector": self.target_vector.to_dict(),
                "inferred_minus_baseline_vector": self.discrepancy.to_dict(),
                "baseline_predicted_current_residual_cornea": self.baseline_predicted_current.to_dict(),
            },
            "result": {
                "best_available_candidate": self.best.to_dict() if self.best else None,
                "tied_best_label_axes_deg": [display_axis(a) for a in self.tied_best_axes],
                "continuous_optimum": self.continuous.to_dict() if self.continuous else None,
                "axis_only_theoretical_lower_bound_abs_C_D": self.lower_bound_C,
                "baseline_only_optimal_label_axis_deg": display_axis(self.baseline_continuous_axis),
                "baseline_only_best_available": self.baseline_best.to_dict() if self.baseline_best else None,
                "baseline_predicted_residual_at_primary_best_cornea":
                    self.baseline_predicted_at_primary_best.to_dict() if self.baseline_predicted_at_primary_best else None,
                "all_candidates": [x.to_dict() for x in self.candidates],
                "warnings": list(self.warnings),
            },
            "sensitivity_scope": "Next rotation only. The inferred target is fixed; this is NOT a statistical confidence interval and does NOT propagate current-rotation or refraction measurement error.",
            "references": REFERENCES,
        }


def make_candidate(case: Case, target: PowerVector, axis: float) -> Candidate:
    residual = residual_for_axis(target, case.next_lens, axis, case.next_rotation_cw)
    lo, hi = cylinder_range(target, case.next_lens, axis, case.next_rotation_cw, case.rotation_half_width_deg)
    return Candidate(axis, on_eye_axis(axis, case.next_rotation_cw), residual,
                     to_spectacle(residual, case.over_vertex_mm), lo, hi,
                     signed_axis_difference(axis, case.lens.axis))


def ranked_candidates(case: Case, target: PowerVector) -> tuple[Candidate, ...]:
    items = [make_candidate(case, target, a) for a in case.axes]
    # Tie tolerance is numerical, not clinical. Prefer least LABEL change, then axis.
    return tuple(sorted(items, key=lambda x: (round(x.cylinder_abs, 10), abs(x.label_change), display_axis(x.axis))))


def analyze(case: Case) -> Analysis:
    baseline = to_cornea(case.baseline, case.baseline_vertex_mm)
    over = to_cornea(case.over_refraction, case.over_vertex_mm)
    actual = lens_on_eye(case.lens, case.rotation_cw)
    p_lens = to_vector(actual)
    target = p_lens + to_vector(over)  # Do NOT add baseline here: that would double-count.
    p_base = to_vector(baseline)
    target_rx = from_vector(target)
    difference = target - p_base
    continuous_axis = optimal_order_axis(target, case.next_lens, case.next_rotation_cw)
    continuous = make_candidate(case, target, continuous_axis) if continuous_axis is not None else None
    candidates = ranked_candidates(case, target)
    best = candidates[0] if continuous is not None else None
    tied = tuple(x.axis for x in candidates if best and abs(x.cylinder_abs - best.cylinder_abs) < 1e-9)
    base_axis = optimal_order_axis(p_base, case.next_lens, case.next_rotation_cw)
    base_best = ranked_candidates(case, p_base)[0] if base_axis is not None else None
    lower_bound = abs(target.cylinder_magnitude - abs(case.next_lens.cylinder))
    warnings: list[str] = []
    if case.stability != "安定している":
        warnings.append("回転の安定・再現性が確認されていません。表示軸は仮定条件下のシミュレーションであり、処方候補として確定しないでください。")
    if "他覚" in case.measurement:
        warnings.append("他覚的屈折値を使用しています。装用下の自覚的追加矯正と視力を確認してください。")
    if abs(difference.m) > case.discrepancy_threshold_D or difference.cylinder_magnitude > case.discrepancy_threshold_D:
        warnings.append("装用前の矯正値と装用後から再構成した必要矯正が、設定した便宜的な確認閾値を超えて不一致です。回転方向・測定時点・頂点間距離・度数表記・調節状態などを再確認してください。両者は自動平均していません。")
    if continuous is None:
        warnings.append("次レンズが球面、または推定必要矯正のCが数値的に0です。どの軸でも残余|C|が同じため、最適軸を1つに決定できません。")
    elif abs(target_rx.cylinder) < 0.25:
        warnings.append("推定必要矯正の|C|が0.25 D未満です。軸の数値は測定誤差の影響を受けやすく、角度の細かな差を重視しないでください（便宜的な注意表示）。")
    if lower_bound >= 0.25:
        warnings.append("選択した次レンズのCでは、軸だけを変えても角膜面に0.25 D以上の残余乱視が理論上残ります。Cの変更や別レンズの試験装用を検討する際は再評価が必要です（0.25 Dは便宜的な表示閾値）。")
    if abs(case.next_lens.m - case.lens.m) > EPS or abs(case.next_lens.cylinder - case.lens.cylinder) > EPS:
        warnings.append("次レンズのS/Cを変更した仮想計算です。度数・設計変更によって回転挙動が変わり得るため、次レンズの回転再現性は未保証です。")
    if abs(case.next_rotation_cw - case.rotation_cw) > EPS:
        warnings.append("次レンズに別の予測回転量を指定しています。その回転が実測されたものか、単なる仮定かを区別してください。")
    if best and len(tied) > 1:
        warnings.append("残余乱視が同率最小の軸があります。同率内では現在の表示軸からの変更が小さいものを先に表示しています。")
    return Analysis(
        case, baseline, over, actual, target_rx, target, difference, candidates, best, tied, continuous,
        base_axis, base_best, from_vector(p_base - p_lens),
        residual_for_axis(p_base, case.next_lens, best.axis, case.next_rotation_cw) if best else None,
        lower_bound, tuple(warnings),
    )


def fmt_axis(a: float | None, decimals: int = 1) -> str:
    if a is None:
        return "—（C=0）"
    # Round modulo 180 again so 179.999 -> 180 and 0.001 -> 180, never '0.0'.
    value = display_axis(round(display_axis(a), decimals))
    return f"{value:.{decimals}f}°"


def fmt_rx(rx: Rx) -> str:
    # Do not print meaningless axis when cylinder rounds to zero at 0.01 D.
    s = 0.0 if abs(rx.sphere) < 0.005 else rx.sphere
    c = 0.0 if abs(rx.cylinder) < 0.005 else rx.cylinder
    a = "—（丸め後C=0）" if c == 0 else fmt_axis(rx.axis)
    return f"S {s:+.2f} D / C {c:+.2f} D × {a}"


def json_export(result: Analysis) -> str:
    return json.dumps(result.to_dict(), ensure_ascii=False, indent=2, allow_nan=False)


def csv_export(result: Analysis) -> bytes:
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    writer.writerow([
        "app_version", "eye", "basis", "axis_label_deg", "axis_on_eye_deg", "next_S_D", "next_C_D",
        "residual_S_cornea_D", "residual_C_cornea_D", "residual_axis_cornea_deg", "residual_M_cornea_D",
        "residual_S_overref_plane_D", "residual_C_overref_plane_D", "residual_axis_overref_plane_deg",
        "overref_vertex_mm", "next_rotation_CW_positive_deg", "rotation_scenario_half_width_deg",
        "scenario_min_abs_C_cornea_D", "scenario_max_abs_C_cornea_D", "warning",
    ])
    c = result.case
    for row in result.candidates:
        r, rs = row.residual_cornea, row.residual_spectacle
        writer.writerow([
            VERSION, c.eye, "current_on_eye_SCL_plus_overref", display_axis(row.axis),
            display_axis(row.on_eye_axis), c.next_lens.sphere, c.next_lens.cylinder,
            r.sphere, r.cylinder, display_axis(r.axis), r.m,
            rs.sphere, rs.cylinder, display_axis(rs.axis), c.over_vertex_mm,
            c.next_rotation_cw, c.rotation_half_width_deg, row.minimum_C, row.maximum_C, MODEL_WARNING,
        ])
    return out.getvalue().encode("utf-8-sig")


def text_export(result: Analysis) -> str:
    c = result.case
    best = result.best
    lines = [
        f"# トーリックSCL軸選択シミュレーション v{VERSION}", "", MODEL_WARNING, "",
        f"眼: {c.eye} / 入力: {c.source} / 回転安定性: {c.stability}", CONVENTION,
        f"装用前矯正: {fmt_rx(c.baseline)} / 頂点間距離 {c.baseline_vertex_mm:g} mm",
        f"現在のSCL: {fmt_rx(c.lens)} / 時計回り正の回転 {c.rotation_cw:+.2f}°",
        f"装用後屈折: {fmt_rx(c.over_refraction)} / 頂点間距離 {c.over_vertex_mm:g} mm / {c.measurement}",
        f"実際の眼上SCL: {fmt_rx(result.current_actual)}",
        f"推定必要矯正（角膜面）: {fmt_rx(result.inferred_target)}",
        f"次レンズの固定度数: S {c.next_lens.sphere:+.2f} / C {c.next_lens.cylinder:+.2f}",
        f"次レンズの仮定回転量: {c.next_rotation_cw:+.2f}°（時計回り正）",
        "候補軸: " + ", ".join(fmt_axis(a) for a in c.axes), "",
    ]
    if best:
        lines += [
            f"候補内で残余|C|最小の表示軸: {fmt_axis(best.axis)}",
            f"同率最小の表示軸: {', '.join(fmt_axis(a) for a in result.tied_best_axes)}",
            f"予測眼上軸: {fmt_axis(best.on_eye_axis)}",
            f"予測残余屈折（角膜面）: {fmt_rx(best.residual_cornea)}",
            f"予測残余屈折（装用後測定面 {c.over_vertex_mm:g} mm）: {fmt_rx(best.residual_spectacle)}",
            f"連続値の理論最適表示軸: {fmt_axis(result.continuous.axis)}",
            f"次回転が±{c.rotation_half_width_deg:g}°変動した仮想範囲: |C| {best.minimum_C:.3f}〜{best.maximum_C:.3f} D（角膜面、信頼区間ではない）",
        ]
    else:
        lines.append("軸による残余|C|の差がないため、最適軸は決定できません。")
    lines += [
        f"軸のみ変更の理論最小|C|: {result.lower_bound_C:.3f} D（角膜面）",
        f"装用前のみで求める理論表示軸: {fmt_axis(result.baseline_continuous_axis)}",
        f"装用前との不一致: ΔM {result.discrepancy.m:+.3f} D / 乱視ベクトル差の等価|C| {result.discrepancy.cylinder_magnitude:.3f} D",
        "", "## 注意", *[f"- {w}" for w in result.warnings], "", "## 計算の根拠",
        "M=S+C/2; J0=−(C/2)cos(2A); J45=−(C/2)sin(2A).",
        "必要矯正 = 実際の眼上SCL + 角膜面へ換算した装用後の追加矯正。",
        "予測残余 = 必要矯正 − 候補SCLの予測眼上矯正。装用前矯正は重ねて加算しない。",
        "", *[f"- {r['title']} {r['url']}" for r in REFERENCES],
    ]
    return "\n".join(lines)
