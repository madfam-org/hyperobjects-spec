"""Tests for the BRIDGE-HANDSHAKE checker.

The fixtures are built in tmp_path rather than committed, because the point of each
one is a SINGLE deliberate defect and a committed fixture tree of near-identical
cartridges reads as noise. Each builder below produces a two-repo pair — a Fashion
Cabinet checkout with one garment, a yantra4d checkout with one hardware cartridge —
differing only in the defect under test.

The hardware target is a deliberately tiny CadQuery box: a plate whose two dimensions
are the two mapped parameters. It renders in well under a second, so the geometry
tests here cost a fraction of a real cartridge while exercising the identical code
path (`y4d_spec.geometry.render_part`, the real sandbox, a real STL round-trip).

Geometry tests are marked `geometry` and skip unless cadquery + trimesh import,
matching the existing suite.
"""

import json
from pathlib import Path

import pytest

from bridge_check import check_bridge, discover_links, load_y4d_index
from bridge_check.core import evaluate_params_map

# ── the tiny hardware cartridge ──────────────────────────────────────────────
# A plate `plate_w` × `plate_d` × 4mm. Both parameters are read and both drive the
# solid — this is the HEALTHY target, and every defect fixture is a mutation of the
# script or the manifest around it.
GOOD_SCRIPT = '''
import cadquery as cq


def PARAM(getter, default):
    try:
        v = getter()
        return default if v is None else v
    except Exception:
        return default


plate_w = float(PARAM(lambda: plate_w, 20.0))
plate_d = float(PARAM(lambda: plate_d, 10.0))
target_part = str(PARAM(lambda: target_part, "plate"))

result = cq.Workplane("XY").box(plate_w, plate_d, 4.0)
'''

# The SAME cartridge with `plate_d` declared in the manifest and ignored by the
# script — the dead-wiring bug class this tool exists to find. The manifest still
# lists it, so every name-level check (fc-spec included) passes this cartridge.
DEAD_PARAM_SCRIPT = '''
import cadquery as cq


def PARAM(getter, default):
    try:
        v = getter()
        return default if v is None else v
    except Exception:
        return default


plate_w = float(PARAM(lambda: plate_w, 20.0))
target_part = str(PARAM(lambda: target_part, "plate"))

result = cq.Workplane("XY").box(plate_w, 10.0, 4.0)
'''


def _y4d_manifest(*, w_min=5.0, w_max=100.0, w_default=20.0,
                  d_min=5.0, d_max=100.0, d_default=10.0) -> dict:
    return {
        "project": {
            "slug": "test-plate",
            "name": {"en": "Test Plate", "es": "Placa"},
            "thumbnail": "/thumb.png",
            "tags": ["test"],
            "difficulty": "beginner",
        },
        "modes": [
            {
                "id": "plate",
                "label": {"en": "Plate", "es": "Placa"},
                "scad_file": "main.py",
                "cq_file": "main.py",
                "parts": ["plate"],
            }
        ],
        "parameters": [
            {"id": "plate_w", "type": "slider", "default": w_default,
             "min": w_min, "max": w_max, "step": 0.5, "modes": ["plate"],
             "label": {"en": "Width", "es": "Ancho"}},
            {"id": "plate_d", "type": "slider", "default": d_default,
             "min": d_min, "max": d_max, "step": 0.5, "modes": ["plate"],
             "label": {"en": "Depth", "es": "Fondo"}},
        ],
    }


def _fc_manifest(params_map: dict, *, params: list | None = None) -> dict:
    return {
        "project": {"slug": "test-garment", "name": {"en": "Test Garment"}},
        "modes": [{"id": "set", "script_file": "main.py", "pieces": ["body"]}],
        "pieces": [{"id": "body"}],
        "parameters": params or [
            {"id": "tape_width", "type": "slider", "default": 30.0,
             "min": 10.0, "max": 60.0},
            {"id": "tape_depth", "type": "slider", "default": 12.0,
             "min": 5.0, "max": 40.0},
        ],
        "notion": {
            "hardware_ref": {
                "platform": "yantra4d",
                "project_slug": "test-plate",
                "linked": True,
                "params_map": params_map,
            }
        },
    }


def _build(tmp_path: Path, *, params_map: dict, script: str = GOOD_SCRIPT,
           y4d_manifest: dict | None = None, fc_manifest: dict | None = None):
    """Write a two-repo pair into tmp_path; return (fc_repo, y4d_repo)."""
    fc = tmp_path / "fc"
    y4d = tmp_path / "y4d"
    garment = fc / "projects" / "test-garment"
    plate = y4d / "projects" / "test-plate"
    garment.mkdir(parents=True)
    plate.mkdir(parents=True)

    (garment / "project.json").write_text(
        json.dumps(fc_manifest or _fc_manifest(params_map)), encoding="utf-8"
    )
    (plate / "project.json").write_text(
        json.dumps(y4d_manifest or _y4d_manifest()), encoding="utf-8"
    )
    (plate / "main.py").write_text(script, encoding="utf-8")
    return fc, y4d


# ── discovery and resolution (no geometry needed) ────────────────────────────
def test_discovers_the_link(tmp_path):
    fc, y4d = _build(tmp_path, params_map={"plate_w": "tape_width"})
    index = load_y4d_index(y4d)
    assert "test-plate" in index

    links = discover_links(fc, index)
    assert len(links) == 1
    assert links[0].fc_slug == "test-garment"
    assert links[0].target_slug == "test-plate"
    assert links[0].y4d_dir is not None


def test_unlinked_hardware_ref_is_not_a_link(tmp_path):
    """`linked: false` is a declared intent, not a claim — the same exemption
    fc_spec.rules.hardware_ref_rules makes."""
    mf = _fc_manifest({"plate_w": "tape_width"})
    mf["notion"]["hardware_ref"]["linked"] = False
    fc, y4d = _build(tmp_path, params_map={}, fc_manifest=mf)
    assert discover_links(fc, load_y4d_index(y4d)) == []


def test_unknown_slug_is_a_resolve_failure(tmp_path):
    mf = _fc_manifest({"plate_w": "tape_width"})
    mf["notion"]["hardware_ref"]["project_slug"] = "no-such-cartridge"
    fc, y4d = _build(tmp_path, params_map={}, fc_manifest=mf)
    [v] = check_bridge(fc, y4d, render=False)
    assert v.status == "resolve_fail"
    assert any("does not resolve" in p for p in v.resolve_problems)


def test_expression_evaluation_against_defaults():
    mf = _fc_manifest({})
    values, problems = evaluate_params_map(
        {"a": "tape_width", "b": "tape_width + 6", "c": "round(tape_width / 4)"}, mf
    )
    assert problems == []
    assert values == {"a": 30.0, "b": 36.0, "c": 8.0}


def test_expression_referencing_a_defaultless_parameter_is_caught():
    """Structurally fine — the identifier IS a declared parameter — but there is no
    number to render at. This is the half hardware_ref_rules cannot check."""
    mf = _fc_manifest({}, params=[{"id": "tape_width", "type": "slider"}])  # no default
    _values, problems = evaluate_params_map({"plate_w": "tape_width"}, mf)
    assert any("has no default value" in p for p in problems)


def test_expression_evaluator_refuses_anything_outside_the_grammar():
    """The evaluator is an AST walk, not eval(): a manifest is third-party input."""
    mf = _fc_manifest({})
    _v, problems = evaluate_params_map({"plate_w": "__import__('os').system('x')"}, mf)
    assert problems and "not one of the safe map functions" in problems[0]


# ── the handshake (geometry) ─────────────────────────────────────────────────
@pytest.mark.geometry
@pytest.mark.geometry
def test_happy_path_passes(tmp_path):
    """Both mapped parameters drive the solid: renders, and both prove responsive."""
    fc, y4d = _build(
        tmp_path, params_map={"plate_w": "tape_width", "plate_d": "tape_depth"}
    )
    [v] = check_bridge(fc, y4d)
    assert v.ok, v.summary
    assert v.status == "ok"
    assert v.mapped_values == {"plate_w": 30.0, "plate_d": 12.0}
    assert v.rendered == ("plate", "plate")
    assert len(v.probes) == 2
    assert all(p.responsive for p in v.probes)
    # Real evidence, not a boolean: the volume genuinely moved.
    for p in v.probes:
        assert p.delta > 1.0


@pytest.mark.geometry
@pytest.mark.geometry
def test_a_params_map_key_the_script_ignores_is_caught_as_dead(tmp_path):
    """THE bug class. `plate_d` is a declared parameter of the target (so every
    name-level check passes), the expression is valid, and the script never reads
    it. Only a render at perturbed values can see this."""
    fc, y4d = _build(
        tmp_path,
        params_map={"plate_w": "tape_width", "plate_d": "tape_depth"},
        script=DEAD_PARAM_SCRIPT,
    )
    [v] = check_bridge(fc, y4d)
    assert not v.ok
    assert v.status == "dead_params"
    assert v.dead_params == ["plate_d"]
    assert "plate_w" not in v.dead_params  # the live one is not collateral damage
    assert "dead params_map key" in v.summary


@pytest.mark.geometry
def test_the_structural_check_alone_passes_the_dead_link(tmp_path):
    """Proves the tool is not redundant: fc-spec's resolution rule is happy with the
    exact link the handshake fails. If this ever starts failing, the structural rule
    grew teeth and this test should be re-read, not deleted."""
    from fc_spec.rules import hardware_ref_rules

    fc, y4d = _build(
        tmp_path,
        params_map={"plate_w": "tape_width", "plate_d": "tape_depth"},
        script=DEAD_PARAM_SCRIPT,
    )
    index = load_y4d_index(y4d)
    [link] = discover_links(fc, index)
    resolve = {slug: [p["id"] for p in doc["parameters"]] for slug, (_d, doc) in index.items()}
    assert hardware_ref_rules(link.fc_manifest, resolve) == []


@pytest.mark.geometry
@pytest.mark.geometry
def test_out_of_range_mapping_clamps_and_is_skipped_not_failed(tmp_path):
    """A mapped value sitting AT the parameter's max: +10% would leave the declared
    range, so it is clamped — and clamping back to the same value proves nothing.
    That is a skip, never a failure. Reporting it as dead would be a false positive
    manufactured by the checker itself."""
    y4d_mf = _y4d_manifest(d_min=12.0, d_max=12.0)  # plate_d pinned: no room either way
    fc, y4d = _build(
        tmp_path,
        params_map={"plate_w": "tape_width", "plate_d": "tape_depth"},
        y4d_manifest=y4d_mf,
    )
    [v] = check_bridge(fc, y4d)
    assert v.ok, v.summary          # NOT a failure
    assert v.dead_params == []
    skipped = [p for p in v.probes if p.skipped]
    assert [p.param for p in skipped] == ["plate_d"]
    assert "no perturbation moves the value" in skipped[0].skipped
    assert any("probe 'plate_d' skipped" in n for n in v.notes)


@pytest.mark.geometry
@pytest.mark.geometry
def test_default_at_max_perturbs_downward(tmp_path):
    """When the mapped value IS the max, -10% is inside the range by construction —
    so the parameter is still provable, and must not be skipped."""
    y4d_mf = _y4d_manifest(w_min=5.0, w_max=30.0)  # tape_width default 30 == max
    fc, y4d = _build(tmp_path, params_map={"plate_w": "tape_width"}, y4d_manifest=y4d_mf)
    [v] = check_bridge(fc, y4d)
    assert v.ok, v.summary
    [probe] = v.probes
    assert probe.skipped is None
    assert probe.probe_value < probe.base_value
    assert probe.responsive is True


@pytest.mark.geometry
@pytest.mark.geometry
def test_render_failure_at_mapped_values_is_reported(tmp_path):
    """A garment mapping a value the solid cannot build at. Here the mapping drives
    the plate to zero width — a degenerate box the kernel refuses. Structurally the
    link is perfect, and the cartridge renders fine at its own defaults, so the
    mapping is the only thing that can be blamed."""
    fc_mf = _fc_manifest(
        {"plate_w": "tape_width - tape_width"},
        params=[{"id": "tape_width", "type": "slider", "default": 30.0,
                 "min": 10.0, "max": 60.0}],
    )
    fc, y4d = _build(tmp_path, params_map={}, fc_manifest=fc_mf)
    [v] = check_bridge(fc, y4d)
    assert not v.ok
    assert v.status == "render_fail"
    assert any(
        "renders clean at the cartridge's defaults but FAILS" in p
        for p in v.render_problems
    )


@pytest.mark.geometry
@pytest.mark.geometry
def test_target_already_broken_at_its_own_defaults_is_skipped_not_failed(tmp_path):
    """THE false positive the first calibration run produced. Two real yantra4d
    cartridges (magnetic-clasp, tpu-scale-mail) fail `y4d-spec check --render` at
    their own defaults; blaming the garment's mapping for a solid that was already
    broken is a finding the FC maintainer cannot act on. The link is skipped with a
    note pointing at the tool that owns the defect."""
    # A bare face, not a solid: exports no STL at all, so the cartridge is broken at
    # every parameter value including its own defaults.
    broken = GOOD_SCRIPT.replace(
        'result = cq.Workplane("XY").box(plate_w, plate_d, 4.0)',
        'result = cq.Workplane("XY").box(plate_w, plate_d, 4.0).faces(">Z")',
    )
    fc, y4d = _build(
        tmp_path, params_map={"plate_w": "tape_width"}, script=broken
    )
    [v] = check_bridge(fc, y4d)
    assert v.status == "skipped"
    assert v.render_problems == []
    assert v.dead_params == []
    assert "does not render cleanly at its OWN defaults" in v.geometry_skipped
    assert "y4d-spec check" in v.geometry_skipped


# ── the two bugs the real-commons calibration found in this checker ──────────
def test_integral_parameter_perturbs_by_a_whole_step():
    """CALIBRATION BUG 1. lacing-hook's `hook_count` is `step: 1, default: 4` and its
    script does `int(PARAM(...))`. +10% of 5 is 5.5, which truncates straight back to
    5 — a guaranteed false 'dead' verdict on every count parameter in the commons.
    An integral parameter must move by at least one whole step."""
    from bridge_check.core import _perturb_value

    meta = {"id": "hook_count", "type": "slider", "default": 4, "min": 2, "max": 8,
            "step": 1}
    probe, skip = _perturb_value(meta, 5.0)
    assert skip is None
    assert probe == 6.0                    # not 5.5
    assert probe == int(probe)             # survives the cartridge's int()


def test_integral_parameter_at_max_steps_down_a_whole_step():
    from bridge_check.core import _perturb_value

    meta = {"id": "hook_count", "type": "slider", "default": 4, "min": 2, "max": 8,
            "step": 1}
    probe, skip = _perturb_value(meta, 8.0)
    assert skip is None
    assert probe == 7.0


def test_continuous_parameter_still_perturbs_fractionally():
    """The integral path must not swallow ordinary sliders."""
    from bridge_check.core import _perturb_value

    meta = {"id": "cord_dia", "type": "slider", "default": 4.0, "min": 2.0,
            "max": 6.0, "step": 0.1}
    probe, skip = _perturb_value(meta, 4.0)
    assert skip is None
    assert probe == pytest.approx(4.4)


def test_out_of_range_mapping_is_detected():
    """CALIBRATION BUG 2. ankle-gaiter maps `pitch` = 26 to a parameter whose
    declared max is 25. The cartridge clamps it, so the garment gets a part of a
    size it did not order — a REAL finding, but a different one from a dead key.
    The naive rule reported it as dead: a real problem given the wrong name."""
    from bridge_check.core import _out_of_range

    meta = {"id": "pitch", "min": 8.0, "max": 25.0}
    assert "above the target parameter's declared max 25" in _out_of_range(meta, 26.0)
    assert "below the target parameter's declared min 8" in _out_of_range(meta, 7.0)
    assert _out_of_range(meta, 12.0) is None


@pytest.mark.geometry
@pytest.mark.geometry
def test_out_of_range_mapping_is_a_measurement_not_a_failure(tmp_path):
    """House doctrine: a new rule lands as a measurement, gets calibrated, and only
    then may block. The range finding is counted and printed, and the link still
    passes."""
    y4d_mf = _y4d_manifest(w_min=5.0, w_max=25.0)  # tape_width default 30 > max 25
    fc, y4d = _build(tmp_path, params_map={"plate_w": "tape_width"}, y4d_manifest=y4d_mf)
    [v] = check_bridge(fc, y4d)
    assert v.ok                     # NOT blocking
    assert v.status == "ok"
    assert v.dead_params == []      # and NOT misreported as dead wiring
    assert len(v.range_problems) == 1
    assert "above the target parameter's declared max 25" in v.range_problems[0]
    assert "[range: 1]" in v.summary


def test_target_cap_bounds_the_render_budget_and_says_so():
    """CALIBRATION FINDING 3. The render count is targets x (2 + probes), and
    ownership resolution can select several modes at once: `zipper`'s `zip_length` is
    scoped to both `closed` and `separating`, which declare seven parts between them,
    so each of the eleven zipper links wanted 21+ renders of a 300mm zipper. Measured
    across the commons a full sweep is 1080 renders. The cap bounds a link's cost and
    records exactly what it did not render — never silently."""
    from bridge_check.core import _cap_targets

    targets = [("closed", "tape_left"), ("closed", "tape_right"),
               ("closed", "slider"), ("separating", "tape_left"),
               ("separating", "pin_box")]
    kept, note = _cap_targets(targets, 4)
    assert kept == targets[:4]
    assert "5 targets owned the mapped parameters" in note
    assert "(separating, pin_box)" in note      # names what was dropped
    assert "--max-targets" in note              # and how to get it back

    kept, note = _cap_targets(targets, 10)
    assert kept == targets and note is None


@pytest.mark.geometry
@pytest.mark.geometry
def test_range_check_covers_every_key_not_just_the_probed_ones(tmp_path):
    """CALIBRATION FINDING 4. The range check is pure arithmetic — it costs no
    render — so it must not inherit the probe budget. `balconette-bra` hardcodes
    `wire_d: "1.4"` against a bra-underwire whose declared minimum is 1.5, and
    `wire_d` sorts LAST of that link's three keys: bounded by --max-probes 1, the
    single most informative fact about the failure would have gone unreported."""
    y4d_mf = _y4d_manifest(d_min=20.0, d_max=40.0)   # plate_d mapped to 12 -> below min
    fc, y4d = _build(
        tmp_path,
        params_map={"plate_w": "tape_width", "plate_d": "tape_depth"},
        y4d_manifest=y4d_mf,
    )
    [v] = check_bridge(fc, y4d, max_probes=1)        # only plate_d probed... but
    assert len(v.probes) == 1                        # ...the budget still binds probes
    assert any("plate_d" in r for r in v.range_problems)
    assert "below the target parameter's declared min 20" in v.range_problems[0]


@pytest.mark.geometry
@pytest.mark.geometry
def test_max_probes_caps_the_render_budget(tmp_path):
    fc, y4d = _build(
        tmp_path, params_map={"plate_w": "tape_width", "plate_d": "tape_depth"}
    )
    [v] = check_bridge(fc, y4d, max_probes=1)
    assert len(v.probes) == 1


# ── OpenSCAD-only targets ────────────────────────────────────────────────────
def test_openscad_only_target_is_skipped_not_failed(tmp_path):
    """The OpenSCAD kernel is the platform's job. Step 1 still runs and still
    counts; steps 2-3 are recorded as skipped so the run never over-claims."""
    y4d_mf = _y4d_manifest()
    y4d_mf["modes"][0].pop("cq_file")  # scad_file only
    fc, y4d = _build(tmp_path, params_map={"plate_w": "tape_width"}, y4d_manifest=y4d_mf)
    [v] = check_bridge(fc, y4d, render=False)
    # With render off everything skips; the interesting assertion is the kernel path.
    assert v.status == "skipped"

    [v2] = check_bridge(fc, y4d, render=True) if _geometry() else [v]
    if _geometry():
        assert v2.status == "skipped"
        assert "no CadQuery mode" in v2.geometry_skipped
        assert v2.resolve_problems == []


def _geometry() -> bool:
    from y4d_spec.geometry import geometry_available

    return geometry_available()


# ── CLI ──────────────────────────────────────────────────────────────────────
def test_cli_reports_counts_and_exits_zero(tmp_path, capsys):
    from bridge_check.cli import main

    fc, y4d = _build(tmp_path, params_map={"plate_w": "tape_width"})
    rc = main(["check", "--fc", str(fc), "--y4d", str(y4d), "--no-render"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "bridge-check: links=1 ok=0" in out
    assert "skipped=1" in out
    # Read-proof: a resolution-only run must never read like a verified one.
    assert "geometry was NOT verified" in out


@pytest.mark.geometry
@pytest.mark.geometry
def test_cli_exits_nonzero_on_a_dead_param(tmp_path, capsys):
    from bridge_check.cli import main

    fc, y4d = _build(
        tmp_path,
        params_map={"plate_w": "tape_width", "plate_d": "tape_depth"},
        script=DEAD_PARAM_SCRIPT,
    )
    rc = main(["check", "--fc", str(fc), "--y4d", str(y4d)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "dead_params=1" in out
    assert "plate_d" in out


def test_cli_usage_error_on_a_bad_repo(tmp_path, capsys):
    from bridge_check.cli import main

    rc = main(["check", "--fc", str(tmp_path), "--y4d", str(tmp_path / "nope"),
               "--no-render"])
    assert rc == 2
    assert "is not a directory" in capsys.readouterr().out


def test_cli_zero_links_is_a_usage_error(tmp_path, capsys):
    """Checking nothing must not read as a pass."""
    from bridge_check.cli import main

    fc = tmp_path / "fc"
    (fc / "projects").mkdir(parents=True)
    y4d = tmp_path / "y4d"
    (y4d / "projects").mkdir(parents=True)
    rc = main(["check", "--fc", str(fc), "--y4d", str(y4d), "--no-render"])
    assert rc == 2
    assert "checked=0 links" in capsys.readouterr().out
