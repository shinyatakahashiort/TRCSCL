"""Paraxial spherocylindrical optics. No third-party dependencies.

Units: diopters, degrees, millimetres (only vertex arguments).
Axes increase counterclockwise as seen by an examiner facing the patient.
Clockwise physical rotation is positive: on-eye axis = labelled axis - rotation.
All addition/subtraction takes place at the corneal plane, using power vectors.
This is an unvalidated research/education model, not an autonomous prescription.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, degrees, hypot, isfinite, radians, sin, sqrt
from typing import Iterable
import re
import unicodedata

EPS = 1e-10


def finite(value: float, name: str = "値") -> float:
    try:
        x = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name}には数値を入力してください。") from exc
    if not isfinite(x):
        raise ValueError(f"{name}には有限の数値を入力してください。")
    return x


def normalize_axis(axis: float) -> float:
    """Internal axis in [0,180); zero and 180 are the same meridian."""
    x = finite(axis, "軸") % 180.0
    return 0.0 if abs(x) < EPS or abs(x - 180.0) < EPS else x


def display_axis(axis: float | None) -> float | None:
    if axis is None:
        return None
    x = normalize_axis(axis)
    return 180.0 if x == 0.0 else x


def signed_axis_difference(target: float, source: float) -> float:
    """Smallest numerical axis change, [-90,90), not physical CW rotation."""
    return (normalize_axis(target) - normalize_axis(source) + 90.0) % 180.0 - 90.0


def axis_distance(a: float, b: float) -> float:
    return abs(signed_axis_difference(a, b))


@dataclass(frozen=True)
class Rx:
    sphere: float
    cylinder: float
    axis: float | None

    def __post_init__(self) -> None:
        s = finite(self.sphere, "S")
        c = finite(self.cylinder, "C")
        if abs(c) < EPS:
            c, a = 0.0, None
        else:
            if self.axis is None:
                raise ValueError("Cが0以外の場合、軸が必要です。")
            a = normalize_axis(self.axis)
        object.__setattr__(self, "sphere", s)
        object.__setattr__(self, "cylinder", c)
        object.__setattr__(self, "axis", a)

    @property
    def m(self) -> float:
        return self.sphere + self.cylinder / 2.0

    def minus_cylinder(self) -> Rx:
        if self.cylinder <= 0:
            return self
        return Rx(self.sphere + self.cylinder, -self.cylinder, self.axis + 90.0)

    def at_axis(self, axis: float) -> Rx:
        return Rx(self.sphere, self.cylinder, axis)

    def to_dict(self) -> dict:
        return {"S_D": self.sphere, "C_D": self.cylinder, "axis_deg": display_axis(self.axis)}


@dataclass(frozen=True)
class PowerVector:
    m: float
    j0: float
    j45: float

    def __post_init__(self) -> None:
        for key in ("m", "j0", "j45"):
            object.__setattr__(self, key, finite(getattr(self, key), key))

    def __add__(self, other: PowerVector) -> PowerVector:
        return PowerVector(self.m + other.m, self.j0 + other.j0, self.j45 + other.j45)

    def __sub__(self, other: PowerVector) -> PowerVector:
        return PowerVector(self.m - other.m, self.j0 - other.j0, self.j45 - other.j45)

    @property
    def cylinder_magnitude(self) -> float:
        return 2.0 * hypot(self.j0, self.j45)

    @property
    def norm(self) -> float:
        return sqrt(self.m**2 + self.j0**2 + self.j45**2)

    def to_dict(self) -> dict:
        return {"M_D": self.m, "J0_D": self.j0, "J45_D": self.j45}


def to_vector(rx: Rx) -> PowerVector:
    a = radians(2.0 * (rx.axis or 0.0))
    return PowerVector(rx.m, -rx.cylinder * cos(a) / 2.0, -rx.cylinder * sin(a) / 2.0)


def from_vector(p: PowerVector) -> Rx:
    c = -p.cylinder_magnitude
    if abs(c) < EPS:
        return Rx(p.m, 0.0, None)
    return Rx(p.m - c / 2.0, c, degrees(atan2(p.j45, p.j0)) / 2.0)


def vertex_transform(rx: Rx, distance_mm: float, *, to_corneal: bool) -> Rx:
    """Transform BOTH principal powers, then reconstruct (never vertex C alone).

    Spectacle -> cornea: F/(1-dF); cornea -> spectacle: F/(1+dF).
    d is nonnegative, in metres internally. Reject pole-crossing cases.
    """
    dmm = finite(distance_mm, "頂点間距離")
    if not 0.0 <= dmm <= 30.0:
        raise ValueError("頂点間距離は0〜30 mmの範囲で設定してください。")
    d = dmm / 1000.0
    x = rx.minus_cylinder()
    powers = (x.sphere, x.sphere + x.cylinder)
    out = []
    for f in powers:
        denominator = 1.0 - d * f if to_corneal else 1.0 + d * f
        if denominator <= EPS:
            raise ValueError("頂点間距離換算の適用範囲を超えています。度数と距離を確認してください。")
        out.append(f / denominator)
    return Rx(out[0], out[1] - out[0], x.axis)


def to_cornea(rx: Rx, distance_mm: float) -> Rx:
    return vertex_transform(rx, distance_mm, to_corneal=True)


def to_spectacle(rx: Rx, distance_mm: float) -> Rx:
    return vertex_transform(rx, distance_mm, to_corneal=False)


def on_eye_axis(label_axis: float, clockwise_rotation: float) -> float:
    return normalize_axis(label_axis - finite(clockwise_rotation, "回転量"))


def order_axis(target_on_eye_axis: float, clockwise_rotation: float) -> float:
    return normalize_axis(target_on_eye_axis + finite(clockwise_rotation, "回転量"))


def lens_on_eye(lens: Rx, clockwise_rotation: float, label_axis: float | None = None) -> Rx:
    if lens.cylinder > EPS:
        raise ValueError("SCLの度数はマイナス円柱表記で入力してください。")
    a = lens.axis if label_axis is None else label_axis
    return lens.at_axis(on_eye_axis(a or 0.0, clockwise_rotation))


def residual_for_axis(target: PowerVector, lens: Rx, label_axis: float, rotation: float) -> Rx:
    return from_vector(target - to_vector(lens_on_eye(lens, rotation, label_axis)))


def optimal_order_axis(target: PowerVector, lens: Rx, rotation: float) -> float | None:
    """Analytic optimum for negative cylinder and fixed S/C; None means flat objective."""
    if lens.cylinder > EPS:
        raise ValueError("候補SCLはマイナス円柱表記が必要です。")
    if abs(lens.cylinder) < EPS or target.cylinder_magnitude < EPS:
        return None
    return order_axis(from_vector(target).axis, rotation)


def axis_grid(step: int) -> tuple[float, ...]:
    if step not in (1, 5, 10):
        raise ValueError("軸刻みは1°・5°・10°のいずれかです。")
    return tuple(normalize_axis(x) for x in range(step, 181, step))


def clean_axes(values: Iterable[float]) -> tuple[float, ...]:
    axes = set()
    for value in values:
        x = finite(value, "候補軸")
        if not 0 <= x <= 180:
            raise ValueError("候補軸は0〜180°で入力してください。")
        axes.add(round(normalize_axis(x), 10))
    if not axes:
        raise ValueError("候補軸を1つ以上入力してください。")
    if len(axes) > 361:
        raise ValueError("候補軸は361個以内にしてください。")
    return tuple(sorted(axes, key=lambda a: display_axis(a)))


def parse_axes(text: str) -> tuple[float, ...]:
    normalized = unicodedata.normalize("NFKC", str(text)).replace("、", ",")
    tokens = [x for x in re.split(r"[,;\s]+", normalized.strip()) if x]
    if not tokens:
        raise ValueError("候補軸を入力してください（例：10, 20, 90, 180）。")
    try:
        return clean_axes(float(t) for t in tokens)
    except ValueError as exc:
        raise ValueError("候補軸は0〜180°の数値をカンマまたは空白で区切って入力してください。") from exc


def cylinder_range(target: PowerVector, lens: Rx, axis: float,
                   rotation: float, half_width: float) -> tuple[float, float]:
    """Exact min/max |C| when rotation is in [r-h,r+h]. Not a confidence interval.

    Include endpoints AND interior extrema (parallel/orthogonal cylinder axes).
    Only next-lens rotation is perturbed; target reconstructed from current inputs
    is held fixed. Current measurement uncertainty is NOT propagated.
    """
    h = finite(half_width, "回転変動幅")
    if not 0 <= h <= 30:
        raise ValueError("回転変動幅は0〜30°の範囲で設定してください。")
    lo, hi = rotation - h, rotation + h
    probes = [lo, hi]
    target_rx = from_vector(target)
    if target_rx.axis is not None:
        # r = a - target_axis - 90k contains all stationary points.
        for k in range(-8, 9):
            r = normalize_axis(axis) - target_rx.axis - 90.0 * k
            if lo - EPS <= r <= hi + EPS:
                probes.append(r)
    values = [abs(residual_for_axis(target, lens, axis, r).cylinder) for r in probes]
    return min(values), max(values)
