"""The compiled kinematic model, a consumable export (ASM-1 §9,
`hyperobjects.assembly-kinematics` 1.0.0).

A viewer poses an assembly from `<name>.kinematics.json` and proves parity against
`<name>.poses.json`. These tests prove the export is complete: a consumer that reads
ONLY the model file (no resolver, no catalog, no geometry) and follows its stated
`placement` reproduces every string of every golden pose file.
"""

from __future__ import annotations

import importlib.util
import json
import math
from collections import deque
from pathlib import Path

import pytest

from hyperobjects_aas.resolver import bundled_standard_parts_dir
from y4d_spec.assembly import (
    CompositeResolver,
    PoseError,
    format_number,
    kinematic_model,
    validate_assembly,
)
from y4d_spec.assembly.kinematics import joint_matrix
from y4d_spec.assembly.transforms import IDENTITY, flip_rz, matmul, rigid_inverse
from y4d_spec.cli import main as cli_main

REPO = Path(__file__).resolve().parent.parent
KIN = REPO / "tests" / "fixtures" / "kinematics"


def _refresh_script():
    spec = importlib.util.spec_from_file_location(
        "refresh_pose_golden", REPO / "scripts" / "refresh_pose_golden.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _matrix(flat):
    return tuple(tuple(flat[4 * r:4 * r + 4]) for r in range(4))


def _values(model, inputs):
    """Joint values from the model alone: driven at input (else home), then followers."""
    values = {}
    for j in model["joints"]:
        if j["role"] == "driven":
            values[j["id"]] = float(inputs.get(j["id"], j["home"]))
    pending = [j for j in model["joints"] if j["role"] == "follower"]
    while pending:
        for j in list(pending):
            terms = j["follows"]["terms"]
            if all(t["joint"] in values for t in terms):
                values[j["id"]] = j["follows"]["offset"] + sum(
                    t["scale"] * values[t["joint"]] for t in terms)
                pending.remove(j)
    return values


def _place(model, values):
    """The model's `placement`, read from the file and nothing else."""
    passive = {j["id"] for j in model["joints"] if j["role"] == "passive"}
    types = {j["id"]: (j["type"], j["axis"]) for j in model["joints"]}
    placed = {model["root"]: IDENTITY}
    queue = deque([model["root"]])
    while queue:
        current = queue.popleft()
        for e in model["edges"]:
            ca, cb, jid = e["a"], e["b"], e["joint"]
            if current not in (ca, cb) or jid in passive:
                continue
            h_a, h_b = _matrix(e["h_a"]), _matrix(e["h_b"])
            m = flip_rz(math.radians(e["theta_deg"]))
            j = None if jid is None else joint_matrix(*types[jid], values.get(jid, 0.0))
            if current == ca and cb not in placed:
                chain = [placed[ca], h_a] + ([j] if j else []) + [m, rigid_inverse(h_b)]
                placed[cb] = matmul(*chain)
            elif current == cb and ca not in placed:
                chain = [placed[cb], h_b, m] + ([rigid_inverse(j)] if j else []) + [
                    rigid_inverse(h_a)]
                placed[ca] = matmul(*chain)
            else:
                continue
            queue.append(cb if current == ca else ca)
    return placed


def _guarded(golden):
    return set(golden["tie_guard"])


@pytest.mark.parametrize("index", range(3))
def test_the_model_alone_reproduces_every_golden_pose(index):
    script = _refresh_script()
    _document, golden_path, _res = script.targets()[index]
    golden = json.loads(golden_path.read_text("utf-8"))
    model = json.loads(script.kinematics_path(golden_path).read_text("utf-8"))
    assert model["format"] == "hyperobjects.assembly-kinematics"
    assert model["format_version"] == "1.0.0"
    assert model["assembly_digest"] == golden["assembly_digest"]
    guard = _guarded(golden)
    for p in golden["poses"]:
        values = _values(model, p["inputs"])
        assert {k: format_number(values[k]) for k in p["joints"]} == p["joints"], p["name"]
        placed = _place(model, values)
        assert set(placed) == set(p["transforms"])
        for cid, expected in p["transforms"].items():
            flat = [v for row in placed[cid] for v in row]
            for i, (value, text) in enumerate(zip(flat, expected, strict=True)):
                if f"{p['name']}/{cid}/{i}" in guard:
                    assert abs(value - float(text)) <= 1e-6
                else:
                    assert format_number(value) == text, f"{p['name']}/{cid}/{i}"


def test_the_kinematic_model_files_are_current():
    script = _refresh_script()
    for document, golden, res in script.targets():
        _poses, model = script.build_all(document, res)
        path = script.kinematics_path(golden)
        assert path.is_file(), f"{path} is missing: run scripts/refresh_pose_golden.py"
        assert model == path.read_text("utf-8"), (
            f"{path.name} moved: run scripts/refresh_pose_golden.py and review the diff")


def _gantry():
    doc = json.loads((KIN / "kinematic-gantry.assembly.json").read_text("utf-8"))
    res = CompositeResolver.for_directories(
        standard_parts=[bundled_standard_parts_dir(), KIN / "standard-parts"])
    return doc, validate_assembly(doc, res, pose_samples=0)


def test_the_model_states_roles_bindings_and_geometry():
    doc, report = _gantry()
    model = kinematic_model(doc, report)
    roles = {j["id"]: j["role"] for j in model["joints"]}
    assert roles["gantry_y"] == "driven" and roles["motor_rotation"] == "follower"
    assert "passive" in roles.values()
    assert [c["id"] for c in model["components"]] == [c["id"] for c in doc["components"]]
    assert len(model["edges"]) == len(report.kinematics.edges)
    assert all(len(e["h_a"]) == 16 and len(e["h_b"]) == 16 for e in model["edges"])
    # every number is a plain JSON number: the text has no NaN, no Infinity
    text = json.dumps(model, allow_nan=False)
    assert "NaN" not in text
    kinds = {(c["geometry"] or {}).get("kind") for c in model["components"]}
    assert kinds <= {"envelope", "cartridge", None}


def test_no_model_for_an_assembly_that_does_not_pass():
    doc, _report = _gantry()
    broken = json.loads(json.dumps(doc))
    broken["mates"][0]["a"]["interface"] = "no-such-interface"
    res = CompositeResolver.for_directories(
        standard_parts=[bundled_standard_parts_dir(), KIN / "standard-parts"])
    report = validate_assembly(broken, res, pose_samples=0)
    assert not report.ok
    with pytest.raises(PoseError):
        kinematic_model(broken, report)


def test_the_cli_writes_the_model(tmp_path, capsys):
    out = tmp_path / "gantry.kinematics.json"
    code = cli_main(["assembly", "kinematics", str(KIN / "kinematic-gantry.assembly.json"),
                     "--standard-parts", str(bundled_standard_parts_dir()),
                     "--standard-parts", str(KIN / "standard-parts"), "--out", str(out)])
    assert code == 0, capsys.readouterr().out
    assert out.read_text("utf-8") == (KIN / "kinematic-gantry.kinematics.json").read_text(
        "utf-8")
