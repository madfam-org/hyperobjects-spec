"""Tests for pliego-spec, the sheet commons' conformance runner (the third kernel).

The fixtures under tests/fixtures/sheet/ are faithful minimal sheet cartridges (manifest,
main.py against the documented Pliego kernel API, docs/README.md). The keystone's rule is
that fixtures are REAL cartridges; the sheet commons holds none yet (2026-10-10), so these
stand in until the first real cartridges replace them in the commons' first re-pin. Every
rule is shown passing on them and failing on a minimal mutation, so no rule's only proof
is that healthy cartridges pass.
"""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path

import pytest

import hyperobjects_schemas
import pliego_spec
from hyperobjects_lexicon.lexicon import check_term, load_lexicon
from hyperobjects_schemas.generator_output import canonical_json as goc1_canonical_json
from pliego_spec import cli, rules, structure
from pliego_spec.conformance import check, check_cartridge, check_manifest
from pliego_spec.document import ALLOWED_TREATMENT, check_document, document_digest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures" / "sheet"
DOCUMENTS = Path(__file__).parent / "fixtures" / "sheet-documents"
CARTRIDGES = ("valley-fold", "v-fold-popup", "papel-picado-banner")
VENDORED = Path(pliego_spec.__file__).parent / "schemas"


def _manifest(slug: str = "v-fold-popup") -> dict:
    return json.loads((FIXTURES / slug / "project.json").read_text(encoding="utf-8"))


def _document() -> dict:
    return json.loads((DOCUMENTS / "valley-fold.fold").read_text(encoding="utf-8"))


def _copy(tmp_path: Path, slug: str = "v-fold-popup") -> Path:
    dest = tmp_path / slug
    shutil.copytree(FIXTURES / slug, dest)
    return dest


def _write(cart: Path, doc: dict) -> None:
    (cart / "project.json").write_text(json.dumps(doc), encoding="utf-8")


# ── the vendored contract ────────────────────────────────────────────────────
VENDORED_FILES = ("sheet-document.schema.json", "stock-card.schema.json")


@pytest.mark.parametrize("name", VENDORED_FILES)
def test_vendored_pliego_contracts_match_their_lock(name):
    """Byte identity is the mechanism: a verdict here is a verdict about the schema
    Pliego publishes only while the copy is the copy. Re-vendor, then re-pin."""
    lock = json.loads((VENDORED / "pliego.lock.json").read_text(encoding="utf-8"))
    data = (VENDORED / name).read_bytes()
    assert hashlib.sha256(data).hexdigest() == lock["hashes"][name]
    assert len(data) == lock["bytes"][name]
    blob = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
    assert blob == lock["git_blob_sha1"][name]
    # Pliego is published: the lock names a fetchable commit of the public repo.
    assert lock["published"] is True and len(lock["commit"]) == 40
    assert lock["canonical_repo"] == "https://github.com/madfam-org/pliego"
    assert len(lock["last_changed"][name]) == 40


def test_no_stale_lock_is_left_behind():
    assert sorted(p.name for p in VENDORED.glob("*.json")) == sorted(
        [*VENDORED_FILES, "pliego.lock.json"])


@pytest.mark.parametrize("name", VENDORED_FILES)
def test_the_vendored_schemas_are_valid_2020_12_schemas(name):
    from jsonschema import Draft202012Validator

    Draft202012Validator.check_schema(
        json.loads((VENDORED / name).read_text(encoding="utf-8"))
    )


def test_kernel_0_2_stock_snapshot_keys_are_accepted():
    """The copy this replaced refused every kernel-0.2.0 document: the stock snapshot's
    `appearance`, `G12` and `perf_*` keys were unknown to it."""
    doc = _document()
    stock = next(iter(doc["pliego:stocks"].values()))
    stock["appearance"] = {"front": "#f4efe6", "back": "#f4efe6"}
    stock["derived"].update(G12=1161000000.0, score_yield_deg=12.25, perf_cut_mm=3.0,
                            perf_bridge_mm=1.0)
    doc["pliego:meta"]["digest"] = document_digest(doc)
    assert check("sheet-document", doc).ok, check("sheet-document", doc).problems


@pytest.mark.parametrize("slug", ["cardstock-250", "washi-kozo-30", "corrugated-b-flute"])
def test_real_stock_cards_pass_the_stock_card_contract(slug):
    card = json.loads((ROOT / "tests" / "fixtures" / "sheet-stock" / f"{slug}.stock.json")
                      .read_text(encoding="utf-8"))
    assert check("stock-card", card).ok, check("stock-card", card).problems
    del card["physical"]
    assert not check("stock-card", card).ok


def test_sheet_manifest_has_one_home_and_one_copy():
    assert hyperobjects_schemas.SCHEMAS["sheet-manifest"] == "hyperobjects-spec"
    assert hyperobjects_schemas.schema_path("sheet-manifest").is_file()
    assert not (VENDORED / "sheet-manifest.schema.json").exists()


def test_contract_surface():
    assert pliego_spec.list_contracts() == ["sheet-manifest", "sheet-document", "stock-card"]
    with pytest.raises(ValueError):
        check("garment-manifest", {})


def test_the_licence_constant_is_the_ruled_one():
    """Owner ruling 2026-10-10: the sheet commons' object licence is CERN-OHL-W-2.0."""
    assert rules.SHEET_COMMONS_LICENSE == "CERN-OHL-W-2.0"
    assert pliego_spec.SHEET_COMMONS_LICENSE is rules.SHEET_COMMONS_LICENSE


# ── fixtures pass ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("slug", CARTRIDGES)
def test_fixture_cartridges_conform(slug):
    result = check_cartridge(FIXTURES / slug)
    assert result.ok, result.problems
    assert result.slug == slug
    assert any("documents: NOT built" in n for n in result.notes)


@pytest.mark.parametrize("slug", CARTRIDGES)
def test_fixture_manifests_conform(slug):
    assert check_manifest(_manifest(slug)) == []


def test_fixture_document_conforms_with_read_proof_counts():
    result = check("sheet-document", _document())
    assert result.ok, result.problems
    assert result.counts == {"sheets": 1, "vertices": 4, "edges": 5, "faces": 2, "joins": 0}


# ── schema ───────────────────────────────────────────────────────────────────
def test_schema_requires_all_four_languages():
    doc = _manifest()
    del doc["modes"][0]["label"]["pt"]
    assert any("modes/0/label" in p and "'pt'" in p for p in check_manifest(doc))


def test_schema_forbids_the_legacy_hyperobject_location():
    doc = _manifest()
    doc["project"]["hyperobject"] = {"is_hyperobject": True}
    assert any(p.startswith("schema project:") and "False schema" in p
               for p in check_manifest(doc))


@pytest.mark.parametrize("slug", ["v_fold", "V-fold", "v-fold-", "v--fold", "v"])
def test_slugs_are_strict_kebab(slug):
    doc = _manifest()
    doc["project"]["slug"] = slug
    problems = check_manifest(doc)
    assert any(p.startswith("project.slug:") for p in problems), problems


def test_engine_kernel_and_unknown_keys_are_closed():
    doc = _manifest()
    doc["project"]["engine"] = "fc"
    doc["hyperobject"]["kernel"] = "soft"
    doc["sheet"] = []  # a typo of `sheets`
    problems = check_manifest(doc)
    assert any("project/engine" in p for p in problems)
    assert any("hyperobject/kernel" in p for p in problems)
    assert any("Additional properties" in p and "'sheet'" in p for p in problems)


def test_symmetric_frame_needs_an_x_axis():
    doc = _manifest()
    doc["hyperobject"]["interfaces"][0]["symmetry"] = 2
    doc["hyperobject"]["interfaces"][0]["frame"] = {
        "sheet": "base", "origin": [0, 0, 0], "normal": [0, 1, 0], "fold_state": 90}
    assert any("x_axis" in p for p in check_manifest(doc))
    doc["hyperobject"]["interfaces"][0]["frame"]["x_axis"] = [1, 0, 0]
    assert check_manifest(doc) == []


# ── house rules ──────────────────────────────────────────────────────────────
def test_blank_translation_fails_the_i18n_rule():
    doc = _manifest()
    doc["sheets"][1]["label"]["fr"] = "   "
    assert any("sheets['piece'].label.fr" in p for p in rules.i18n_rules(doc))


@pytest.mark.parametrize(
    "attribution, commons, expect",
    [
        ("MIT", "CERN-OHL-W-2.0", "project.attribution.license"),
        ("CERN-OHL-W-2.0", "CERN-OHL-P-2.0", "hyperobject.commons_license"),
        ("MIT", "GPL-3.0", "disagree"),
    ],
)
def test_licence_fields_equal_the_commons_licence_and_agree(attribution, commons, expect):
    doc = _manifest()
    doc["project"]["attribution"]["license"] = attribution
    doc["hyperobject"]["commons_license"] = commons
    assert any(expect in p for p in rules.license_rules(doc))


def test_references_resolve_and_ids_are_unique():
    doc = _manifest()
    doc["modes"][0]["sheets"].append("cover")
    doc["hyperobject"]["interfaces"][0]["parameters"].append("gutter_depth")
    doc["hyperobject"]["interfaces"][1]["edges"].append({"sheet": "lid", "edge": "tab"})
    doc["presets"][0]["values"]["height"] = 1
    doc["sheets"].append(copy.deepcopy(doc["sheets"][0]))
    problems = rules.reference_rules(doc)
    for needle in ("unknown sheet 'cover'", "unknown parameter 'gutter_depth'",
                   "unknown sheet 'lid'", "unknown parameter 'height'",
                   "id 'base' is declared more than once"):
        assert any(needle in p for p in problems), (needle, problems)


def test_slider_default_outside_range_fails():
    doc = _manifest()
    doc["parameters"][0]["default"] = 999
    assert any("outside" in p for p in rules.reference_rules(doc))


def test_heritage_sources_cannot_be_blank():
    doc = _manifest("papel-picado-banner")
    doc["hyperobject"]["heritage"]["sources"] = ["    "]
    assert rules.heritage_rules(doc)
    del doc["hyperobject"]["heritage"]["sources"]
    assert any("heritage" in p and "sources" in p for p in check_manifest(doc))


@pytest.mark.parametrize(
    "expression, needle",
    [
        ("min(piece_height, 10) < spread_width", "function call"),
        ("spread_width > 'wide'", "string literal"),
        ("spread_height > 0", "unknown identifier"),
        ("x" * 257, "256"),
    ],
)
def test_constraints_that_safeformula_would_swallow(expression, needle):
    doc = _manifest()
    doc["constraints"][0]["expression"] = expression
    assert any(needle in p for p in check_manifest(doc)), check_manifest(doc)


def test_a_text_select_cannot_be_compared():
    doc = _manifest("valley-fold")
    doc["constraints"][0]["expression"] = "stock == 1"
    assert any("not a numeric parameter" in p for p in rules.constraint_rules(doc))
    doc = _manifest("papel-picado-banner")
    doc["constraints"][0]["expression"] = "symmetry > 0"  # numeric select options
    assert rules.constraint_rules(doc) == []


def test_hardware_ref_local_half():
    doc = _manifest()
    doc["hardware_ref"] = {"platform": "yantra4d", "linked": True,
                           "params_map": {"shank_dia": "tab_width / 4", "length": "depth * 2"}}
    problems = check_manifest(doc)
    assert any("linked=true but project_slug is empty" in p for p in problems)
    assert any("reads 'depth'" in p for p in problems)
    assert not any("tab_width" in p for p in problems)


def test_control_default_outside_range():
    doc = _manifest()
    doc["controls"][0]["default"] = 270
    assert any("outside" in p for p in rules.control_rules(doc))


def test_size_key_must_be_a_vocabulary_key():
    """The shared SEM-1 §4 rule applies unchanged: no sheet size keys exist yet, so a
    sheet size_key fails until cited keys are added to interface-sizes."""
    doc = _manifest()
    doc["hyperobject"]["interfaces"][1]["size_key"] = "tab-10mm"
    assert any(p.startswith("fabrication vocabulary:") for p in check_manifest(doc))


# ── G-DEADPARAM (y4d_spec's rule, reused) ────────────────────────────────────
def test_dead_parameter_fails_and_allow_list_needs_a_reason(tmp_path):
    cart = _copy(tmp_path)
    doc = _manifest()
    doc["parameters"].append({
        "id": "flap_curl", "type": "slider", "default": 1, "min": 0, "max": 2,
        "label": {"en": "Curl", "es": "Curvatura", "fr": "Courbure", "pt": "Curvatura"}})
    _write(cart, doc)
    assert any("'flap_curl'" in p and "G-DEADPARAM" in p for p in check_cartridge(cart).problems)

    doc["parameters"][-1]["intentionally_unused"] = {"reason": "reserved for a curled mode"}
    _write(cart, doc)
    assert check_cartridge(cart).ok

    doc["parameters"][-1]["intentionally_unused"] = {"reason": " "}
    _write(cart, doc)
    assert any("non-empty 'reason'" in p for p in check_cartridge(cart).problems)


def test_a_parameter_named_only_in_prose_is_dead(tmp_path):
    """Comments and string literals are stripped before the identifier search (the y4d
    rule, unchanged): naming a parameter is not wiring it. The rule can still MISS a
    dead parameter — a keyword-argument name such as `stock=` counts as an occurrence —
    but it never invents one."""
    cart = _copy(tmp_path, "valley-fold")
    doc = _manifest("valley-fold")
    doc["parameters"].append({
        "id": "margin", "type": "slider", "default": 5, "min": 0, "max": 20,
        "label": {"en": "Margin", "es": "Margen", "fr": "Marge", "pt": "Margem"}})
    _write(cart, doc)
    with (cart / "main.py").open("a", encoding="utf-8") as f:
        f.write('# margin: not wired yet\nNOTE = "margin is reserved"\n')
    assert any("'margin'" in p for p in check_cartridge(cart).problems)


# ── on-disk rules ────────────────────────────────────────────────────────────
def test_a_directory_without_project_json_is_a_failure(tmp_path):
    result = check_cartridge(tmp_path)
    assert not result.ok and "not a cartridge" in result.problems[0]


@pytest.mark.parametrize("missing", ["main.py", "docs/README.md"])
def test_the_triple_is_required(tmp_path, missing):
    cart = _copy(tmp_path)
    (cart / missing).unlink()
    assert any(p.startswith(f"{missing}: missing") for p in check_cartridge(cart).problems)


@pytest.mark.parametrize("name", ["LICENSE", "docs/COPYING.txt"])
def test_no_licence_file_inside_a_cartridge(tmp_path, name):
    cart = _copy(tmp_path)
    (cart / name).write_text("CERN Open Hardware Licence Version 2 - Weakly Reciprocal\n")
    assert any("must not ship its own licence" in p for p in check_cartridge(cart).problems)


def test_directory_must_match_slug(tmp_path):
    cart = tmp_path / "renamed"
    shutil.copytree(FIXTURES / "valley-fold", cart)
    assert any("does not match project.slug" in p for p in check_cartridge(cart).problems)


def test_scripts_import_only_pliego_and_math(tmp_path):
    cart = _copy(tmp_path)
    src = (cart / "main.py").read_text(encoding="utf-8")
    (cart / "main.py").write_text("import os\nfrom ..shared import tabs\n" + src)
    problems = check_cartridge(cart).problems
    assert any("imports 'os'" in p for p in problems)
    assert any("imports '..shared'" in p for p in problems)


def test_mode_script_must_exist_and_stay_inside(tmp_path):
    cart = _copy(tmp_path)
    doc = _manifest()
    doc["modes"][0]["script_file"] = "spread.py"
    _write(cart, doc)
    assert any("'spread.py' does not exist" in p for p in check_cartridge(cart).problems)
    assert structure.mode_script_rules(cart, {"modes": [{"id": "m", "script_file": "../x.py"}]})


def test_vendor_tree_fails(tmp_path):
    cart = _copy(tmp_path)
    (cart / "vendor").mkdir()
    assert any(p.startswith("vendor/") for p in check_cartridge(cart).problems)


# ── sheet documents: the structural §8 subset ────────────────────────────────
def _redigest(doc: dict) -> dict:
    doc["pliego:meta"]["digest"] = document_digest(doc)
    return doc


def test_document_length_and_index_problems():
    doc = _document()
    doc["edges_foldAngle"].pop()
    doc["edges_vertices"][4] = [0, 9]
    problems = check_document(_redigest(doc)).problems
    assert any("§8.1 edges_foldAngle" in p for p in problems)
    assert any("vertex 9 out of range" in p for p in problems)


def test_document_treatment_and_zero_angles():
    doc = _document()
    doc["pliego:edges_treatment"][4] = "cut"
    doc["edges_foldAngle"][0] = 90
    problems = check_document(_redigest(doc)).problems
    assert any("treatment 'cut' does not admit assignment 'V'" in p for p in problems)
    assert any("edge 0: assignment 'B' must have fold angle 0" in p for p in problems)


def test_treatment_table_matches_the_spec():
    """Spec §4, transcribed — a change here is a contract change, made in Pliego first."""
    assert {k: "".join(sorted(v)) for k, v in ALLOWED_TREATMENT.items()} == {
        "none": "BFJU", "crease": "FMV", "score": "FMV", "perforation": "CFMV",
        "cut": "C", "halfcut": "F"}


def test_document_references():
    doc = _document()
    doc["pliego:sheets"][0]["stock"] = "copy-80"
    doc["pliego:sequence"]["steps"][0]["targets"] = [[0, 90]]
    doc["pliego:controls"] = []
    doc["pliego:joins"] = [{"id": "pull", "type": "pin", "a": {"sheet": "lid", "at": [0, 0]},
                            "world": None, "mechanism": "spread"}]
    doc["pliego:mechanisms"] = [{"id": "spread", "type": "slide", "control": "open",
                                 "travel": 10}]
    problems = check_document(_redigest(doc)).problems
    for needle in ("stock 'copy-80' is not in pliego:stocks", "target edge 0 is 'B'",
                   "no control of kind 'sequence'", "unknown sheet 'lid'",
                   "driven by a 'translate' mechanism", "control 'open' is not in"):
        assert any(needle in p for p in problems), (needle, problems)


def test_document_sheet_membership_and_frames():
    doc = _document()
    doc["pliego:vertices_sheet"][3] = 1
    doc["file_frames"] = [{"frame_title": "initial", "vertices_coords": [[0, 0, 0]]}]
    problems = check_document(_redigest(doc)).problems
    assert any(p.startswith("§8.2 face 1") for p in problems)
    assert any("§8.9 file_frames[0]" in p for p in problems)


def test_document_digest_must_match():
    doc = _document()
    doc["vertices_coords"][2] = [150, 151]
    assert any("§8.10" in p for p in check_document(doc).problems)
    # GOC-1 canonical form: an integral float hashes like the integer.
    respelt = _document()
    respelt["vertices_coords"][1] = [150.0, 0.0]
    assert check_document(respelt).ok


def test_document_schema_is_applied():
    doc = _document()
    doc["frame_unit"] = "in"
    assert any(p.startswith("schema frame_unit") for p in check_document(doc).problems)
    assert not check_document([]).ok


# ── the CLI, as a third party runs it ────────────────────────────────────────
def test_cli_cartridge_summary_is_read_proof(capsys):
    code = cli.main(["check", "cartridge", *[str(FIXTURES / s) for s in CARTRIDGES]])
    out = capsys.readouterr().out
    assert code == 0
    assert ("pliego-spec check: cartridges=3 failures=0 notes=3 documents=NOT built "
            "geometry=NOT verified") in out


def test_cli_fails_with_exit_1(capsys, tmp_path):
    assert cli.main(["check", "cartridge", str(tmp_path)]) == 1
    assert "failures=1" in capsys.readouterr().out
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"project": {}}))
    assert cli.main(["check", "sheet-manifest", str(bad)]) == 1


def test_cli_document_summary_names_what_was_not_verified(capsys):
    assert cli.main(["check", "sheet-document", str(DOCUMENTS / "valley-fold.fold")]) == 0
    out = capsys.readouterr().out
    assert "sheets=1 vertices=4 edges=5 faces=2 joins=0 geometry=NOT verified" in out


def test_cli_rules_and_list(capsys):
    assert cli.main(["rules"]) == 0
    out = capsys.readouterr().out
    assert rules.SHEET_COMMONS_LICENSE in out and "NOT verified" in out
    assert cli.main(["list"]) == 0
    assert "sheet-document" in capsys.readouterr().out


def test_cli_mounts_the_shared_dictionary(capsys):
    assert cli.main(["define", "mountain-fold"]) == 0
    assert "mountain" in capsys.readouterr().out.lower()


# ── the widened hard-codes ───────────────────────────────────────────────────
def test_sheet_terms_declare_contract_4():
    lexicon = load_lexicon()
    term = copy.deepcopy(lexicon["valley-fold"])
    assert term["domain"] == "sheet-folding" and term["spec_version"] == 4
    term["spec_version"] = 3
    assert any("contract 4" in p for p in check_term(term))
    term = copy.deepcopy(lexicon["bolt-pattern"])
    term["embodied_by"] = ["pliego/v-fold-popup"]
    assert any("contract 4" in p for p in check_term(term))
    term["spec_version"] = 4
    assert not any("contract 4" in p for p in check_term(term))


def test_generator_output_admits_the_sheet_kind():
    from jsonschema import Draft202012Validator

    schema = hyperobjects_schemas.load("generator-output")
    props = schema["properties"]
    gen = props["generator"]["properties"]
    assert "sheet" in props["kind"]["enum"]
    assert "pliego" in gen["platform"]["enum"] and "pliego" in gen["engine"]["enum"]
    assert "sheet-hyperobjects" in gen["commons"]["properties"]["repo"]["enum"]
    Draft202012Validator.check_schema(schema)


@pytest.mark.parametrize(
    "schema, pointer",
    [
        ("lexicon-term", ("$defs", "cartridgeSlug", "pattern")),
        ("article-frontmatter", ("$defs", "objectSlug", "pattern")),
        ("fabrication-vocabulary", ("$defs", "cardRef", "pattern")),
    ],
)
def test_cross_reference_patterns_admit_pliego(schema, pointer):
    import re

    node = hyperobjects_schemas.load(schema)
    for key in pointer:
        node = node[key]
    assert re.match(node, "pliego/papel-picado-banner")
    assert not re.match(node, "sheet-hyperobjects/papel-picado-banner")


def test_readme_documents_the_third_kernel():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "pliego-spec check cartridge" in readme
    assert f"`{rules.SHEET_COMMONS_LICENSE}`" in readme


# ── project.name and the packaging domains ───────────────────────────────────
def test_project_name_must_be_quadrilingual():
    """The Pliego API refuses a bare-string name, so the manifest schema does too."""
    doc = _manifest()
    doc["project"]["name"] = "V-fold pop-up"
    assert any("project/name" in p for p in check_manifest(doc))


@pytest.mark.parametrize("domain", ["packaging", "stationery"])
def test_packaging_and_stationery_are_domains(domain):
    doc = _manifest()
    doc["hyperobject"]["domain"] = domain
    assert not any("domain" in p for p in check_manifest(doc))
    doc["hyperobject"]["domain"] = "boxes"
    assert any("domain" in p for p in check_manifest(doc))


# ── real kernel documents ────────────────────────────────────────────────────
KERNEL_02 = DOCUMENTS / "kernel-0.2"
KERNEL_03 = DOCUMENTS / "kernel-0.3"


@pytest.mark.parametrize("name", ["valley-fold.default.fold", "reveal-block.default.preview.fold"])
def test_real_kernel_documents_pass(name):
    """What the kernel writes today (NOTICE.md in kernel-0.3/). The copy the first lock
    replaced refused both, on the stock snapshot keys and on `remove`."""
    doc = json.loads((KERNEL_03 / name).read_text(encoding="utf-8"))
    assert doc["pliego:meta"]["kernel"] == "pliego-kernel 0.3.0"
    result = check("sheet-document", doc)
    assert result.ok, result.problems[:5]


def test_the_reveal_block_document_exercises_pieces_and_remove():
    text = (KERNEL_03 / "reveal-block.default.preview.fold").read_text(encoding="utf-8")
    assert '"pliego:pieces"' in text and '"remove"' in text


# ── the canonical digest: spec §5.15 (RFC 8785), not GOC-1 ───────────────────
DIGEST_VECTOR = DOCUMENTS / "digest_vector.json"


def test_the_shared_digest_vector_byte_for_byte():
    """Pliego's shared vector (packages/kernel/tests/fixtures/digest_vector.json, copied
    unmodified): the canonical text byte for byte, then the digest. GOC-1's
    `canonical_json` gives sha256:cf5240c2… for the same document."""
    from pliego_spec.canonical import canonical_bytes

    data = DIGEST_VECTOR.read_bytes()
    assert hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest() == (
        "c6847785edc8e6ced4bfcd3af2972517f23fef93")  # Pliego's blob (NOTICE.md)
    vector = json.loads(data)
    assert canonical_bytes(vector["document"]) == vector["canonical"].encode("utf-8")
    assert document_digest(vector["document"]) == vector["digest"]
    assert vector["digest"].startswith("sha256:1c9d6a6a")
    goc1 = hashlib.sha256(
        goc1_canonical_json(vector["document"])).hexdigest()
    assert goc1.startswith("cf5240c2")


@pytest.mark.parametrize("value, spelled", [
    (0.0, "0"), (-0.0, "0"), (90.0, "90"), (12.5, "12.5"), (0.1, "0.1"),
    (1.5e-05, "0.000015"), (5e-06, "0.000005"), (1e-06, "0.000001"), (1e-07, "1e-7"),
    (-1e-07, "-1e-7"), (6.3e-05, "0.000063"), (1e16, "10000000000000000"),
    (1.2345678901234568e20, "123456789012345680000"), (1e21, "1e+21"),
    (1.5e300, "1.5e+300"), (5e-324, "5e-324"), (2**53, "9007199254740992"),
])
def test_numbers_are_spelled_as_ecmascript_does(value, spelled):
    """Spec §5.15's examples, plus the boundaries of plain notation (1e-7 and 1e21)."""
    from pliego_spec.canonical import canonical_bytes

    assert canonical_bytes(value) == spelled.encode()


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), 2**53 + 1, "\ud800x",
                                 {"\udfff": 1}, {1: 2}])
def test_what_has_no_canonical_form_is_refused(bad):
    from pliego_spec.canonical import canonical_bytes

    with pytest.raises(ValueError):
        canonical_bytes(bad)


def test_keys_sort_by_utf16_code_units_not_code_points():
    """U+1F600 is the surrogate pair D83D DE00 in UTF-16, so it sorts BEFORE U+E000, the
    reverse of code-point order (Python's default sort, and GOC-1's)."""
    from pliego_spec.canonical import canonical_bytes

    obj = {"\ue000": 1, "\U0001f600": 2, "b": 3}
    assert canonical_bytes(obj) == '{"b":3,"\U0001f600":2,"\ue000":1}'.encode()
    assert list(json.loads(goc1_canonical_json(obj))) == [
        "b", "\ue000", "\U0001f600"]


def test_strings_escape_as_json_stringify_does():
    from pliego_spec.canonical import canonical_bytes

    text = "a\"b\\c\b\f\n\r\t\x01\x1f\x7f/\u2028\u2029é"
    assert canonical_bytes(text) == (
        '"a\\"b\\\\c\\b\\f\\n\\r\\t\\u0001\\u001f\x7f/\u2028\u2029é"'.encode())


def test_goc1_canonical_json_is_untouched():
    """The sheet digest is its own function: GOC-1 keeps Python's spelling, which its
    golden vectors, the AAS content ids and the assembly digest hash."""
    assert goc1_canonical_json({"x": 1.5e-05, "y": 20.0}) == b'{"x":1.5e-05,"y":20}'


KERNEL_02_OUTSIDE_OVERLAP = {
    "papercraft-unfold.fold.crystal.fold": "1e-06",
    "reveal-block.default.preview.fold": "8e-05",
    "valley-fold.default.fold": "6.3e-05",
}


@pytest.mark.parametrize("path", sorted(KERNEL_02.glob("*.fold")), ids=lambda p: p.name)
def test_kernel_0_2_digests_are_goc1_and_fail_5_15_only_outside_the_overlap(path):
    """Kernel 0.2 stamped the GOC-1 digest; spec §5.15 (kernel 0.3) hashes RFC 8785. The
    two agree only while every non-integral number lies in 1e-4 <= |x| < 1e16, so three of
    these six kernel-0.2 files (each with a number below 1e-4) now fail rule 10 and
    nothing else, as they do in Pliego's own `verify`. Kept unmodified as the record of
    that contract change; kernel-0.3/ holds the current output."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    nulled = copy.deepcopy(doc)
    nulled["pliego:meta"]["digest"] = None
    goc1 = goc1_canonical_json(nulled)
    assert doc["pliego:meta"]["digest"] == "sha256:" + hashlib.sha256(goc1).hexdigest()
    problems = check("sheet-document", doc).problems
    if path.name in KERNEL_02_OUTSIDE_OVERLAP:
        assert KERNEL_02_OUTSIDE_OVERLAP[path.name].encode() in goc1
        assert len(problems) == 1 and problems[0].startswith("§8.10 "), problems
    else:
        assert problems == []


# ── pliego:meta, as the kernel writes it ─────────────────────────────────────
def test_meta_min_feature_mm_is_accepted_and_meta_stays_closed():
    """`Assembly(min_feature_mm=…)` writes `pliego:meta.min_feature_mm` (spec §5.7); the copy
    the commons pinned before refused it. The vendored meta stays exactly as closed as the
    kernel's own schema: an unknown key is refused, never waved through."""
    doc = _document()
    doc["pliego:meta"]["min_feature_mm"] = 0.8
    doc["pliego:meta"]["digest"] = document_digest(doc)
    assert check("sheet-document", doc).ok, check("sheet-document", doc).problems
    doc["pliego:meta"]["min_feature_mm"] = 0
    assert any("min_feature_mm" in p or "pliego:meta" in p
               for p in check("sheet-document", doc).problems)
    doc["pliego:meta"]["min_feature_mm"] = 0.8
    doc["pliego:meta"]["designer"] = "someone"
    assert not check("sheet-document", doc).ok


def test_meta_keys_are_the_kernel_writers_keys():
    """`pliego.document_build.build_document` writes kernel, min_feature_mm, digest and the
    cartridge runner's cartridge/mode/params; the vendored meta admits exactly those."""
    meta = pliego_spec.document.load_document_schema()["$defs"]["meta"]
    assert sorted(meta["properties"]) == sorted(
        ["cartridge", "mode", "params", "kernel", "digest", "min_feature_mm"])
    assert meta["additionalProperties"] is False


# ── material_ref: role bridges and the sheet-behaviour contract's reference ─────
def _with_material_ref(*refs: dict) -> dict:
    doc = _manifest()
    doc["material_ref"] = list(refs)
    return doc


@pytest.mark.parametrize("ref", [
    {"platform": "fashion-cabinet", "material_slug": "book-cloth", "role": "spine"},
    {"platform": "fashion-cabinet", "material_slug": "felt-wool", "behaviour": "sheet"},
    {"platform": "pliego", "material_slug": "eva-foam-2", "behaviour": "sheet",
     "role": "custom", "linked": True},
    {"platform": "yantra4d", "material_slug": "bambu-tpu-95a", "behaviour": "sheet"},
])
def test_material_ref_accepts_role_bridges_and_sheet_behaviour_refs(ref):
    problems = check_manifest(_with_material_ref(ref))
    assert not any("material_ref" in p for p in problems), problems


@pytest.mark.parametrize("ref", [
    {"platform": "fashion-cabinet", "material_slug": "book-cloth"},  # neither role nor behaviour
    {"platform": "solid-hyperobjects", "material_slug": "pla", "behaviour": "sheet"},
    {"platform": "pliego", "material_slug": "eva-foam-2", "behaviour": "solid"},
    {"platform": "pliego", "material_slug": "eva-foam-2", "role": "core"},
    {"platform": "pliego", "material_slug": "Eva Foam", "behaviour": "sheet"},
    {"platform": "pliego", "material_slug": "eva-foam-2", "behaviour": "sheet", "grade": "x"},
])
def test_material_ref_stays_closed(ref):
    assert any("material_ref" in p for p in check_manifest(_with_material_ref(ref)))


def test_material_ref_note_names_the_unresolved_platforms(tmp_path):
    cart = _copy(tmp_path)
    doc = _with_material_ref(
        {"platform": "yantra4d", "material_slug": "bambu-tpu-95a", "behaviour": "sheet"},
        {"platform": "fashion-cabinet", "material_slug": "book-cloth", "role": "spine"},
    )
    _write(cart, doc)
    result = check_cartridge(cart)
    assert result.ok, result.problems
    assert any("material_ref" in n and "fashion-cabinet, yantra4d" in n and "NOT resolved" in n
               for n in result.notes)


# ── §8.13 / §8.14 structural halves (packaging blocks, print layout) ──────────
def _restamp(doc: dict) -> dict:
    doc["pliego:meta"]["digest"] = document_digest(doc)
    return doc


def _sheet_id(doc: dict) -> str:
    return doc["pliego:sheets"][0]["id"]


def test_packaging_blocks_must_name_a_declared_sheet():
    doc = _document()
    finish = {"id": "logo", "kind": "deboss", "sheet": _sheet_id(doc), "side": "front",
              "region": [[[1, 1], [5, 1], [5, 5]]], "depth_mm": 0.3, "profile": "flat"}
    doc["pliego:finishes"] = [finish]
    assert check("sheet-document", _restamp(doc)).ok, check("sheet-document", doc).problems
    finish["sheet"] = "nowhere"
    problems = check("sheet-document", _restamp(doc)).problems
    assert any(p.startswith("§8.13 pliego:finishes[0]: unknown sheet 'nowhere'") for p in problems)


def test_annotations_must_name_a_declared_sheet_with_printable_text():
    doc = _document()
    note = {"sheet": _sheet_id(doc), "at": [10, 10], "text": "12", "size": 3}
    doc["pliego:annotations"] = [note]
    assert check("sheet-document", _restamp(doc)).ok, check("sheet-document", doc).problems
    note.update(sheet="nowhere", text="1\t2")
    problems = check("sheet-document", _restamp(doc)).problems
    assert any("§8.14 pliego:annotations[0]: unknown sheet" in p for p in problems)
    assert any("§8.14 pliego:annotations[0]: text" in p for p in problems)


def test_print_pages_margin_ids_and_overlap():
    doc = _document()
    doc["pliego:pages"] = {"size": [210, 297], "margin": 10,
                           "pages": [{"id": "p1", "origin": [0, 0]},
                                     {"id": "p2", "origin": [220, 0]}]}
    assert check("sheet-document", _restamp(doc)).ok, check("sheet-document", doc).problems
    doc["pliego:pages"]["margin"] = 105
    doc["pliego:pages"]["pages"][1] = {"id": "p1", "origin": [100, 0]}
    problems = check("sheet-document", _restamp(doc)).problems
    assert any("§8.14 pliego:pages: margin 105" in p for p in problems)
    assert any("page id 'p1' is declared more than once" in p for p in problems)
    assert any("pages 'p1' and 'p1' overlap" in p for p in problems)


def test_containment_rules_are_named_as_not_verified(capsys):
    from pliego_spec.document import UNCHECKED_RULES

    assert {"8.11", "8.12", "8.13 containment", "8.14 containment"} <= set(UNCHECKED_RULES)
    assert cli.main(["rules"]) == 0
    out = capsys.readouterr().out
    assert "§8.13 containment" in out and "§8.14 containment" in out


# ── real kernel documents with the packaging and print-layout blocks ─────────
PACKAGING_DOCUMENTS = {
    "folding-carton.carton.fold": ("pliego:dielines", "pliego:artwork"),
    "embossed-stationery.card.fold": ("pliego:finishes",),
    "papercraft-unfold.fold.crystal.fold": ("pliego:annotations", "pliego:pages"),
}


@pytest.mark.parametrize("name", sorted(PACKAGING_DOCUMENTS))
def test_real_packaging_and_print_layout_documents_pass(name):
    """Kernel 0.3 output (kernel-0.3/NOTICE.md). Each file really carries the blocks it is
    here for, so a pass is a verdict on them and not on their absence."""
    doc = json.loads((KERNEL_03 / name).read_text(encoding="utf-8"))
    for key in PACKAGING_DOCUMENTS[name]:
        assert doc.get(key), f"{name} lost {key}"
    result = check("sheet-document", doc)
    assert result.ok, result.problems[:5]


def test_the_vendored_schema_validates_the_packaging_blocks_rather_than_passing_them():
    """The copy this replaced admitted any `pliego:`-prefixed key unvalidated, so a dieline
    with a made-up family passed. Now the block is held to Pliego's definition."""
    doc = json.loads((KERNEL_03 / "folding-carton.carton.fold").read_text(encoding="utf-8"))
    doc["pliego:dielines"][0]["family"] = "crate"
    problems = check("sheet-document", _restamp(doc)).problems
    assert any("pliego:dielines/0/family" in p for p in problems), problems
    doc = json.loads((KERNEL_03 / "papercraft-unfold.fold.crystal.fold")
                     .read_text(encoding="utf-8"))
    doc["pliego:annotations"][0]["size"] = 80
    assert not check("sheet-document", _restamp(doc)).ok


def test_a_real_min_feature_document_passes():
    doc = json.loads((KERNEL_03 / "origamic-architecture.default.fold")
                     .read_text(encoding="utf-8"))
    assert doc["pliego:meta"]["min_feature_mm"] > 0
    assert check("sheet-document", doc).ok, check("sheet-document", doc).problems[:5]


def test_a_board_card_carries_construction_and_it_is_validated():
    """The copy this replaced refused all 8 board cards on Pliego main: `construction` was
    unknown to it. Now the block is accepted and held to `pliego.board v1`."""
    card = json.loads((ROOT / "tests" / "fixtures" / "sheet-stock" /
                       "corrugated-b-flute.stock.json").read_text(encoding="utf-8"))
    assert card["construction"]["layers"]
    card["construction"]["model"] = "pliego.board v2"
    assert any("construction" in p for p in check("stock-card", card).problems)
