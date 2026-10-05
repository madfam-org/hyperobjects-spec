"""The canonical assembly digest (ASM-1 §3.8), algorithm `hyperobjects-assembly-v1`.

    assembly_digest(doc, identities) =
        sha256( canonical_json({
            "algorithm":  "hyperobjects-assembly-v1",
            "document":   <the assembly document as parsed>,
            "components": {<component id>: <resolved identity>, ...},
            "path_parts": {<path id>: <belt's resolved identity>, ...},   # only with paths
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


def assembly_digest(doc: Mapping, identities: Mapping[str, Mapping],
                    path_parts: Mapping[str, Mapping] | None = None) -> str:
    """sha256 hex of the canonical JSON of the document plus every component's identity.

    `identities` maps every component id to its `ResolvedComponent.identity`.
    `path_parts` (ASM-1 §9, v1.3) maps every declared path id to its belt part's resolved
    identity; it enters the payload as `"path_parts"` only when the document declares a
    path, so the digest of every document without paths is unchanged.
    """
    payload = {
        "algorithm": ASSEMBLY_DIGEST_ALGORITHM,
        "document": doc,
        "components": dict(identities),
    }
    if path_parts:
        payload["path_parts"] = dict(path_parts)
    return hashlib.sha256(canonical_json(payload)).hexdigest()
