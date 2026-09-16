"""Run with: python -m streamlit run app.py
Research/education prototype. No database, external API, or patient identifier.
"""
from __future__ import annotations
import json
import pandas as pd
import streamlit as st

from optics import (Rx, axis_grid, display_axis, from_vector, lens_on_eye,
                    parse_axes, residual_for_axis, to_vector)
from engine import (Analysis, Case, MODEL_WARNING, REFERENCES, VERSION, analyze,
                    csv_export, fmt_axis, fmt_rx, json_export, text_export)
from visuals import curve_figure, axis_figure

CW = "時計回り（＋）"
CCW = "反時計回り（−）"
NONE = "回転なし"
GRID_OPTIONS = ["10°刻み（仮の候補）", "5°刻み（仮の候補）", "1°刻み（理論比較）", "使用可能な軸を手入力"]
STATE_DEFAULTS = {
    "eye": "右眼 OD", "baseline_s": None, "baseline_c": None, "baseline_a": None,
    "baseline_vertex": 12.0, "lens_s": None, "lens_c": None, "lens_a": None,
    "over_s": None, "over_c": None, "over_a": None, "over_vertex": 12.0,
    "rotation_direction": NONE, "rotation_amount": 0.0,
    "stability": "未確認", "measurement": "他覚的屈折（SCL装用下）",
    "grid_mode": GRID_OPTIONS[0], "axes_text": "10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150, 160, 170, 180",
    "change_power": False, "next_s": None, "next_c": None,
    "change_rotation": False, "next_rotation_direction": NONE, "next_rotation_amount": 0.0,
    "rotation_half_width": 5.0, "discrepancy_threshold": 0.50,
    "consent": False,
}


def init_state() -> None:
    for key, value in STATE_DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = value
    if "_demo" not in st.session_state:
        st.session_state["_demo"] = False


def clear_inputs() -> None:
    for key, value in STATE_DEFAULTS.items():
        st.session_state[key] = value
    st.session_state["_demo"] = False
    for key in ("_result", "_result_signature"):
        st.session_state.pop(key, None)


def load_demo(rotation: float) -> None:
    clear_inputs()
    target = Rx(-3.0, -1.25, 180.0)
    over = from_vector(to_vector(target) - to_vector(lens_on_eye(target, rotation)))
    st.session_state.update({
        "baseline_s": -3.0, "baseline_c": -1.25, "baseline_a": 180.0,
        "baseline_vertex": 0.0, "lens_s": -3.0, "lens_c": -1.25, "lens_a": 180.0,
        "over_s": over.sphere, "over_c": over.cylinder, "over_a": display_axis(over.axis),
        "over_vertex": 0.0, "rotation_direction": CW if rotation > 0 else CCW,
        "rotation_amount": abs(rotation), "stability": "安定している", "_demo": True,
    })


def direction_changed(prefix: str) -> None:
    if st.session_state[f"{prefix}_direction"] == NONE:
        st.session_state[f"{prefix}_amount"] = 0.0


def signed_rotation(prefix: str) -> float:
    direction = st.session_state[f"{prefix}_direction"]
    amount = float(st.session_state[f"{prefix}_amount"])
    return amount if direction == CW else (-amount if direction == CCW else 0.0)


def input_signature() -> str:
    data = {k: st.session_state.get(k) for k in STATE_DEFAULTS}
    if not data["change_power"]:
        data.pop("next_s", None)
        data.pop("next_c", None)
    if not data["change_rotation"]:
        data.pop("next_rotation_direction", None)
        data.pop("next_rotation_amount", None)
    if data["grid_mode"] != GRID_OPTIONS[3]:
        data.pop("axes_text", None)
    data["_demo"] = st.session_state["_demo"]
    return json.dumps(data, ensure_ascii=False, sort_keys=True, allow_nan=False)


def rx_inputs(prefix: str, *, scl: bool = False) -> None:
    c1, c2, c3 = st.columns(3)
    with c1:
        st.number_input("S / SPH（D）", min_value=-30.0, max_value=25.0, value=None,
                        step=0.25, format="%.3f", key=f"{prefix}_s", placeholder="例：−3.00")
    with c2:
        st.number_input("C / CYL（D）", min_value=-15.0, max_value=0.0 if scl else 15.0,
                        value=None, step=0.25, format="%.3f", key=f"{prefix}_c", placeholder="例：−1.25")
    with c3:
        st.number_input("Axis（°）", min_value=0.0, max_value=180.0, value=None,
                        step=1.0, format="%.2f", key=f"{prefix}_a", placeholder="例：180")
    if scl:
        st.caption("容器・処方に記載された表示軸を入力します。SCLはマイナス円柱表記です。")
    else:
        st.caption("プラス円柱表記も入力できます。C=0のとき軸は空欄で構いません。")


def read_rx(prefix: str, label: str) -> Rx:
    values = [st.session_state[f"{prefix}_{x}"] for x in ("s", "c", "a")]
    if values[0] is None or values[1] is None:
        raise ValueError(f"{label}のSとCを入力してください。")
    if abs(values[1]) > 1e-10 and values[2] is None:
        raise ValueError(f"{label}の軸を入力してください。")
    return Rx(*values)


def build_case() -> Case:
    lens = read_rx("lens", "装用中SCL")
    next_lens = None
    if st.session_state["change_power"]:
        if st.session_state["next_s"] is None or st.session_state["next_c"] is None:
            raise ValueError("変更する次レンズのSとCを入力してください。")
        next_lens = Rx(st.session_state["next_s"], st.session_state["next_c"], lens.axis)
    mode = st.session_state["grid_mode"]
    axes = parse_axes(st.session_state["axes_text"]) if mode == GRID_OPTIONS[3] else axis_grid([10, 5, 1][GRID_OPTIONS.index(mode)])
    return Case(
        baseline=read_rx("baseline", "装用前の矯正値"), lens=lens,
        over_refraction=read_rx("over", "装用後の屈折値"), rotation_cw=signed_rotation("rotation"),
        axes=axes, baseline_vertex_mm=st.session_state["baseline_vertex"],
        over_vertex_mm=st.session_state["over_vertex"], next_lens=next_lens,
        next_rotation_cw=signed_rotation("next_rotation") if st.session_state["change_rotation"] else None,
        rotation_half_width_deg=st.session_state["rotation_half_width"],
        eye="OD" if st.session_state["eye"] == "右眼 OD" else "OS",
        stability=st.session_state["stability"], measurement=st.session_state["measurement"],
        source="架空デモ（編集値を含む）" if st.session_state["_demo"] else "手入力",
        discrepancy_threshold_D=st.session_state["discrepancy_threshold"],
    )


def candidate_frame(result: Analysis) -> pd.DataFrame:
    return pd.DataFrame([{
        "順位": i + 1,
        "表示軸（°）": display_axis(x.axis),
        "予測眼上軸（°）": display_axis(x.on_eye_axis),
        "残余 |C|（D）": x.cylinder_abs,
        "残余 S（D）": x.residual_cornea.sphere,
        "残余 C（D）": x.residual_cornea.cylinder,
        "残余軸（°）": display_axis(x.residual_cornea.axis) if abs(x.residual_cornea.cylinder) >= 0.005 else None,
        "次回転変動時の最大 |C|（D）": x.maximum_C,
    } for i, x in enumerate(result.candidates)])


def show_results(result: Analysis) -> None:
    c, best = result.case, result.best
    st.divider()
    st.subheader("計算結果｜次に試すレンズの比較")
    st.caption(f"{c.eye} / {c.source} / 基準：装用中SCL＋装用後の追加矯正 / 角膜面で残余 |C| を最小化")
    st.info(f"次レンズの固定度数：S {c.next_lens.sphere:+.2f} D / C {c.next_lens.cylinder:+.2f} D。"
            f"次の回転は {c.next_rotation_cw:+.1f}°（時計回り＋）と仮定しています。")
    for warning in result.warnings:
        st.warning(warning)
    if best:
        a, b, d = st.columns(3)
        a.metric("候補内で残余乱視が最小の表示軸", fmt_axis(best.axis))
        b.metric("そのレンズの予測眼上軸", fmt_axis(best.on_eye_axis))
        d.metric("予測残余 |C|（角膜面）", f"{best.cylinder_abs:.2f} D")
        st.markdown(f"**予測残余屈折（角膜面）**　{fmt_rx(best.residual_cornea)}")
        st.write(f"装用後の測定面（VD {c.over_vertex_mm:g} mm）に戻した予測値：{fmt_rx(best.residual_spectacle)}")
        st.caption(f"連続値の理論最適表示軸：{fmt_axis(result.continuous.axis)}。現在の表示軸 {fmt_axis(c.lens.axis)} からの最短の数値変更：{best.label_change:+.1f}°。"
                   "これは交換するSCLの表示軸の変更であり、眼上のレンズをその角度だけ手で回す指示ではありません。")
        if len(result.tied_best_axes) > 1:
            st.caption("同率最小の表示軸：" + " / ".join(fmt_axis(a) for a in result.tied_best_axes))
    else:
        st.info("軸を1つに選べない条件です。下の表では全候補を比較できますが、最適軸は表示しません。")
    a, b = st.columns(2)
    a.metric("軸だけを変えた場合の理論最小 |C|", f"{result.lower_bound_C:.2f} D")
    b.metric("次レンズの予測残余球面等価 M", f"{result.target_vector.m - c.next_lens.m:+.2f} D")
    st.caption("S/Cを固定した軸変更では、角膜面の残余Mは変わりません。乱視の最小化と球面度数の適正化は別に評価します。")

    t1, t2, t3, t4 = st.tabs(["候補軸と残余乱視", "軸・回転の図", "装用前との整合性", "計算式・結果保存"])
    with t1:
        st.plotly_chart(curve_figure(result), use_container_width=True, config={"displayModeBar": False}, key="curve")
        st.caption("0°と180°は同じ軸です。順位は測定どおりの回転を仮定した残余 |C| 順であり、変動時の最大値順ではありません。")
        df = candidate_frame(result)
        st.dataframe(df, hide_index=True, use_container_width=True, column_config={
            "表示軸（°）": st.column_config.NumberColumn(format="%.1f"),
            "予測眼上軸（°）": st.column_config.NumberColumn(format="%.1f"),
            "残余 |C|（D）": st.column_config.NumberColumn(format="%.3f"),
            "残余 S（D）": st.column_config.NumberColumn(format="%+.3f"),
            "残余 C（D）": st.column_config.NumberColumn(format="%+.3f"),
            "残余軸（°）": st.column_config.NumberColumn(format="%.1f"),
            "次回転変動時の最大 |C|（D）": st.column_config.NumberColumn(format="%.3f"),
        })
        if best:
            st.write(f"次レンズの回転のみが±{c.rotation_half_width_deg:g}°ずれた場合、選択候補の残余 |C| は "
                     f"**{best.minimum_C:.3f}〜{best.maximum_C:.3f} D**（角膜面）です。")
        st.caption("変動幅は入力した仮想条件です。統計的信頼区間ではなく、現在の回転測定・他覚屈折の誤差は伝播させていません。製品の実際の製作範囲を必ず確認してください。")
    with t2:
        st.markdown("**検者が患者の正面から見た図**")
        st.plotly_chart(axis_figure(result), use_container_width=True, config={"displayModeBar": False}, key="axes_diagram")
        st.write(f"現在：表示軸 {fmt_axis(c.lens.axis)} − 時計回り正の回転 {c.rotation_cw:+.1f}° "
                 f"＝ 眼上の光学軸 {fmt_axis(result.current_actual.axis)}（180°周期）")
        if best:
            st.write(f"次候補：表示軸 {fmt_axis(best.axis)} − 仮定回転 {c.next_rotation_cw:+.1f}° "
                     f"＝ 予測眼上軸 {fmt_axis(best.on_eye_axis)}")
        st.warning("6時マークは回転方向を説明する例です。レンズの位置マークそのものが円柱軸とは限りません。製品ごとのマーク配置を確認し、その基準からの回転量を入力してください。")
    with t3:
        st.markdown("**装用前の矯正値は、主計算に加算せず独立した確認に使用します。**")
        rows = [
            {"項目": "装用前の矯正値（角膜面換算）", "S/C/Axis": fmt_rx(result.baseline_cornea)},
            {"項目": "現在のSCLの実際の眼上矯正", "S/C/Axis": fmt_rx(result.current_actual)},
            {"項目": "装用後の実測追加矯正（角膜面換算）", "S/C/Axis": fmt_rx(result.over_cornea)},
            {"項目": "装用後から再構成した必要矯正（主計算）", "S/C/Axis": fmt_rx(result.inferred_target)},
            {"項目": "装用前から予測した現在の残余屈折", "S/C/Axis": fmt_rx(result.baseline_predicted_current)},
        ]
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        x, y = st.columns(2)
        x.metric("必要矯正の不一致 ΔM", f"{result.discrepancy.m:+.3f} D")
        y.metric("乱視ベクトル差の等価 |C|", f"{result.discrepancy.cylinder_magnitude:.3f} D")
        st.caption("右の値はC度数の単純な差ではなく、軸の違いを含むベクトル差です。")
        if result.baseline_best:
            st.write(f"装用前の矯正値だけから選ぶ場合：候補内の表示軸 **{fmt_axis(result.baseline_best.axis)}** "
                     f"／連続理論軸 {fmt_axis(result.baseline_continuous_axis)}。")
        else:
            st.write("装用前の値だけでは最適軸を一意に決められません。")
        if result.baseline_predicted_at_primary_best:
            st.write("主計算で選んだ候補を、装用前の値から評価した予測残余屈折："
                     + fmt_rx(result.baseline_predicted_at_primary_best))
        st.caption(f"不一致の注意表示は |ΔM| または乱視ベクトル差の等価 |C| が {c.discrepancy_threshold_D:g} Dを超える場合です。"
                   "この閾値は便宜的な確認用で、臨床的妥当性が検証された合否基準ではありません。")
    with t4:
        st.markdown("**1. 屈折値を同じ面へ換算する**")
        st.latex(r"F_c=\frac{F_s}{1-dF_s}\quad(F_s=S,\;S+C;\ d\text{ in m})")
        st.write("SとS+Cの両主経線を別々に換算します。装用前と装用後でそれぞれの測定面・頂点間距離を指定します。")
        st.markdown("**2. ベクトルへ変換する**")
        st.latex(r"M=S+\frac{C}{2},\quad J_0=-\frac{C}{2}\cos(2A),\quad J_{45}=-\frac{C}{2}\sin(2A)")
        st.markdown("**3. 実測残余から必要矯正を再構成し、次候補を差し引く**")
        st.latex(r"\mathbf P_{target}=\mathbf P_{SCL,on-eye}+\mathbf P_{over,c}")
        st.latex(r"\mathbf P_{res}(a)=\mathbf P_{target}-\mathbf P_{next}(a-r_{next})")
        st.latex(r"|C_{res}|=2\sqrt{J_{0,res}^2+J_{45,res}^2}")
        st.write("全候補軸の残余 |C| を評価します。固定したマイナス円柱の連続最適眼上軸は推定必要矯正の軸で、次の予測回転量を加えると表示軸になります。")
        st.caption("このレンズ交換モデルの実装は本アプリの設計です。下記文献・メーカー資料は数学表現と回転補正の根拠であり、本アプリの臨床的有効性を検証した資料ではありません。")
        a, b, d = st.columns(3)
        a.download_button("入力・全結果 JSON", json_export(result), file_name=f"toric_result_{c.eye}.json", mime="application/json", use_container_width=True)
        b.download_button("候補一覧 CSV", csv_export(result), file_name=f"toric_candidates_{c.eye}.csv", mime="text/csv", use_container_width=True)
        d.download_button("計算メモ TXT", text_export(result), file_name=f"toric_summary_{c.eye}.txt", mime="text/plain", use_container_width=True)
        for ref in REFERENCES:
            st.markdown(f"[{ref['title']}]({ref['url']})")
        st.caption("JSONには入力条件・仮定・未丸めの計算結果を含みます。CSVはUTF-8 BOM付きです。患者名・IDは入力しないでください。")


def main() -> None:
    st.set_page_config(page_title="Toric SCL Axis Planner", page_icon="◉", layout="wide")
    init_state()
    st.markdown("""<style>
        .block-container {max-width: 1160px; padding-top: 2rem;}
        h1 {letter-spacing: -0.035em;}
        [data-testid="stMetricValue"] {font-variant-numeric: tabular-nums;}
        .direction-note {padding: .8rem 1rem; border-left: 4px solid #385e77;
                         background: #f1f5f8; border-radius: 4px; color: #183749;}
    </style>""", unsafe_allow_html=True)
    st.caption(f"TORIC SCL · AXIS PLANNER · v{VERSION}")
    st.title("トーリックSCL 軸選択シミュレーター")
    st.write("装用後の残余屈折と実際のレンズ回転から、次に試す **表示軸** を比較します。")
    st.warning("教育・研究用プロトタイプ／臨床未検証です。結果だけで処方を確定せず、自覚的追加矯正・視力・フィッティングを確認してください。")
    st.caption("クラウド公開時は入力値がStreamlitサーバーへ送られます。本コードはデータベースへの保存・外部API送信・入力値のログ出力を行いませんが、ローカル端末内だけで完結する仕組みではありません。患者名・IDは扱わないでください。")
    b1, b2, b3, b4 = st.columns([1.15, 1.25, 0.8, 1])
    b1.button("時計回り10°のデモ", on_click=load_demo, args=(10.0,), use_container_width=True)
    b2.button("反時計回り10°のデモ", on_click=load_demo, args=(-10.0,), use_container_width=True)
    b3.button("入力をクリア", on_click=clear_inputs, use_container_width=True)
    with b4:
        st.selectbox("対象眼", ["右眼 OD", "左眼 OS"], key="eye", label_visibility="collapsed")
    if st.session_state["_demo"]:
        st.info("架空デモです（編集値を含む）。検算を明瞭にするため、装用前・装用後ともVD=0 mmの値を使用しています。")

    st.markdown('<div class="direction-note"><b>回転方向は検者が患者の正面から見た向きです。</b><br>'
                '↻ 時計回り＝＋ ／ ↺ 反時計回り＝−。右眼・左眼で符号は反転しません。<br>'
                '6時にあるマークは、時計回りで検者から見て左へ、反時計回りで右へ移動します。</div>', unsafe_allow_html=True)
    st.write("")
    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            st.subheader("01｜装用前の矯正値")
            rx_inputs("baseline")
            st.number_input("装用前屈折値の頂点間距離（mm）", min_value=0.0, max_value=25.0,
                            step=0.5, key="baseline_vertex", format="%.1f")
            st.caption("角膜面換算済みなら0 mm。眼鏡面の屈折値なら実際の頂点間距離を入力します。主計算には重ねて加算せず、整合性の確認に使います。")
        with st.container(border=True):
            st.subheader("03｜装用中SCLの回転")
            st.radio("回転方向", [CW, CCW, NONE], horizontal=True, key="rotation_direction",
                     on_change=direction_changed, args=("rotation",))
            st.number_input("回転量（°・絶対値）", min_value=0.0, max_value=90.0, step=0.5,
                            format="%.2f", key="rotation_amount", disabled=st.session_state["rotation_direction"] == NONE)
            st.selectbox("回転の安定・再現性", ["未確認", "安定している", "不安定"], key="stability")
            st.caption("製品の基準位置からの回転量を入力します。装用後屈折を測定したときと同じ回転状態を使用してください。")
            if st.session_state["lens_a"] is not None and st.session_state["lens_c"] not in (None, 0):
                angle = (st.session_state["lens_a"] - signed_rotation("rotation")) % 180
                st.write(f"現在の計算上の眼上光学軸：**{fmt_axis(angle)}**")
    with right:
        with st.container(border=True):
            st.subheader("02｜装用中SCLの表示度数")
            rx_inputs("lens", scl=True)
            st.caption("次に試すレンズは、初期設定では同じS・Cを維持して軸のみ変更します。レンズ交換後も同じ回転を示すと仮定した計算です。")
        with st.container(border=True):
            st.subheader("04｜装用後の屈折値")
            rx_inputs("over")
            st.selectbox("測定方法", ["他覚的屈折（SCL装用下）", "自覚的追加矯正（SCL装用下）"], key="measurement")
            st.number_input("装用後屈折値の頂点間距離（mm）", min_value=0.0, max_value=25.0,
                            step=0.5, key="over_vertex", format="%.1f")
            st.caption("SCLを装用したまま測定した残余屈折／追加矯正値です。SCL度数を含んだ最終処方や裸眼時の屈折値は入力しません。機器のVD設定を確認してください。")

    with st.container(border=True):
        st.subheader("05｜次に試せる軸の候補")
        st.selectbox("候補軸の指定方法", GRID_OPTIONS, key="grid_mode")
        if st.session_state["grid_mode"] == GRID_OPTIONS[3]:
            st.text_area("使用可能な表示軸（カンマ区切り）", key="axes_text", height=90)
        st.caption("10°・5°刻みは製品在庫を示すものではありません。メーカー・製品・S/Cによって選択可能な軸が異なるため、実際の規格に合わせて手入力してください。")
    with st.expander("詳細設定｜次レンズのS/C、予測回転、変動幅"):
        st.checkbox("次レンズのS/Cを変更した場合を仮想比較する", key="change_power")
        if st.session_state["change_power"]:
            x, y = st.columns(2)
            x.number_input("次レンズ S（D）", min_value=-30.0, max_value=25.0, value=None,
                           step=0.25, format="%.3f", key="next_s")
            y.number_input("次レンズ C（D・マイナス円柱）", min_value=-15.0, max_value=0.0, value=None,
                           step=0.25, format="%.3f", key="next_c")
            st.caption("度数・デザイン変更時には回転の再現性が変わり得ます。この入力だけで次レンズの回転が分かるわけではありません。")
        st.checkbox("次レンズに別の予測回転量を仮定する", key="change_rotation")
        if st.session_state["change_rotation"]:
            st.radio("次レンズの仮定回転方向", [CW, CCW, NONE], horizontal=True,
                     key="next_rotation_direction", on_change=direction_changed, args=("next_rotation",))
            st.number_input("次レンズの仮定回転量（°）", min_value=0.0, max_value=90.0,
                            step=0.5, format="%.2f", key="next_rotation_amount",
                            disabled=st.session_state["next_rotation_direction"] == NONE)
        st.number_input("次レンズの回転変動シナリオ（±°）", min_value=0.0, max_value=30.0,
                        step=1.0, format="%.1f", key="rotation_half_width")
        st.caption("初期値±5°は仮想条件です。推定精度や信頼区間を意味しません。")
        st.number_input("装用前との不一致の確認閾値（D・便宜的）", min_value=0.05,
                        max_value=5.0, step=0.05, format="%.2f", key="discrepancy_threshold")
    st.checkbox("回転方向の定義と測定面を確認し、結果は処方確定値ではないことを理解した", key="consent")
    calculate = st.button("残余乱視が最小になる軸を計算", type="primary", use_container_width=True)
    if calculate:
        st.session_state.pop("_result", None)
        st.session_state.pop("_result_signature", None)
        if not st.session_state["consent"]:
            st.error("上の確認欄にチェックしてから計算してください。")
        else:
            try:
                result = analyze(build_case())
                st.session_state["_result"] = result
                st.session_state["_result_signature"] = input_signature()
            except ValueError as exc:
                st.error(str(exc))
    if "_result" in st.session_state:
        if st.session_state.get("_result_signature") != input_signature():
            st.info("入力が変更されました。古い結果は非表示にしています。計算ボタンを押して更新してください。")
        else:
            show_results(st.session_state["_result"])
    else:
        st.caption("入力後に計算ボタンを押してください。デモを使うと、時計回り10°→表示軸10°、反時計回り10°→表示軸170°を検算できます。")
    with st.expander("適用範囲と注意事項"):
        st.write(MODEL_WARNING)
        st.write("対象は正乱視を矯正するトーリックSCLです。不正乱視、高次収差、涙液・角膜形状の変化、レンズ変形・偏心、瞳孔径・調節、回転の経時変化などはモデル化していません。RGP・オルソケラトロジー・トーリックIOLへの転用は想定していません。")
        st.write("製品のマークは必ずしも円柱軸を表しません。軸が安定しない場合は固定した補正軸の計算より装用状態の再評価を優先してください。残余乱視が小さくても良好な視力や快適性を保証しません。")
        for ref in REFERENCES:
            st.markdown(f"[{ref['title']}]({ref['url']})")


if __name__ == "__main__":
    main()
