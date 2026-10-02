"""The canonical assembly digest (ASM-1 §3.8), algorithm `hyperobjects-assembly-v1`.

    assembly_digest(doc, identities) =
        sha256( canonical_json({
            "algorithm":  "hyperobjects-assembly-v1",
            "document":   <the assembly document as parsed>,
            "components": {<component id>: <resolved identity>, ...},
        }) )

`canonical_json` is GOC-1 §3.1 (integral floats become ints, sorted keys, no
whitespace, UTF-8), so `12.0` and `12` in a parameter hash identically and key order in
the file does not matter. The resolved identities are what the document alone cannot
say: a cartridge's GOC-1 `instance_id` (which moves when any file of the cartridge or
any of its resolved inputs moves), a standard part's catalog-entry digest and
parameters, an external design's declared facts. The asset-shells shell id uses the
first 16 hex (`digest16`, ASM-1 §5).
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping

from hyperobjects_schemas.generator_output import canonical_json

__all__ = ["ASSEMBLY_DIGEST_ALGORITHM", "assembly_digest"]

ASSEMBLY_DIGEST_ALGORITHM = "hyperobjects-assembly-v1"


def assembly_digest(doc: Mapping, identities: Mapping[str, Mapping]) -> str:
    """sha256 hex of the canonical JSON of the document plus every component's identity.

    `identities` maps every component id to its `ResolvedComponent.identity`.
    """
    payload = {
        "algorithm": ASSEMBLY_DIGEST_ALGORITHM,
        "document": doc,
        "components": dict(identities),
    }
    return hashlib.sha256(canonical_json(payload)).hexdigest()
