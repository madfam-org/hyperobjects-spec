"""sheet_behaviour v1: the validator, the mapping goldens on real cards, material_ref
resolution and the CLI.

The cards under tests/fixtures/sheet-behaviour/cards are byte-identical copies of the
platforms' own (NOTICE.md there). A rule that cannot map one of them, or maps it to an
invalid document, is wrong; the goldens pin what every rule writes today.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import math
from pathlib import Path

import pytest

from hyperobjects_schemas import list_schemas
from hyperobjects_sheet import (
    MappingError,
    StackError,
    build_laminate,
    laminate_behaviour,
    map_fc_fabric,
    map_pliego_stock,
    resolve_material_ref,
    resolver_for,
    thin_print,
    validate,
)
from hyperobjects_sheet.mapping import ASSUMED_TEST_LOAD_N_M, BEND_CLASS_GF_CM2_CM

REPO = Path(__file__).resolve().parents[1]
FIX = REPO / "tests" / "fixtures" / "sheet-behaviour"
CARDS = FIX / "cards"
MATERIALS = {p: CARDS / p for p in ("pliego", "fashion-cabinet", "yantra4d")}

_spec = importlib.util.spec_from_file_location(
    "refresh_sheet_behaviour_golden", REPO / "scripts" / "refresh_sheet_behaviour_golden.py")
refresh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(refresh)


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _pliego(slug: str) -> dict:
    return _read(CARDS / "pliego" / slug / "stock.json")


def _fc(slug: str) -> dict:
    return _read(CARDS / "fashion-cabinet" / slug / "material.json")


# ------------------------------------------------------------------- goldens


def test_the_schema_is_bundled():
    assert "sheet-behaviour" in list_schemas()


def test_every_real_card_is_covered_and_the_goldens_are_current():
    pairs = refresh.targets()
    assert len(list((CARDS / "pliego").glob("*/stock.json"))) == 14
    assert len(list((CARDS / "fashion-cabinet").glob("*/material.json"))) == 11
    assert len(pairs) == 14 + 11 + 2 + 2
    for path, doc in pairs:
        assert path.is_file(), f"missing golden {path.name}: run the refresh script"
        assert path.read_text(encoding="utf-8") == refresh.dump(doc), (
            f"{path.relative_to(REPO)} drifted: run scripts/refresh_sheet_behaviour_golden.py "
            "and review the diff")


@pytest.mark.parametrize("golden", sorted((FIX / "golden").rglob("*.json")),
                         ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_every_golden_is_a_valid_document(golden):
    check = validate(_read(golden))
    assert check.ok, check.errors


# ------------------------------------------------------------------- Pliego


def test_pliego_mapping_converts_engine_units_exactly():
    card = _pliego("cardstock-250")
    d = card["derived"]
    doc = map_pliego_stock(card)
    t = d["thickness"] * 1e-3
    assert doc["caliper_mm"] == d["thickness"]
    assert math.isclose(doc["areal_density_kg_m2"], d["areal_density"] * 1000)
    assert math.isclose(doc["membrane"]["E1t"], d["E_md"] * t, rel_tol=1e-6)
    assert math.isclose(doc["bending"]["D11"], d["D_md"] * 1e-9, rel_tol=1e-6)
    # the card's ν is √(ν12·ν21); the split keeps the geometric mean and reciprocity
    m = doc["membrane"]
    nu21 = m["nu12"] * m["E2t"] / m["E1t"]
    assert math.isclose(math.sqrt(m["nu12"] * nu21), d["nu"], rel_tol=1e-5)
    assert doc["regime"]["inextensible"] and not doc["regime"]["stretchy"]
    assert doc["crease"]["crease_length_scale_t"] == 200


def test_pliego_provenance_follows_the_card_statuses():
    doc = map_pliego_stock(_pliego("kami"))           # gsm and caliper measured on kami
    prov = doc["provenance"]
    assert prov["caliper_mm"]["status"] == "measured"
    assert prov["areal_density_kg_m2"]["status"] == "measured"
    assert prov["E1t"]["status"] == "estimated"        # E_md is an estimate
    assert prov["G12t"]["status"] == "estimated"
    nominal = map_pliego_stock(_pliego("cardstock-250"))["provenance"]
    assert nominal["areal_density_kg_m2"]["status"] == "measured"
    assert "nominal" in nominal["areal_density_kg_m2"]["basis"]


def test_pliego_measured_bending_wins_and_is_marked_measured():
    card = copy.deepcopy(_pliego("cardstock-250"))
    card["physical"]["bending_stiffness_mNm"] = {"md": 12.0, "cd": 5.0, "method": "ISO 5628",
                                                 "source": "test bench"}
    card["derived"]["D_md"], card["derived"]["D_cd"] = 12.0e6, 5.0e6
    doc = map_pliego_stock(card)
    assert math.isclose(doc["bending"]["D11"], 0.012)
    assert doc["provenance"]["D11"]["status"] == "measured"


def test_pliego_refuses_a_card_without_its_derived_block():
    card = copy.deepcopy(_pliego("copy-80"))
    del card["derived"]
    with pytest.raises(MappingError, match="derived block"):
        map_pliego_stock(card)
    card = copy.deepcopy(_pliego("copy-80"))
    card["derived_basis"] = "pliego.stock.derive v9"
    with pytest.raises(MappingError, match="derived_basis"):
        map_pliego_stock(card)


# ------------------------------------------------------------------- Fashion Cabinet


def test_fc_stretch_becomes_a_secant_membrane_stiffness():
    doc = map_fc_fabric(_fc("jersey-algodon"))          # 15 % warp, 40 % weft
    assert math.isclose(doc["membrane"]["E1t"], ASSUMED_TEST_LOAD_N_M / 0.15, rel_tol=1e-5)
    assert math.isclose(doc["membrane"]["E2t"], ASSUMED_TEST_LOAD_N_M / 0.40, rel_tol=1e-5)
    assert doc["axis_1"] == "wale"
    assert doc["regime"]["stretchy"] and not doc["regime"]["inextensible"]
    for key in ("E1t", "E2t", "G12t", "nu12", "D11", "D22", "D12", "D66"):
        assert doc["provenance"][key]["status"] == "estimated", key
    assert "500 gf/cm" in doc["provenance"]["E1t"]["basis"]
    assert "contact" not in doc


def test_fc_bend_classes_are_ordered_and_a_woven_is_inextensible():
    values = list(BEND_CLASS_GF_CM2_CM.values())
    assert values == sorted(values) and len(set(values)) == 7
    poplin = map_fc_fabric(_fc("popelina-algodon"))
    denim = map_fc_fabric(_fc("mezclilla-denim"))
    assert poplin["regime"]["inextensible"]
    assert denim["bending"]["D11"] > poplin["bending"]["D11"]   # stiff > medium-stiff


def test_fc_bend_classes_cover_the_vendored_fabric_schema():
    """Fashion Cabinet holds its schema enum, its preview and its sidecar equal; this rule
    must map at least every class the keystone's vendored fabric schema admits. (That copy
    still lists five classes; fashion-cabinet main lists the seven mapped here.)"""
    from hyperobjects_schemas import load

    physics = load("fabric-manifest")["properties"]["digital_twin"]["properties"]["physics"]
    vendored = physics["properties"]["bend_stiffness_class"]["enum"]
    assert set(vendored) <= set(BEND_CLASS_GF_CM2_CM)
    ladder = list(BEND_CLASS_GF_CM2_CM)
    assert [c for c in ladder if c in vendored] == vendored   # same order


def test_fc_refuses_an_unknown_bend_class_and_zero_stretch():
    card = copy.deepcopy(_fc("manta-cruda"))
    card["digital_twin"]["physics"]["bend_stiffness_class"] = "floppy"
    with pytest.raises(MappingError, match="bend_stiffness_class"):
        map_fc_fabric(card)
    card = copy.deepcopy(_fc("manta-cruda"))
    card["digital_twin"]["physics"]["stretch_warp_pct"] = 0
    card["physical"]["stretch_pct"]["warp"] = 0
    with pytest.raises(MappingError, match="stretch warp"):
        map_fc_fabric(card)


# ------------------------------------------------------------------- thin prints, stacks


def test_thin_print_angle_ply_is_coupled_and_the_symmetric_one_is_not():
    card = _read(CARDS / "yantra4d" / "bambu-tpu-95a" / "material.json")
    pm45 = thin_print(_read(FIX / "thin-prints" / "tpu95a-4l-pm45.json"), card)
    sym = thin_print(_read(FIX / "thin-prints" / "tpu95a-4l-0-90-sym.json"), card)
    assert pm45["laminate"]["coupled"] and not sym["laminate"]["coupled"]
    assert pm45["caliper_mm"] == sym["caliper_mm"] == 0.8
    assert math.isclose(pm45["areal_density_kg_m2"], 1220 * 0.8e-3)
    assert pm45["regime"]["stretchy"]                   # an EMMO elastomer
    assert all(p["status"] == "estimated" for p in pm45["provenance"].values())
    assert pm45["source"]["rule"] == "y4d-thin-print/1"


def test_thin_print_refuses_what_it_cannot_honestly_compute():
    card = _read(CARDS / "yantra4d" / "bambu-tpu-95a" / "material.json")
    desc = _read(FIX / "thin-prints" / "tpu95a-4l-pm45.json")
    for change, match in (({"pattern": "gyroid"}, "no effective-moduli rule"),
                          ({"layers": 0}, "positive integer"),
                          ({"infill": 1.5}, "fraction"),
                          ({"material_ref": {"platform": "yantra4d",
                                             "material_slug": "polymaker-polylite-pla",
                                             "behaviour": "sheet"}}, "card slug")):
        with pytest.raises(StackError, match=match):
            thin_print({**desc, **change}, card)


def test_laminate_documents_resolve_their_refs_and_curl_under_prestrain():
    doc = laminate_behaviour(_read(FIX / "laminates" / "print-on-stretched-tricot.json"),
                             resolver_for(MATERIALS))
    k = doc["laminate"]["prestrain_response"]["curvature_1_m"]
    assert k[0] > 0 and k[1] > 0 and k[2] == 0
    assert doc["laminate"]["layers"][0]["own_bending"] == "card"
    assert doc["laminate"]["layers"][1]["own_bending"] == "plate"
    book = laminate_behaviour(_read(FIX / "laminates" / "bookcloth-on-cardstock.json"),
                              resolver_for(MATERIALS))
    assert book["laminate"]["coupled"] and book["regime"]["inextensible"]


def test_a_laminate_layer_that_does_not_resolve_says_which_layer():
    spec = {"layers": [{"material_ref": {"platform": "pliego", "material_slug": "no-such",
                                         "behaviour": "sheet"}}]}
    with pytest.raises(StackError, match=r"layers\[0\].*no card"):
        build_laminate(spec, resolver_for(MATERIALS))
    with pytest.raises(StackError, match="exactly one"):
        build_laminate({"layers": [{"angle_deg": 0}]})


# ------------------------------------------------------------------- the validator


def _valid() -> dict:
    return map_pliego_stock(_pliego("cardstock-250"))


@pytest.mark.parametrize("mutate, message", [
    (lambda d: d["membrane"].update(nu12=2.0), "schema"),
    (lambda d: d["membrane"].update(nu12=0.99, E2t=d["membrane"]["E1t"] * 2), "membrane"),
    (lambda d: d["bending"].update(D12=1.0), "bending"),
    (lambda d: d["regime"].update(stretchy=True), "exclude each other"),
    (lambda d: d["regime"].update(compressible=True), "compression"),
    (lambda d: d.update(compression={"Ez": 5e4}), "regime.compressible is false"),
    (lambda d: d["provenance"].pop("D66"), "'D66' has no entry"),
    (lambda d: d["provenance"].update(Ez={"status": "measured", "basis": "x"}),
     "names no number"),
    (lambda d: d["units"].update(membrane="kN/m"), "schema"),
    (lambda d: d["provenance"]["E1t"].update(status="guessed"), "schema"),
])
def test_the_validator_rejects(mutate, message):
    doc = _valid()
    mutate(doc)
    check = validate(doc)
    assert not check.ok
    assert any(message in e for e in check.errors), check.errors


def test_a_compressible_sheet_needs_its_modulus_and_unit():
    doc = _valid()
    doc["regime"]["compressible"] = True
    doc["compression"] = {"Ez": 5e4}
    doc["provenance"]["Ez"] = {"status": "estimated", "basis": "test fixture, not a card"}
    assert any("units.compression" in e for e in validate(doc).errors)
    doc["units"]["compression"] = "Pa"
    assert validate(doc).ok


def test_density_and_plate_mismatches_are_notes_not_failures():
    doc = _valid()
    doc["areal_density_kg_m2"] = 5.0          # 16 667 kg/m³
    check = validate(doc)
    assert check.ok and any("density" in n for n in check.notes)
    fabric = map_fc_fabric(_fc("lana-melton-abrigo"))
    check = validate(fabric)
    assert check.ok and any("plate value" in n for n in check.notes)


# ------------------------------------------------------------------- material_ref


def test_material_refs_resolve_name_level():
    def ref(platform, slug):
        return {"platform": platform, "material_slug": slug, "behaviour": "sheet"}

    ok = resolve_material_ref(ref("fashion-cabinet", "popelina-algodon"), MATERIALS)
    assert ok.ok and ok.status == "maps" and ok.behaviour["source"]["rule"] == "fc-fabric/1"
    assert resolve_material_ref(ref("pliego", "washi-kozo-30"), MATERIALS).status == "maps"
    tpu = resolve_material_ref(ref("yantra4d", "bambu-tpu-95a"), MATERIALS)
    assert tpu.ok and tpu.status == "needs-descriptor" and tpu.behaviour is None
    missing = resolve_material_ref(ref("pliego", "greyboard-2mm"), MATERIALS)
    assert not missing.ok and "no card" in missing.problems[0]
    nodir = resolve_material_ref(ref("pliego", "kami"), {})
    assert not nodir.ok and "no materials directory" in nodir.problems[0]
    bad = resolve_material_ref({"platform": "pliego", "material_slug": "kami"}, MATERIALS)
    assert not bad.ok and "behaviour" in bad.problems[0]


def test_a_card_that_carries_its_block_is_used_as_carried(tmp_path):
    card = _fc("popelina-algodon")
    card["sheet_behaviour"] = map_fc_fabric(card)
    (tmp_path / "popelina-algodon").mkdir()
    (tmp_path / "popelina-algodon" / "material.json").write_text(json.dumps(card))
    res = resolve_material_ref({"platform": "fashion-cabinet",
                                "material_slug": "popelina-algodon", "behaviour": "sheet"},
                               {"fashion-cabinet": tmp_path})
    assert res.status == "carries" and res.ok
    card["sheet_behaviour"]["bending"]["D12"] = 1.0
    (tmp_path / "popelina-algodon" / "material.json").write_text(json.dumps(card))
    res = resolve_material_ref({"platform": "fashion-cabinet",
                                "material_slug": "popelina-algodon", "behaviour": "sheet"},
                               {"fashion-cabinet": tmp_path})
    assert not res.ok and any("not positive definite" in p for p in res.problems)


def test_a_card_named_otherwise_does_not_resolve(tmp_path):
    card = _pliego("kami")
    (tmp_path / "origami-15").mkdir()
    (tmp_path / "origami-15" / "stock.json").write_text(json.dumps(card))
    res = resolve_material_ref({"platform": "pliego", "material_slug": "origami-15",
                                "behaviour": "sheet"}, {"pliego": tmp_path})
    assert not res.ok and "names itself 'kami'" in res.problems[0]


# ------------------------------------------------------------------- CLI


def test_cli_check_resolve_map_and_laminate(capsys, tmp_path):
    from fc_spec.cli import main as fc_main
    from y4d_spec.cli import main as y4d_main

    golden = sorted(str(p) for p in (FIX / "golden" / "pliego").glob("*.json"))
    assert fc_main(["sheet", "check", *golden]) == 0
    out = capsys.readouterr().out
    assert f"fc-spec sheet check: files={len(golden)} failures=0" in out

    mats = [f"--materials={p}={CARDS / p}" for p in MATERIALS]
    refs = json.dumps([
        {"platform": "pliego", "material_slug": "kraft-120", "behaviour": "sheet"},
        {"platform": "yantra4d", "material_slug": "bambu-tpu-95a", "behaviour": "sheet"},
        {"platform": "fashion-cabinet", "material_slug": "nope", "behaviour": "sheet"},
    ])
    assert y4d_main(["sheet", "resolve", refs, *mats]) == 1
    out = capsys.readouterr().out
    assert ("y4d-spec sheet resolve: refs=3 carries=0 maps=1 needs-descriptor=1 "
            "unresolved=1") in out

    target = tmp_path / "tpu.json"
    assert y4d_main(["sheet", "map", "yantra4d", str(FIX / "thin-prints" / "tpu95a-4l-pm45.json"),
                     *mats, "-o", str(target)]) == 0
    assert _read(target) == _read(FIX / "golden" / "thin-prints" / "tpu95a-4l-pm45.json")
    capsys.readouterr()

    assert fc_main(["sheet", "laminate", str(FIX / "laminates" / "print-on-stretched-tricot.json"),
                    *mats]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["laminate"]["coupled"] is True
    assert "fc-spec sheet laminate: layers=2" in captured.err
    assert "curvature_1_m=[" in captured.err


def test_cli_rejects_a_bad_materials_argument(capsys):
    from fc_spec.cli import main as fc_main

    assert fc_main(["sheet", "resolve", "{}", "--materials", "solid=/tmp"]) == 2
    assert "PLATFORM=DIR" in capsys.readouterr().err
