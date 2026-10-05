"""Lane P6-XCAR: collision envelopes for MGN9 and the 6 mm XY idler; the toolhead mount key.

ASM-1 §3.7 builds each standard part's collision body from its cited dimensions. Before
this change `mgn9-rail`, `mgn9h-carriage` and `gt2-idler-20t-6mm` carried none, so a
2.4-class assembly's Y and Z rails and its XY idlers read `collision-unchecked`.

* An MGN9H on its MGN9 rail (HIWIN: WR 9, HR 6.5; H 10, H1 2, W 20, L 39.9) runs the whole
  rail with no interference: the block's envelope leaves the 9 mm channel open, as the
  MGN12H's does, so the two only touch.
* The 6 mm idler (OD 18 × 9, Motedis) on an M5x40 SHCS overlaps only by the shank in its
  unhollowed bore: π · 2.5² · 9 = 176.71 mm³, a designed overlap an assembly declares.
* `toolhead-mount-20x20-m3` is in the interface-sizes vocabulary.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from assembly_helpers import assembly, mate, standard

KEY = "toolhead-mount-20x20-m3"


def _check(doc, **kw):
    from hyperobjects_aas.resolver import bundled_standard_parts_dir
    from y4d_spec.assembly import CompositeResolver, validate_assembly

    both = CompositeResolver.for_directories(None, bundled_standard_parts_dir())
    return validate_assembly(doc, both, **kw)


def _block_on_rail(limit=180.05):
    joint = {"id": "y", "type": "prismatic", "axis": "x", "limits": [-limit, limit], "home": 0}
    run = mate("run", "rail.track", "block.rail_way")
    run["joint"] = joint
    return assembly([standard("rail", "mgn9-rail", length_mm=400),
                     standard("block", "mgn9h-carriage")], [run])


def test_the_new_envelopes_are_present_and_traceable():
    from hyperobjects_aas.resolver import bundled_standard_parts_dir

    parts = Path(bundled_standard_parts_dir())
    for key in ("mgn9-rail", "mgn9h-carriage", "gt2-idler-20t-6mm"):
        entry = json.loads((parts / f"{key}.json").read_text(encoding="utf-8"))
        solids = entry["envelope"]["solids"]
        assert solids, key
        for solid in solids:
            assert set(solid["from"]) <= set(entry["dimensions"]), (key, solid["from"])


@pytest.mark.geometry
def test_an_mgn9h_runs_its_whole_rail_without_interference():
    report = _check(_block_on_rail(), collision=True, pose_samples=8)
    assert report.ok, [f.message for f in report.errors]
    assert report.collision == "checked"
    assert report.collision_result.unchecked == {}
    assert report.collision_result.pairs == {}


@pytest.mark.geometry
def test_the_6mm_idler_on_its_axle_overlaps_only_by_the_shank_in_its_bore():
    doc = assembly([standard("screw", "shcs-m5x40", journal_offset_mm=14),
                    standard("idler", "gt2-idler-20t-6mm")],
                   [mate("on_axle", "screw.journal", "idler.bore", angle_deg=0)])
    report = _check(doc, collision=True)
    assert report.collision == "checked"
    (finding,) = [f for f in report.errors if f.code == "collision"]
    assert finding.subject in ("screw|idler", "idler|screw")
    shank_in_bore = math.pi * 2.5 ** 2 * 9
    assert report.collision_result.pairs[finding.subject]["max_mm3"] == pytest.approx(
        shank_in_bore, abs=0.05)


def test_the_toolhead_mount_key_is_in_the_vocabulary():
    from importlib.resources import files

    path = files("hyperobjects_lexicon") / "vocabularies" / "fabrication" / (
        "interface-sizes.standard-parts.json")
    entries = {e["key"]: e for e in json.loads(path.read_text(encoding="utf-8"))["entries"]}
    entry = entries[KEY]
    assert entry["geometry_type"] == "bolt_pattern"
    assert entry["dimensions"]["hole_spacing"]["value"] == 20
    assert set(entry["definition"]) == {"en", "es", "fr", "pt"}
