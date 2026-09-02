"""hyperobjects_schemas — the bundled JSON Schemas of the MADFAM hyperobject commons.

One place to read the contracts from, whichever side of the commons you author on:

    from hyperobjects_schemas import load, schema_path, list_schemas

    load("project-manifest")        # the Yantra4D cartridge manifest (solid side)
    load("garment-manifest")        # the Fashion Cabinet cartridge manifest (soft side)
    load("cross-commons-identity")  # the identity key that pairs the two

Names are given without the ``.schema.json`` suffix; the suffixed filename works too.

Provenance and the compat rule
------------------------------
These files are copies of the schemas each platform repo publishes:

  * ``project-manifest``   ← yantra4d/packages/schemas/
  * ``garment-manifest``, ``fabric-manifest``, ``body-measurements``
                           ← fashion-cabinet/packages/schemas/
  * ``cross-commons-identity``, ``lexicon-term``, ``commons-vocabulary``,
    ``article-frontmatter`` — authored HERE; this package is their home. The lexicon
    term schema formalizes RFC 0039 §3, the vocabulary schema its G3 controlled
    vocabularies, and the article schema its G2 elevation of the per-cartridge README;
    the corpus and the vocabularies they validate ship in ``hyperobjects_lexicon``.

``fc_spec`` deliberately keeps loading its own bundled copies from
``fc_spec/schemas/`` rather than reaching into this package: the FC runner's
loading path is a published contract that downstream CI lanes depend on, and
compat comes first. ``hyperobjects_schemas`` is the consolidation surface, and a
test in this repo asserts the two copies are byte-equal, so they cannot drift.
"""

from __future__ import annotations

import json
from functools import cache
from importlib import resources
from pathlib import Path

__all__ = ["load", "schema_path", "list_schemas", "SCHEMAS", "__version__"]

__version__ = "0.1.0"

# The schemas this package bundles: name -> the repo that publishes it.
SCHEMAS: dict[str, str] = {
    "project-manifest": "yantra4d",
    "garment-manifest": "fashion-cabinet",
    "fabric-manifest": "fashion-cabinet",
    "body-measurements": "fashion-cabinet",
    "cross-commons-identity": "hyperobjects-spec",
    "lexicon-term": "hyperobjects-spec",
    "commons-vocabulary": "hyperobjects-spec",
    "article-frontmatter": "hyperobjects-spec",
}


def _filename(name: str) -> str:
    return name if name.endswith(".schema.json") else f"{name}.schema.json"


def list_schemas() -> list[str]:
    """The bundled schema names (without the ``.schema.json`` suffix)."""
    return sorted(SCHEMAS)


def schema_path(name: str) -> Path:
    """Filesystem path to a bundled schema. Raises KeyError on an unknown name."""
    fname = _filename(name)
    stem = fname[: -len(".schema.json")]
    if stem not in SCHEMAS:
        raise KeyError(f"unknown schema {name!r}; known: {', '.join(list_schemas())}")
    return Path(str(resources.files("hyperobjects_schemas.schemas").joinpath(fname)))


@cache
def _load_cached(fname: str) -> dict:
    with resources.files("hyperobjects_schemas.schemas").joinpath(fname).open(
        encoding="utf-8"
    ) as f:
        return json.load(f)


def load(name: str) -> dict:
    """Load a bundled schema as a dict. Raises KeyError on an unknown name.

    The result is cached and SHARED — treat it as read-only, or copy before mutating.
    """
    fname = _filename(name)
    stem = fname[: -len(".schema.json")]
    if stem not in SCHEMAS:
        raise KeyError(f"unknown schema {name!r}; known: {', '.join(list_schemas())}")
    return _load_cached(fname)
