"""Joints, machine-axis bindings and the pose sweep (ASM-1 §9, contract v1.3).

A mate may carry a `joint`: one degree of freedom between its two components. The mate's
frames coincide at joint value 0; at value q the child (side b) is displaced from the
parent (side a) along (`prismatic`, mm) or about (`revolute`, degrees, right-handed) one
axis of side a's interface frame (`x`, `y`, or `z` = the frame normal):

    T_b = T_a · H(F_a) · J(q) · Flip · Rz(θ) · H(F_b)^-1

A joint has one of three roles:

* **driven** — its value is set (a machine axis, a sample of the sweep, or its `home`);
* **follower** — `follows: {terms: [{joint, scale}], offset}`: its value is
  offset + Σ scale · value(joint), computed from driven joints (and earlier followers);
* **passive** — `passive: true`: its value is not set but *measured*. The mate never
  places a component; it only closes a cycle, with the joint's degree of freedom free,
  and the measured value must stay inside `limits`.

The pose sweep (a documented convention, `POSE_SAMPLES` and `POSE_SEED`): the home pose;
each driven joint at its lower and at its upper limit with the others at home; then
`POSE_SAMPLES` points of a Halton sequence over every driven joint at once. Sample k
(k = 1 … N) gives driven joint i (document order, i = 0, 1, …) the value
`lower + (upper − lower) · φ_p(k + seed − 1)`, where φ_p is the radical inverse in the
i-th prime base p (2, 3, 5, …), rounded to 4 decimals. A continuous revolute joint (no
limits) is swept over [−180, 180) for the samples and has no limit poses. The sequence
needs no random-number generator, so any language reproduces the joint values; the golden
pose files record them anyway (`golden_poses`).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from .transforms import Matrix, rotation_z

__all__ = [
    "CONTINUOUS_SWEEP_DEG",
    "JOINT_AXES",
    "JOINT_TYPES",
    "POSE_SAMPLES",
    "POSE_SEED",
    "Joint",
    "PoseError",
    "PoseSpec",
    "axis_joint_values",
    "joint_matrix",
    "joint_values",
    "joints_of",
    "machine_bindings",
    "pose_sweep",
    "radical_inverse",
    "static_kinematic_problems",
]

JOINT_TYPES = ("prismatic", "revolute")
JOINT_AXES = ("x", "y", "z")

#: The number of Halton samples of the pose sweep — a CONVENTION, not a fact: it is what
#: every-PR CI runs (the timing is in docs/ASSEMBLIES.md). `--pose-samples` overrides it.
POSE_SAMPLES = 16
#: The Halton start index (sample k uses index k + POSE_SEED − 1) — a CONVENTION.
POSE_SEED = 1
#: The range a continuous revolute joint is sampled over — a CONVENTION.
CONTINUOUS_SWEEP_DEG = (-180.0, 180.0)
#: Sample joint values are rounded to this many decimals (0.1 µm, 0.0001°) so golden
#: files stay readable; the rounded value IS the sample.
SAMPLE_DIGITS = 4


class PoseError(ValueError):
    """A pose cannot be computed: an unknown joint, a value that is not a finite number,
    a value outside a joint's limits (never clamped), or an assembly that does not pass."""


@dataclass(frozen=True)
class Joint:
    """One joint as the document states it (ASM-1 §9)."""

    id: str
    mate_id: str
    type: str
    axis: str
    parent: str  # side a's component
    child: str  # side b's component
    limits: tuple[float, float] | None
    home: float | None
    passive: bool = False
    follows: tuple[tuple[str, float], ...] = ()
    follow_offset: float = 0.0
    note: str | None = None

    @property
    def role(self) -> str:
        if self.passive:
            return "passive"
        return "follower" if self.follows else "driven"

    @property
    def unit(self) -> str:
        return "mm" if self.type == "prismatic" else "deg"

    @property
    def sweep_range(self) -> tuple[float, float]:
        return self.limits if self.limits is not None else CONTINUOUS_SWEEP_DEG

    def within_limits(self, value: float, tolerance: float = 0.0) -> bool:
        if self.limits is None:
            return True
        return self.limits[0] - tolerance <= value <= self.limits[1] + tolerance


@dataclass(frozen=True)
class PoseSpec:
    """One pose of the sweep: a name, its kind, and the value of every driven joint."""

    name: str
    kind: str  # "home" | "limit" | "sample"
    driven: Mapping[str, float] = field(default_factory=dict)


def _num(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def joints_of(doc: Mapping) -> list[Joint]:
    """Every joint of a schema-valid document, in mate order."""
    out = []
    for mate in doc.get("mates") or []:
        spec = mate.get("joint")
        if not isinstance(spec, Mapping):
            continue
        limits = spec.get("limits")
        follows = spec.get("follows") or {}
        out.append(Joint(
            id=spec["id"], mate_id=mate["id"], type=spec["type"], axis=spec["axis"],
            parent=mate["a"]["component"], child=mate["b"]["component"],
            limits=(float(limits[0]), float(limits[1])) if limits is not None else None,
            home=_num(spec.get("home")),
            passive=bool(spec.get("passive", False)),
            follows=tuple((t["joint"], float(t["scale"])) for t in follows.get("terms") or []),
            follow_offset=float(follows.get("offset", 0.0)),
            note=spec.get("note"),
        ))
    return out


def machine_bindings(doc: Mapping) -> list[dict]:
    """The machine block's axis bindings with scale/offset filled in (identity default)."""
    machine = doc.get("machine") or {}
    return [
        {"axis": b["axis"], "joint": b["joint"], "scale": float(b.get("scale", 1.0)),
         "offset": float(b.get("offset", 0.0)), "note": b.get("note")}
        for b in machine.get("axes") or []
    ]


def static_kinematic_problems(doc: Mapping) -> list[tuple[str, str | None, str]]:
    """Problems with the joints and the machine block that need no geometry, as
    (code, subject, message). The schema has already passed."""
    out: list[tuple[str, str | None, str]] = []
    joints = joints_of(doc)
    by_id: dict[str, Joint] = {}
    for j in joints:
        if j.id in by_id:
            out.append(("joint", j.id, f"joint id is used by mates '{by_id[j.id].mate_id}' and "
                                       f"'{j.mate_id}'"))
            continue
        by_id[j.id] = j
    for j in joints:
        if j.limits is not None:
            lo, hi = j.limits
            if not (math.isfinite(lo) and math.isfinite(hi) and lo < hi):
                out.append(("joint", j.id, f"limits [{lo:g}, {hi:g}] must be finite with "
                                           "lower < upper"))
            elif j.home is not None and not lo <= j.home <= hi:
                out.append(("joint", j.id, f"home {j.home:g} is outside its limits "
                                           f"[{lo:g}, {hi:g}]"))
        for leader, scale in j.follows:
            if leader == j.id:
                out.append(("joint", j.id, "a joint cannot follow itself"))
            elif leader not in by_id:
                out.append(("joint", j.id, f"follows '{leader}', which is not a joint"))
            elif by_id[leader].passive:
                out.append(("joint", j.id, f"follows '{leader}', a passive joint: a passive "
                                           "joint's value is measured, not set"))
            if not math.isfinite(scale) or scale == 0:
                out.append(("joint", j.id, f"follows '{leader}' with scale {scale!r}; a "
                                           "scale is a finite non-zero number"))
    cycle = _follow_cycle(by_id)
    if cycle:
        out.append(("joint", cycle[0], "followers form a cycle: " + " → ".join(cycle)))

    machine = doc.get("machine")
    if machine is not None:
        seen_axes: set[str] = set()
        seen_joints: dict[str, str] = {}
        for b in machine_bindings(doc):
            axis, jid = b["axis"], b["joint"]
            if axis in seen_axes:
                out.append(("machine", axis, f"axis '{axis}' is bound twice"))
            seen_axes.add(axis)
            joint = by_id.get(jid)
            if joint is None:
                out.append(("machine", axis, f"axis '{axis}' binds '{jid}', which is not a "
                                             "joint"))
            elif joint.role != "driven":
                out.append(("machine", axis, f"axis '{axis}' binds '{jid}', a {joint.role} "
                                             "joint; only a driven joint takes an axis value"))
            elif jid in seen_joints:
                out.append(("machine", axis, f"joint '{jid}' is already bound to axis "
                                             f"'{seen_joints[jid]}'"))
            else:
                seen_joints[jid] = axis
            if not math.isfinite(b["scale"]) or b["scale"] == 0:
                out.append(("machine", axis, f"scale {b['scale']!r} must be finite and "
                                             "non-zero"))
            if not math.isfinite(b["offset"]):
                out.append(("machine", axis, f"offset {b['offset']!r} must be finite"))
    return out


def _follow_cycle(by_id: Mapping[str, Joint]) -> list[str] | None:
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(jid: str) -> list[str] | None:
        state[jid] = 1
        stack.append(jid)
        for leader, _ in by_id[jid].follows:
            if leader not in by_id:
                continue
            if state.get(leader) == 1:
                return stack[stack.index(leader):] + [leader]
            if leader not in state:
                found = visit(leader)
                if found:
                    return found
        stack.pop()
        state[jid] = 2
        return None

    for jid in by_id:
        if jid not in state:
            found = visit(jid)
            if found:
                return found
    return None


def _follow_order(joints: Sequence[Joint]) -> list[Joint]:
    """Followers in an order where every leader comes first (the graph is acyclic)."""
    by_id = {j.id: j for j in joints}
    done: set[str] = {j.id for j in joints if not j.follows}
    order: list[Joint] = []
    pending = [j for j in joints if j.follows]
    while pending:
        progressed = False
        for j in list(pending):
            if all(leader in done for leader, _ in j.follows if leader in by_id):
                order.append(j)
                done.add(j.id)
                pending.remove(j)
                progressed = True
        if not progressed:  # a cycle; reported statically, never computed
            raise PoseError("followers form a cycle: " + ", ".join(j.id for j in pending))
    return order


def joint_values(joints: Sequence[Joint], given: Mapping[str, object] | None = None,
                 *, check_limits: bool = True) -> dict[str, float]:
    """The value of every driven and follower joint: each driven joint at its given value
    (else its home), each follower computed. A passive joint has no value here (it is
    measured from the geometry). Raises PoseError on an unknown or passive joint, a value
    that is not a finite number, or (with `check_limits`) a driven value outside its
    limits — values are never clamped."""
    by_id = {j.id: j for j in joints}
    given = dict(given or {})
    for jid in given:
        joint = by_id.get(jid)
        if joint is None:
            raise PoseError(f"'{jid}' is not a joint of this assembly "
                            f"(joints: {', '.join(sorted(by_id)) or 'none'})")
        if joint.role != "driven":
            raise PoseError(f"'{jid}' is a {joint.role} joint; only a driven joint is set")
    values: dict[str, float] = {}
    for j in joints:
        if j.role != "driven":
            continue
        raw = given.get(j.id, j.home)
        value = _num(raw)
        if value is None or not math.isfinite(value):
            raise PoseError(f"joint '{j.id}': {raw!r} is not a finite number")
        if check_limits and not j.within_limits(value):
            raise PoseError(f"joint '{j.id}' = {value:g} {j.unit} is outside its limits "
                            f"[{j.limits[0]:g}, {j.limits[1]:g}] (never clamped)")
        values[j.id] = value
    for j in _follow_order(joints):
        values[j.id] = j.follow_offset + sum(scale * values[leader]
                                             for leader, scale in j.follows)
    return values


def axis_joint_values(doc: Mapping, axis_values: Mapping[str, object]) -> dict[str, float]:
    """Driven-joint values from machine axis values through the `machine` bindings
    (joint = scale · axis + offset). An axis with no binding raises PoseError; an axis
    the machine does not report leaves its joint at home."""
    bindings = {b["axis"]: b for b in machine_bindings(doc)}
    out: dict[str, float] = {}
    for axis, raw in axis_values.items():
        b = bindings.get(axis)
        if b is None:
            raise PoseError(f"axis '{axis}' is not bound by the machine block "
                            f"(bound: {', '.join(sorted(bindings)) or 'none'})")
        value = _num(raw)
        if value is None or not math.isfinite(value):
            raise PoseError(f"axis '{axis}': {raw!r} is not a finite number")
        out[b["joint"]] = b["scale"] * value + b["offset"]
    return out


def joint_matrix(joint_type: str, axis: str, value: float) -> Matrix:
    """J(q): a translation of q mm along, or a rotation of q degrees about, a frame axis."""
    k = JOINT_AXES.index(axis)
    if joint_type == "prismatic":
        t = [0.0, 0.0, 0.0]
        t[k] = float(value)
        return (
            (1.0, 0.0, 0.0, t[0]),
            (0.0, 1.0, 0.0, t[1]),
            (0.0, 0.0, 1.0, t[2]),
            (0.0, 0.0, 0.0, 1.0),
        )
    rz = rotation_z(math.radians(value))
    c, s = rz[0][0], rz[1][0]
    if k == 2:
        return rz
    if k == 0:  # about x: y → z
        return (
            (1.0, 0.0, 0.0, 0.0),
            (0.0, c, -s, 0.0),
            (0.0, s, c, 0.0),
            (0.0, 0.0, 0.0, 1.0),
        )
    return (  # about y: z → x
        (c, 0.0, s, 0.0),
        (0.0, 1.0, 0.0, 0.0),
        (-s, 0.0, c, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    )


def measured_joint_value(joint_type: str, axis: str, residual: Sequence[Sequence[float]]
                         ) -> float:
    """The joint value a relative transform realises: for J(q) ≈ residual, the translation
    along the axis (prismatic) or the rotation about it in degrees (revolute)."""
    k = JOINT_AXES.index(axis)
    if joint_type == "prismatic":
        return residual[k][3]
    if k == 2:
        return math.degrees(math.atan2(residual[1][0], residual[0][0]))
    if k == 0:
        return math.degrees(math.atan2(residual[2][1], residual[1][1]))
    return math.degrees(math.atan2(residual[0][2], residual[2][2]))


def _primes(count: int) -> list[int]:
    out: list[int] = []
    n = 2
    while len(out) < count:
        if all(n % p for p in out if p * p <= n):
            out.append(n)
        n += 1
    return out


def radical_inverse(index: int, base: int) -> float:
    """φ_b(index): the digits of `index` in base `base`, mirrored about the radix point."""
    result, f, i = 0.0, 1.0 / base, index
    while i > 0:
        result += f * (i % base)
        i //= base
        f /= base
    return result


def pose_sweep(joints: Sequence[Joint], samples: int = POSE_SAMPLES,
               seed: int = POSE_SEED) -> list[PoseSpec]:
    """The pose sweep of the module docstring: home, the limits, the Halton samples."""
    driven = [j for j in joints if j.role == "driven"]
    home = {j.id: float(j.home) for j in driven}
    poses = [PoseSpec("home", "home", home)]
    if not driven:
        return poses
    for j in driven:
        if j.limits is None:
            continue
        for bound, value in (("lower", j.limits[0]), ("upper", j.limits[1])):
            poses.append(PoseSpec(f"{j.id}@{bound}", "limit", {**home, j.id: float(value)}))
    bases = _primes(len(driven))
    for k in range(1, samples + 1):
        values = {}
        for j, base in zip(driven, bases, strict=True):
            lo, hi = j.sweep_range
            value = round(lo + (hi - lo) * radical_inverse(k + seed - 1, base), SAMPLE_DIGITS)
            values[j.id] = min(max(value, lo), hi) + 0.0
        poses.append(PoseSpec(f"sample-{k}", "sample", values))
    return poses
