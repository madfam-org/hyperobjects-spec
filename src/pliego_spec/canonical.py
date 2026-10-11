"""The sheet document's canonical serialisation: Pliego spec §5.15 (RFC 8785, JCS).

`pliego:meta.digest` is ``"sha256:"`` + the hex SHA-256 of these bytes, computed with the
digest itself set to null (spec §5.7, §5.15). The form is RFC 8785, the JSON
Canonicalization Scheme: the bytes JavaScript's ``JSON.stringify`` writes for the parsed
document with every object's keys sorted, encoded as UTF-8. A reader in any language can
therefore reproduce the kernel's digest (``pliego.canonical_bytes``) and the engine's
(rule 10) from the JSON it received, whatever number spelling or key order the file used.

- **Objects:** members sorted by key as **UTF-16 code units** (JavaScript's default sort,
  which differs from code-point order only above the BMP); no whitespace.
- **Numbers:** IEEE-754 doubles printed as ECMAScript ``Number.prototype.toString``: the
  shortest round-trip digits, plain notation for 1e-7 <= |x| < 1e21 and exponent form
  otherwise (``e``, a sign, digits without leading zeros). So ``90.0`` -> ``90``,
  ``-0.0`` -> ``0``, ``1.5e-05`` -> ``0.000015``, ``1e-07`` -> ``1e-7``,
  ``1e+16`` -> ``10000000000000000``, ``1e21`` -> ``1e+21``. Integers beyond +/-2^53,
  NaN and the infinities are refused.
- **Strings:** ``JSON.stringify``'s escapes (``\\"``, ``\\\\``, ``\\b \\f \\n \\r \\t``,
  other controls as lower-case ``\\u00xx``; everything else, U+2028 and U+2029 included,
  as itself). A string or key holding a lone surrogate is refused.

**Why this is not GOC-1's `canonical_json`.** GOC-1 §3.1
(`hyperobjects_schemas.generator_output.canonical_json`) spells non-integral floats with
Python's ``repr`` (``1.5e-05``, ``1e-07``, ``1e+16``) and sorts keys by code point. Its
golden vectors, the AAS content-addressed ids, the assembly digest and the
standard-parts entry digests all hash those bytes, so changing it would move every one of
them. The two forms agree only on documents whose non-integral numbers lie in
1e-4 <= |x| < 1e16 and whose keys stay in the BMP (spec §5.15 says the same). So the
sheet document's digest is its own function, here, and GOC-1 is untouched.

Shared test vector: Pliego ``packages/kernel/tests/fixtures/digest_vector.json``, copied
byte for byte into ``tests/fixtures/sheet-documents/digest_vector.json`` (its NOTICE).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

__all__ = ["canonical_bytes", "es_number", "sheet_document_digest"]

#: ECMAScript's Number.MAX_SAFE_INTEGER + 1; an int beyond it is not exactly a double.
_MAX_SAFE = 2**53


def es_number(x: int | float) -> str:
    """``Number.prototype.toString`` of the double `x` (ECMA-262 Number::toString)."""
    if isinstance(x, bool):
        raise ValueError("canonical JSON: a boolean is not a number")
    if isinstance(x, int):
        if abs(x) > _MAX_SAFE:
            raise ValueError(f"canonical JSON: integer {x} is beyond 2^53")
        return str(x)
    if x != x or x in (float("inf"), float("-inf")):
        raise ValueError("canonical JSON: NaN and the infinities are not JSON")
    if x == 0:
        return "0"  # -0 included
    sign = "-" if x < 0 else ""
    # repr() is Python's shortest round-trip spelling: the same digit string ECMAScript
    # chooses (both are the shortest decimal that reads back as the same double).
    mantissa, _, exponent = repr(abs(x)).partition("e")
    whole, _, frac = mantissa.partition(".")
    digits = whole + frac
    leading = len(digits) - len(digits.lstrip("0"))
    d = digits.strip("0")  # the significant digits s, k of them
    k = len(d)
    n = len(whole) + int(exponent or 0) - leading  # x = 0.d × 10^n
    if k <= n <= 21:
        out = d + "0" * (n - k)
    elif 0 < n <= 21:
        out = d[:n] + "." + d[n:]
    elif -6 < n <= 0:
        out = "0." + "0" * (-n) + d
    else:
        e = n - 1
        out = (d if k == 1 else d[0] + "." + d[1:]) + ("e+" if e >= 0 else "e-") + str(abs(e))
    return sign + out


def _has_lone_surrogate(s: str) -> bool:
    # json.loads joins a valid 😀 pair into one code point, so any code point
    # left in the surrogate range is a lone half.
    return any(0xD800 <= ord(c) <= 0xDFFF for c in s)


def _string(s: str) -> str:
    if _has_lone_surrogate(s):
        raise ValueError("canonical JSON: a string holds a lone surrogate")
    # json.dumps(ensure_ascii=False) writes exactly JSON.stringify's escapes: the short
    # forms for \" \\ \b \f \n \r \t, lower-case \u00xx for the other C0 controls, and
    # every other character (U+007F, U+2028, U+2029, "/") as itself.
    return json.dumps(s, ensure_ascii=False)


def _utf16_key(k: str) -> bytes:
    # Big-endian UTF-16 bytes compare exactly as the sequence of code units does.
    return k.encode("utf-16-be")


def _emit(obj: Any, out: list[str]) -> None:
    if obj is None:
        out.append("null")
    elif obj is True:
        out.append("true")
    elif obj is False:
        out.append("false")
    elif isinstance(obj, (int, float)):
        out.append(es_number(obj))
    elif isinstance(obj, str):
        out.append(_string(obj))
    elif isinstance(obj, (list, tuple)):
        out.append("[")
        for i, value in enumerate(obj):
            if i:
                out.append(",")
            _emit(value, out)
        out.append("]")
    elif isinstance(obj, dict):
        if not all(isinstance(k, str) for k in obj):
            raise ValueError("canonical JSON: object keys must be strings")
        for k in obj:
            if _has_lone_surrogate(k):
                raise ValueError("canonical JSON: a key holds a lone surrogate")
        out.append("{")
        for i, k in enumerate(sorted(obj, key=_utf16_key)):
            if i:
                out.append(",")
            out.append(_string(k))
            out.append(":")
            _emit(obj[k], out)
        out.append("}")
    else:
        raise ValueError(f"canonical JSON: {type(obj).__name__} is not a JSON value")


def canonical_bytes(obj: Any) -> bytes:
    """Spec §5.15: the RFC 8785 canonical serialisation of `obj`, UTF-8 encoded.

    Raises ValueError for what has no canonical form: NaN, an infinity, an integer beyond
    2^53, a lone surrogate, a non-string key or a non-JSON value.
    """
    out: list[str] = []
    _emit(obj, out)
    return "".join(out).encode("utf-8")


def sheet_document_digest(doc: dict) -> str:
    """``sha256:<hex>`` of `canonical_bytes` of `doc` with ``pliego:meta.digest`` = null."""
    data = dict(doc)
    meta = data.get("pliego:meta")
    if isinstance(meta, dict):
        data["pliego:meta"] = {**meta, "digest": None}
    return "sha256:" + hashlib.sha256(canonical_bytes(data)).hexdigest()
