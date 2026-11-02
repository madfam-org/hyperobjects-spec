"""Gate G-X2, the keystone half: does a container's inside hold a content's envelope?

A game's box, its keep case, a media pocket: each is a container whose inside must hold an
object from another factory (a cartridge from the solid commons inside a carton from the sheet
commons). Neither commons pins the other, so the fit is decided here, over the facts both read.
Pliego's ``content_ref`` and the commons' title-edition kits call it; it never reads geometry.

    from hyperobjects_reference import load_object
    from hyperobjects_reference.fit import fit

    result = fit(load_object("some-keep-case"), load_object("some-game-card"), clearance_mm=0.5)
    result.verdict          # "fits" | "does not fit" | "unknown (null input)"

The inputs, per axis (``width``, ``height``, ``depth``, compared AS LABELLED: both objects
label their axes in the same frame, face width and height plus thickness; a rotated fit is
never inferred):

- **inside** — ``features.inside_<axis>_mm`` when it is not null; else the container's
  ``closed`` state less twice ``features.wall_mm`` (one wall each side);
- **content** — the content's envelope: its ``shell`` state, else ``body``, else ``closed``
  (the first one the object has);
- **required** — content plus twice ``clearance_mm`` (the clearance is per side).

The verdict is ``does not fit`` as soon as one axis with known inputs is short, whatever the
other axes say; else ``unknown (null input)`` when any input is null; else ``fits``. A margin
of exactly zero fits. Arithmetic is decimal, so ``0.1 + 0.2`` is ``0.3``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal

__all__ = [
    "AXES",
    "CONTENT_STATES",
    "DOES_NOT_FIT",
    "FITS",
    "UNKNOWN",
    "AxisFit",
    "FitResult",
    "content_envelope",
    "fit",
    "inside",
]

AXES = ("width", "height", "depth")
#: The states that are a content's envelope, in order of preference.
CONTENT_STATES = ("shell", "body", "closed")

FITS = "fits"
DOES_NOT_FIT = "does not fit"
UNKNOWN = "unknown (null input)"


@dataclass(frozen=True)
class AxisFit:
    """One axis: where the inside came from, the content, and the margin (all in mm)."""

    axis: str
    inside_mm: float | None
    inside_from: str | None
    content_mm: float | None
    required_mm: float | None
    margin_mm: float | None

    @property
    def fits(self) -> bool | None:
        """True or False when both inputs are known; None when either is null."""
        return None if self.margin_mm is None else self.margin_mm >= 0


@dataclass
class FitResult:
    """The verdict on one (container, content, clearance). Truthy only when it fits."""

    container: str
    content: str
    content_state: str | None
    clearance_mm: float
    verdict: str
    axes: list[AxisFit]
    #: The null inputs, as paths prefixed ``container:`` or ``content:``.
    unknown: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.verdict == FITS

    def as_dict(self) -> dict:
        return {
            "container": self.container,
            "content": self.content,
            "content_state": self.content_state,
            "clearance_mm": self.clearance_mm,
            "verdict": self.verdict,
            "axes": [{"axis": a.axis, "inside_mm": a.inside_mm, "inside_from": a.inside_from,
                      "content_mm": a.content_mm, "required_mm": a.required_mm,
                      "margin_mm": a.margin_mm, "fits": a.fits} for a in self.axes],
            "unknown": list(self.unknown),
        }


def _number(value: object) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return Decimal(str(value))


def _float(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def _state(obj: Mapping, name: str) -> Mapping | None:
    states = (obj.get("dimensions_mm") or {}).get("states") or {}
    state = states.get(name)
    return state if isinstance(state, Mapping) else None


def inside(container: Mapping, axis: str) -> tuple[Decimal | None, str | None, list[str]]:
    """``(inside, where it came from, null inputs)`` for one axis of a container."""
    features = container.get("features") or {}
    direct = f"features.inside_{axis}_mm"
    value = _number(features.get(f"inside_{axis}_mm"))
    if value is not None:
        return value, direct, []
    closed = _state(container, "closed") or {}
    outside = _number(closed.get(axis))
    wall = _number(features.get("wall_mm"))
    derived = f"dimensions_mm.states.closed.{axis} - 2 x features.wall_mm"
    if outside is not None and wall is not None:
        return outside - 2 * wall, derived, []
    missing = [direct]
    if outside is None:
        missing.append(f"dimensions_mm.states.closed.{axis}")
    if wall is None:
        missing.append("features.wall_mm")
    return None, None, missing


def content_envelope(content: Mapping) -> tuple[str | None, Mapping]:
    """The content's envelope state: ``(state name, {width, height, depth})``."""
    for name in CONTENT_STATES:
        state = _state(content, name)
        if state is not None:
            return name, state
    return None, {}


def fit(container: Mapping, content: Mapping, clearance_mm: float = 0.0) -> FitResult:
    """Whether ``container``'s inside holds ``content``'s envelope plus ``clearance_mm``
    per side, on every axis as labelled."""
    clearance = _number(clearance_mm)
    if clearance is None or clearance < 0:
        raise ValueError(f"clearance_mm must be a number >= 0, not {clearance_mm!r}")
    state_name, envelope = content_envelope(content)
    axes: list[AxisFit] = []
    unknown: list[str] = []
    for axis in AXES:
        room, source, missing = inside(container, axis)
        unknown += [f"container:{m}" for m in missing if f"container:{m}" not in unknown]
        size = _number(envelope.get(axis))
        if size is None:
            where = (f"dimensions_mm.states.{state_name}.{axis}" if state_name
                     else f"dimensions_mm.states.({'|'.join(CONTENT_STATES)})")
            unknown.append(f"content:{where}")
        required = None if size is None else size + 2 * clearance
        margin = None if room is None or required is None else room - required
        axes.append(AxisFit(axis, _float(room), source, _float(size), _float(required),
                            _float(margin)))
    if any(a.fits is False for a in axes):
        verdict = DOES_NOT_FIT
    elif unknown:
        verdict = UNKNOWN
    else:
        verdict = FITS
    return FitResult(
        container=str(container.get("key")),
        content=str(content.get("key")),
        content_state=state_name,
        clearance_mm=float(clearance),
        verdict=verdict,
        axes=axes,
        unknown=unknown,
    )
