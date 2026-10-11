"""Sheet-document rules from Pliego kernel 0.3.0 that need no polygon kernel.

Split out of `document` (the file-size gate), as the kernel splits them. Each follows the
kernel's own check at `pliego@2f85906`:

- `trace_problems` — §5.30's trace record (rule 13's record check for a `trace` finish):
  `packages/kernel/src/pliego/press.py` `_check_trace`, the 120° mitre test of `_stroke`
  and `_path_dist`. The stroke equality and the self-crossing test are NOT made here.
- `presentation_problems` — rule 17 (§5.16): `document_verify_view.py`
  `rule17_presentation`.
- `keys_problems` and `join_step_problems` — rules 19, 20 and 21 (§5.18–§5.20):
  `document_verify_engine.py` `rules19_21`.
"""

from __future__ import annotations

import math

__all__ = [
    "GATED",
    "KEYED",
    "RIDE",
    "join_step_problems",
    "keys_problems",
    "presentation_problems",
    "trace_problems",
]

#: Spec §5.18/§5.19 (rules 19–21): which types carry keys, ride, or can be step-activated.
KEYED = frozenset({"hinge", "rotate", "leaf", "translate", "slide"})
RIDE = frozenset({"hinge", "rotate", "translate"})
GATED = frozenset({"glue", "pivot", "string", "pin"})


def _is_index(value: object, bound: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value < bound


def _num(x: object) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _point(p: object) -> bool:
    return isinstance(p, list) and len(p) == 2 and all(_num(c) for c in p)


def _seg_dist(p: list, a: list, b: list) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy or 1.0)
    t = max(0.0, min(1.0, t))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def trace_problems(k: int, f: dict) -> list[str]:
    """§5.30's record checks a polygon-free reader can make (kernel `press._check_trace`)."""
    where = f"§8.13 pliego:finishes[{k}] (trace '{f.get('id')}')"
    out = []
    if _num(f.get("depth_mm")) and f["depth_mm"] != 0:
        out.append(f"{where}: a trace has no relief (depth_mm must be 0)")
    path, width = f.get("path"), f.get("width_mm")
    if not (isinstance(path, list) and len(path) >= 2 and all(_point(q) for q in path)
            and _num(width)):
        return out  # the schema has already said what is wrong with the shape
    units = []
    for i, (a, b) in enumerate(zip(path, path[1:], strict=False)):
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        if length < 1e-6:
            out.append(f"{where}: path segment {i} has zero length")
            return out
        units.append(((b[0] - a[0]) / length, (b[1] - a[1]) / length))
    for i in range(1, len(units)):
        (ux, uy), (vx, vy) = units[i - 1], units[i]
        # The kernel's mitre test: the sum of the two left normals, dotted with the first.
        if (-uy - vy) * -uy + (ux + vx) * ux < 0.5:
            out.append(f"{where}: the path turns sharper than 120° at point {i}")
    seen: set = set()
    for pad in f.get("pads") or []:
        if not isinstance(pad, dict):
            continue
        pid = pad.get("id")
        if pid in seen:
            out.append(f"{where}: pad id '{pid}' repeats")
        seen.add(pid)
        at, size = pad.get("at"), pad.get("size_mm")
        if _point(at) and _num(size):
            gap = min(_seg_dist(at, a, b) for a, b in zip(path, path[1:], strict=False))
            if gap > width / 2.0 + size / 2.0 + 1e-6:
                out.append(f"{where}: pad '{pid}' does not touch its trace (centre {gap:g} mm "
                           f"from the path; at most {width / 2 + size / 2:g} mm)")
    return out


def presentation_problems(sheets: list[dict], faces_sheet: list, n_f: int) -> list[str]:
    """Rule 17 (§5.16), as the kernel's `rule17_presentation`."""
    out = []
    for i, s in enumerate(sheets):
        pr = s.get("presentation")
        if not isinstance(pr, dict):
            continue
        where = f"§8.17 sheet '{s.get('id')}' presentation"
        if "root_face" in pr:
            f = pr["root_face"]
            if not (_is_index(f, n_f) and f < len(faces_sheet) and faces_sheet[f] == i):
                out.append(f"{where}: root_face {f!r} is not a face of this sheet")
        end = pr.get("end")
        if isinstance(end, dict):
            origin, q = end.get("origin"), end.get("rotation")
            ok = (isinstance(origin, list) and len(origin) == 3 and all(_num(c) for c in origin)
                  and isinstance(q, list) and len(q) == 4 and all(_num(c) for c in q)
                  and abs(math.sqrt(sum(c * c for c in q)) - 1.0) < 1e-6)
            if not ok:
                out.append(f"{where}: end needs a finite origin [x, y, z] and a unit "
                           f"quaternion rotation [x, y, z, w]")
    return out


def keys_problems(mechanisms: list[dict]) -> list[str]:
    """Rule 19 (§5.18), as the kernel's `rules19_21`."""
    out = []
    by_id = {m.get("id"): m for m in mechanisms}
    for m in mechanisms:
        where, kind = f"§8.19 mechanism '{m.get('id')}'", m.get("type")
        keys = m.get("keys")
        table = (isinstance(keys, list) and len(keys) >= 2
                 and all(isinstance(k, list) and len(k) == 2 and _num(k[0]) and _num(k[1])
                         for k in keys))
        if keys is not None:
            if kind not in KEYED:
                out.append(f"{where}: a '{kind}' cannot carry keys")
            elif not table:
                out.append(f"{where}: keys must list ≥ 2 [control value, output] pairs")
            else:
                if any(keys[i][0] <= keys[i - 1][0] for i in range(1, len(keys))):
                    out.append(f"{where}: key control values must increase strictly")
                travel = m.get("travel")
                if kind in ("translate", "slide") and _num(travel):
                    lo = 0.0 if kind == "slide" else -travel
                    if any(not lo - 1e-9 <= y <= travel + 1e-9 for _, y in keys):
                        out.append(f"{where}: a key output lies outside [{lo:g}, {travel:g}] mm")
        if "period" in m:
            period = m["period"]
            if keys is None:
                out.append(f"{where}: period needs keys")
            elif not (_num(period) and period > 0):
                out.append(f"{where}: period must be > 0")
            elif table and keys[-1][0] - keys[0][0] > period + 1e-9:
                out.append(f"{where}: keys span more than one period")
        if "ride" in m:
            ridden = by_id.get(m["ride"])
            if kind not in RIDE:
                out.append(f"{where}: a '{kind}' cannot ride another mechanism")
            elif ridden is None or ridden.get("type") not in RIDE:
                out.append(f"{where}: ride '{m['ride']}' is not a hinge, rotate or translate "
                           f"mechanism")
            else:
                seen, cur = {m.get("id")}, ridden
                while cur is not None:
                    if cur.get("id") in seen:
                        out.append(f"{where}: rides form a cycle")
                        break
                    seen.add(cur.get("id"))
                    cur = by_id.get(cur["ride"]) if "ride" in cur else None
    return out


def _step_index(steps: list[dict], ref: object) -> int:
    """The 0-based step a §5.19 reference names, or -1 when it names none."""
    if isinstance(ref, int) and not isinstance(ref, bool):
        return ref if 0 <= ref < len(steps) else -1
    if isinstance(ref, str):
        return next((k for k, st in enumerate(steps) if st.get("id") == ref), -1)
    return -1


def join_step_problems(joins: list[dict], steps: list[dict]) -> list[str]:
    """Rules 20 and 21 (§5.19, §5.20), as the kernel's `rules19_21`."""
    out = []
    by_id = {j.get("id"): j for j in joins}
    for j in joins:
        if "active_from" not in j:
            continue
        where = f"§8.20 join '{j.get('id')}'"
        if j.get("type") not in GATED:
            out.append(f"{where}: a '{j.get('type')}' join cannot carry active_from")
        elif not steps:
            out.append(f"{where}: active_from needs a fold program (pliego:sequence)")
        elif _step_index(steps, j["active_from"]) < 0:
            out.append(f"{where}: active_from {j['active_from']!r} is not a step id or index "
                       f"of the program")
    released: dict = {}
    for r, step in enumerate(steps):
        ids = step.get("release_joins")
        if not isinstance(ids, list):
            continue
        where = f"§8.21 step '{step.get('id')}'"
        for jid in ids:
            j = by_id.get(jid)
            if j is None:
                out.append(f"{where}: release_joins names '{jid}', which is not a join")
            elif j.get("type") not in GATED:
                out.append(f"{where}: join '{jid}' is a '{j.get('type')}', which cannot be "
                           f"released")
            elif jid in released:
                out.append(f"{where}: join '{jid}' is already released at step "
                           f"{released[jid]}")
            else:
                released[jid] = r
                k = _step_index(steps, j["active_from"]) if "active_from" in j else -1
                if k >= 0 and r <= k:
                    out.append(f"{where}: join '{jid}' is released at or before the step "
                               f"that activates it ({k})")
    return out
