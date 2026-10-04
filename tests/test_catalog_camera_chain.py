"""The FPV camera chain (ASM-1 v1.1 follow-up, lane P4-AUTH-C), proven by placement.

* fpv-frame-5in-x-225 gains the side plates' inner faces (``camera_plate_left/right``) on
  the side-screw axis, ``camera_bay_width_mm`` apart (the class's cited 19–20 mm).
* fpv-camera-micro-19mm gains planar faces a printed part can mate: the two side faces
  (where the side screws enter), and the front and back faces.
* The chain frame plates → camera closes as a cycle together with the existing
  camera_bay ↔ side_mount mate, at any tilt.
* A cradle framed like fpv-camera-cage's floor (the gate-proven frame) closes with the
  camera, and which face it receives decides where the camera looks.
* A cage whose tab faces stand wider than the bay cannot close on both side plates: the
  reason no cage ↔ side-plate mate is authored for the cage as it is modelled today.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

import hyperobjects_standard_parts
from hyperobjects_lexicon.fabrication import load_fabrication_vocabulary
from hyperobjects_standard_parts import interface_frames, load_part, resolve_parameters
from y4d_spec.assembly import (
    CompositeResolver,
    ExternalResolver,
    StandardPartsResolver,
    validate_assembly,
)

FRAME = {"id": "frame", "source": {"type": "standard", "key": "fpv-frame-5in-x-225"}}
CATALOG = Path(hyperobjects_standard_parts.__file__).parent / "parts"
CAMERA = {"id": "camera", "source": {"type": "standard", "key": "fpv-camera-micro-19mm"}}


def _resolver():
    return CompositeResolver(standard=StandardPartsResolver(CATALOG), external=ExternalResolver())


def _external(cid, *ifaces):
    return {"id": cid, "source": {"type": "external", "name": f"Test {cid}",
                                  "license": "CERN-OHL-W-2.0", "url": "https://example.org/x",
                                  "interfaces": list(ifaces)}}


def _assembly(components, mates):
    return {
        "format": "hyperobjects.assembly", "format_version": "1.0.0", "slug": "camera-chain",
        "kind": "product", "name": {"en": "x", "es": "x"}, "license": "CERN-OHL-W-2.0",
        "root": components[0]["id"], "components": components, "mates": mates,
    }


def _mate(mid, a, b, **kw):
    (ca, ia), (cb, ib) = a.split("."), b.split(".")
    return {"id": mid, "a": {"component": ca, "interface": ia},
            "b": {"component": cb, "interface": ib}, **kw}


def _apply(matrix, point):
    return tuple(sum(matrix[r][c] * (list(point) + [1.0])[c] for c in range(4)) for r in range(3))


def _column(matrix, c):
    return tuple(matrix[r][c] for r in range(3))


# ── vocabulary ────────────────────────────────────────────────────────────────
def test_the_two_new_keys_are_cited_socket_keys():
    entries = {e["key"]: e for e in load_fabrication_vocabulary("interface-sizes")["entries"]}
    mini, ufl = entries["fpv-camera-mini-21mm"], entries["u-fl-cable-exit"]
    assert mini["geometry_type"] == ufl["geometry_type"] == "socket"
    assert mini["dimensions"]["body_width_min"]["value"] == 21.8
    assert mini["dimensions"]["body_width_max"]["value"] == 22
    assert ufl["dimensions"]["mated_height_max"]["value"] == 2.5
    for entry in (mini, ufl):
        assert entry["sources"] and all(s["url"].startswith("https://") for s in entry["sources"])
    # the camera classes stay three distinct keys: a mini does not mate a micro
    assert {"fpv-camera-nano-14mm", "fpv-camera-micro-19mm", "fpv-camera-mini-21mm"} <= set(entries)


# ── the frame's side plates ───────────────────────────────────────────────────
@pytest.mark.parametrize("bay", [19, 20])
def test_side_plates_face_each_other_across_the_bay(bay):
    part = load_part("fpv-frame-5in-x-225")
    frames = interface_frames(part, resolve_parameters(part, {"camera_bay_width_mm": bay}))
    left, right, bay_frame = (frames[k] for k in ("camera_plate_left", "camera_plate_right",
                                                  "camera_bay"))
    assert left.origin == pytest.approx((50.0, bay / 2, 13.75))
    assert right.origin == pytest.approx((50.0, -bay / 2, 13.75))
    assert left.normal == pytest.approx((0.0, -1.0, 0.0))   # into the bay
    assert right.normal == pytest.approx((0.0, 1.0, 0.0))
    # Both plates sit on the bay's side-screw axis (x and z of the bay origin).
    for plate in (left, right):
        assert (plate.origin[0], plate.origin[2]) == pytest.approx(
            (bay_frame.origin[0], bay_frame.origin[2]))


def test_the_bay_width_is_the_cited_range():
    part = load_part("fpv-frame-5in-x-225")
    param = next(p for p in part["parameters"] if p["id"] == "camera_bay_width_mm")
    assert (param["min"], param["max"]) == (
        part["dimensions"]["camera_bay_width_min"]["value"],
        part["dimensions"]["camera_bay_width_max"]["value"])


# ── frame plates → camera ─────────────────────────────────────────────────────
@pytest.mark.parametrize("tilt", [0, 30, -15])
def test_camera_bolts_between_both_plates_and_the_cycle_closes(tilt):
    doc = _assembly(
        [FRAME, CAMERA],
        [_mate("m1", "frame.camera_plate_left", "camera.side_face_left", angle_deg=tilt),
         _mate("m2", "frame.camera_plate_right", "camera.side_face_right", angle_deg=-tilt),
         _mate("m3", "frame.camera_bay", "camera.side_mount", angle_deg=-tilt)],
    )
    report = validate_assembly(doc, _resolver())
    assert report.ok, report.findings
    assert [m.ok for m in report.mates] == [True, True, True]
    cam = report.placements["camera"]
    # The camera's mid-plane origin lands on the bay's side-screw axis.
    assert _apply(cam, (0, 0, 0)) == pytest.approx((50.0, 0.0, 13.75))
    # Tilting about the side-screw axis keeps the optical axis in the x–z plane.
    optical = _column(cam, 0)
    assert optical[1] == pytest.approx(0.0, abs=1e-12)
    assert abs(math.degrees(math.atan2(optical[2], optical[0]))) == pytest.approx(abs(tilt))


def test_a_20_mm_bay_does_not_seat_a_19_mm_body_on_both_plates():
    """The plates are faces, not a clamp: in a 20 mm bay the body touches one plate only."""
    frame = {**FRAME, "source": {**FRAME["source"], "parameters": {"camera_bay_width_mm": 20}}}
    doc = _assembly(
        [frame, CAMERA],
        [_mate("m1", "frame.camera_plate_left", "camera.side_face_left", angle_deg=0),
         _mate("m2", "frame.camera_plate_right", "camera.side_face_right", angle_deg=0)],
    )
    report = validate_assembly(doc, _resolver())
    assert not report.ok
    closure = [f for f in report.errors if f.code == "closure"]
    assert closure and "1.0000 mm apart" in closure[0].message


# ── camera → a printed cradle ─────────────────────────────────────────────────
def _cradle(tilt=30.0, cw=19.0, cam_clear=0.4):
    """fpv-camera-cage's cradle floor at its gate-proven frame (P4-SPEC2 proof, 26/26 ok)."""
    t = math.radians(max(0.0, min(tilt, 55.0)))
    pocket_d = cw * 0.85 + 2 * cam_clear
    return {"id": "cradle_floor", "polarity": "female", "size_key": "fpv-camera-micro-19mm",
            "symmetry": 4, "geometry_type": "socket",
            "frame": {"origin": [0, -pocket_d * math.cos(t), pocket_d * math.sin(t)],
                      "normal": [0, math.cos(t), -math.sin(t)], "x_axis": [1, 0, 0]}}


@pytest.mark.parametrize(("face", "looks_up"), [("front_face", True), ("back_face", False)])
def test_which_face_seats_on_the_cradle_floor_decides_where_the_camera_looks(face, looks_up):
    """The cage's floor faces its open side and tilts DOWN by `tilt`; its lens aperture is in
    the floor. Lens-first (front_face on the floor) the camera looks out through the aperture,
    UP by the tilt; back_face on the floor would aim it down."""
    doc = _assembly([_external("cage", _cradle(30)), CAMERA],
                    [_mate("m1", "cage.cradle_floor", f"camera.{face}", rotation_index=0)])
    report = validate_assembly(doc, _resolver())
    assert report.ok, report.findings
    optical = _column(report.placements["camera"], 0)
    elevation = math.degrees(math.asin(optical[2]))
    assert elevation == pytest.approx(30.0 if looks_up else -30.0)
    assert optical[0] == pytest.approx(0.0, abs=1e-12)


def test_a_mini_cradle_does_not_take_a_micro_camera():
    cradle = {**_cradle(30, cw=21.0), "size_key": "fpv-camera-mini-21mm"}
    doc = _assembly([_external("cage", cradle), CAMERA],
                    [_mate("m1", "cage.cradle_floor", "camera.front_face", rotation_index=0)])
    report = validate_assembly(doc, _resolver())
    assert not report.ok
    assert any(f.code == "size_key" for f in report.errors)


# ── why no cage ↔ side-plate mate exists yet ──────────────────────────────────
def test_a_cage_wider_than_the_bay_cannot_close_on_both_plates():
    """fpv-camera-cage at its defaults (micro, wall 2, clearance 0.4, tab 3): the body is
    19 + 2·0.4 + 2·2 = 23.8 mm wide and its tabs' outer faces stand ±14.9 mm from the
    centre. Whatever tab face is chosen, the spacing is not the 19–20 mm bay, so one plate
    mate holds and the other misses by the difference."""
    tab_outer = (23.8 + 2 * 3.0) / 2
    tabs = [{"id": f"tab_{side}", "polarity": "female", "size_key": "fpv-camera-micro-19mm",
             "symmetry": 0, "geometry_type": "socket",
             "frame": {"origin": [0, sgn * tab_outer, 0], "normal": [0, sgn, 0],
                       "x_axis": [1, 0, 0]}}
            for side, sgn in (("left", 1), ("right", -1))]
    doc = _assembly(
        [FRAME, _external("cage", *tabs)],
        [_mate("m1", "frame.camera_plate_left", "cage.tab_left", angle_deg=0),
         _mate("m2", "frame.camera_plate_right", "cage.tab_right", angle_deg=0)],
    )
    report = validate_assembly(doc, _resolver())
    assert not report.ok
    miss = next(m for m in report.mates if not m.ok)
    assert miss.origin_mm == pytest.approx(2 * tab_outer - 19.0)  # 10.8 mm


# ── O1(a): the cage ahead of the frame, its ears on the plates' OUTER faces ──
def _ear_cage(tilt, mount_width=24.0, ear_reach=12.0, cw=19.0, cam_clear=0.4, wall=2.0,
              cam_len=20.0):
    """fpv-camera-cage's interfaces as its manifest frames them (owner decision O1(a)).

    Cage coordinates: the housing pivots about +x through the origin (the open face's
    centre); the lens looks along −y, tilted UP by `tilt`; +z up. Each ear's inner face
    stands mount_width / 2 out, its screw on the pivot's height, `ear_y` behind the
    pivot — at least 4 mm behind the housing's swing-back so a plate's edge fits ahead
    of the screw.
    """
    t = math.radians(max(0.0, min(tilt, 55.0)))
    out_h = cw + 2 * cam_clear + 2 * wall
    bar = max(1.4, wall * 0.7)
    ear_y = max(ear_reach, out_h / 2 * math.sin(t) + bar * math.cos(t) + 4)
    pocket_d = cam_len + 2 * cam_clear
    ears = [{"id": f"ear_{side}", "polarity": "male", "size_key": "fpv-camera-side-plate-screw",
             "symmetry": 0, "geometry_type": "bolt_pattern",
             "frame": {"origin": [sgn * mount_width / 2, ear_y, 0], "normal": [-sgn, 0, 0],
                       "x_axis": [0, -1, 0]}}
            for side, sgn in (("left", 1), ("right", -1))]
    cradle = {"id": "cradle_floor", "polarity": "female", "size_key": "fpv-camera-micro-19mm",
              "symmetry": 4, "geometry_type": "pocket",
              "frame": {"origin": [0, -pocket_d * math.cos(t), pocket_d * math.sin(t)],
                        "normal": [0, math.cos(t), -math.sin(t)], "x_axis": [1, 0, 0]}}
    return _external("cage", *ears, cradle), ear_y


def _ear_chain(tilt, **cage_kw):
    cage, ear_y = _ear_cage(tilt, **cage_kw)
    doc = _assembly(
        [FRAME, cage, CAMERA],
        [_mate("m1", "frame.camera_plate_left_outer", "cage.ear_left", angle_deg=0),
         _mate("m2", "frame.camera_plate_right_outer", "cage.ear_right", angle_deg=0),
         _mate("m3", "cage.cradle_floor", "camera.front_face", rotation_index=0)],
    )
    return validate_assembly(doc, _resolver()), ear_y


def test_plate_outer_faces_stand_bay_plus_two_plates_apart():
    part = load_part("fpv-frame-5in-x-225")
    for given, half in (({}, 12.0), ({"camera_bay_width_mm": 20, "side_plate_thickness_mm": 3},
                                     13.0)):
        frames = interface_frames(part, resolve_parameters(part, given))
        left, right = frames["camera_plate_left_outer"], frames["camera_plate_right_outer"]
        assert left.origin == pytest.approx((50.0, half, 13.75))
        assert right.origin == pytest.approx((50.0, -half, 13.75))
        assert left.normal == pytest.approx((0.0, 1.0, 0.0))     # away from the bay
        assert right.normal == pytest.approx((0.0, -1.0, 0.0))
    thickness = next(p for p in part["parameters"] if p["id"] == "side_plate_thickness_mm")
    assert thickness["default"] == 2.5 and part["sources"][thickness["source"]]["supports"].count(
        "2.5 mm top, bottom and side plates")


@pytest.mark.parametrize("tilt", [0, 15, 30, 45, 55])
def test_frame_outer_faces_to_cage_ears_to_cradle_to_camera_closes(tilt):
    report, ear_y = _ear_chain(tilt)
    assert report.ok, report.findings
    assert [m.ok for m in report.mates] == [True, True, True]
    for m in report.mates[:2]:  # the stated angle is the one the geometry realises
        assert min(m.measured_deg, 360 - m.measured_deg) == pytest.approx(0.0, abs=1e-6)
    cage, cam = report.placements["cage"], report.placements["camera"]
    # The cage sits level and AHEAD of the frame: its −y (the lens side) is world +x, and
    # its pivot lies ear_y forward of the side-screw axis at (50, 0, 13.75).
    assert _column(cage, 1) == pytest.approx((-1.0, 0.0, 0.0), abs=1e-12)
    assert _apply(cage, (0, 0, 0)) == pytest.approx((50.0 + ear_y, 0.0, 13.75))
    # The camera looks forward and UP by the printed tilt, upright, its left on world +y.
    optical = _column(cam, 0)
    assert optical == pytest.approx(
        (math.cos(math.radians(tilt)), 0.0, math.sin(math.radians(tilt))), abs=1e-12)
    assert _column(cam, 2)[2] > 0 and _column(cam, 1) == pytest.approx((0.0, 1.0, 0.0),
                                                                       abs=1e-12)
    # Its back face (20 mm behind the front face) is still ahead of the side-screw axis.
    assert _apply(cam, (10 - 20, 0, 0))[0] > 50.0


def test_ear_spacing_must_be_the_plates_outer_spacing():
    """The cage's old reading of mount_width (the 19 mm bay) misses the second plate by
    the two plate thicknesses; a 20 mm bay needs ears 25 mm apart."""
    report, _ = _ear_chain(30, mount_width=19.0)
    assert not report.ok
    miss = next(m for m in report.mates if not m.ok)
    assert miss.origin_mm == pytest.approx(5.0)
    frame = {**FRAME, "source": {**FRAME["source"], "parameters": {"camera_bay_width_mm": 20}}}
    cage, _ = _ear_cage(30, mount_width=25.0)
    doc = _assembly(
        [frame, cage, CAMERA],
        [_mate("m1", "frame.camera_plate_left_outer", "cage.ear_left", angle_deg=0),
         _mate("m2", "frame.camera_plate_right_outer", "cage.ear_right", angle_deg=0),
         _mate("m3", "cage.cradle_floor", "camera.front_face", rotation_index=0)])
    assert validate_assembly(doc, _resolver()).ok


def test_an_ear_does_not_mate_a_plate_inner_face():
    cage, _ = _ear_cage(30)
    doc = _assembly([FRAME, cage],
                    [_mate("m1", "frame.camera_plate_left", "cage.ear_left", angle_deg=0)])
    report = validate_assembly(doc, _resolver())
    assert not report.ok
    assert {f.code for f in report.errors} >= {"size_key"}
