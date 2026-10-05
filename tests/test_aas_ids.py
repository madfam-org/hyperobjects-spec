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
        "https://id.madfam.io/aas/soft/a-line-skirt/0123456789abcdef/p3")
    assert ids.submodel_id("solid", "tslot-corner", TREE, "Nameplate") == (
        "https://id.madfam.io/sm/solid/tslot-corner/0123456789abcdef/p3/Nameplate")


def test_every_shell_and_submodel_id_carries_the_projection_version(monkeypatch):
    # 3: material cards and assemblies project their canonical form (F1, 0.10.0)
    assert ids.PROJECTION_VERSION == 3
    assert ids.shell_id("solid", "x", TREE, version=7).endswith("/0123456789abcdef/p7")
    assert ids.submodel_id("assembly", "x", TREE, "Mates", version=7).endswith(
        "/0123456789abcdef/p7/Mates")
    card = {"material": {"slug": "x-pla"}}
    assert ids.material_shell_id("x-pla", card, version=3).endswith("/p3")
    assert ids.material_submodel_id("x-pla", card, "MaterialData", version=3).endswith(
        "/p3/MaterialData")
    # Read at call time, so a patched module constant is what new ids carry.
    monkeypatch.setattr(ids, "PROJECTION_VERSION", 3)
    assert ids.shell_id("solid", "x", TREE).endswith("/p3")
    assert ids.projection_extension() == {
        "name": "ProjectionVersion", "valueType": "xs:positiveInteger", "value": "3"}


@pytest.mark.parametrize("bad", [0, -1, True, "1", 1.0])
def test_a_projection_version_is_a_positive_integer(bad):
    with pytest.raises(ValueError):
        ids.shell_id("solid", "x", TREE, version=bad)


def test_ids_that_name_no_projection_carry_no_version():
    assert ids.asset_id("solid", "x") == "https://id.madfam.io/asset/solid/x"
    assert ids.standard_part_id("m3") == "https://id.madfam.io/asset/standard/m3"
    assert ids.concept_id("bolt-pattern") == "https://id.madfam.io/concept/bolt-pattern"
    assert ids.template_id("mates", 1, 0) == "https://id.madfam.io/smt/mates/1/0"


def test_versioned_ids_parse_back():
    sid = ids.shell_id("assembly", "fpv-5in", TREE, version=12)
    parts = ids.parse_shell_id(sid)
    assert parts == ("assembly", "fpv-5in", "0123456789abcdef", 12)
    assert parts.submodel_prefix == "https://id.madfam.io/sm/assembly/fpv-5in/0123456789abcdef/p12/"
    assert sid.startswith(parts.revision_prefix)
    assert ids.parse_submodel_id(parts.submodel_prefix + "Mates") == (
        "assembly", "fpv-5in", "0123456789abcdef", 12, "Mates")
    material = ids.material_shell_id("x-pla", {"a": 1})
    assert ids.parse_shell_id(material).kind == "material"


@pytest.mark.parametrize("bad", [
    "https://id.madfam.io/aas/solid/x/0123456789abcdef",          # unversioned (pre-0.6.0)
    "https://id.madfam.io/aas/solid/x/0123456789abcdef/p0",
    "https://id.madfam.io/aas/solid/x/0123456789abcdef/p01",
    "https://id.madfam.io/aas/solid/x/0123456789abcdef/v1",
    "https://id.madfam.io/aas/solid/x/0123456789abcdef/p1/",
    "https://id.madfam.io/aas/instance/0123456789abcdef/p1",
    "https://id.madfam.io/sm/solid/x/0123456789abcdef/p1/Nameplate",
    None,
])
def test_malformed_shell_ids_do_not_parse(bad):
    assert ids.parse_shell_id(bad) is None


def test_the_shell_extension_reads_back():
    assert ids.shell_projection_version({"extensions": [ids.projection_extension(4)]}) == 4
    assert ids.shell_projection_version({}) is None
    assert ids.shell_projection_version(
        {"extensions": [{"name": "ProjectionVersion", "value": "04"}]}) is None


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
    assert re.fullmatch(r"https://id\.madfam\.io/aas/material/x-pla/[0-9a-f]{16}/p3", a)
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
