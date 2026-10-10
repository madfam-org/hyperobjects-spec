"""Sheet documents: the vendored schema plus the STRUCTURAL subset of the semantic rules.

A sheet document is the FOLD 1.2 file (with `pliego:` extensions) the Pliego kernel
writes from a cartridge (Pliego `docs/spec/v1/sheet-document.md`). Its JSON Schema is
vendored byte-identical in ``pliego_spec/schemas/`` (see VENDORED.md); the semantic rules
of spec §8 are enforced in full by the kernel's ``pliego.document.verify()`` and the
engine's ``loadDocument()``. This module checks the subset that needs no geometry:

  §8.1  every per-vertex / per-edge / per-face array has the right length, and every
        index is in range;
  §8.2  an edge's two vertices and a face's vertices belong to the edge's/face's sheet;
  §8.4  the assignment/treatment pairs of spec §4, and fold angle 0 for B/F/C/J/U edges;
  §8.6  every sheet's stock key resolves in `pliego:stocks`;
  §8.7  every join, mechanism and control reference resolves (sheets, mechanisms,
        controls), ids are unique, and a sequence has its `sequence` control;
  §8.8  every sequence target is an M/V/F edge, and every release index is in range;
  §8.9  (structural half) a 3-D frame has one coordinate per vertex;
  §8.10 `pliego:meta.digest`, when present, equals the SHA-256 of the GOC-1 canonical
        serialisation of the document with `digest` set to null.

NOT checked here, and said so on every run (``geometry=NOT verified``): §8.3 (faces
simple, counter-clockwise, non-degenerate, tiling their sheet), §8.5 (sheets do not
overlap in the layout frame), §8.7's point-in-sheet containment, and §8.9's
developability and glue-weld tolerances. Those need a polygon kernel; they arrive with
a public verifier (a keystone geometry lane or the published Pliego kernel), and until
then a pass here is a STRUCTURAL pass only.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from importlib import resources

from hyperobjects_schemas.generator_output import canonical_json

__all__ = [
    "DOCUMENT_SCHEMA",
    "ALLOWED_TREATMENT",
    "UNCHECKED_RULES",
    "DocumentResult",
    "load_document_schema",
    "document_digest",
    "check_document",
]

DOCUMENT_SCHEMA = "sheet-document.schema.json"

#: Spec §4: the assignments each treatment admits.
ALLOWED_TREATMENT: dict[str, frozenset[str]] = {
    "none": frozenset("BJUF"),
    "crease": frozenset("MVF"),
    "score": frozenset("MVF"),
    "perforation": frozenset("MVFC"),
    "cut": frozenset("C"),
    "halfcut": frozenset("F"),
}
#: Spec §2: `edges_foldAngle` is 0 for these assignments.
ZERO_ANGLE = frozenset("BFCJU")
#: Spec §5.6/§8.8: a sequence may drive only these.
FOLDABLE = frozenset("MVF")

#: The §8 rules this module does not verify — printed with every verdict.
UNCHECKED_RULES = ("8.3", "8.5", "8.7 containment", "8.9 developability")


@dataclass
class DocumentResult:
    ok: bool
    problems: list[str] = field(default_factory=list)
    sheets: int = 0
    vertices: int = 0
    edges: int = 0
    faces: int = 0
    joins: int = 0

    def __bool__(self) -> bool:
        return self.ok


def load_document_schema() -> dict:
    with resources.files("pliego_spec.schemas").joinpath(DOCUMENT_SCHEMA).open(
        encoding="utf-8"
    ) as f:
        return json.load(f)


def document_digest(doc: dict) -> str:
    """`sha256:<hex>` of the GOC-1 canonical serialisation with meta.digest = null."""
    copy = json.loads(json.dumps(doc))
    meta = copy.get("pliego:meta")
    if isinstance(meta, dict):
        meta["digest"] = None
    return "sha256:" + hashlib.sha256(canonical_json(copy)).hexdigest()


def _schema_problems(doc: object) -> list[str]:
    from jsonschema import Draft202012Validator

    validator = Draft202012Validator(load_document_schema())
    out = []
    for err in sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in err.absolute_path) or "<root>"
        out.append(f"schema {where}: {err.message}")
    return out


def _arr(doc: dict, key: str) -> list:
    value = doc.get(key)
    return value if isinstance(value, list) else []


def _is_index(value: object, bound: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value < bound


def _structural_problems(doc: dict) -> list[str]:
    problems: list[str] = []
    say = problems.append

    coords = _arr(doc, "vertices_coords")
    ev = _arr(doc, "edges_vertices")
    fv = _arr(doc, "faces_vertices")
    sheets = [s for s in _arr(doc, "pliego:sheets") if isinstance(s, dict)]
    n_v, n_e, n_f, n_s = len(coords), len(ev), len(fv), len(sheets)

    # §8.1 lengths
    for key, n, what in (
        ("pliego:vertices_sheet", n_v, "vertex"),
        ("edges_assignment", n_e, "edge"),
        ("edges_foldAngle", n_e, "edge"),
        ("pliego:edges_sheet", n_e, "edge"),
        ("pliego:edges_treatment", n_e, "edge"),
        ("pliego:faces_sheet", n_f, "face"),
    ):
        if len(_arr(doc, key)) != n:
            say(f"§8.1 {key}: {len(_arr(doc, key))} entries for {n} {what}s")
    for key, n, what in (
        ("pliego:edges_restAngle", n_e, "edge"),
        ("edges_length", n_e, "edge"),
        ("faces_edges", n_f, "face"),
    ):
        if key in doc and len(_arr(doc, key)) != n:
            say(f"§8.1 {key}: {len(_arr(doc, key))} entries for {n} {what}s")

    # §8.1 index ranges
    for e, pair in enumerate(ev):
        for v in pair if isinstance(pair, list) else []:
            if not _is_index(v, n_v):
                say(f"§8.1 edges_vertices[{e}]: vertex {v!r} out of range (0..{n_v - 1})")
    for f, cycle in enumerate(fv):
        for v in cycle if isinstance(cycle, list) else []:
            if not _is_index(v, n_v):
                say(f"§8.1 faces_vertices[{f}]: vertex {v!r} out of range (0..{n_v - 1})")
    for f, cycle in enumerate(_arr(doc, "faces_edges")):
        for e in cycle if isinstance(cycle, list) else []:
            if not _is_index(e, n_e):
                say(f"§8.1 faces_edges[{f}]: edge {e!r} out of range (0..{n_e - 1})")
    for key in ("pliego:vertices_sheet", "pliego:edges_sheet", "pliego:faces_sheet"):
        for i, s in enumerate(_arr(doc, key)):
            if not _is_index(s, n_s):
                say(f"§8.1 {key}[{i}]: sheet {s!r} out of range (0..{n_s - 1})")
    for i, order in enumerate(_arr(doc, "faceOrders")):
        if isinstance(order, list) and len(order) >= 2:
            for f in order[:2]:
                if not _is_index(f, n_f):
                    say(f"§8.1 faceOrders[{i}]: face {f!r} out of range (0..{n_f - 1})")

    # §8.2 sheet membership
    vs = _arr(doc, "pliego:vertices_sheet")
    es = _arr(doc, "pliego:edges_sheet")
    fs = _arr(doc, "pliego:faces_sheet")

    def _vsheet(v: object) -> object:
        return vs[v] if _is_index(v, len(vs)) else None

    for e, pair in enumerate(ev):
        if e < len(es) and isinstance(pair, list):
            for v in pair:
                if _is_index(v, n_v) and _vsheet(v) != es[e]:
                    say(f"§8.2 edge {e} (sheet {es[e]}) uses vertex {v} of sheet {_vsheet(v)}")
    for f, cycle in enumerate(fv):
        if f < len(fs) and isinstance(cycle, list):
            for v in cycle:
                if _is_index(v, n_v) and _vsheet(v) != fs[f]:
                    say(f"§8.2 face {f} (sheet {fs[f]}) uses vertex {v} of sheet {_vsheet(v)}")

    # §8.4 assignment / treatment, zero fold angles
    assign = _arr(doc, "edges_assignment")
    treat = _arr(doc, "pliego:edges_treatment")
    angles = _arr(doc, "edges_foldAngle")
    for e in range(min(len(assign), len(treat))):
        allowed = ALLOWED_TREATMENT.get(treat[e])
        if allowed is not None and assign[e] not in allowed:
            say(f"§8.4 edge {e}: treatment '{treat[e]}' does not admit assignment "
                f"'{assign[e]}' (admits {', '.join(sorted(allowed))})")
    for e in range(min(len(assign), len(angles))):
        if assign[e] in ZERO_ANGLE and isinstance(angles[e], (int, float)) and angles[e] != 0:
            say(f"§8.4 edge {e}: assignment '{assign[e]}' must have fold angle 0 "
                f"(has {angles[e]})")

    # §8.6 / §8.7 references
    stocks = doc.get("pliego:stocks") if isinstance(doc.get("pliego:stocks"), dict) else {}
    sheet_ids = [s.get("id") for s in sheets]
    mechanisms = [m for m in _arr(doc, "pliego:mechanisms") if isinstance(m, dict)]
    controls = [c for c in _arr(doc, "pliego:controls") if isinstance(c, dict)]
    joins = [j for j in _arr(doc, "pliego:joins") if isinstance(j, dict)]
    mech_by_id = {m.get("id"): m for m in mechanisms}
    control_ids = {c.get("id") for c in controls}

    for label, ids in (("pliego:sheets", sheet_ids),
                       ("pliego:mechanisms", [m.get("id") for m in mechanisms]),
                       ("pliego:controls", [c.get("id") for c in controls]),
                       ("pliego:joins", [j.get("id") for j in joins])):
        seen: set = set()
        for i in ids:
            if i in seen:
                say(f"§8.7 {label}: id '{i}' is declared more than once")
            seen.add(i)

    known_sheets = set(sheet_ids)

    def _sheet_ref(value: object, where: str) -> None:
        if value not in known_sheets:
            say(f"§8.7 {where}: unknown sheet '{value}'")

    for s in sheets:
        if s.get("stock") not in stocks:
            say(f"§8.6 sheet '{s.get('id')}': stock '{s.get('stock')}' is not in pliego:stocks")
        kin = s.get("kinematic")
        if isinstance(kin, dict) and kin.get("mechanism") not in mech_by_id:
            say(f"§8.7 sheet '{s.get('id')}': kinematic mechanism '{kin.get('mechanism')}' "
                f"is not declared")

    for j in joins:
        jid = j.get("id")
        for end in ("a", "b", "track"):
            ref = j.get(end)
            if isinstance(ref, dict) and "sheet" in ref:
                _sheet_ref(ref["sheet"], f"join '{jid}'.{end}")
        if "mechanism" in j:
            want = {"slider": "slide", "pin": "translate"}.get(j.get("type"))
            mech = mech_by_id.get(j["mechanism"])
            if mech is None:
                say(f"§8.7 join '{jid}': mechanism '{j['mechanism']}' is not declared")
            elif want and mech.get("type") != want:
                say(f"§8.7 join '{jid}': a {j.get('type')} join is driven by a '{want}' "
                    f"mechanism, not '{mech.get('type')}'")

    for m in mechanisms:
        mid = m.get("id")
        for key in ("angle_control", "control"):
            if key in m and m[key] not in control_ids:
                say(f"§8.7 mechanism '{mid}': {key} '{m[key]}' is not in pliego:controls")
        for sid in m.get("sheets_moving") or []:
            _sheet_ref(sid, f"mechanism '{mid}'.sheets_moving")
        if "sheet" in m:
            _sheet_ref(m["sheet"], f"mechanism '{mid}'.sheet")
        center = m.get("center")
        if isinstance(center, dict):
            _sheet_ref(center.get("sheet"), f"mechanism '{mid}'.center")

    # §8.8 sequence
    sequence = doc.get("pliego:sequence")
    if isinstance(sequence, dict):
        if not any(c.get("kind") == "sequence" for c in controls):
            say("§8.7 pliego:sequence: no control of kind 'sequence' — the sequence clock must "
                "be declared in pliego:controls")
        for step in sequence.get("steps") or []:
            if not isinstance(step, dict):
                continue
            sid = step.get("id")
            for target in step.get("targets") or []:
                e = target[0] if isinstance(target, list) and target else None
                if not _is_index(e, n_e):
                    say(f"§8.8 step '{sid}': target edge {e!r} out of range")
                elif e < len(assign) and assign[e] not in FOLDABLE:
                    say(f"§8.8 step '{sid}': target edge {e} is '{assign[e]}', not M/V/F")
            for e in step.get("release") or []:
                if not _is_index(e, n_e):
                    say(f"§8.8 step '{sid}': release edge {e!r} out of range")

    # §8.9 structural half: one 3-D coordinate per vertex, unique frame titles
    titles: set = set()
    for i, frame in enumerate(_arr(doc, "file_frames")):
        if not isinstance(frame, dict):
            continue
        title = frame.get("frame_title")
        if title in titles:
            say(f"§8.9 file_frames[{i}]: frame title '{title}' repeats")
        titles.add(title)
        if len(_arr(frame, "vertices_coords")) != n_v:
            say(f"§8.9 file_frames[{i}] ('{title}'): {len(_arr(frame, 'vertices_coords'))} "
                f"coordinates for {n_v} vertices")

    # §8.10 digest
    meta = doc.get("pliego:meta")
    if isinstance(meta, dict) and isinstance(meta.get("digest"), str):
        try:
            actual = document_digest(doc)
        except ValueError as exc:
            say(f"§8.10 pliego:meta.digest: the document has no canonical form — {exc}")
        else:
            if meta["digest"] != actual:
                say(f"§8.10 pliego:meta.digest: {meta['digest']} does not match the "
                    f"document ({actual})")
    return problems


def check_document(doc: object) -> DocumentResult:
    """Schema + the structural §8 subset. Nothing short-circuits."""
    if not isinstance(doc, dict):
        return DocumentResult(ok=False, problems=["<root>: a sheet document is a JSON object"])
    problems = _schema_problems(doc) + _structural_problems(doc)
    sheets = _arr(doc, "pliego:sheets")
    if not sheets:
        problems.append("sheets=0 — a sheet document with no sheet is a failure")
    return DocumentResult(
        ok=not problems,
        problems=problems,
        sheets=len(sheets),
        vertices=len(_arr(doc, "vertices_coords")),
        edges=len(_arr(doc, "edges_vertices")),
        faces=len(_arr(doc, "faces_vertices")),
        joins=len(_arr(doc, "pliego:joins")),
    )
