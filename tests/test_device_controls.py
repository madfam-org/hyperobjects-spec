"""The device-control vocabulary (device-controls 1.0, `y4d_spec.device`).

Three passes, tested in the order a commons CI meets them. The manifest pass and the
graph pass need no CAD kernel. The render pass is tested twice: against stand-in renders
(a bounding box is all it reads), so every verdict is exercised on any machine, and
against the real meshes of the fixture cartridge where the kernel is installed.

The fixture is a real cartridge (`tests/fixtures/device/NOTICE.md`). A test that needs a
broken declaration edits a copy; the fixture itself must stay clean.
"""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from y4d_spec import check_cartridge, check_manifest
from y4d_spec import device as dev

CARTRIDGE = Path(__file__).parent / "fixtures" / "device" / "candybar-handheld"
REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads((CARTRIDGE / "project.json").read_text(encoding="utf-8"))


@pytest.fixture
def doc(manifest) -> dict:
    return copy.deepcopy(manifest)


def control(doc: dict, part: str) -> dict:
    return next(c for c in doc["device"]["controls"] if c["part"] == part)


def problems(doc: dict) -> list[str]:
    return dev.manifest_rules(doc)[0]


def one(found: list[str], *needles: str) -> str:
    """The single finding that carries every needle."""
    hits = [f for f in found if all(n in f for n in needles)]
    assert len(hits) == 1, (needles, found)
    return hits[0]


# ── the fixture, and a cartridge with no device block ────────────────────────────────


def test_the_fixture_cartridge_is_clean_without_a_render(manifest):
    assert dev.manifest_rules(manifest) == ([], [])
    assert dev.graph_rules(CARTRIDGE, manifest) == ([], [])
    result = check_cartridge(CARTRIDGE)
    assert result.ok, result.problems
    assert not [n for n in result.notes if dev.RULE_ID in n]


def test_a_manifest_without_a_device_block_is_untouched(doc):
    del doc["device"]
    assert dev.manifest_rules(doc) == ([], [])
    assert dev.graph_rules(CARTRIDGE, doc) == ([], [])
    assert dev.render_checks(doc, []) == []
    assert dev.resolve(doc) == []


def test_the_device_pass_is_part_of_check_manifest(doc):
    control(doc, "button_south")["code"] = "BTN_SOTH"
    result = check_manifest(doc)
    assert not result.ok
    one(result.problems, "button_south", "BTN_SOTH")


def test_the_fixture_declares_every_role_but_a_motor(manifest):
    roles = {c["role"] for c in manifest["device"]["controls"]}
    assert roles == set(dev.ROLES) - {"motor"}


# ── the shape ────────────────────────────────────────────────────────────────────────


def test_a_device_block_that_is_not_an_object_is_refused(doc):
    doc["device"] = ["screen"]
    assert problems(doc) == ["device-controls: device must be an object"]


def test_an_unknown_role_and_a_missing_field_are_schema_failures(doc):
    control(doc, "screen")["role"] = "dial"
    del control(doc, "button_east")["code"]
    del control(doc, "stick_left")["travel"]["tilt"]
    found = problems(doc)
    assert any("schema" in f and "'dial' is not one of" in f for f in found)
    assert any("schema" in f and "'code' is a required property" in f for f in found)
    assert any("schema" in f and "'tilt' is a required property" in f for f in found)


def test_a_field_of_another_role_is_refused(doc):
    control(doc, "light_bar_upper")["code"] = "BTN_SOUTH"
    assert any("schema" in f and "Additional properties" in f for f in problems(doc))


def test_a_motor_and_a_fixed_colour_light_fit_the_schema(doc):
    doc["parts"].append({"id": "rumble", "label": {"en": "Rumble motor", "es": "Motor"}})
    doc["modes"][0]["parts"].append("rumble")
    doc["device"]["controls"].append({"part": "rumble", "role": "motor", "effect": "rumble"})
    control(doc, "light_bar_upper")["colours"] = ["#ff0000", "#00ff00"]
    assert problems(doc) == []


def test_a_later_minor_is_checked_and_noted(doc):
    doc["device"]["vocabulary"] = "device-controls/1.7"
    found, notes = dev.manifest_rules(doc)
    assert found == []
    one(notes, "device-controls/1.7", "device-controls/1.0")
    doc["device"]["vocabulary"] = "device-controls/2.0"
    assert any("schema" in f and "vocabulary" in f for f in problems(doc))


# ── declarations against the cartridge's parts ───────────────────────────────────────


def test_a_control_must_name_a_part_of_the_cartridge(doc):
    control(doc, "power_button")["part"] = "power_key"
    found = problems(doc)
    one(found, "control 'power_key' is not a part of this cartridge")
    # ... and the part it used to describe is now unaccounted for
    one(found, "part 'power_button' is neither a control nor listed in device.structure")


def test_every_part_is_a_control_or_structure(doc):
    doc["device"]["structure"] = ["body"]  # the mount's entry is gone
    one(problems(doc), "part 'rear_mount' is neither a control nor listed")


def test_a_structure_entry_may_say_where_the_part_is_present(manifest, doc):
    assert {"part": "rear_mount", "present_when": "rear_mount_present"} in (
        manifest["device"]["structure"]
    )
    # the mode that lists the mount, at a point where the switch is off
    next(p for p in doc["parameters"] if p["id"] == "rear_mount_present")["default"] = False
    found = problems(doc)
    one(found, "mode 'device' at its defaults", "lists structure 'rear_mount'",
        "'rear_mount_present' is false")
    assert len(found) == 1, found


def test_a_structure_expression_is_checked_like_a_controls(doc):
    doc["device"]["structure"][1]["present_when"] = "mount_present"
    one(problems(doc), "structure 'rear_mount': present_when reads 'mount_present', which "
        "is not a declared parameter")
    doc["device"]["structure"][1]["present_when"] = "rear_mount_present &&"
    one(problems(doc), "structure 'rear_mount': present_when:")
    doc["device"]["structure"][1] = {"part": "rear_mount", "colours": "rgb"}
    assert any("schema" in f and "device/structure/1" in f for f in problems(doc))


def test_a_structure_entry_is_declared_once(doc):
    doc["device"]["structure"].append("body")
    one(problems(doc), "part 'body' is declared twice (structure and structure)")


def test_structure_no_mode_renders_is_refused(doc):
    for mode in doc["modes"]:
        mode["parts"] = [p for p in mode["parts"] if p != "rear_mount"]
    one(problems(doc), "structure 'rear_mount' is rendered by no mode")


def test_a_part_is_declared_once(doc):
    doc["device"]["structure"].append("screen")
    one(problems(doc), "part 'screen' is declared twice")


def test_a_control_no_mode_renders_is_refused(doc):
    for mode in doc["modes"]:
        mode["parts"] = [p for p in mode["parts"] if p != "port_rear"]
    one(problems(doc), "control 'port_rear' is rendered by no mode")


def test_a_label_carries_both_locales(doc):
    control(doc, "screen")["label"] = {"en": "Screen"}
    one(problems(doc), "control 'screen'", "missing its 'es' translation")


# ── input names ──────────────────────────────────────────────────────────────────────


def test_the_input_code_table_says_where_it_came_from():
    table = dev.input_codes()
    assert table["source"]["file"] == "include/uapi/linux/input-event-codes.h"
    assert table["source"]["tag"].startswith("v")
    assert len(table["source"]["sha256"]) == 64
    assert table["event_types"] == {
        "EV_KEY": 1, "EV_REL": 2, "EV_ABS": 3, "EV_SW": 5, "EV_LED": 17,
    }
    keys = table["codes"]["EV_KEY"]
    # the gamepad block is contiguous from BTN_SOUTH, and BTN_A is its alias
    assert [keys[n] for n in ("BTN_SOUTH", "BTN_EAST", "BTN_C", "BTN_NORTH", "BTN_WEST")] == [
        0x130, 0x131, 0x132, 0x133, 0x134,
    ]
    assert keys["BTN_A"] == keys["BTN_SOUTH"]
    assert table["codes"]["EV_ABS"]["ABS_HAT0X"] == 0x10
    assert table["codes"]["EV_SW"]["SW_LID"] == 0
    for names in table["codes"].values():
        assert not [n for n in names if n.endswith(("_MAX", "_CNT", "_RESERVED"))]
    # what the table holds, next to the table (docs/DEVICE_CONTROLS.md says the same)
    assert table["source"]["spdx_license_identifier"] == "GPL-2.0-only WITH Linux-syscall-note"
    assert "only names and numbers" in table["contents"]
    assert "no text of the header is copied" in table["contents"]
    assert table["source"]["tag"] in table["contents"]


def test_a_reserved_placeholder_is_not_an_input_name(doc):
    control(doc, "button_south")["code"] = "KEY_RESERVED"
    one(problems(doc), "code 'KEY_RESERVED' is not an input event name")


def test_input_codes_reads_the_package_data(tmp_path, monkeypatch):
    """The table is read through importlib.resources from the y4d_spec.device package,
    never from a path in a source tree; the wheel check (scripts/qa/check_graph_wheel.py)
    loads it from an unpacked wheel. Here the package's resources are pointed at a stand-in
    directory, and what input_codes() returns must be what that directory holds."""
    from importlib import resources

    stand_in = {"source": {"tag": "v0.0-test"}, "event_types": {}, "codes": {}}
    (tmp_path / "input-codes.json").write_text(json.dumps(stand_in), encoding="utf-8")
    asked = []

    def files(package):
        asked.append(package)
        return tmp_path

    dev.input_codes.cache_clear()
    monkeypatch.setattr(resources, "files", files)
    try:
        assert dev.input_codes() == stand_in
    finally:
        monkeypatch.undo()
        dev.input_codes.cache_clear()
    assert asked == ["y4d_spec.device"]
    assert dev.input_codes()["source"]["tag"] == "v6.12"


def test_the_table_is_shipped_in_the_wheel_manifest():
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert '"y4d_spec.device" = ["*.json"]' in text


def test_a_name_the_table_lacks_is_refused(doc):
    control(doc, "button_south")["code"] = "BTN_SOTH"
    one(problems(doc), "code 'BTN_SOTH' is not an input event name", "v6.12")


def test_a_name_must_suit_the_field_it_is_in(doc):
    control(doc, "stick_left")["click"] = "KEY_ENTER"  # any key name is a key
    assert problems(doc) == []
    control(doc, "trigger_left")["axis"] = "ABS_NOPE"
    one(problems(doc), "axis 'ABS_NOPE' is not an input event name")
    # a switch name in a button: the schema refuses the spelling, and the table says why
    control(doc, "button_south")["code"] = "SW_LID"
    one(problems(doc), "code 'SW_LID' is an EV_SW name, and a button's code is EV_KEY")


def test_a_stick_reports_two_different_axes(doc):
    control(doc, "stick_left")["axes"] = {"x": "ABS_X", "y": "ABS_X"}
    one(problems(doc), "axes.x and axes.y are both 'ABS_X'")


def test_a_switch_takes_a_switch_name_or_a_key_name(doc):
    control(doc, "slide_switch")["code"] = "KEY_MUTE"
    assert problems(doc) == []
    control(doc, "slide_switch")["code"] = "SW_NOPE"
    one(problems(doc), "code 'SW_NOPE' is not an input event name")


def test_a_button_may_send_one_direction_of_a_hat_axis(doc):
    control(doc, "dpad_up")["code"] = {"axis": "ABS_HAT0Y", "value": -1}
    control(doc, "dpad_down")["code"] = {"axis": "ABS_HAT0Y", "value": 1}
    assert dev.manifest_rules(doc) == ([], [])  # two directions are two signals
    control(doc, "dpad_down")["code"]["value"] = -1
    found, notes = dev.manifest_rules(doc)
    assert found == []
    assert len([n for n in notes if "both send ABS_HAT0Y=-1" in n]) >= 1
    control(doc, "dpad_up")["code"] = {"axis": "ABS_HAT9Y", "value": -1}
    one(problems(doc), "code.axis 'ABS_HAT9Y' is not an input event name")


def test_two_controls_sending_one_code_is_a_note_per_point(doc):
    control(doc, "button_east")["code"] = "BTN_SOUTH"
    found, notes = dev.manifest_rules(doc)
    assert found == []
    hits = [n for n in notes if "'button_south' and 'button_east' both send BTN_SOUTH" in n]
    # both modes list the two buttons: two modes at their defaults, and a preset in each
    assert len(hits) == 4


# ── expressions, in the graph core's dialect ─────────────────────────────────────────


def test_an_expression_must_parse(doc):
    control(doc, "stick_left")["present_when"] = "stick_count >= "
    one(problems(doc), "control 'stick_left'", "present_when")


def test_an_expression_reads_declared_numbers_and_booleans_only(doc):
    control(doc, "stick_left")["present_when"] = "stick_total >= 1"
    one(problems(doc), "present_when reads 'stick_total', which is not a declared parameter")
    doc["parameters"].append({
        "id": "finish", "type": "select", "default": "matte",
        "options": [{"value": "matte", "label": {"en": "Matte", "es": "Mate"}}],
        "label": {"en": "Finish", "es": "Acabado"},
    })
    control(doc, "stick_left")["present_when"] = "finish == 1"
    one(problems(doc), "reads 'finish', which is not a number or a boolean")


def test_a_listed_parameter_must_exist(doc):
    control(doc, "screen")["parameters"].append("screen_tint")
    one(problems(doc), "parameters names 'screen_tint'")


# ── the points a run renders ─────────────────────────────────────────────────────────


def test_a_mode_may_not_list_a_control_its_point_lacks(doc):
    # the compact preset switches thirteen controls and the rear mount off; in the full
    # mode they are listed
    doc["presets"][1]["mode"] = "device"
    found = problems(doc)
    absent = [f for f in found if "the declaration says it is absent there" in f]
    assert len(absent) == 14, absent
    one(absent, "mode 'device', preset 'compact_no_sticks'", "control 'stick_left'",
        "'stick_count >= 1' is false")
    one(absent, "mode 'device', preset 'compact_no_sticks'", "structure 'rear_mount'",
        "'rear_mount_present' is false")
    assert len(found) == len(absent)


def test_a_default_that_switches_a_listed_control_off_is_refused(doc):
    next(p for p in doc["parameters"] if p["id"] == "stick_count")["default"] = 1
    found = problems(doc)
    one(found, "mode 'device' at its defaults", "control 'stick_right'")
    one(found, "mode 'device' at its defaults", "control 'light_ring_right'")


def test_a_number_is_checked_at_each_point(doc):
    control(doc, "power_button")["travel"]["depth"] = 0
    found = problems(doc)
    assert len([f for f in found if "control 'power_button'" in f
                and "travel.depth is 0; it must be above 0 mm" in f]) == 4
    control(doc, "power_button")["travel"]["depth"] = 0.4
    control(doc, "stick_left")["travel"]["tilt"] = {"expr": "stick_tilt * 6"}
    one(problems(doc), "control 'stick_left'", "mode 'device' at its defaults",
        "travel.tilt is 108; it must be between 0 and 90")


def test_pixels_are_whole_and_division_by_zero_is_reported(doc):
    control(doc, "screen")["pixels"][0] = {"expr": "screen_pixels_w / 3"}
    assert any("pixels[0] is 213.333" in f and "whole number" in f for f in problems(doc))
    control(doc, "screen")["pixels"][0] = {"expr": "screen_pixels_w / (stick_count - 2)"}
    assert any("pixels[0]" in f and "Division by zero" in f for f in problems(doc))


def test_a_screen_surface_needs_two_different_axes(doc):
    control(doc, "screen")["surface"] = {"normal": "+z", "up": "-z"}
    one(problems(doc), "surface.normal +z and surface.up -z lie on one axis")


def test_resolve_gives_the_device_at_a_parameter_point(manifest):
    at_defaults = {c["part"]: c for c in dev.resolve(manifest)}
    assert all(c["present"] for c in at_defaults.values())
    assert at_defaults["screen"]["pixels"] == [640, 480]
    assert at_defaults["dpad_up"]["travel"] == {"axis": "-z", "depth": 0.6}
    assert at_defaults["stick_left"]["travel"]["tilt"] == 18.0

    compact = {c["part"]: c for c in dev.resolve(manifest, manifest["presets"][1]["values"])}
    assert compact["screen"]["pixels"] == [320, 240]
    assert compact["dpad_up"]["travel"]["depth"] == 0.5
    assert not compact["stick_left"]["present"] and not compact["light_ring_left"]["present"]
    assert compact["menu_left"]["present"] and not compact["menu_center"]["present"]
    # the declaration is returned, not edited
    assert control(manifest, "screen")["pixels"][0] == {"expr": "screen_pixels_w"}


# ── the graph (RFC 0067) ─────────────────────────────────────────────────────────────


@pytest.fixture
def scratch(tmp_path) -> Path:
    target = tmp_path / "candybar-handheld"
    shutil.copytree(CARTRIDGE, target)
    return target


def rewrite(path: Path, edit) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    edit(data)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def test_a_mode_that_shows_controls_names_a_graph(doc):
    del doc["modes"][1]["graph_file"]
    found, notes = dev.graph_rules(CARTRIDGE, doc)
    assert notes == []
    one(found, "mode 'device_plain' shows controls", "names no graph")


def test_a_mode_of_structure_alone_needs_no_graph(doc):
    doc["modes"].append({
        "id": "shell", "label": {"en": "Shell", "es": "Carcasa"}, "scad_file": "main.py",
        "cq_file": "main.py", "parts": ["body", "rear_mount"], "estimate": {"base_time": 5},
    })
    assert dev.graph_rules(CARTRIDGE, doc) == ([], [])


def test_a_control_is_an_output_of_its_modes_graph(scratch):
    def drop(graph):
        del graph["outputs"]["stick_left"]

    rewrite(scratch / "candybar.graph.json", drop)
    doc = json.loads((scratch / "project.json").read_text(encoding="utf-8"))
    found, _ = dev.graph_rules(scratch, doc)
    one(found, "graph candybar.graph.json", "mode 'device' shows control 'stick_left'",
        "not one of the graph's outputs")
    assert len(found) == 1  # device_plain does not list the stick


def test_a_12_graph_declares_what_the_declaration_reads(scratch):
    def drop(graph):
        graph["declarations"]["parameters"] = [
            p for p in graph["declarations"]["parameters"] if p["id"] != "stick_tilt"
        ]

    rewrite(scratch / "candybar.graph.json", drop)
    doc = json.loads((scratch / "project.json").read_text(encoding="utf-8"))
    found, _ = dev.graph_rules(scratch, doc)
    assert sorted(f.split("control ")[1].split(" ")[0] for f in found) == sorted(
        ["'stick_left'", "'stick_right'", "'light_ring_left'", "'light_ring_right'"]
    )
    assert all("'stick_tilt', which the graph does not declare" in f for f in found)


def test_an_unreadable_graph_is_left_to_the_lanes_that_report_it(scratch):
    (scratch / "candybar.graph.json").write_text("[]", encoding="utf-8")
    doc = json.loads((scratch / "project.json").read_text(encoding="utf-8"))
    assert dev.graph_rules(scratch, doc) == ([], [])
    (scratch / "candybar.graph.json").unlink()
    assert dev.graph_rules(scratch, doc) == ([], [])


def test_the_fixture_graph_pins_the_fixture_script():
    """The copy is whole: a refreshed script without its graph would be source-drift."""
    graph = json.loads((CARTRIDGE / "candybar.graph.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256((CARTRIDGE / "main.py").read_bytes()).hexdigest()
    assert graph["provenance"]["sources"][0]["sha256"] == digest
    assert graph["version"].startswith("1.2")


# ── the render pass, against stand-in renders ────────────────────────────────────────


def render(part, lo, hi, *, mode="device", preset=None, ok=True, skipped=None, bodies=1):
    lo, hi = tuple(map(float, lo)), tuple(map(float, hi))
    return SimpleNamespace(
        mode=mode, part=part, preset=preset, engine="cadquery", ok=ok, skipped=skipped,
        bodies=bodies, bounds=(lo, hi) if ok else None,
        extents=tuple(h - low for low, h in zip(lo, hi, strict=True)) if ok else None,
    )


BODY = render("body", (-44, -82, 0), (44, 82, 18))


def verdicts(doc, *renders):
    return {c.part: c for c in dev.render_checks(doc, [BODY, *renders])}


def test_a_control_seated_in_the_body_passes(manifest):
    south = render("button_south", (20, -25, 17), (28, -17, 19.4))
    check = verdicts(manifest, south)["button_south"]
    assert check.status == "pass" and check.notes == () and check.host == "body"
    assert "on 'body'" in check.detail and "presses in along -z" in check.detail
    assert check.summary.startswith(
        "device-controls: button (device, button_south, defaults, cadquery): ok"
    )


def test_structure_parts_are_not_judged(manifest):
    assert set(verdicts(manifest)) == set()


def test_a_control_away_from_the_structure_fails(manifest):
    adrift = render("button_south", (20, -25, 30), (28, -17, 32.4))
    check = verdicts(manifest, adrift)["button_south"]
    assert check.status == "fail"
    assert "sits 12.00 mm away from the nearest structure part, 'body'" in check.detail


def test_a_press_that_moves_the_part_out_fails(doc):
    control(doc, "power_button")["travel"]["axis"] = "+x"  # it sits on the +x side
    power = render("power_button", (42.5, 35.5, 7.5), (44.8, 44.5, 10.5))
    check = verdicts(doc, power)["power_button"]
    assert check.status == "fail"
    assert "travel.axis +x points away from structure part 'body'" in check.detail
    assert "(the structure part lies -x of the control)" in check.detail


def test_a_control_buried_in_its_host_fails(manifest):
    """A light has no travel to judge, so only its seat can say it is not on the surface:
    every side of this box is 2 mm or more inside the body's."""
    buried = render("light_bar_upper", (-20, 60.5, 2), (20, 63.5, 3))
    check = verdicts(manifest, buried)["light_bar_upper"]
    assert check.status == "fail"
    assert "lies 2.00 mm inside structure part 'body' on every side" in check.detail
    # a port mouth set back 0.3 mm into its edge is on the surface
    mouth = render("port_bottom", (-4.5, -81.7, 7.4), (4.5, -80.7, 10.6))
    assert verdicts(manifest, mouth)["port_bottom"].status == "pass"


def test_a_press_into_a_face_the_control_is_not_on_fails(doc):
    """The power button sits on the +x side; declared to press -z, it would be pressed
    into the front face it does not reach. Its centre is above the body's, so a test of
    centres alone passes it."""
    control(doc, "power_button")["travel"]["axis"] = "-z"
    power = render("power_button", (42.5, 35.5, 9), (44.8, 44.5, 13))
    check = verdicts(doc, power)["power_button"]
    assert check.status == "fail"
    assert "travel.axis -z: the part's +z side is 5.00 mm short of that face of structure " \
        "part 'body'" in check.detail


def clamshell(doc) -> tuple[dict, object, object]:
    """The fixture with a second structure part, a lid opened upright behind the top
    edge: the box of the two is tall, and its centre is far above the face buttons."""
    doc["parts"].append({"id": "lid", "label": {"en": "Lid", "es": "Tapa"}})
    doc["modes"][0]["parts"].append("lid")
    doc["device"]["structure"].append("lid")
    lid = render("lid", (-44, 82, 0), (44, 100, 164))
    return doc, BODY, lid


def test_each_control_is_judged_against_the_part_it_is_on(doc):
    doc, body, lid = clamshell(doc)
    south = render("button_south", (20, -25, 17), (28, -17, 19.4))
    check = {c.part: c for c in dev.render_checks(doc, [body, lid, south])}["button_south"]
    assert check.status == "pass" and check.host == "body", check.detail
    # a screen on the lid's inner face, looking at the visitor (-y) from the lid
    control(doc, "screen")["surface"] = {"normal": "-y", "up": "+z"}
    screen = render("screen", (-35, 81.8, 30), (35, 82.8, 130))
    check = {c.part: c for c in dev.render_checks(doc, [body, lid, screen])}["screen"]
    assert check.status == "pass" and check.host == "lid", check.detail
    assert "looks out along -y" in check.detail


def test_a_screen_looks_away_from_its_host(doc):
    screen = render("screen", (-35.56, 17.33, 17.2), (35.56, 70.67, 18.2))
    control(doc, "screen")["surface"] = {"normal": "-z", "up": "+y"}
    check = verdicts(doc, screen)["screen"]
    assert check.status == "fail"
    assert "surface.normal -z looks into structure part 'body'" in check.detail
    # thin along its normal, looking out, but 5 mm below the face it is said to light
    # (it pokes out of the top edge, so it is not buried)
    control(doc, "screen")["surface"] = {"normal": "+z", "up": "+y"}
    sunk = render("screen", (-35.56, 40, 12), (35.56, 90, 13))
    check = verdicts(doc, sunk)["screen"]
    assert check.status == "fail"
    assert "surface.normal +z: the part's +z side is 5.00 mm short" in check.detail


def test_no_host_rendered_leaves_a_control_unverified(manifest, doc):
    screen = render("screen", (-35.56, 17.33, 17.2), (35.56, 70.67, 18.2))
    check = dev.render_checks(manifest, [screen])[0]
    assert check.status == "unverified" and check.host is None
    assert "no structure part was rendered at this point" in check.detail
    # a structure part the declaration calls absent at the point is nobody's host
    doc["device"]["structure"][0] = {"part": "body", "present_when": "stick_count >= 3"}
    check = dev.render_checks(doc, [BODY, screen])[0]
    assert check.status == "unverified", check.detail
    # what the part's own extents show is still judged
    control(doc, "screen")["surface"] = {"normal": "+x", "up": "+y"}
    assert dev.render_checks(doc, [BODY, screen])[0].status == "fail"


def test_a_switch_may_slide_along_its_edge(manifest):
    knob = render("slide_switch", (42.8, 26.5, 7.8), (45, 30.5, 10.2))
    assert verdicts(manifest, knob)["slide_switch"].status == "pass"


def test_a_screen_face_must_be_the_parts_large_face(doc):
    screen = render("screen", (-35.56, 17.33, 17.2), (35.56, 70.67, 18.2))
    check = verdicts(doc, screen)["screen"]
    assert check.status == "pass" and "face 71.12 × 53.34 mm looking +z" in check.detail
    assert check.notes == ()
    control(doc, "screen")["surface"] = {"normal": "+x", "up": "+y"}
    check = verdicts(doc, screen)["screen"]
    assert check.status == "fail" and "is not the part's thin direction" in check.detail


def test_pixels_that_are_not_square_are_a_note(doc):
    control(doc, "screen")["pixels"] = [640, 640]
    screen = render("screen", (-35.56, 17.33, 17.2), (35.56, 70.67, 18.2))
    check = verdicts(doc, screen)["screen"]
    assert check.status == "pass"
    assert any("are not square" in n for n in check.notes)


def test_a_press_deeper_than_the_part_and_a_split_part_are_notes(doc):
    control(doc, "button_south")["travel"]["depth"] = 5
    south = render("button_south", (20, -25, 17), (28, -17, 19.4), bodies=2)
    check = verdicts(doc, south)["button_south"]
    assert check.status == "pass"
    assert any("travel.depth 5 mm is more than the part's 2.400 mm along z" in n
               for n in check.notes)
    assert any("renders as 2 bodies" in n for n in check.notes)


def test_a_failed_or_skipped_render_leaves_its_control_unverified(manifest):
    failed = render("button_south", (0, 0, 0), (1, 1, 1), ok=False)
    check = verdicts(manifest, failed)["button_south"]
    assert check.status == "unverified" and check.detail == "its render failed"
    assert ": unverified — " in check.summary


def test_an_absent_control_is_not_judged_at_that_point(manifest):
    stick = render("stick_left", (-28.5, -52.5, 16.8), (-15.5, -39.5, 23),
                   mode="device", preset="compact_no_sticks")
    body = render("body", (-37, -58, 0), (37, 58, 15), preset="compact_no_sticks")
    assert dev.render_checks(manifest, [body, stick]) == []


def test_a_preset_point_uses_the_presets_numbers(manifest):
    # 320 × 240 on the compact preset's 2.8 in face is square; 640 × 480 would be too,
    # so make the face the wrong shape and read which pixel count the note names
    body = render("body", (-37, -58, 0), (37, 58, 15), mode="device_plain",
                  preset="compact_no_sticks")
    screen = render("screen", (-30, 6, 14.2), (30, 50, 15.2), mode="device_plain",
                    preset="compact_no_sticks")
    check = dev.render_checks(manifest, [body, screen])[0]
    assert any("320 × 240 pixels" in n for n in check.notes)


def test_a_preset_without_an_id_is_read_as_the_render_lane_names_it(doc):
    """`rules.preset_targets` names a preset with no id or slug `presets[i]`; the device
    pass must read that preset's numbers under the same name, not the defaults."""
    del doc["presets"][1]["id"]
    body = render("body", (-37, -58, 0), (37, 58, 15), mode="device_plain", preset="presets[1]")
    screen = render("screen", (-30, 6, 14.2), (30, 50, 15.2), mode="device_plain",
                    preset="presets[1]")
    check = dev.render_checks(doc, [body, screen])[0]
    assert any("320 × 240 pixels" in n for n in check.notes), check.notes


# ── no pass crashes on a malformed declaration ───────────────────────────────────────

WRONG = (None, 5, 0.5, True, "x", "+w", [], ["x"], {}, {"x": 1}, {"expr": 5}, {"expr": "1 +"})


def test_no_pass_raises_on_a_field_of_the_wrong_type(manifest):
    """The schema refuses these; what is tested is that every pass still returns. A
    checker that stops with a traceback reports nothing about the rest of the cartridge.
    Every field of every control and of every structure entry, twelve wrong values each."""
    renders = [
        BODY,
        render("screen", (-35.56, 17.33, 17.2), (35.56, 70.67, 18.2)),
        render("button_south", (20, -25, 17), (28, -17, 19.4)),
        render("stick_left", (-28.5, -52.5, 16.8), (-15.5, -39.5, 23)),
        render("slide_switch", (42.8, 26.5, 7.8), (45, 30.5, 10.2)),
    ]
    paths = [("vocabulary",), ("structure",), ("controls",)]
    for i, entry in enumerate(manifest["device"]["structure"]):
        paths.append(("structure", i))
        if isinstance(entry, dict):
            paths.extend(("structure", i, key) for key in entry)
    for i, entry in enumerate(manifest["device"]["controls"]):
        for key, value in entry.items():
            paths.append(("controls", i, key))
            if isinstance(value, dict):
                paths.extend(("controls", i, key, sub) for sub in value)
            if isinstance(value, list):
                paths.append(("controls", i, key, 0))
    assert len(paths) > 200
    assert ("structure", 1, "present_when") in paths
    for path in paths:
        for wrong in WRONG:
            mutated = copy.deepcopy(manifest)
            node = mutated["device"]
            for step in path[:-1]:
                node = node[step]
            node[path[-1]] = wrong
            dev.manifest_rules(mutated)
            dev.graph_rules(CARTRIDGE, mutated)
            dev.render_checks(mutated, renders)
    for wrong in WRONG:
        mutated = copy.deepcopy(manifest)
        mutated["device"] = wrong
        dev.manifest_rules(mutated)
        dev.graph_rules(CARTRIDGE, mutated)
        dev.render_checks(mutated, renders)


# ── a device finding fails the run: check_cartridge and the CLI, no stand-in ─────────


def test_a_device_graph_failure_fails_the_check_and_the_cli(scratch, capsys):
    """A mode that shows controls and names no graph is a finding only the device pass
    makes, so it alone must turn the cartridge's verdict and the exit code."""
    from y4d_spec.cli import main

    def drop(doc):
        del doc["modes"][1]["graph_file"]

    rewrite(scratch / "project.json", drop)
    result = check_cartridge(scratch)
    assert not result.ok
    assert len(result.problems) == 1, result.problems
    one(result.problems, "device-controls: mode 'device_plain' shows controls", "names no graph")
    assert main(["check", str(scratch)]) == 1
    out = capsys.readouterr().out
    assert "names no graph" in out and "failures=1" in out


def two_parts(scratch: Path, axis: str) -> Path:
    """The fixture cut down to the body and the power button, one mode, no preset: four
    renders (the script and its wrapper graph), with the button's travel set to `axis`."""
    keep = ("body", "power_button")

    def manifest(doc):
        doc["parts"] = [p for p in doc["parts"] if p["id"] in keep]
        doc["modes"] = [dict(doc["modes"][0], parts=list(keep))]
        doc["presets"] = []
        doc["device"]["structure"] = ["body"]
        doc["device"]["controls"] = [c for c in doc["device"]["controls"] if c["part"] in keep]
        doc["device"]["controls"][0]["travel"]["axis"] = axis

    def graph(doc):
        doc["outputs"] = {k: v for k, v in doc["outputs"].items() if k in keep}
        doc["declarations"]["presets"] = []

    rewrite(scratch / "project.json", manifest)
    rewrite(scratch / "candybar.graph.json", graph)
    return scratch


@pytest.mark.geometry
def test_a_device_render_failure_fails_the_check_and_the_cli(scratch, capsys):
    """Rendered for real: the power button pressed -x passes, the same button declared to
    press +x (out of the body) fails check_cartridge and makes the CLI exit 1."""
    from y4d_spec.cli import main

    cartridge = two_parts(scratch, "-x")
    clean = check_cartridge(cartridge, render=True, printability=False)
    assert clean.ok, clean.problems
    assert {c.status for c in clean.device} == {"pass"} and len(clean.device) >= 1

    two_parts(cartridge, "+x")
    broken = check_cartridge(cartridge, render=True, printability=False)
    assert not broken.ok
    assert broken.device and {c.status for c in broken.device} == {"fail"}
    assert broken.problems == [c.summary for c in broken.device], broken.problems
    assert all("travel.axis +x points away from structure part 'body'" in p
               for p in broken.problems)

    assert main(["check", str(cartridge), "--render", "--no-printability"]) == 1
    last = capsys.readouterr().out.strip().splitlines()[-1]
    total = len(broken.device)
    assert f" device=0/{total} ok, unverified=0, failures={total}" in last


# ── the render pass, against the real meshes ─────────────────────────────────────────


@pytest.fixture(scope="module")
def rendered():
    """One render of the fixture for the whole module: 33 parts, two modes, two presets."""
    return check_cartridge(CARTRIDGE, render=True, parity=True)


@pytest.mark.geometry
def test_the_fixture_cartridge_passes_against_its_rendered_parts(rendered):
    assert rendered.ok, rendered.problems
    assert rendered.device, "the device pass ran"
    assert {c.status for c in rendered.device} == {"pass"}, [
        c.summary for c in rendered.device if c.status != "pass"
    ]
    # device: 31 controls at its defaults and at its preset; device_plain: 18 at each.
    # Once per engine: the script, and the wrapper graph that renders as the script.
    assert {c.engine for c in rendered.device} == {"cadquery", "graph"}
    assert len(rendered.device) == 2 * (2 * 31 + 2 * 18)
    assert not [n for n in rendered.notes if n.startswith("device-controls")], rendered.notes
    screen = next(c for c in rendered.device if c.part == "screen" and c.preset is None)
    assert "face 71.12 × 53.34 mm looking +z" in screen.detail


@pytest.mark.geometry
def test_the_wrapper_graph_renders_the_fixtures_own_meshes(rendered):
    """The cartridge's graph mode (RFC 0067): identical to the script, byte for byte."""
    assert rendered.parity and all(p.ok for p in rendered.parity), [
        p.summary for p in rendered.parity if not p.ok
    ]
    assert all(r.bodies == 1 for r in rendered.verified_renders), [
        r.summary for r in rendered.verified_renders if r.bodies != 1
    ]


@pytest.mark.geometry
def test_the_cli_reports_a_device_clause(rendered, monkeypatch, capsys):
    from y4d_spec import cli

    monkeypatch.setattr(cli, "check_cartridge", lambda *a, **k: rendered)
    assert cli.main(["check", str(CARTRIDGE), "--render"]) == 0
    last = capsys.readouterr().out.strip().splitlines()[-1]
    total = len(rendered.device)
    assert f" device={total}/{total} ok, unverified=0, failures=0" in last


def test_the_cli_prints_no_device_clause_without_a_render(capsys):
    from y4d_spec.cli import main

    assert main(["check", str(CARTRIDGE)]) == 0
    assert " device=" not in capsys.readouterr().out
