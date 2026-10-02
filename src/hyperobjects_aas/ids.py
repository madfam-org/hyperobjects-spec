"""SEM-1 §1 — the permanent MADFAM identifier scheme, and AAS idShort rules.

Every identifier this package mints is built here and nowhere else, so the scheme has
one implementation that the projection and the checker share:

    asset_id("solid", "tslot-corner")                 # globalAssetId of the type asset
    shell_id("solid", "tslot-corner", tree)           # one shell per design revision
    submodel_id("solid", "tslot-corner", tree, "Nameplate")
    material_shell_id("bambu-tpu-95a", card)          # content-addressed card shell
    concept_id("bolt-pattern")                        # semanticId of a lexicon term
    template_id("mating-interfaces", 1, 0)            # a MADFAM submodel template

``tree16`` is the first 16 hex characters of the GOC-1 ``tree_sha256`` of the cartridge
directory (``hyperobjects_schemas.generator_output.tree_sha256``), so a shell id names
one immutable revision of a design. ``content16`` is the same prefix of the sha256 of a
material card's canonical JSON.

The AAS v3.1.2 metamodel constrains ``idShort`` to ``^[a-zA-Z][a-zA-Z0-9_-]*[a-zA-Z0-9_]+$``
(at least two characters, at most 128) and ``administration.version`` / ``revision`` to
``^(0|[1-9][0-9]*)$`` with at most four characters. Manifest ids and semvers do not always
fit, so :func:`id_short` and :func:`administration` map them deterministically; the exact
manifest value is always kept in a Property next to the element.
"""

from __future__ import annotations

import base64
import hashlib
import re

from hyperobjects_schemas.generator_output import canonical_json

__all__ = [
    "BASE",
    "COMMONS_REPOS",
    "KINDS",
    "IdShortAllocator",
    "administration",
    "asset_id",
    "concept_id",
    "content16",
    "encode_id",
    "id_short",
    "is_id_short",
    "material_asset_id",
    "material_shell_id",
    "material_submodel_id",
    "shell_id",
    "standard_part_id",
    "submodel_id",
    "template_id",
    "tree16",
]

#: The permanent namespace (owner decision, SEM-1 §0).
BASE = "https://id.madfam.io"

#: The two type-asset kinds of §1 and the commons repository each one lives in.
KINDS = ("solid", "soft")
COMMONS_REPOS = {"solid": "solid-hyperobjects", "soft": "soft-hyperobjects"}

#: The slug grammar both manifest schemas enforce (`project.slug`).
_SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
#: AAS v3.1.2 `idShort` pattern, verbatim from aas.json.
_ID_SHORT = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]*[a-zA-Z0-9_]+$")
_ID_SHORT_MAX = 128
#: AAS v3.1.2 `administration.version` / `revision` pattern, verbatim from aas.json.
_VERSION_PART = re.compile(r"^(0|[1-9][0-9]*)$")
_SEMVER_HEAD = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:\.|$)")
_HEX = re.compile(r"^[0-9a-f]{64}$")


def _slug(slug: str) -> str:
    if not isinstance(slug, str) or not _SLUG.match(slug):
        raise ValueError(f"not a commons slug: {slug!r} (expected {_SLUG.pattern})")
    return slug


def _kind(kind: str) -> str:
    if kind not in KINDS:
        raise ValueError(f"unknown asset kind {kind!r}; expected one of {', '.join(KINDS)}")
    return kind


def tree16(tree_sha256: str) -> str:
    """The first 16 hex characters of a GOC-1 ``tree_sha256``."""
    if not isinstance(tree_sha256, str) or not _HEX.match(tree_sha256):
        raise ValueError(f"not a sha256 hex digest: {tree_sha256!r}")
    return tree_sha256[:16]


def content16(card: object) -> str:
    """First 16 hex of the sha256 of a material card's canonical JSON (GOC-1 §3.1)."""
    return hashlib.sha256(canonical_json(card)).hexdigest()[:16]


def asset_id(kind: str, slug: str) -> str:
    """globalAssetId of a type asset: ``…/asset/{solid|soft}/{slug}``."""
    return f"{BASE}/asset/{_kind(kind)}/{_slug(slug)}"


def shell_id(kind: str, slug: str, tree_sha256: str) -> str:
    """Type shell id: ``…/aas/{solid|soft}/{slug}/{tree16}``."""
    return f"{BASE}/aas/{_kind(kind)}/{_slug(slug)}/{tree16(tree_sha256)}"


def submodel_id(kind: str, slug: str, tree_sha256: str, submodel_id_short: str) -> str:
    """Type submodel id: ``…/sm/{solid|soft}/{slug}/{tree16}/{SubmodelIdShort}``."""
    if not is_id_short(submodel_id_short):
        raise ValueError(f"not a valid idShort: {submodel_id_short!r}")
    return f"{BASE}/sm/{_kind(kind)}/{_slug(slug)}/{tree16(tree_sha256)}/{submodel_id_short}"


def material_asset_id(slug: str) -> str:
    """Material card asset: ``…/asset/material/{slug}``."""
    return f"{BASE}/asset/material/{_slug(slug)}"


def material_shell_id(slug: str, card: object) -> str:
    """Material card shell: ``…/aas/material/{slug}/{content16}``."""
    return f"{BASE}/aas/material/{_slug(slug)}/{content16(card)}"


def material_submodel_id(slug: str, card: object, submodel_id_short: str) -> str:
    """Material card submodel, following the type-submodel pattern of §1:
    ``…/sm/material/{slug}/{content16}/{SubmodelIdShort}``."""
    if not is_id_short(submodel_id_short):
        raise ValueError(f"not a valid idShort: {submodel_id_short!r}")
    return f"{BASE}/sm/material/{_slug(slug)}/{content16(card)}/{submodel_id_short}"


def standard_part_id(size_key: str) -> str:
    """A standard (COTS) part asset: ``…/asset/standard/{size-key}``."""
    if not isinstance(size_key, str) or not re.match(r"^[a-z0-9][a-z0-9._-]*$", size_key):
        raise ValueError(f"not an interface-sizes key: {size_key!r}")
    return f"{BASE}/asset/standard/{size_key}"


def concept_id(term_id: str) -> str:
    """The IRI of a lexicon term — derived, never stored (SEM-1 §4)."""
    return f"{BASE}/concept/{_slug(term_id)}"


def template_id(name: str, major: int, minor: int) -> str:
    """A MADFAM submodel template: ``…/smt/{template-name}/{major}/{minor}``."""
    return f"{BASE}/smt/{_slug(name)}/{int(major)}/{int(minor)}"


def encode_id(identifier: str) -> str:
    """UTF8-BASE64-URL encoding of an identifier for AAS Part-2 API paths (no padding)."""
    return base64.urlsafe_b64encode(identifier.encode("utf-8")).decode("ascii").rstrip("=")


def administration(semver: object) -> dict | None:
    """``{"version": major, "revision": minor}`` from a manifest semver, or None.

    The metamodel allows only ``^(0|[1-9][0-9]*)$`` of at most 4 characters in each
    field, so ``1.2.3`` becomes version ``1``, revision ``2``; the full semver goes in a
    ``ManifestVersion`` Property (SEM-1 §1). A version that does not start with
    ``MAJOR.MINOR`` (or whose parts exceed 4 digits) yields None: no administration is
    better than an invented one.
    """
    if not isinstance(semver, str):
        return None
    match = _SEMVER_HEAD.match(semver.strip())
    if not match:
        return None
    major, minor = match.group(1), match.group(2)
    if len(major) > 4 or len(minor) > 4:
        return None
    return {"version": major, "revision": minor}


def is_id_short(value: object) -> bool:
    """True iff ``value`` satisfies the AAS v3.1.2 idShort constraints."""
    return (
        isinstance(value, str)
        and 0 < len(value) <= _ID_SHORT_MAX
        and _ID_SHORT.match(value) is not None
    )


def id_short(raw: object, fallback: str = "Element") -> str:
    """Map an arbitrary manifest id onto a valid idShort, deterministically.

    Characters outside ``[A-Za-z0-9_-]`` become ``_``; a leading non-letter gets the
    prefix ``x``; a trailing ``-`` becomes ``_``; a single character gets a trailing
    ``_``; the result is cut to 128 characters. Ids that are already valid (all but a
    handful in either commons) pass through unchanged.
    """
    text = raw if isinstance(raw, str) else ""
    text = re.sub(r"[^A-Za-z0-9_-]", "_", text)
    if not text:
        text = fallback
    if not text[0].isalpha() or not text[0].isascii():
        text = "x" + text
    text = text[:_ID_SHORT_MAX]
    if text.endswith("-"):
        text = text[:-1] + "_"
    if len(text) < 2:
        text = text + "_"
    return text


class IdShortAllocator:
    """Allocates unique idShorts among siblings (AASd-022) for one container."""

    def __init__(self, reserved: tuple[str, ...] = ()) -> None:
        self._taken: set[str] = set(reserved)

    def take(self, raw: object, fallback: str = "Element") -> str:
        base = id_short(raw, fallback)
        candidate, n = base, 2
        while candidate in self._taken:
            suffix = f"_{n}"
            candidate = base[: _ID_SHORT_MAX - len(suffix)] + suffix
            n += 1
        self._taken.add(candidate)
        return candidate


def version_part_ok(value: object) -> bool:
    """True iff ``value`` is a valid ``administration.version`` / ``revision``."""
    return isinstance(value, str) and len(value) <= 4 and _VERSION_PART.match(value) is not None
