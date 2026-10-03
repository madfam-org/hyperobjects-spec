"""SEM-1 §1 identifiers and the AAS idShort / administration constraints."""

from __future__ import annotations

import base64
import re

import pytest

from hyperobjects_aas import ids

TREE = "0123456789abcdef" + "0" * 48
IDSHORT = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]*[a-zA-Z0-9_]+$")


def test_type_identifiers_follow_the_scheme():
    assert ids.asset_id("solid", "tslot-corner") == "https://id.madfam.io/asset/solid/tslot-corner"
    assert ids.shell_id("soft", "a-line-skirt", TREE) == (
        "https://id.madfam.io/aas/soft/a-line-skirt/0123456789abcdef")
    assert ids.submodel_id("solid", "tslot-corner", TREE, "Nameplate") == (
        "https://id.madfam.io/sm/solid/tslot-corner/0123456789abcdef/Nameplate")


def test_other_identifiers_follow_the_scheme():
    assert ids.concept_id("bolt-pattern") == "https://id.madfam.io/concept/bolt-pattern"
    assert ids.template_id("mating-interfaces", 1, 0) == (
        "https://id.madfam.io/smt/mating-interfaces/1/0")
    assert ids.standard_part_id("nema-17-face") == "https://id.madfam.io/asset/standard/nema-17-face"
    assert ids.material_asset_id("bambu-tpu-95a") == (
        "https://id.madfam.io/asset/material/bambu-tpu-95a")


def test_material_shell_is_content_addressed():
    card = {"material": {"slug": "x-pla", "name": "X"}}
    a = ids.material_shell_id("x-pla", card)
    assert re.fullmatch(r"https://id\.madfam\.io/aas/material/x-pla/[0-9a-f]{16}", a)
    assert ids.material_shell_id("x-pla", {"material": {"slug": "x-pla", "name": "Y"}}) != a
    # Canonical JSON: key order and 12.0 vs 12 do not change the identity.
    assert ids.content16({"b": 12.0, "a": 1}) == ids.content16({"a": 1, "b": 12})


@pytest.mark.parametrize("bad", ["", "Has Space", "UPPER", "-lead", None])
def test_bad_slugs_are_refused(bad):
    with pytest.raises(ValueError):
        ids.asset_id("solid", bad)


def test_unknown_kind_and_bad_digest_are_refused():
    with pytest.raises(ValueError):
        ids.asset_id("liquid", "x")
    with pytest.raises(ValueError):
        ids.shell_id("solid", "x", "abc")
    with pytest.raises(ValueError):
        ids.submodel_id("solid", "x", TREE, "1bad")


@pytest.mark.parametrize("semver,expected", [
    ("1.0.0", {"version": "1", "revision": "0"}),
    ("2.13.4", {"version": "2", "revision": "13"}),
    ("0.1.0", {"version": "0", "revision": "1"}),
    ("3.1", {"version": "3", "revision": "1"}),
    ("12345.0.0", None),   # more than 4 characters: no administration rather than a lie
    ("v1.0.0", None),
    ("01.2.3", None),
    (None, None),
])
def test_administration_from_semver(semver, expected):
    assert ids.administration(semver) == expected


@pytest.mark.parametrize("raw,expected", [
    ("plate_t", "plate_t"),
    ("h", "h_"),              # single characters are invalid idShorts
    ("3d_offset", "x3d_offset"),
    ("_private", "x_private"),
    ("a-", "a_"),
    ("with space", "with_space"),
    ("", "Element"),
    (None, "Element"),
])
def test_id_short_mapping(raw, expected):
    assert ids.id_short(raw) == expected
    assert IDSHORT.match(expected)


def test_id_short_cuts_to_128_and_allocator_deduplicates():
    assert len(ids.id_short("a" * 300)) == 128
    alloc = ids.IdShortAllocator()
    assert [alloc.take(x) for x in ("a b", "a_b", "a-b", "a b")] == ["a_b", "a_b_2", "a-b", "a_b_3"]
    assert all(ids.is_id_short(alloc.take("z" * 200)) for _ in range(3))


def test_encode_id_is_base64url_without_padding():
    shell = ids.shell_id("solid", "tslot-corner", TREE)
    encoded = ids.encode_id(shell)
    assert "=" not in encoded and "/" not in encoded and "+" not in encoded
    assert base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode() == shell
