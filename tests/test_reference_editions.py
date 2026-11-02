"""Editions, containers and the box-content fit (gate G-X2).

The fixtures in ``tests/fixtures/reference/`` are fictional and say so in their notes: two
editions, a game card and a keep case. They are not in the bundled catalog, because real
editions arrive with measured data. Each rule has a failure case built by mutating a deep copy
of one of them, and the resolution cases join them with a real bundled device
(``nintendo-3ds``).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from hyperobjects_reference import FACT_ROOTS, leaves, load_catalog, load_object
from hyperobjects_reference.check import check_catalog, check_object, check_references
from hyperobjects_reference.cli import main
from hyperobjects_reference.fit import DOES_NOT_FIT, FITS, UNKNOWN, fit

FIXTURES = Path(__file__).parent / "fixtures" / "reference"


@pytest.fixture
def fixtures():
    return copy.deepcopy(load_catalog(FIXTURES))


@pytest.fixture
def joined(fixtures):
    """The fixtures plus the bundled catalog: the 3DS edition's platform resolves."""
    return {**copy.deepcopy(load_catalog()), **fixtures}


@pytest.fixture
def quest(fixtures):
    return fixtures["fixture-quest-3ds-na"]


@pytest.fixture
def case(fixtures):
    return fixtures["fixture-keep-case"]


@pytest.fixture
def card(fixtures):
    return fixtures["fixture-game-card"]


# ── the fixtures and the schema ──────────────────────────────────────────────────


def test_fixtures_pass_the_lane_with_notes_only(fixtures):
    result = check_catalog(fixtures)
    assert result.ok, "\n".join(result.problems)
    # The N64 edition names four formats no catalog holds yet; the 3DS edition's platform
    # is bundled, not a fixture.
    assert len(result.notes) == 5
    assert all("does not hold yet" in n for n in result.notes)


def test_every_fixture_says_it_is_fictional(fixtures):
    for obj in fixtures.values():
        assert obj["notes"][0].startswith("TEST FIXTURE."), obj["key"]


def test_fixtures_are_not_in_the_bundled_catalog(fixtures):
    assert not set(fixtures) & set(load_catalog())


def test_edition_and_contents_are_fact_roots(quest, case):
    assert {"edition", "contents"} <= set(FACT_ROOTS)
    paths = {p for p, _ in leaves(quest)}
    assert {"edition.title", "edition.media.key", "edition.booklet.pages",
            "edition.inserts[0].kind"} <= paths
    assert "contents[0].key" in {p for p, _ in leaves(case)}


def test_an_edition_value_must_be_sourced(quest):
    quest["sources"][0]["field"] = "edition.booklet"
    problems = check_object(quest)
    assert any(p.startswith("edition.title: 'Fixture Quest' is not covered") for p in problems)
    assert not any(p.startswith("edition.booklet.") for p in problems)


def test_a_contents_key_is_sourced_by_its_count(case):
    i = next(i for i, s in enumerate(case["sources"]) if s["field"] == "contents")
    case["sources"][i]["field"] = "contents[0].count"
    assert check_object(case) == []
    del case["sources"][i]
    assert any(p.startswith("contents[0].key:") for p in check_object(case))


def test_an_edition_needs_its_block(quest):
    del quest["edition"]
    assert any("'edition' is a required property" in p for p in check_object(quest))


def test_only_an_edition_carries_the_block(quest, case):
    case["edition"] = quest["edition"]
    assert check_object(case) != []


def test_an_edition_needs_no_dimensions_but_every_other_kind_does(quest, card):
    assert "dimensions_mm" not in quest and check_object(quest) == []
    del card["dimensions_mm"]
    assert any("'dimensions_mm' is a required property" in p for p in check_object(card))


def test_schema_refuses_an_unknown_binding_and_insert_kind(quest):
    quest["edition"]["booklet"]["binding"] = "spiral"
    quest["edition"]["inserts"][0]["kind"] = "flyer"
    problems = check_object(quest)
    assert any(p.startswith("edition/booklet:") for p in problems)
    assert any("inserts/0/kind" in p for p in problems)


def test_region_takes_a_market_or_a_country(quest):
    for region in ("NA", "global", "DE"):
        quest["edition"]["region"] = region
        assert check_object(quest) == [], region
    quest["edition"]["region"] = "Europe"
    assert any("edition/region" in p for p in check_object(quest))


# ── rule 8: booklet pages ────────────────────────────────────────────────────────


def test_booklet_pages_must_be_positive(quest):
    quest["edition"]["booklet"]["pages"] = 0
    assert any("at least one page" in p for p in check_object(quest))


def test_saddle_stitched_pages_are_a_multiple_of_four(quest):
    quest["edition"]["booklet"]["pages"] = 18
    assert any("multiple of 4" in p for p in check_object(quest))
    quest["edition"]["booklet"]["binding"] = "perfect"     # a perfect binding takes any count
    assert check_object(quest) == []


def test_unresolved_pages_are_not_judged(quest):
    quest["edition"]["booklet"]["pages"] = None
    assert check_object(quest) == []


# ── rule 9: contents ─────────────────────────────────────────────────────────────


def test_a_container_cannot_hold_itself_or_list_twice(case):
    case["contents"].append({"key": "fixture-keep-case", "count": 1})
    case["contents"].append({"key": "fixture-game-card", "count": 2})
    problems = check_object(case)
    assert any("cannot hold itself" in p for p in problems)
    assert any("listed twice" in p for p in problems)


# ── rule 10: references resolve to the right kind ────────────────────────────────


def test_references_resolve_against_a_joined_catalog(joined):
    problems, notes = check_references(joined)
    assert problems == []
    assert not any(n.startswith("fixture-quest-3ds-na:") for n in notes)


def test_platform_must_be_a_device(joined):
    joined["fixture-quest-3ds-na"]["edition"]["platform"] = "fixture-game-card"
    result = check_catalog(joined)
    assert any("edition.platform names 'fixture-game-card', a 'media' — it must be 'device'"
               in p for p in result.problems)


def test_media_must_be_a_media_object(joined):
    joined["fixture-quest-3ds-na"]["edition"]["media"]["key"] = "fixture-keep-case"
    problems, _ = check_references(joined)
    assert any("edition.media.key names 'fixture-keep-case', a 'case' — it must be 'media'"
               in p for p in problems)


def test_package_must_be_a_case_or_a_carton(joined):
    joined["fixture-quest-3ds-na"]["edition"]["package"] = "nintendo-3ds"
    problems, _ = check_references(joined)
    assert any("a 'device' — it must be 'carton' or 'case'" in p for p in problems)


def test_bundled_is_never_an_edition(joined):
    joined["fixture-quest-3ds-na"]["edition"]["bundled"] = ["fixture-rally-64-na"]
    problems, _ = check_references(joined)
    assert any("edition.bundled[0] names 'fixture-rally-64-na', an edition" in p
               for p in problems)


def test_a_missing_key_is_a_note_not_a_failure(joined):
    joined["fixture-quest-3ds-na"]["edition"]["bundled"] = ["nintendo-3ds-circle-pad-pro"]
    result = check_catalog(joined)
    assert result.ok
    assert any("fixture-quest-3ds-na: edition.bundled[0] names 'nintendo-3ds-circle-pad-pro'"
               in n for n in result.notes)


# ── G-X2: the fit ────────────────────────────────────────────────────────────────


def test_fits_from_inside_dimensions(case, card):
    result = fit(case, card, clearance_mm=0.5)
    assert result.verdict == FITS and result
    assert result.content_state == "shell"
    depth = result.axes[2]
    assert (depth.inside_from, depth.required_mm, depth.margin_mm) == (
        "features.inside_depth_mm", 4.8, 6.2)


def test_inside_falls_back_to_closed_less_two_walls(case, card):
    for axis in ("width", "height", "depth"):
        case["features"][f"inside_{axis}_mm"] = None
    result = fit(case, card)
    assert [a.inside_mm for a in result.axes] == [122.0, 134.0, 11.0]
    assert all(a.inside_from.endswith("- 2 x features.wall_mm") for a in result.axes)


def test_does_not_fit(case, card):
    card["dimensions_mm"]["states"]["shell"]["depth"] = 10.2
    result = fit(case, card, clearance_mm=0.5)
    assert result.verdict == DOES_NOT_FIT and not result
    assert result.axes[2].margin_mm == pytest.approx(-0.2)


def test_a_zero_margin_fits_exactly(case, card):
    card["dimensions_mm"]["states"]["shell"]["depth"] = 10.4
    assert fit(case, card, clearance_mm=0.3).axes[2].margin_mm == 0.0
    assert fit(case, card, clearance_mm=0.3).verdict == FITS


def test_a_null_input_is_unknown_never_a_pass(case, card):
    card["dimensions_mm"]["states"]["shell"]["height"] = None
    result = fit(case, card)
    assert result.verdict == UNKNOWN and not result
    assert result.unknown == ["content:dimensions_mm.states.shell.height"]
    case["features"]["inside_width_mm"] = None
    case["features"]["wall_mm"] = None
    assert "container:features.wall_mm" in fit(case, card).unknown


def test_a_short_axis_beats_an_unknown_one(case, card):
    card["dimensions_mm"]["states"]["shell"]["height"] = None
    card["dimensions_mm"]["states"]["shell"]["width"] = 200.0
    assert fit(case, card).verdict == DOES_NOT_FIT


def test_the_envelope_prefers_shell_then_body_then_closed(case, card):
    states = card["dimensions_mm"]["states"]
    states["body"] = {"width": 1.0, "height": 1.0, "depth": 1.0}
    assert fit(case, card).content_state == "shell"
    del states["shell"]
    assert fit(case, card).content_state == "body"
    assert fit(case, {"key": "x", "dimensions_mm": {"states": {}}}).verdict == UNKNOWN


def test_negative_clearance_is_refused(case, card):
    with pytest.raises(ValueError):
        fit(case, card, clearance_mm=-1)


def test_cli_fit_exit_codes(capsys, tmp_path, case, card):
    base = ["fit", "--objects", str(FIXTURES)]
    assert main(base + ["--container", "fixture-keep-case", "--content", "fixture-game-card",
                        "--clearance-mm", "0.5"]) == 0
    assert capsys.readouterr().out.strip().endswith("ho-reference fit: fits")
    assert main(base + ["--container", "fixture-keep-case", "--content", "fixture-game-card",
                        "--clearance-mm", "4"]) == 1
    assert "does not fit" in capsys.readouterr().out
    assert main(base + ["--container", "fixture-keep-case", "--content", "nope"]) == 2
    card["dimensions_mm"]["states"]["shell"]["depth"] = None
    for obj in (case, card):
        (tmp_path / f"{obj['key']}.json").write_text(json.dumps(obj), encoding="utf-8")
    assert main(["fit", "--objects", str(tmp_path), "--container", "fixture-keep-case",
                 "--content", "fixture-game-card", "--json"]) == 3
    assert json.loads(capsys.readouterr().out)["verdict"] == UNKNOWN


def test_cli_check_prints_notes(capsys):
    assert main(["check", "--objects", str(FIXTURES)]) == 0
    out = capsys.readouterr().out
    assert out.count("\nnote ") + out.startswith("note ") == 5
    assert out.strip().endswith("failures=0 notes=5")


def test_load_object_reads_a_fixture_by_path():
    assert load_object(FIXTURES / "fixture-rally-64-na.json")["kind"] == "edition"
