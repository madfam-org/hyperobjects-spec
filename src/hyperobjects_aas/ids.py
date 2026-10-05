"""SEM-1 §1 — the permanent MADFAM identifier scheme, and AAS idShort rules.

Every identifier this package mints is built here and nowhere else, so the scheme has
one implementation that the projection and the checker share:

    asset_id("solid", "tslot-corner")                 # globalAssetId of the type asset
    shell_id("solid", "tslot-corner", tree)           # …/aas/solid/tslot-corner/{tree16}/p1
    shell_id("assembly", "fpv-5in-freestyle", digest) # one shell per assembly digest (ASM-1 §5)
    submodel_id("solid", "tslot-corner", tree, "Nameplate")   # …/{tree16}/p1/Nameplate
    material_shell_id("bambu-tpu-95a", card)          # content-addressed card shell, …/p1
    concept_id("bolt-pattern")                        # semanticId of a lexicon term
    template_id("mating-interfaces", 1, 0)            # a MADFAM submodel template
    parse_shell_id(ident)                             # -> ShellIdParts | None

``tree16`` is the first 16 hex characters of the GOC-1 ``tree_sha256`` of the cartridge
directory (``hyperobjects_schemas.generator_output.tree_sha256``), so a shell id names
one immutable revision of a design. For an ``assembly`` (ASM-1 §5) the same 16 hex are
the prefix of the canonical assembly digest (``hyperobjects-assembly-v1``), which moves
whenever the document or any component's resolved identity moves. ``content16`` is the
same prefix of the sha256 of a material card's canonical JSON.

**Projection version** (owner decision 2026-10-04). A shell id names the design revision
*and* the projection that produced its bytes: every shell and submodel id ends its
revision part with ``/p{N}``, where ``N`` is :data:`PROJECTION_VERSION`. Shells are
immutable per id (asset-shells refuses different bytes under a stored id with a 409), so
a projection change that moves the bytes for the same inputs must bump the version; the
new projection then lands as *new* shells beside the old ones instead of colliding with
them. ``scripts/refresh_assembly_golden.py --check`` and ``tests/test_projection_version.py``
enforce the bump. Asset ids, concept ids, template ids and standard-part ids name things
that do not depend on the projection, and carry no version.

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
from typing import NamedTuple

from hyperobjects_schemas.generator_output import canonical_json

__all__ = [
    "BASE",
    "COMMONS_REPOS",
    "KINDS",
    "PROJECTION_EXTENSION",
    "PROJECTION_VERSION",
    "IdShortAllocator",
    "ShellIdParts",
    "SubmodelIdParts",
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
    "parse_shell_id",
    "parse_submodel_id",
    "projection_extension",
    "projection_version",
    "shell_projection_version",
    "shell_id",
    "standard_part_id",
    "submodel_id",
    "template_id",
    "tree16",
]

#: The permanent namespace (owner decision, SEM-1 §0).
BASE = "https://id.madfam.io"

#: The version of the AAS projection this package writes (owner decision 2026-10-04). It is
#: part of every shell and submodel id (``…/{revision16}/p{N}``) and is recorded in the shell
#: as the ``ProjectionVersion`` extension. Bump it whenever the projected shell or submodel
#: bytes change for the same inputs; the golden drift guard fails until you do.
#:
#: * ``1`` — the 0.5.0 projection (assembly BoM/Mates/placement, IDTA 02020 capability,
#:   lexicon-attached interface terms) with the version itself added (package 0.6.0).
#: * ``2`` — every assembly shell gains the ``Kinematics`` submodel (ASM-1 §9: joints,
#:   machine-axis bindings, belt paths, the pose sweep) (package 0.7.0).
#: * ``3`` — a material card is projected in its canonical form (GOC-1 §3.1), the form
#:   its ``content16`` hashes, so a whole number's ``valueType`` follows its canonical
#:   value (``220.0`` -> ``xs:integer``) whatever the spelling; assemblies likewise
#:   project their canonical document (lane P6-PROJFIX, F1) (package 0.10.0).
PROJECTION_VERSION = 3

#: The type-asset kinds of SEM-1 §1 (plus ASM-1 §5's assemblies) and the commons
#: repository each one lives in. Assemblies are authored in the solid commons
#: (`assemblies/{slug}/assembly.json`, ASM-1 §7).
KINDS = ("solid", "soft", "assembly")
COMMONS_REPOS = {
    "solid": "solid-hyperobjects",
    "soft": "soft-hyperobjects",
    "assembly": "solid-hyperobjects",
}

#: The slug grammar both manifest schemas enforce (`project.slug`).
_SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
#: AAS v3.1.2 `idShort` pattern, verbatim from aas.json.
_ID_SHORT = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]*[a-zA-Z0-9_]+$")
_ID_SHORT_MAX = 128
#: AAS v3.1.2 `administration.version` / `revision` pattern, verbatim from aas.json.
_VERSION_PART = re.compile(r"^(0|[1-9][0-9]*)$")
_SEMVER_HEAD = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:\.|$)")
_HEX = re.compile(r"^[0-9a-f]{64}$")
#: Every kind that mints a shell: the type kinds plus content-addressed material cards.
_SHELL_KINDS = (*KINDS, "material")
_SHELL_KIND_RE = "|".join(_SHELL_KINDS)
_SLUG_RE = r"[a-z0-9][a-z0-9_-]*"
#: ``p`` + a positive integer without leading zeros.
_VERSION_RE = r"p([1-9][0-9]*)"
_SHELL_ID = re.compile(
    rf"^{re.escape(BASE)}/aas/({_SHELL_KIND_RE})/({_SLUG_RE})/([0-9a-f]{{16}})/{_VERSION_RE}$")
_SUBMODEL_ID = re.compile(
    rf"^{re.escape(BASE)}/sm/({_SHELL_KIND_RE})/({_SLUG_RE})/([0-9a-f]{{16}})/{_VERSION_RE}/([^/]+)$")


def _slug(slug: str) -> str:
    if not isinstance(slug, str) or not _SLUG.match(slug):
        raise ValueError(f"not a commons slug: {slug!r} (expected {_SLUG.pattern})")
    return slug


def _kind(kind: str) -> str:
    if kind not in KINDS:
        raise ValueError(f"unknown asset kind {kind!r}; expected one of {', '.join(KINDS)}")
    return kind


def projection_version(version: int | None = None) -> int:
    """The projection version to mint with: ``version`` when given, else the module's
    :data:`PROJECTION_VERSION` read at call time (so a test can patch it)."""
    value = PROJECTION_VERSION if version is None else version
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"not a projection version: {value!r} (a positive integer)")
    return value


def _p(version: int | None) -> str:
    return f"p{projection_version(version)}"


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


def shell_id(kind: str, slug: str, tree_sha256: str, *, version: int | None = None) -> str:
    """Type shell id: ``…/aas/{solid|soft|assembly}/{slug}/{tree16}/p{N}``."""
    return f"{BASE}/aas/{_kind(kind)}/{_slug(slug)}/{tree16(tree_sha256)}/{_p(version)}"


def submodel_id(kind: str, slug: str, tree_sha256: str, submodel_id_short: str, *,
                version: int | None = None) -> str:
    """Type submodel id: ``…/sm/{solid|soft|assembly}/{slug}/{tree16}/p{N}/{SubmodelIdShort}``."""
    if not is_id_short(submodel_id_short):
        raise ValueError(f"not a valid idShort: {submodel_id_short!r}")
    return (f"{BASE}/sm/{_kind(kind)}/{_slug(slug)}/{tree16(tree_sha256)}/{_p(version)}/"
            f"{submodel_id_short}")


def material_asset_id(slug: str) -> str:
    """Material card asset: ``…/asset/material/{slug}``."""
    return f"{BASE}/asset/material/{_slug(slug)}"


def material_shell_id(slug: str, card: object, *, version: int | None = None) -> str:
    """Material card shell: ``…/aas/material/{slug}/{content16}/p{N}``."""
    return f"{BASE}/aas/material/{_slug(slug)}/{content16(card)}/{_p(version)}"


def material_submodel_id(slug: str, card: object, submodel_id_short: str, *,
                         version: int | None = None) -> str:
    """Material card submodel, following the type-submodel pattern of §1:
    ``…/sm/material/{slug}/{content16}/p{N}/{SubmodelIdShort}``."""
    if not is_id_short(submodel_id_short):
        raise ValueError(f"not a valid idShort: {submodel_id_short!r}")
    return (f"{BASE}/sm/material/{_slug(slug)}/{content16(card)}/{_p(version)}/"
            f"{submodel_id_short}")


#: The name of the shell extension that records the projection version (SEM-1 §1).
PROJECTION_EXTENSION = "ProjectionVersion"


def projection_extension(version: int | None = None) -> dict:
    """The shell's ``extensions`` entry recording its projection version.

    ``administration`` is already the manifest semver (``version``/``revision``) and a
    shell has no submodel elements of its own, so the version goes where AAS v3.1 puts a
    fact about the element itself: a ``HasExtensions`` Extension on the shell. A reader
    gets it without parsing the id; ``aas check`` fails a shell whose extension and id
    disagree."""
    return {"name": PROJECTION_EXTENSION, "valueType": "xs:positiveInteger",
            "value": str(projection_version(version))}


def shell_projection_version(shell: object) -> int | None:
    """The projection version a shell records in its extension, or None."""
    for ext in (shell.get("extensions") or []) if isinstance(shell, dict) else []:
        if isinstance(ext, dict) and ext.get("name") == PROJECTION_EXTENSION:
            value = ext.get("value")
            if isinstance(value, str) and re.fullmatch(r"[1-9][0-9]*", value):
                return int(value)
            return None
    return None


class ShellIdParts(NamedTuple):
    """A parsed shell id: kind (solid, soft, assembly, material), slug, the 16-hex revision
    and the projection version."""

    kind: str
    slug: str
    revision16: str
    version: int

    @property
    def submodel_prefix(self) -> str:
        """Every submodel of this shell has an id that starts with this."""
        return f"{BASE}/sm/{self.kind}/{self.slug}/{self.revision16}/p{self.version}/"

    @property
    def revision_prefix(self) -> str:
        """The shell ids of every projection of this revision start with this."""
        return f"{BASE}/aas/{self.kind}/{self.slug}/{self.revision16}/"


class SubmodelIdParts(NamedTuple):
    kind: str
    slug: str
    revision16: str
    version: int
    id_short: str


def parse_shell_id(value: object) -> ShellIdParts | None:
    """The parts of a versioned shell id, or None (an unversioned id is not one)."""
    m = _SHELL_ID.match(value) if isinstance(value, str) else None
    return ShellIdParts(m[1], m[2], m[3], int(m[4])) if m else None


def parse_submodel_id(value: object) -> SubmodelIdParts | None:
    """The parts of a versioned submodel id, or None."""
    m = _SUBMODEL_ID.match(value) if isinstance(value, str) else None
    return SubmodelIdParts(m[1], m[2], m[3], int(m[4]), m[5]) if m else None


def standard_part_id(key: str) -> str:
    """A standard (COTS) part asset: ``…/asset/standard/{key}``.

    SEM-1 §1 keys it by the interface-sizes key (what a cartridge's ``bom.hardware`` names);
    ASM-1 §5 by the standard-parts catalog key (what an assembly component names). Both
    keys share one grammar, and for several parts they are the same string."""
    if not isinstance(key, str) or not re.match(r"^[a-z0-9][a-z0-9._-]*$", key):
        raise ValueError(f"not an interface-sizes or standard-parts key: {key!r}")
    return f"{BASE}/asset/standard/{key}"


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
