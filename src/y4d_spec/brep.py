"""B-Rep validity: is the shape a solid BEFORE anybody tessellates it?

WHY THIS EXISTS (solid #45, tripod-hub, 2026-09-06)
---------------------------------------------------
`tripod-hub` swept its thread ribs along `cq.Wire.makeHelix(..., radius=1e-6)` — a
degenerate path. At 4.5 turns the `core.union(rib)` fuse returned ONE INVERTED SHELL:
13 individually valid faces, total volume −44.47 mm³, `BRepCheck_Analyzer(...).IsValid()`
False. macOS OCCT then carried that invalid solid through every subsequent boolean and
tessellated a watertight STL with the right body count and a plausible volume — so every
mesh check in geometry.py passed. The Linux OCP build segfaulted on the next boolean with
no Python traceback: two CI runners died and the failure was attributed to the runners.

The mesh bar in geometry.py cannot see this. It judges the STL, and tessellation is where
the evidence is destroyed: OCCT triangulates an inverted or self-inconsistent shell into
triangles that merge, seal and measure like a solid. By the time trimesh has an opinion,
the B-Rep that would have named the fault is gone. The check has to run on the SHAPE.

`grep -rl "radius=1e-6" --include=main.py` finds the same idiom in 28 solid-commons
cartridges, so any parameter change that pushes one past ~4 turns reproduces the same
untraceable Linux segfault. This gate makes that fail on the author's machine instead.

TWO GATES, BECAUSE ONE IS NOT ENOUGH
------------------------------------
1. ``BRepCheck_Analyzer(shape).IsValid()`` — OCCT's own topological/geometric audit. It
   catches the tripod-hub fuse (``face: UnorientableShape``) and the whole family of
   free edges, unclosed shells, bad orientations and invalid curves-on-surface.

2. ``BRepGProp.VolumeProperties_s`` signed volume — negative on the total, or on ANY
   solid inside a compound. This is NOT redundant: a solid whose orientation is simply
   REVERSED is *topologically perfect* and `IsValid()` returns **True** for it, while its
   signed volume is exactly minus the right answer. That is the inverted-shell signature,
   it is what prints as nothing, and gate 1 alone would wave it through.

Both are cheap — microseconds against a render measured in seconds — and both run on the
built shape, before export.

WHAT A FAILURE DOES
-------------------
It is a conformance FAILURE, and the STL is still exported so the author can look at what
the kernel produced. A gate that suppressed the artefact would be asking someone to debug
a shape they cannot open.

THE IMPORT GUARD
----------------
OCP is the CAD kernel's C extension and ships with the `[geometry]` extra. A
manifest-only install must never import it, exactly as geometry.py never imports
cadquery at module scope. Everything here imports inside the functions.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: How many distinct (sub-shape kind, status) lines a failure message prints. A shape
#: with one bad fuse reports one line; a thoroughly broken one can report hundreds of
#: repetitions of the same two statuses, and a wall of them buries the finding it is
#: supposed to deliver. The count of each kind survives (`×N`), so nothing is lost
#: except the repetition, and an elided remainder is stated rather than dropped.
MAX_STATUS_LINES = 4

#: Signed volumes are floats out of a numerical integration, so a shape whose true
#: volume is zero can land either side of it. Only a volume more negative than this
#: counts as inverted — below it the shape is degenerate-but-not-inverted, which the
#: mesh bar's own `volume <= 0` check reports in the language it already uses.
NEGATIVE_VOLUME_EPS = 1e-9


@dataclass
class BRepVerdict:
    """What the two gates found on one shape."""

    #: False when either gate failed. The render verdict is this.
    ok: bool
    #: `BRepCheck_Analyzer.IsValid()`, or None when the analyzer itself could not run.
    analyzer_valid: bool | None = None
    #: Total signed volume of the shape, or None when it could not be measured.
    volume: float | None = None
    #: Signed volumes of the negatively-oriented solids found inside, in the order the
    #: explorer walked them. Empty on a healthy shape.
    negative_solids: list[float] = field(default_factory=list)
    #: One line per finding, already formatted for a report.
    problems: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.ok


def brep_available() -> bool:
    """True when OCP can be imported — i.e. the [geometry] extra is really installed.

    A predicate, like geometry.geometry_available: the reason for a False is swallowed
    because the callers (the gate itself, the pytest skip) only need the verdict.
    """
    try:
        import OCP.BRepCheck  # noqa: F401
        import OCP.BRepGProp  # noqa: F401
    except Exception:
        return False
    return True


def _unwrap(shape):
    """The raw `TopoDS_Shape` behind whatever the caller passed.

    Callers hand this module CadQuery objects (`Workplane`, `Shape`) as often as raw
    OCCT ones, and the difference is an attribute lookup, not a reason for every call
    site to grow the same three lines.
    """
    val = shape
    # cq.Workplane — the modelling result the cartridge assigned to `result`.
    if hasattr(val, "val") and not hasattr(val, "wrapped"):
        val = val.val()
    # cq.Shape (Solid/Compound/…) — wraps the TopoDS_Shape.
    return getattr(val, "wrapped", val)


def status_names(shape) -> list[str]:
    """Readable `<kind>: <Status>` lines for the sub-shapes the analyzer rejects.

    `BRepCheck_Analyzer.Result(sub)` returns the per-sub-shape result whose `Status()`
    is a `BRepCheck_ListOfStatus`; `BRepCheck_NoError` entries are the analyzer saying
    "nothing wrong here" and are dropped. Identical findings are counted rather than
    repeated (see MAX_STATUS_LINES), because the useful content of a failure is WHICH
    statuses on WHICH kind of sub-shape, not how many times.

    Returns `[]` on a valid shape, and on a shape whose statuses could not be read: an
    empty list means "the analyzer named nothing", never "the shape is fine" — that is
    what `IsValid()` is for, and the caller has already asked it.
    """
    from collections import Counter

    from OCP.BRepCheck import BRepCheck_Analyzer, BRepCheck_Status
    from OCP.TopAbs import TopAbs_ShapeEnum
    from OCP.TopExp import TopExp_Explorer

    raw = _unwrap(shape)
    analyzer = BRepCheck_Analyzer(raw)

    def _of(sub) -> list[str]:
        try:
            result = analyzer.Result(sub)
        except Exception:
            # No result registered for this sub-shape: the analyzer had no complaint
            # about it, which is the common case on a mostly-healthy shape.
            return []
        if result is None:
            return []
        try:
            statuses = list(result.Status())
        except Exception:
            return []
        return [
            s.name.replace("BRepCheck_", "")
            for s in statuses
            if s != BRepCheck_Status.BRepCheck_NoError
        ]

    # Coarse to fine, so a shell-level fault is reported before the twenty edges under
    # it. VERTEX is walked too: a degenerate sweep (the tripod-hub idiom) can fail at
    # the vertex the helix collapsed to and nowhere else.
    kinds = (
        ("solid", TopAbs_ShapeEnum.TopAbs_SOLID),
        ("shell", TopAbs_ShapeEnum.TopAbs_SHELL),
        ("face", TopAbs_ShapeEnum.TopAbs_FACE),
        ("wire", TopAbs_ShapeEnum.TopAbs_WIRE),
        ("edge", TopAbs_ShapeEnum.TopAbs_EDGE),
        ("vertex", TopAbs_ShapeEnum.TopAbs_VERTEX),
    )

    counts: Counter = Counter()
    order: list[tuple[str, str]] = []

    def _record(kind: str, names: list[str]) -> None:
        for name in names:
            key = (kind, name)
            if key not in counts:
                order.append(key)
            counts[key] += 1

    _record("shape", _of(raw))
    for kind, enum in kinds:
        explorer = TopExp_Explorer(raw, enum)
        while explorer.More():
            _record(kind, _of(explorer.Current()))
            explorer.Next()

    lines = [
        f"{kind}: {name}" + (f" ×{counts[(kind, name)]}" if counts[(kind, name)] > 1 else "")
        for kind, name in order[:MAX_STATUS_LINES]
    ]
    remaining = len(order) - MAX_STATUS_LINES
    if remaining > 0:
        lines.append(f"(+{remaining} more status kind(s))")
    return lines


def signed_volumes(shape) -> tuple[float, list[float]]:
    """`(total signed volume, signed volume of every negatively-oriented solid)`.

    `BRepGProp.VolumeProperties_s` integrates over the shape's oriented faces, so a
    REVERSED solid contributes its volume with a minus sign — which is precisely how an
    inverted shell is detected while `IsValid()` still says True.

    A compound is walked solid by solid rather than trusted to its total: two inverted
    shells and one larger correct solid sum to a comfortable positive number, and the
    total alone would call that healthy. A shape with no TopAbs_SOLID under it (a bare
    shell or face) has no per-solid list, and only its total is reported.
    """
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.TopAbs import TopAbs_ShapeEnum
    from OCP.TopExp import TopExp_Explorer

    raw = _unwrap(shape)

    def _volume(sub) -> float:
        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(sub, props)
        return float(props.Mass())

    total = _volume(raw)

    negative: list[float] = []
    explorer = TopExp_Explorer(raw, TopAbs_ShapeEnum.TopAbs_SOLID)
    while explorer.More():
        vol = _volume(explorer.Current())
        if vol < -NEGATIVE_VOLUME_EPS:
            negative.append(vol)
        explorer.Next()

    return total, negative


def check_shape(shape) -> BRepVerdict:
    """Run both gates on one built shape and return the verdict.

    Never raises for a bad shape — a broken B-Rep is a finding, not an exception — and
    never raises for a kernel that will not answer either: an analyzer or an integration
    that blows up is recorded as a problem in its own words, because a verifier that
    crashes reports nothing about the cartridge it was checking.
    """
    from OCP.BRepCheck import BRepCheck_Analyzer

    raw = _unwrap(shape)
    problems: list[str] = []

    try:
        analyzer_valid: bool | None = bool(BRepCheck_Analyzer(raw).IsValid())
    except Exception as exc:
        analyzer_valid = None
        problems.append(
            f"B-Rep validity could not be evaluated "
            f"({type(exc).__name__}: {exc}) — the shape is UNVERIFIED"
        )

    if analyzer_valid is False:
        try:
            names = status_names(raw)
        except Exception as exc:
            names = [f"(status enumeration failed: {type(exc).__name__}: {exc})"]
        # A shape can be IsValid()-False while no sub-shape carries a status: the
        # analyzer's per-sub-shape results are only populated for the checks it ran,
        # and a fault found at the top level (or by the exact-method pass) leaves the
        # walk empty. That is a real finding — the shape IS invalid — so it must not
        # read as an absence of one. Observed on tripod-hub's `quarter_to_arca` at
        # the parent of #45, where `reducer_bushing` in the same cartridge did report
        # `face: UnorientableShape`.
        detail = (
            "; ".join(names)
            if names
            else (
                "the analyzer rejected the shape without attributing a status to any "
                "sub-shape (top-level fault)"
            )
        )
        problems.append(f"invalid B-Rep (BRepCheck): {detail}")

    volume: float | None
    negative: list[float] = []
    try:
        volume, negative = signed_volumes(raw)
    except Exception as exc:
        volume = None
        problems.append(
            f"signed volume could not be measured ({type(exc).__name__}: {exc})"
        )

    # The total is reported only when the per-solid walk found nothing to report:
    # on a single inverted solid both rules fire on the same fact, and saying it twice
    # in two wordings reads as two faults. The per-solid line is the more specific one
    # and wins; the total is what catches a shape with no TopAbs_SOLID under it at all.
    if volume is not None and volume < -NEGATIVE_VOLUME_EPS and not negative:
        problems.append(
            f"B-Rep signed volume is {volume:.4f} — the shape is inside-out "
            f"(an inverted shell), not a solid"
        )
    for i, vol in enumerate(negative):
        problems.append(
            f"B-Rep solid {i} has negative volume ({vol:.4f}) — an inverted shell "
            f"inside the compound; it tessellates into a plausible STL and segfaults "
            f"the next boolean on Linux"
        )

    return BRepVerdict(
        ok=not problems,
        analyzer_valid=analyzer_valid,
        volume=volume,
        negative_solids=negative,
        problems=problems,
    )


def check_result(result) -> list[tuple[str, BRepVerdict]]:
    """Both gates applied to a cartridge's whole result, member by member.

    A `cq.Assembly` exports as one STL but is BUILT as a tree of independently modelled
    children, and a single verdict over the export would name the assembly rather than
    the part that is broken. So each member is checked under its own name; anything else
    (a Workplane, a Shape) is one unnamed target.

    Returns `[(label, verdict), …]`. The caller decides what a failing label means; this
    function has no opinion about STL, and does not import cadquery unless it has to.
    """
    import cadquery as cq

    if isinstance(result, cq.Assembly):
        out: list[tuple[str, BRepVerdict]] = []
        for i, child in enumerate(result.traverse()):
            # traverse() yields (name, AssemblyObject) pairs; a node with no shape of
            # its own is a pure grouping node and has no B-Rep to judge.
            name, obj = child if isinstance(child, tuple) else (str(i), child)
            shape = getattr(obj, "obj", None)
            if shape is None:
                continue
            out.append((str(name), check_shape(shape)))
        return out

    return [("", check_shape(result))]
