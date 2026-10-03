"""`validate_assembly(doc, resolver) -> AssemblyReport` — ASM-1 §3 steps 1–6 and 8.

    1. schema; unique component and mate ids; `root` and every mate endpoint exist
    2. resolve every component through the resolver (errors name the component)
    3. per mate: both interfaces exist and can mate (frame, polarity, size_key,
       symmetry), equal size_key, complementary polarity, equal symmetry, and a
       rotation that fits it (rotation_index < symmetry, or angle_deg for symmetry 0)
    4. placement: BFS from the root over the mates that passed step 3
    5. closure: EVERY mate (tree or not) re-checked in world space — origins ≤ 0.05 mm,
       normals antiparallel ≤ 0.5°, x-axes agree modulo the symmetry ≤ 0.5°
    6. every component reachable from the root
    7. (--collision) NOT implemented in v1: requesting it adds a warning saying no
       intersection was checked. It never reports a pass.
    8. the report, the placement table, and the canonical assembly digest

A pure function of the document and the resolver: no file is read here, so a service
holding its components elsewhere calls it with its own resolver.
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field

from .digest import assembly_digest
from .resolution import ComponentResolver, ResolutionError, ResolvedComponent, ResolvedInterface
from .transforms import (
    IDENTITY,
    Matrix,
    angle_between_deg,
    apply_vector,
    column,
    mate_transform,
    matmul,
    rigid_inverse,
)

__all__ = [
    "ANGLE_TOLERANCE_DEG",
    "ORIGIN_TOLERANCE_MM",
    "AssemblyFinding",
    "AssemblyReport",
    "MateCheck",
    "validate_assembly",
]

#: ASM-1 §3.5 / SEM-1 §2.3 mating rule.
ORIGIN_TOLERANCE_MM = 0.05
ANGLE_TOLERANCE_DEG = 0.5

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

    def as_dict(self) -> dict:
        def r(v):
            return None if v is None else round(v, 6) + 0.0
        return {
            "mate": self.mate_id, "a": self.a, "b": self.b, "symmetry": self.symmetry,
            "theta_deg": r(self.theta_deg), "in_tree": self.in_tree,
            "origin_mm": r(self.origin_mm), "normal_deg": r(self.normal_deg),
            "x_axis_deg": r(self.x_axis_deg), "measured_deg": r(self.measured_deg),
            "ok": self.ok,
        }


@dataclass
class AssemblyReport:
    findings: list[AssemblyFinding] = field(default_factory=list)
    components: dict[str, ResolvedComponent] = field(default_factory=dict)
    placements: dict[str, Matrix] = field(default_factory=dict)
    mates: list[MateCheck] = field(default_factory=list)
    digest: str | None = None
    collision: str = "not run"

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
            blocked.append(
                f"{side}: interface '{ref['component']}.{iface.id}' declares no {field_name}"
            )
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
def _place(root: str, edges: list[tuple[Mapping, MateCheck, ResolvedInterface,
                                          ResolvedInterface]]) -> dict[str, Matrix]:
    """BFS from the root. Mates are visited in document order, which makes the tree —
    and so the placement of an over-constrained assembly — deterministic."""
    placements: dict[str, Matrix] = {root: IDENTITY}
    queue = deque([root])
    while queue:
        current = queue.popleft()
        for mate, check, ia, ib in edges:
            ca, cb = mate["a"]["component"], mate["b"]["component"]
            if current not in (ca, cb):
                continue
            theta = math.radians(check.theta_deg)
            if current == ca and cb not in placements:
                placements[cb] = mate_transform(
                    placements[ca], ia.frame.homogeneous(), ib.frame.homogeneous(), theta
                )
            elif current == cb and ca not in placements:
                # M = Flip·Rz(θ) is an involution, so the same formula serves both ways.
                placements[ca] = mate_transform(
                    placements[cb], ib.frame.homogeneous(), ia.frame.homogeneous(), theta
                )
            else:
                continue
            check.in_tree = True
            queue.append(cb if current == ca else ca)
    return placements


def _closure(check: MateCheck, t_a: Matrix, t_b: Matrix, ia, ib) -> None:
    w_a = matmul(t_a, ia.frame.homogeneous())
    w_b = matmul(t_b, ib.frame.homogeneous())
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
        d = (phi - check.theta_deg) % period
        check.x_axis_deg = min(d, period - d)
    check.ok = (
        check.origin_mm <= ORIGIN_TOLERANCE_MM
        and check.normal_deg <= ANGLE_TOLERANCE_DEG
        and (check.x_axis_deg is None or check.x_axis_deg <= ANGLE_TOLERANCE_DEG)
    )


def _closure_findings(report: AssemblyReport, check: MateCheck) -> None:
    if not check.ok:
        parts = [f"origins {check.origin_mm:.4f} mm apart (≤ {ORIGIN_TOLERANCE_MM})",
                 f"normals {check.normal_deg:.4f}° from antiparallel (≤ {ANGLE_TOLERANCE_DEG})"]
        if check.x_axis_deg is not None:
            parts.append(
                f"x-axes {check.x_axis_deg:.4f}° apart modulo symmetry {check.symmetry} "
                f"(≤ {ANGLE_TOLERANCE_DEG})"
            )
        kind = "the BFS tree" if check.in_tree else "a cycle"
        report._err(
            "closure",
            f"{check.a} ↔ {check.b} does not hold (closes {kind}): " + "; ".join(parts),
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


# ── entry point ───────────────────────────────────────────────────────────────
def validate_assembly(
    doc: object, resolver: ComponentResolver, *, collision: bool = False
) -> AssemblyReport:
    """Check an assembly document (ASM-1 §3). Never raises on a bad document; every
    problem is a finding. `report.ok` is True iff there is no error."""
    report = AssemblyReport()
    if not _schema_step(doc, report):
        return report

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

    edges = []
    for mate in doc["mates"]:
        ia = _interface(report, mate, "a", report.components)
        ib = _interface(report, mate, "b", report.components)
        check = _mate_rule_step(report, mate, ia, ib) if ia and ib else None
        if check is None:
            report.mates.append(MateCheck(mate["id"], _ref(mate, "a"), _ref(mate, "b")))
            continue
        report.mates.append(check)
        edges.append((mate, check, ia, ib))

    if doc["root"] in report.components:
        report.placements = _place(doc["root"], edges)
    for mate, check, ia, ib in edges:
        ca, cb = mate["a"]["component"], mate["b"]["component"]
        if ca in report.placements and cb in report.placements:
            _closure(check, report.placements[ca], report.placements[cb], ia, ib)
            _closure_findings(report, check)

    for component in doc["components"] if doc["root"] in report.components else []:
        cid = component["id"]
        if cid in report.components and cid not in report.placements:
            report._err(
                "unreachable",
                "not reachable from the root through mates that pass the mating rule",
                cid,
            )

    if collision:
        report._warn(
            "collision",
            "--collision was requested but is not implemented in this version: no mesh "
            "intersection was checked (ASM-1 §3.7 is reported, not gating, in v1)",
        )
    if len(report.components) == len(doc["components"]):
        try:
            report.digest = assembly_digest(
                doc, {cid: rc.identity for cid, rc in report.components.items()}
            )
        except (TypeError, ValueError) as exc:  # NaN / Infinity has no canonical JSON
            report._err("digest", f"the document has no canonical JSON form: {exc}")
    return report
