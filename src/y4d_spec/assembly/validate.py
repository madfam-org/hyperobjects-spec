"""`validate_assembly(doc, resolver) -> AssemblyReport` — ASM-1 §3 steps 1–6 and 8.

    1. schema; unique component and mate ids; `root` and every mate endpoint exist;
       a producer's `capability_profile` keys and values are in the
       `fabrication-capabilities` vocabulary (`process` is a list of `processes` keys)
    2. resolve every component through the resolver (errors name the component)
    3. per mate: both interfaces exist and can mate (frame, polarity, size_key,
       symmetry), equal size_key, complementary polarity, equal symmetry, and a
       rotation that fits it (rotation_index < symmetry, or angle_deg for symmetry 0)
    4. placement: BFS from the root over the mates that passed step 3
    5. closure: EVERY mate (tree or not) re-checked in world space — origins ≤ 0.05 mm,
       normals antiparallel ≤ 0.5°, x-axes agree modulo the symmetry ≤ 0.5°; for
       continuous symmetry (0) the stated angle_deg agrees with the realised angle
       ≤ 0.5° whenever both frames declare an x_axis (else a cycle-closing mate warns
       `angle-unchecked`)
    6. every component reachable from the root
    6b. (ASM-1 §9, v1.3) the pose sweep: when the document has driven joints, every mate
       and cycle is re-checked at each joint's limits and over a seeded Halton sweep
       (`kinematics.pose_sweep`); a passive joint's measured value and a follower's
       computed value stay inside their limits; every declared path is planar at home
       and its pitch-line length is reported at every pose
    7. (--collision) rigid-body interference at every pose of the sweep (`collision.py`):
       cartridges rendered at their parameters, standard parts and external designs as
       their envelopes; an undeclared overlap above 1 mm³ is an error. A component with
       no solid is named (`collision-unchecked`), never silently passed.
    8. the report, the placement table (the home pose), and the canonical assembly digest

A pure function of the document and the resolver: no file is read here, so a service
holding its components elsewhere calls it with its own resolver.
"""

from __future__ import annotations

import dataclasses
import math
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field

from .digest import assembly_digest
from .kinematics import (
    POSE_SAMPLES,
    POSE_SEED,
    Joint,
    PoseError,
    joint_matrix,
    joint_values,
    joints_of,
    measured_joint_value,
    pose_sweep,
    static_kinematic_problems,
)
from .paths import PATH_LENGTH_TOLERANCE_MM, PATH_LOOP_TOLERANCE_MM, PathResult
from .resolution import ComponentResolver, ResolutionError, ResolvedComponent, ResolvedInterface
from .sweep import (
    PoseResult,
    limit_findings,
    measure_paths,
    path_static_step,
    pose_result,
    resolve_paths,
    sweep_step,
)
from .tolerances import ANGLE_TOLERANCE_DEG, ORIGIN_TOLERANCE_MM
from .transforms import (
    IDENTITY,
    Matrix,
    angle_between_deg,
    apply_vector,
    column,
    flip_rz,
    mate_transform,
    matmul,
    rigid_inverse,
)

__all__ = [
    "ANGLE_TOLERANCE_DEG",
    "ORIGIN_TOLERANCE_MM",
    "AssemblyFinding",
    "AssemblyReport",
    "KinematicModel",
    "MateCheck",
    "PoseResult",
    "validate_assembly",
]


ERROR = "error"
WARNING = "warning"
COMPLEMENT = {"male": "female", "female": "male", "neutral": "neutral"}


@dataclass(frozen=True)
class AssemblyFinding:
    severity: str
    code: str
    message: str
    subject: str | None = None  # a component id or a mate id

    def __str__(self) -> str:
        where = f"[{self.subject}] " if self.subject else ""
        return f"{self.code}: {where}{self.message}"


@dataclass
class MateCheck:
    """One mate's verdict. Residuals are None when the mate never got that far."""

    mate_id: str
    a: str
    b: str
    symmetry: int | None = None
    theta_deg: float | None = None
    in_tree: bool = False
    origin_mm: float | None = None
    normal_deg: float | None = None
    x_axis_deg: float | None = None
    measured_deg: float | None = None
    ok: bool = False
    #: ASM-1 §9: the mate's joint id, and its value at this pose (set, computed, or —
    #: for a passive joint — measured from the geometry). None for a rigid mate.
    joint: str | None = None
    joint_value: float | None = None

    def as_dict(self) -> dict:
        def r(v):
            return None if v is None else round(v, 6) + 0.0
        out = {
            "mate": self.mate_id, "a": self.a, "b": self.b, "symmetry": self.symmetry,
            "theta_deg": r(self.theta_deg), "in_tree": self.in_tree,
            "origin_mm": r(self.origin_mm), "normal_deg": r(self.normal_deg),
            "x_axis_deg": r(self.x_axis_deg), "measured_deg": r(self.measured_deg),
            "ok": self.ok,
        }
        if self.joint is not None:
            out["joint"] = self.joint
            out["joint_value"] = r(self.joint_value)
        return out

    def reset(self) -> MateCheck:
        """A copy with the static facts only (for re-checking at another pose)."""
        return dataclasses.replace(self, origin_mm=None, normal_deg=None, x_axis_deg=None,
                                   measured_deg=None, ok=False, joint_value=None)


@dataclass
class AssemblyReport:
    findings: list[AssemblyFinding] = field(default_factory=list)
    components: dict[str, ResolvedComponent] = field(default_factory=dict)
    placements: dict[str, Matrix] = field(default_factory=dict)
    mates: list[MateCheck] = field(default_factory=list)
    digest: str | None = None
    collision: str = "not run"
    #: ASM-1 §9 (v1.3): the document's joints, the pose sweep's verdicts (home first) and
    #: the declared paths. Empty for a rigid assembly, whose only pose is home.
    joints: list[Joint] = field(default_factory=list)
    poses: list[PoseResult] = field(default_factory=list)
    paths: list[PathResult] = field(default_factory=list)
    pose_samples: int = POSE_SAMPLES
    pose_seed: int = POSE_SEED
    #: The collision check's details (`collision.CollisionResult`) when it ran.
    collision_result: object | None = None
    #: The compiled kinematic model (placement at any joint values), when every
    #: component resolved and the root is placed; None otherwise.
    kinematics: KinematicModel | None = None

    @property
    def errors(self) -> list[AssemblyFinding]:
        return [f for f in self.findings if f.severity == ERROR]

    @property
    def warnings(self) -> list[AssemblyFinding]:
        return [f for f in self.findings if f.severity == WARNING]

    @property
    def ok(self) -> bool:
        return not self.errors

    def __bool__(self) -> bool:
        return self.ok

    def _err(self, code: str, message: str, subject: str | None = None) -> None:
        self.findings.append(AssemblyFinding(ERROR, code, message, subject))

    def _warn(self, code: str, message: str, subject: str | None = None) -> None:
        self.findings.append(AssemblyFinding(WARNING, code, message, subject))


# ── step 1 ────────────────────────────────────────────────────────────────────
def _schema_step(doc: object, report: AssemblyReport) -> bool:
    from jsonschema import Draft202012Validator

    from hyperobjects_schemas import load

    validator = Draft202012Validator(load("assembly"))
    for err in sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in err.absolute_path) or "<root>"
        report._err("schema", f"{where}: {err.message}")
    if report.errors:
        return False

    ids = [c["id"] for c in doc["components"]]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        report._err("component-id", "component id is used more than once", dup)
    mate_ids = [m["id"] for m in doc["mates"]]
    for dup in sorted({i for i in mate_ids if mate_ids.count(i) > 1}):
        report._err("mate-id", "mate id is used more than once", dup)
    from hyperobjects_lexicon import capability_profile_problems

    for problem in capability_profile_problems(doc.get("capability_profile")):
        report._err("capability", problem)
    if doc["root"] not in ids:
        report._err("root", f"root '{doc['root']}' is not a component")
    for mate in doc["mates"]:
        for side in ("a", "b"):
            cid = mate[side]["component"]
            if cid not in ids:
                report._err("mate-endpoint", f"{side}: no component '{cid}'", mate["id"])
        if mate["a"]["component"] == mate["b"]["component"]:
            report._err("mate-endpoint", "a component cannot mate with itself", mate["id"])
    return not report.errors


# ── step 3 ────────────────────────────────────────────────────────────────────
def _interface(report, mate, side, components) -> ResolvedInterface | None:
    ref = mate[side]
    comp = components.get(ref["component"])
    if comp is None:
        return None  # its resolution error is already reported
    iface = comp.interfaces.get(ref["interface"])
    if iface is None:
        known = ", ".join(sorted(comp.interfaces)) or "none"
        report._err(
            "interface",
            f"{side}: component '{ref['component']}' ({comp.label}) has no interface "
            f"'{ref['interface']}' (it has: {known})",
            mate["id"],
        )
        return None
    blocked = [f"{side}: interface '{ref['component']}.{iface.id}' {p}" for p in iface.problems]
    for field_name in ("polarity", "size_key", "symmetry"):
        if getattr(iface, field_name) is None:
            reason = (
                iface.size_key_absent_reason
                if field_name == "size_key" and getattr(iface, "size_key_absent_reason", None)
                else f"declares no {field_name}"
            )
            blocked.append(f"{side}: interface '{ref['component']}.{iface.id}' {reason}")
    for message in blocked:
        report._err("interface", message, mate["id"])
    return None if blocked else iface


def _mate_rule_step(report, mate, ia, ib) -> MateCheck | None:
    """Static mating rule; returns a MateCheck with θ when the mate may be placed."""
    mid = mate["id"]
    ok = True
    if ia.size_key != ib.size_key:
        report._err("size_key", f"size_key differs: a '{ia.size_key}' vs b '{ib.size_key}'", mid)
        ok = False
    if COMPLEMENT.get(ia.polarity) != ib.polarity:
        report._err(
            "polarity",
            f"polarity is not complementary: a {ia.polarity} vs b {ib.polarity} "
            "(male mates female, neutral mates neutral)",
            mid,
        )
        ok = False
    if ia.symmetry != ib.symmetry:
        report._err(
            "symmetry", f"symmetry differs: a {ia.symmetry} vs b {ib.symmetry}", mid
        )
        return None
    s = ia.symmetry
    theta: float | None = None
    if s == 0:
        if "rotation_index" in mate:
            report._err(
                "rotation",
                "the interfaces have continuous symmetry (0): state angle_deg, not "
                "rotation_index",
                mid,
            )
            ok = False
        elif not math.isfinite(mate["angle_deg"]):
            report._err("rotation", f"angle_deg {mate['angle_deg']!r} is not finite", mid)
            ok = False
        else:
            theta = float(mate["angle_deg"])
    else:
        if "angle_deg" in mate:
            report._err(
                "rotation",
                f"the interfaces have symmetry {s}: state rotation_index (0..{s - 1}), "
                "not angle_deg",
                mid,
            )
            ok = False
        elif mate["rotation_index"] >= s:
            report._err(
                "rotation",
                f"rotation_index {mate['rotation_index']} is not < symmetry {s}",
                mid,
            )
            ok = False
        else:
            theta = 360.0 * mate["rotation_index"] / s
    if not ok:
        return None
    return MateCheck(mid, _ref(mate, "a"), _ref(mate, "b"), symmetry=s, theta_deg=theta)


def _ref(mate: Mapping, side: str) -> str:
    return f"{mate[side]['component']}.{mate[side]['interface']}"


# ── steps 4 and 5 ─────────────────────────────────────────────────────────────
Edge = tuple  # (mate, MateCheck, ResolvedInterface a, ResolvedInterface b, Joint | None)


def _frames(mate: Mapping, ia, ib) -> tuple[Matrix, Matrix]:
    """H(F_a), H(F_b) — with a mate `offset` (ASM-1 §9, v1.4) applied: the station lives on
    the mate, so the named side's frame slides `value` mm along its own axis before the
    mate is formed. That is J(value) of a prismatic joint fixed at that value."""
    h_a, h_b = ia.frame.homogeneous(), ib.frame.homogeneous()
    offset = mate.get("offset")
    if offset:
        shift = joint_matrix("prismatic", offset["axis"], float(offset["value"]))
        if offset.get("side", "a") == "a":
            h_a = matmul(h_a, shift)
        else:
            h_b = matmul(h_b, shift)
    return h_a, h_b


def _place(root: str, edges: list[Edge], values: Mapping[str, float]
           ) -> tuple[dict[str, Matrix], set[str]]:
    """BFS from the root. Mates are visited in document order, which makes the tree —
    and so the placement of an over-constrained assembly — deterministic. A joint mate
    places its child at the joint's value; a passive joint's mate never places anything
    (it only closes a cycle). Returns the placements and the ids of the tree's mates."""
    placements: dict[str, Matrix] = {root: IDENTITY}
    tree: set[str] = set()
    queue = deque([root])
    while queue:
        current = queue.popleft()
        for mate, check, ia, ib, joint in edges:
            ca, cb = mate["a"]["component"], mate["b"]["component"]
            if current not in (ca, cb) or (joint is not None and joint.passive):
                continue
            theta = math.radians(check.theta_deg)
            h_a, h_b = _frames(mate, ia, ib)
            if joint is None:
                j = j_inv = None
            else:
                j = joint_matrix(joint.type, joint.axis, values.get(joint.id, 0.0))
                j_inv = rigid_inverse(j)
            if current == ca and cb not in placements:
                if j is None:
                    placements[cb] = mate_transform(placements[ca], h_a, h_b, theta)
                else:  # T_b = T_a · H(F_a) · J(q) · M · H(F_b)^-1
                    placements[cb] = matmul(placements[ca], h_a, j, flip_rz(theta),
                                            rigid_inverse(h_b))
            elif current == cb and ca not in placements:
                # M = Flip·Rz(θ) is an involution, so the same formula serves both ways;
                # a joint is undone from the child's side: T_a = T_b · H_b · M · J^-1 · H_a^-1.
                if j is None:
                    placements[ca] = mate_transform(placements[cb], h_b, h_a, theta)
                else:
                    placements[ca] = matmul(placements[cb], h_b, flip_rz(theta), j_inv,
                                            rigid_inverse(h_a))
            else:
                continue
            tree.add(mate["id"])
            queue.append(cb if current == ca else ca)
    return placements, tree


def _closure(check: MateCheck, t_a: Matrix, t_b: Matrix, ia, ib,
             joint: Joint | None = None, value: float | None = None,
             frames: tuple[Matrix, Matrix] | None = None) -> None:
    h_a, h_b = frames if frames is not None else (ia.frame.homogeneous(),
                                                  ib.frame.homogeneous())
    w_a = matmul(t_a, h_a)
    w_b = matmul(t_b, h_b)
    if joint is not None:
        if joint.passive:
            # The value the geometry realises: J(q) ≈ W_a^-1 · W_b · M (M^-1 = M).
            residual = matmul(rigid_inverse(w_a), w_b,
                              flip_rz(math.radians(check.theta_deg)))
            value = measured_joint_value(joint.type, joint.axis, residual)
        w_a = matmul(w_a, joint_matrix(joint.type, joint.axis, value))
        check.joint_value = value
    o_a, o_b = column(w_a, 3), column(w_b, 3)
    check.origin_mm = math.dist(o_a, o_b)
    n_a, n_b = column(w_a, 2), column(w_b, 2)
    check.normal_deg = angle_between_deg(n_b, tuple(-v for v in n_a))
    # b's x-axis seen from a's frame. For a perfect mate W_b = W_a·Flip·Rz(φ), so it
    # reads (cos φ, −sin φ, 0): φ is the rotation the geometry actually realises.
    x_b_in_a = apply_vector(rigid_inverse(w_a), column(w_b, 0))
    phi = math.degrees(math.atan2(-x_b_in_a[1], x_b_in_a[0])) % 360.0
    check.measured_deg = phi
    if check.symmetry:
        period = 360.0 / check.symmetry
    elif ia.frame.x_axis is not None and ib.frame.x_axis is not None:
        # Continuous symmetry (P4-ASM2 finding 3b): the stated angle_deg is a fact the
        # geometry can contradict only when both frames declare an x_axis. Then the
        # residual is the distance of φ from the stated θ on the full circle; a mate in
        # the BFS tree holds it by construction, a cycle-closing mate is the real test.
        period = 360.0
    else:
        period = None
    if period is not None:
        d = (phi - check.theta_deg) % period
        check.x_axis_deg = min(d, period - d)
    check.ok = (
        check.origin_mm <= ORIGIN_TOLERANCE_MM
        and check.normal_deg <= ANGLE_TOLERANCE_DEG
        and (check.x_axis_deg is None or check.x_axis_deg <= ANGLE_TOLERANCE_DEG)
    )


@dataclass
class KinematicModel:
    """An assembly compiled for posing (ASM-1 §9): the root, the mates that passed the
    mating rule (with their resolved interfaces and joints), and the joints. Built by
    `validate_assembly`; `pose()` and the golden pose files use it."""

    root: str
    edges: list[Edge]
    joints: list[Joint]

    def values(self, driven: Mapping[str, object] | None = None, *,
               check_limits: bool = True) -> dict[str, float]:
        """Every driven and follower joint's value (`kinematics.joint_values`)."""
        return joint_values(self.joints, driven, check_limits=check_limits)

    def place(self, values: Mapping[str, float]) -> dict[str, Matrix]:
        """Every component's world transform with the joints at `values`."""
        return _place(self.root, self.edges, values)[0]

    def evaluate(self, values: Mapping[str, float], checks: Mapping[str, MateCheck] | None = None
                 ) -> tuple[dict[str, Matrix], list[MateCheck]]:
        """Place at `values`, then check every mate in world space. `checks` (by mate id)
        are filled in place when given (the home pose); otherwise fresh copies are."""
        placements, tree = _place(self.root, self.edges, values)
        out = []
        for mate, check, ia, ib, joint in self.edges:
            target = checks[mate["id"]] if checks is not None else check.reset()
            target.in_tree = mate["id"] in tree
            ca, cb = mate["a"]["component"], mate["b"]["component"]
            if ca in placements and cb in placements:
                _closure(target, placements[ca], placements[cb], ia, ib, joint,
                         None if joint is None or joint.passive else values.get(joint.id, 0.0),
                         _frames(mate, ia, ib))
            out.append(target)
        return placements, out


def _signed(deg: float) -> float:
    """An angle in (−180, 180], rounded for a message."""
    d = deg % 360.0
    return round(d - 360.0 if d > 180.0 else d, 4) + 0.0


def _closure_findings(report: AssemblyReport, check: MateCheck) -> None:
    if not check.ok:
        parts = [f"origins {check.origin_mm:.4f} mm apart (≤ {ORIGIN_TOLERANCE_MM})",
                 f"normals {check.normal_deg:.4f}° from antiparallel (≤ {ANGLE_TOLERANCE_DEG})"]
        if check.x_axis_deg is not None and check.symmetry:
            parts.append(
                f"x-axes {check.x_axis_deg:.4f}° apart modulo symmetry {check.symmetry} "
                f"(≤ {ANGLE_TOLERANCE_DEG})"
            )
        elif check.x_axis_deg is not None:
            parts.append(
                f"stated angle_deg {check.theta_deg:g}° but the geometry realises "
                f"{_signed(check.measured_deg):g}° ({check.x_axis_deg:.4f}° apart, "
                f"≤ {ANGLE_TOLERANCE_DEG})"
            )
        kind = "the BFS tree" if check.in_tree else "a cycle"
        report._err(
            "closure",
            f"{check.a} ↔ {check.b} does not hold (closes {kind}): " + "; ".join(parts),
            check.mate_id,
        )
        return
    if check.symmetry == 0 and check.x_axis_deg is None and not check.in_tree:
        report._warn(
            "angle-unchecked",
            f"{check.a} ↔ {check.b} closes a cycle with continuous symmetry, but an "
            "interface declares no x_axis, so the stated angle_deg "
            f"{check.theta_deg:g}° cannot be compared with the geometry",
            check.mate_id,
        )
        return
    if check.symmetry and check.symmetry > 1:
        period = 360.0 / check.symmetry
        index = round(check.measured_deg / period) % check.symmetry
        declared = round(check.theta_deg / period) % check.symmetry
        if index != declared:
            report._warn(
                "rotation",
                f"closes at rotation_index {index}, but the document states {declared}; "
                "the two are the same mating up to symmetry",
                check.mate_id,
            )


def _offset_step(report: AssemblyReport, mate: Mapping, ia, ib) -> None:
    """A mate `offset` (ASM-1 §9, v1.4) must stay inside the travel its interface declares:
    the same axis, lower ≤ value ≤ upper. Undeclared travel cannot be checked: a warning,
    never a silent pass."""
    offset = mate.get("offset")
    if not offset:
        return
    side = offset.get("side", "a")
    iface = ia if side == "a" else ib
    ref = f"{mate[side]['component']}.{mate[side]['interface']}"
    value, axis = float(offset["value"]), offset["axis"]
    if iface.travel is None:
        report._warn("offset-unchecked",
                     f"offset {value:g} mm along {axis} of {ref}, which declares no travel: "
                     "the station is placed but not checked against the interface's run",
                     mate["id"])
        return
    t_axis, low, high = iface.travel
    if t_axis != axis:
        report._err("offset", f"offset is along {axis}, but {ref} travels along {t_axis}",
                    mate["id"])
    elif not low <= value <= high:
        report._err("offset", f"offset {value:g} mm leaves {ref}'s travel [{low:g}, {high:g}] mm "
                    f"along {axis} (never clamped)", mate["id"])


def _allowed_overlap_problems(doc: Mapping, report: AssemblyReport) -> None:
    ids = {c["id"] for c in doc["components"]}
    seen: set[frozenset] = set()
    for entry in doc.get("allowed_overlaps") or []:
        a, b = entry["a"], entry["b"]
        subject = f"{a}|{b}"
        for cid in (a, b):
            if cid not in ids:
                report._err("allowed-overlap", f"'{cid}' is not a component", subject)
        if a == b:
            report._err("allowed-overlap", "a component cannot overlap itself", subject)
        pair = frozenset((a, b))
        if pair in seen:
            report._err("allowed-overlap", "the pair is declared twice", subject)
        seen.add(pair)


def _collision_step(report: AssemblyReport, doc: Mapping) -> None:
    """ASM-1 §3.7: interference at home and at every pose the sweep checked."""
    from .collision import check_collisions  # noqa: PLC0415 — needs the geometry extra

    model = report.kinematics
    if model is None or not report.placements:
        report._warn("collision", "--collision was requested but the assembly could not be "
                     "placed, so no intersection was checked")
        report.collision = "not run"
        return
    poses = [("home", report.placements)]
    if len(report.poses) > 1:  # the sweep ran: the same poses, in the same order
        for spec in pose_sweep(report.joints, report.pose_samples, report.pose_seed)[1:]:
            poses.append((spec.name, model.place(model.values(spec.driven,
                                                              check_limits=False))))
    result = check_collisions(report, [c["id"] for c in doc["components"]], poses,
                              doc.get("allowed_overlaps") or [])
    report.collision = result.status
    report.collision_result = result


# ── entry point ───────────────────────────────────────────────────────────────
def validate_assembly(
    doc: object, resolver: ComponentResolver, *, collision: bool = False,
    pose_samples: int = POSE_SAMPLES, pose_seed: int = POSE_SEED,
) -> AssemblyReport:
    """Check an assembly document (ASM-1 §3, §9). Never raises on a bad document; every
    problem is a finding. `report.ok` is True iff there is no error. `pose_samples` and
    `pose_seed` set the Halton part of the pose sweep (conventions; see kinematics.py)."""
    report = AssemblyReport(pose_samples=pose_samples, pose_seed=pose_seed)
    if not _schema_step(doc, report):
        return report
    report.joints = joints_of(doc)
    for code, subject, message in static_kinematic_problems(doc):
        report._err(code, message, subject)
    path_static_step(doc, report)
    _allowed_overlap_problems(doc, report)
    kinematics_ok = not report.errors

    for component in doc["components"]:
        try:
            report.components[component["id"]] = resolver.resolve(component)
        except ResolutionError as exc:
            for problem in exc.problems:
                report._err("resolve", problem, component["id"])
        except Exception as exc:  # a resolver bug is a finding, never a crash
            report._err(
                "resolve", f"the resolver failed: {type(exc).__name__}: {exc}", component["id"]
            )
    paths = resolve_paths(doc, resolver, report) if kinematics_ok else {}

    joints_by_mate = {j.mate_id: j for j in report.joints}
    edges = []
    for mate in doc["mates"]:
        ia = _interface(report, mate, "a", report.components)
        ib = _interface(report, mate, "b", report.components)
        check = _mate_rule_step(report, mate, ia, ib) if ia and ib else None
        joint = joints_by_mate.get(mate["id"])
        if check is None:
            report.mates.append(MateCheck(mate["id"], _ref(mate, "a"), _ref(mate, "b"),
                                          joint=joint.id if joint else None))
            continue
        check.joint = joint.id if joint else None
        report.mates.append(check)
        edges.append((mate, check, ia, ib, joint))

    for mate, _check, ia, ib, _joint in edges:
        _offset_step(report, mate, ia, ib)

    try:
        home = joint_values(report.joints, check_limits=False) if kinematics_ok else {}
    except PoseError:
        home = {}
    if doc["root"] in report.components:
        model = KinematicModel(doc["root"], edges, report.joints)
        checks = {mate["id"]: check for mate, check, _ia, _ib, _j in edges}
        report.placements, home_checks = model.evaluate(home, checks)
        for check in home_checks:
            if check.origin_mm is not None:
                _closure_findings(report, check)
        report.kinematics = model
        report.poses.append(pose_result("home", "home", home, home_checks, report))
        limits = {jid: [report.poses[0]] for jid in report.poses[0].limit_violations}
        limit_findings(report, limits, 1)

    passive_children = {j.child for j in report.joints if j.passive} | {
        j.parent for j in report.joints if j.passive}
    for component in doc["components"] if doc["root"] in report.components else []:
        cid = component["id"]
        if cid in report.components and cid not in report.placements:
            hint = (" (a passive joint's mate never places a component)"
                    if cid in passive_children else "")
            report._err(
                "unreachable",
                "not reachable from the root through mates that pass the mating rule" + hint,
                cid,
            )

    failed_paths: set[str] = set()
    if report.placements:
        measure_paths(paths, report.placements, "home", report, failed_paths)
    driven = [j for j in report.joints if j.role == "driven"]
    if report.kinematics is not None and driven and kinematics_ok and not report.errors:
        sweep_step(report.kinematics, report, paths, failed_paths)
    for result in report.paths:
        if result.path_id not in failed_paths and result.length_mm is not None:
            result.ok = True
            loop = result.loop_length_mm
            if loop is not None and abs(result.length_mm - loop) > PATH_LOOP_TOLERANCE_MM:
                report._warn(
                    "path-length",
                    f"the computed pitch-line length at home is {result.length_mm:.4f} mm, but "
                    f"the belt's catalog loop length is {loop:g} mm ({result.length_mm - loop:+.4f}"
                    f" mm; > {PATH_LOOP_TOLERANCE_MM} mm, a convention)",
                    result.path_id,
                )
            spread = result.length_spread_mm
            if spread is not None and spread > PATH_LENGTH_TOLERANCE_MM:
                low = min(result.lengths, key=result.lengths.get)
                high = max(result.lengths, key=result.lengths.get)
                report._warn(
                    "path-length",
                    f"the pitch-line length varies by {spread:.4f} mm across the sweep "
                    f"(> {PATH_LENGTH_TOLERANCE_MM} mm, a convention): {result.lengths[low]:.4f} "
                    f"at {low}, {result.lengths[high]:.4f} at {high}",
                    result.path_id,
                )

    if collision:
        _collision_step(report, doc)
    if len(report.components) == len(doc["components"]):
        try:
            report.digest = assembly_digest(
                doc, {cid: rc.identity for cid, rc in report.components.items()},
                path_parts=getattr(report, "_path_parts", None) or None,
            )
        except (TypeError, ValueError) as exc:  # NaN / Infinity has no canonical JSON
            report._err("digest", f"the document has no canonical JSON form: {exc}")
    return report
