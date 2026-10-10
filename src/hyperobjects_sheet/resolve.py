"""``material_ref`` resolution: name-level first, as in the bridge handshake.

A cartridge in any commons may use a material another platform owns:

    {"platform": "fashion-cabinet", "material_slug": "popelina-algodon", "behaviour": "sheet"}

Resolution reads the owning platform's card from a supplied materials directory (a
``materials/`` folder, or a platform or commons root that contains one) and answers
three name-level questions: does the card exist, does it name itself by that slug, and
does it carry — or map, through a keystone rule, to — a valid ``sheet_behaviour``.
Physical checks (does the material really behave so) come later, with calibration,
exactly as ``ho-bridge`` proves a hardware link live before anyone claims it fits.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .behaviour import material_ref_errors, validate
from .mapping import MappingError, map_fc_fabric, map_pliego_stock

#: The card file each platform keeps per material, and where its own slug lives.
CARD_FILES: dict[str, tuple[str, str]] = {
    "pliego": ("stock.json", "stock"),
    "fashion-cabinet": ("material.json", "fabric"),
    "yantra4d": ("material.json", "material"),
}

# Resolution verdicts.
CARRIES = "carries"            # the card carries a valid sheet_behaviour block
MAPS = "maps"                  # a keystone rule maps the card to a valid document
NEEDS_DESCRIPTOR = "needs-descriptor"   # a filament card: maps only with a thin print
UNRESOLVED = "unresolved"


@dataclass
class Resolution:
    ref: Any
    status: str
    card_path: Path | None = None
    behaviour: dict | None = None
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status in (CARRIES, MAPS, NEEDS_DESCRIPTOR) and not self.problems


def materials_root(path: str | Path) -> Path:
    """``path`` itself if it holds material folders, else its ``materials/`` child."""
    p = Path(path)
    return p / "materials" if (p / "materials").is_dir() else p


def parse_materials_args(pairs: list[str] | None) -> dict[str, Path]:
    """``["pliego=DIR", "fashion-cabinet=DIR"]`` → ``{platform: materials root}``."""
    out: dict[str, Path] = {}
    for raw in pairs or []:
        platform, sep, directory = raw.partition("=")
        if not sep or platform not in CARD_FILES or not directory:
            raise ValueError(f"--materials expects PLATFORM=DIR with PLATFORM one of "
                             f"{', '.join(CARD_FILES)}; got {raw!r}")
        out[platform] = materials_root(directory)
    return out


def resolve_material_ref(ref: Any, materials: dict[str, Path]) -> Resolution:
    """Resolve one ``material_ref`` against ``{platform: materials root}``."""
    errs = material_ref_errors(ref)
    if errs:
        return Resolution(ref, UNRESOLVED, problems=errs)
    platform, slug = ref["platform"], ref["material_slug"]
    root = materials.get(platform)
    if root is None:
        return Resolution(ref, UNRESOLVED, problems=[
            f"{platform}/{slug}: no materials directory supplied for {platform!r}"])
    filename, ident = CARD_FILES[platform]
    path = root / slug / filename
    if not path.is_file():
        return Resolution(ref, UNRESOLVED, problems=[
            f"{platform}/{slug}: no card at {slug}/{filename} under {root}"])
    try:
        card = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return Resolution(ref, UNRESOLVED, path, problems=[f"{platform}/{slug}: unreadable "
                                                           f"card: {exc}"])
    named = (card.get(ident) or {}).get("slug") if isinstance(card, dict) else None
    if named != slug:
        return Resolution(ref, UNRESOLVED, path, problems=[
            f"{platform}/{slug}: the card names itself {named!r}"])

    carried = card.get("sheet_behaviour")
    if carried is not None:
        check = validate(carried)
        res = Resolution(ref, CARRIES if check.ok else UNRESOLVED, path,
                         carried if check.ok else None,
                         [f"{platform}/{slug}: carried sheet_behaviour: {e}"
                          for e in check.errors], list(check.notes))
        res.notes.append("the card carries its own block; the keystone mapping was not "
                         "consulted")
        return res

    if platform == "yantra4d":
        return Resolution(ref, NEEDS_DESCRIPTOR, path, notes=[
            f"{platform}/{slug}: a filament card is not a sheet by itself; it maps through "
            "a thin-print descriptor (layers, layer height, pattern) — rule y4d-thin-print/1"])
    rule = map_pliego_stock if platform == "pliego" else map_fc_fabric
    try:
        doc = rule(card)
    except MappingError as exc:
        return Resolution(ref, UNRESOLVED, path, problems=[f"{platform}/{slug}: {exc}"])
    check = validate(doc)
    if not check.ok:
        return Resolution(ref, UNRESOLVED, path, problems=[
            f"{platform}/{slug}: mapped document invalid: {e}" for e in check.errors])
    return Resolution(ref, MAPS, path, doc, notes=list(check.notes))


def resolver_for(materials: dict[str, Path]):
    """A callable ``ref → sheet_behaviour`` for :func:`stack.build_laminate`; raises
    ``ValueError`` naming the problem when a reference does not resolve to a sheet."""

    def _resolve(ref: dict) -> dict:
        res = resolve_material_ref(ref, materials)
        if res.behaviour is None:
            why = res.problems or res.notes or [res.status]
            raise ValueError("; ".join(why))
        return res.behaviour

    return _resolve
