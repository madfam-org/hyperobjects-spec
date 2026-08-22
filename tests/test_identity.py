"""Tests for the cross-commons identity key — RFC 0038 §9's semi-rigid rule.

The worked example is real: Fashion Cabinet's `chainmail-panel` notion links to
Yantra4D's `tpu-chainmail-panel` cartridge (see its project.json hardware_ref), and
the identity holds under TPU: FC's fabric card `tpu-panel-impreso` describes the same
printed panel AS CLOTH, Yantra4D prints it in `bambu-tpu-95a`.
"""

import json
from pathlib import Path

import pytest

import hyperobjects_schemas
from hyperobjects_schemas.identity import check_identity, check_identity_file

FIXTURES = Path(__file__).parent / "fixtures"

CHAINMAIL = {
    "identity_id": "chainmail-panel",
    "solid": {"repo": "yantra4d", "slug": "tpu-chainmail-panel"},
    "soft": {"repo": "fashion-cabinet", "slug": "chainmail-panel"},
    "material_identity": {
        "soft_material": "tpu-panel-impreso",
        "solid_material": "bambu-tpu-95a",
    },
}


def test_the_chainmail_pair_is_valid():
    assert check_identity(CHAINMAIL).ok


def test_result_carries_the_identity_id():
    assert check_identity(CHAINMAIL).identity_id == "chainmail-panel"


def test_result_is_falsey_on_problems():
    result = check_identity({})
    assert not result
    assert result.problems


def test_the_schema_is_bundled_and_loadable():
    schema = hyperobjects_schemas.load("cross-commons-identity")
    assert schema["title"] == "Cross-Commons Identity Key"
    assert "cross-commons-identity" in hyperobjects_schemas.list_schemas()


@pytest.mark.parametrize(
    "field", ["identity_id", "solid", "soft", "material_identity"]
)
def test_every_required_field_is_required(field):
    doc = {k: v for k, v in CHAINMAIL.items() if k != field}
    result = check_identity(doc)
    assert not result.ok
    assert any(field in p for p in result.problems)


def test_material_identity_needs_both_sides():
    doc = json.loads(json.dumps(CHAINMAIL))
    doc["material_identity"].pop("solid_material")
    assert not check_identity(doc).ok


def test_the_material_identity_is_what_makes_the_claim_falsifiable():
    """Same geometry, different material: the pairing is claimed only for the material
    named. A record cannot omit it and still mean anything."""
    doc = json.loads(json.dumps(CHAINMAIL))
    doc.pop("material_identity")
    result = check_identity(doc)
    assert not result.ok
    assert any("material_identity" in p for p in result.problems)


# ── the side/repo rules the schema cannot express ────────────────────────────
def test_sides_may_not_be_swapped():
    doc = json.loads(json.dumps(CHAINMAIL))
    doc["solid"], doc["soft"] = doc["soft"], doc["solid"]
    result = check_identity(doc)
    assert not result.ok
    assert any("solid side" in p or "soft side" in p for p in result.problems)


def test_a_pair_may_not_live_in_one_repo():
    doc = json.loads(json.dumps(CHAINMAIL))
    doc["soft"]["repo"] = "yantra4d"
    result = check_identity(doc)
    assert not result.ok
    assert any("spans the two commons" in p for p in result.problems)


def test_an_unknown_repo_is_rejected():
    doc = json.loads(json.dumps(CHAINMAIL))
    doc["solid"]["repo"] = "some-other-repo"
    assert not check_identity(doc).ok


def test_a_slug_must_be_a_slug():
    doc = json.loads(json.dumps(CHAINMAIL))
    doc["soft"]["slug"] = "Not A Slug"
    assert not check_identity(doc).ok


def test_unknown_top_level_keys_are_rejected():
    """additionalProperties:false — a typo'd key must not pass silently as metadata."""
    doc = json.loads(json.dumps(CHAINMAIL))
    doc["matrial_identity"] = {}
    assert not check_identity(doc).ok


def test_optional_fields_are_accepted():
    doc = json.loads(json.dumps(CHAINMAIL))
    doc["spec_version"] = 1
    doc["label"] = {"en": "Chainmail panel", "es": "Panel de cota de malla"}
    doc["notes"] = "The panel drapes as cloth only in TPU."
    doc["solid"]["kind"] = "cartridge"
    doc["soft"]["kind"] = "notion"
    doc["material_identity"]["equivalence"] = "same_object"
    assert check_identity(doc).ok


def test_existence_of_the_slugs_is_deliberately_not_checked():
    """This package has no repo to look in, and a third party pairing against their
    own fork must still be able to validate the record."""
    doc = json.loads(json.dumps(CHAINMAIL))
    doc["solid"]["slug"] = "definitely-not-a-real-cartridge"
    assert check_identity(doc).ok


# ── file loading ─────────────────────────────────────────────────────────────
def test_check_identity_file_reads_a_single_record(tmp_path):
    p = tmp_path / "pair.json"
    p.write_text(json.dumps(CHAINMAIL))
    assert check_identity_file(p).ok


def test_check_identity_file_reads_a_list_and_indexes_problems(tmp_path):
    bad = json.loads(json.dumps(CHAINMAIL))
    bad.pop("material_identity")
    p = tmp_path / "pairs.json"
    p.write_text(json.dumps([CHAINMAIL, bad]))
    result = check_identity_file(p)
    assert not result.ok
    assert any(p_.startswith("[1] ") for p_ in result.problems)
    assert not any(p_.startswith("[0] ") for p_ in result.problems)


# ── the pair matches the REAL cartridges we carry ────────────────────────────
def test_the_chainmail_pair_matches_the_real_fc_hardware_ref():
    """The soft side really does link to the solid side — read it out of the actual
    fashion-cabinet manifest rather than trusting the example."""
    fc = json.loads((FIXTURES / "fc" / "chainmail-panel.project.json").read_text())
    assert fc["project"]["slug"] == CHAINMAIL["soft"]["slug"]
    hw = fc["notion"]["hardware_ref"]
    assert hw["platform"] == "yantra4d"
    assert hw["linked"] is True
    assert hw["project_slug"] == CHAINMAIL["solid"]["slug"]


# ── both CLIs expose it ──────────────────────────────────────────────────────
@pytest.mark.parametrize("tool", ["fc_spec", "y4d_spec"])
def test_both_clis_check_an_identity_file(tmp_path, capsys, tool):
    """A contributor on either side of the commons validates a pair with the tool they
    already have installed."""
    main = __import__(f"{tool}.cli", fromlist=["main"]).main
    p = tmp_path / "pair.json"
    p.write_text(json.dumps(CHAINMAIL))
    assert main(["identity", str(p)]) == 0
    assert "ok" in capsys.readouterr().out


@pytest.mark.parametrize("tool", ["fc_spec", "y4d_spec"])
def test_both_clis_fail_a_bad_identity_file(tmp_path, capsys, tool):
    main = __import__(f"{tool}.cli", fromlist=["main"]).main
    bad = json.loads(json.dumps(CHAINMAIL))
    bad.pop("material_identity")
    p = tmp_path / "pair.json"
    p.write_text(json.dumps(bad))
    assert main(["identity", str(p)]) == 1
    assert "FAIL" in capsys.readouterr().out


def test_the_shipped_example_file_is_valid():
    """examples/chainmail-panel.identity.json is what the README points a contributor
    at — it must never rot into an invalid record."""
    example = Path(__file__).resolve().parents[1] / "examples" / "chainmail-panel.identity.json"
    assert example.is_file(), "the README references this example; it must ship"
    result = check_identity_file(example)
    assert result.ok, result.problems
    assert result.identity_id == "chainmail-panel"
