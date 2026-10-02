"""Tests for the fabrication vocabularies (SEM-1 §4).

Two halves, as for the commons vocabularies: what the shipped documents must contain (the
SEM-1 minimum sets, the cross-maps, the citations), then one test per failure class the
lane claims to catch — a rule never seen to fire is indistinguishable from no rule.
"""

import copy
import json
from pathlib import Path

import pytest

from hyperobjects_lexicon import (
    FABRICATION_VOCABULARIES,
    check_fabrication_vocabularies,
    entry_concept_iri,
    fabrication_status,
    load_fabrication_vocabularies,
    load_vocabularies,
)
from hyperobjects_lexicon.fabrication import vocabulary_keys
from hyperobjects_schemas import list_schemas

ORCA_SOURCE = "https://github.com/OrcaSlicer/OrcaSlicer/blob/"


@pytest.fixture(scope="module")
def docs():
    return load_fabrication_vocabularies()


def _entries(docs, name):
    return {e["key"]: e for e in docs[name]["entries"]}


# ── the shipped documents ───────────────────────────────────────────────────────────


def test_the_bundled_set_passes_the_lane(docs):
    result = check_fabrication_vocabularies(docs)
    assert result.ok, result.problems
    assert result.vocabularies == len(FABRICATION_VOCABULARIES) == 5
    assert result.entries == sum(len(d["entries"]) for d in docs.values())


def test_the_schema_is_registered():
    assert "fabrication-vocabulary" in list_schemas()


@pytest.mark.parametrize(
    "name, minimum",
    [
        ("processes", {"fff", "sla", "sls", "mjf", "cnc_3axis", "cnc_router", "laser_2d"}),
        (
            "material-classes",
            {"pla", "petg", "abs", "asa", "tpu-95a", "tpu-85a", "peba", "pa12", "pa12-cf", "pc",
             "carbon-fiber-plate", "aluminium-6061"},
        ),
        (
            "process-parameters",
            {"wall_loops", "top_shell_layers", "bottom_shell_layers", "sparse_infill_density",
             "layer_height", "nozzle_diameter", "outer_wall_speed", "default_jerk",
             "nozzle_temperature", "bed_temperature", "enable_support"},
        ),
        (
            "fabrication-capabilities",
            {"process", "build_volume_x_mm", "build_volume_y_mm", "build_volume_z_mm",
             "nozzle_diameters_mm", "max_hotend_temp_c", "max_bed_temp_c", "enclosure",
             "heated_chamber", "toolhead_count", "material_slots", "firmware", "connectivity"},
        ),
        (
            "interface-sizes",
            {"nema-17-face", "nema-17-shaft-5mm", "tslot-2020-6mm", "gt2-belt-6mm",
             "gt2-pulley-20t-5mm", "bearing-608", "bearing-625", "motor-mount-16x16-m3",
             "motor-mount-19x19-m3", "motor-mount-12x12-m2", "motor-mount-9x9-m2",
             "stack-30.5x30.5-m3", "stack-20x20-m3", "stack-20x20-m2", "fpv-camera-micro-19mm",
             "fpv-camera-nano-14mm", "gopro-3-prong", "sma-bulkhead", "mgn12-carriage"},
        ),
    ],
)
def test_every_sem1_minimum_key_is_present(docs, name, minimum):
    assert minimum <= vocabulary_keys(name, docs)


def test_processes_map_to_every_cotiza_code_exactly_once(docs):
    codes = {e["key"]: e.get("cotiza_code") for e in docs["processes"]["entries"]}
    assert {"fff": "3d_fff", "sla": "3d_sla", "cnc_3axis": "cnc_3axis",
            "laser_2d": "laser_2d"}.items() <= codes.items()
    mapped = [c for c in codes.values() if c]
    assert sorted(mapped) == sorted({"3d_fff", "3d_sla", "cnc_3axis", "laser_2d"})


def test_every_yantra4d_card_belongs_to_exactly_one_class(docs):
    """The ten solid cards at the capture, each in one class — and the SEM-1 example."""
    owners = {}
    for entry in docs["material-classes"]["entries"]:
        for card in entry.get("cards") or []:
            assert card not in owners, card
            owners[card] = entry["key"]
    assert owners["yantra4d/bambu-tpu-95a"] == "tpu-95a"
    assert sum(1 for c in owners if c.startswith("yantra4d/")) == 10
    assert sum(1 for c in owners if c.startswith("fashion-cabinet/")) == 11


def test_emmo_classes_are_copied_from_the_cards(docs):
    classes = _entries(docs, "material-classes")
    assert classes["tpu-95a"]["emmo_class"] == "http://emmo.info/emmo#Elastomer"
    assert classes["pa-cf"]["emmo_class"] == "http://emmo.info/emmo#Composite"
    assert "emmo_class" not in classes["abs"]  # no card, no claim


def test_every_orcaslicer_key_is_pinned_to_a_source_line(docs):
    for entry in docs["process-parameters"]["entries"]:
        binding = entry["orcaslicer"]
        assert binding["key"] == entry["key"]
        anchor = f"{ORCA_SOURCE}{binding['rev']}/{binding['path']}#L{binding['line']}"
        assert any(s["url"] == anchor for s in entry["sources"]), entry["key"]


def test_bed_temperature_is_marked_as_a_placeholder_not_a_setting(docs):
    params = _entries(docs, "process-parameters")
    assert params["bed_temperature"]["orcaslicer"]["preset"] == "placeholder"
    for plate in ("hot_plate_temp", "textured_plate_temp", "cool_plate_temp", "eng_plate_temp"):
        assert params[plate]["orcaslicer"]["preset"] == "filament"


def test_every_dimension_cites_a_source(docs):
    for entry in docs["interface-sizes"]["entries"]:
        for name, dim in entry["dimensions"].items():
            assert 0 <= dim["source"] < len(entry["sources"]), (entry["key"], name)
            assert entry["sources"][dim["source"]]["url"].startswith("https://")


def test_machine_capabilities_do_not_reuse_garment_capability_keys(docs):
    garment = {e["key"] for e in load_vocabularies()["capabilities"]["entries"]}
    assert not vocabulary_keys("fabrication-capabilities", docs) & garment


def test_nothing_claims_a_review_that_did_not_happen(docs):
    for name, doc in docs.items():
        for entry in doc["entries"]:
            assert entry["review_status"]["state"] == "generated", (name, entry["key"])


def test_status_lines_count_every_vocabulary(docs):
    lines = fabrication_status(docs)
    assert [line.split("[")[1].split("]")[0] for line in lines] == list(FABRICATION_VOCABULARIES)


def test_concept_iris_are_derived_per_vocabulary():
    assert entry_concept_iri("processes", "fff") == "https://id.madfam.io/concept/processes/fff"
    assert entry_concept_iri("interface-sizes", "stack-30.5x30.5-m3").endswith(
        "/interface-sizes/stack-30.5x30.5-m3"
    )
    with pytest.raises(ValueError):
        entry_concept_iri("capabilities", "boned")
    with pytest.raises(ValueError):
        entry_concept_iri("processes", "a/b")


# ── one test per failure class ───────────────────────────────────────────────────────


def _problems(docs, mutate):
    broken = copy.deepcopy(docs)
    mutate(broken)
    return check_fabrication_vocabularies(broken).problems


def _first(broken, name):
    return broken[name]["entries"][0]


def test_lane_catches_a_schema_violation(docs):
    probs = _problems(docs, lambda d: _first(d, "processes").update(colour="red"))
    assert any("colour" in p for p in probs)


def test_lane_catches_a_blank_language(docs):
    probs = _problems(docs, lambda d: _first(d, "processes")["label"].update(pt="  "))
    assert any("label.pt" in p for p in probs)


def test_lane_catches_an_unsigned_review(docs):
    probs = _problems(
        docs, lambda d: _first(d, "processes").update(review_status={"state": "reviewed"})
    )
    assert any("no reviewers" in p for p in probs)


def test_lane_catches_a_duplicate_key(docs):
    probs = _problems(
        docs, lambda d: d["processes"]["entries"].append(copy.deepcopy(_first(d, "processes")))
    )
    assert any("declared twice" in p for p in probs)


def test_lane_catches_an_unknown_process_reference(docs):
    probs = _problems(docs, lambda d: _first(d, "material-classes").update(processes=["fdm"]))
    assert any("'fdm'" in p for p in probs)


def test_lane_catches_a_card_in_two_classes(docs):
    def mutate(d):
        d["material-classes"]["entries"][1]["cards"] = ["yantra4d/polymaker-polylite-pla"]

    assert any("one card, one class" in p for p in _problems(docs, mutate))


def test_lane_catches_an_unknown_card(docs):
    def mutate(d):
        _first(d, "material-classes")["cards"] = ["yantra4d/no-such-card"]

    assert any("does not resolve" in p for p in _problems(docs, mutate))


def test_lane_catches_an_uncited_dimension(docs):
    def mutate(d):
        _first(d, "interface-sizes")["dimensions"]["face_square"]["source"] = 9

    assert any("uncited dimension" in p for p in _problems(docs, mutate))


def test_lane_catches_an_orcaslicer_key_that_is_not_the_entry_key(docs):
    def mutate(d):
        _first(d, "process-parameters")["orcaslicer"]["key"] = "wall_count"

    assert any("orcaslicer.key" in p for p in _problems(docs, mutate))


def test_lane_catches_a_reused_cotiza_code(docs):
    def mutate(d):
        d["processes"]["entries"][1]["cotiza_code"] = "3d_fff"

    assert any("already mapped" in p for p in _problems(docs, mutate))


def test_lane_catches_a_garment_capability_collision(docs):
    def mutate(d):
        _first(d, "fabrication-capabilities")["key"] = "boned"

    assert any("garment capability" in p for p in _problems(docs, mutate))


def test_lane_catches_an_unknown_geometry_type(docs):
    def mutate(d):
        _first(d, "interface-sizes")["geometry_type"] = "zipper_tape"

    assert any("geometry_type" in p for p in _problems(docs, mutate))


def test_lane_catches_an_unknown_term(docs):
    def mutate(d):
        _first(d, "interface-sizes")["term"] = "no-such-term"

    assert any("not in the lexicon" in p for p in _problems(docs, mutate))


def test_lane_catches_an_identifier_that_is_both_exact_and_close(docs):
    def mutate(d):
        _first(d, "processes")["exact_match"] = ["https://example.org/fff"]
        _first(d, "processes")["close_match"] = ["https://example.org/fff"]

    assert any("both exact_match and close_match" in p for p in _problems(docs, mutate))


def test_lane_catches_a_solid_class_with_no_process(docs):
    def mutate(d):
        del _first(d, "material-classes")["processes"]

    assert any("names no processes" in p for p in _problems(docs, mutate))


def test_a_directory_of_documents_loads_by_file_name(tmp_path: Path, docs):
    for name, doc in docs.items():
        (tmp_path / f"{name}.json").write_text(json.dumps(doc), encoding="utf-8")
    assert check_fabrication_vocabularies(load_fabrication_vocabularies(tmp_path)).ok
    (tmp_path / "processes.json").rename(tmp_path / "procs.json")
    probs = check_fabrication_vocabularies(load_fabrication_vocabularies(tmp_path)).problems
    assert any("file named 'procs'" in p for p in probs)


def test_the_vocab_command_runs_the_fabrication_lane(capsys):
    """CI's vocabulary step runs `y4d-spec vocab`; that step must cover this family too."""
    from y4d_spec.cli import main

    assert main(["vocab"]) == 0
    out = capsys.readouterr().out
    assert "y4d-spec vocab fabrication: vocabularies=5" in out
    assert "failures=0" in out.split("vocab fabrication:")[1].splitlines()[0]
