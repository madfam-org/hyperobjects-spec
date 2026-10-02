"""``y4d-spec aas`` and ``fc-spec aas`` exactly as a third party would call them."""

from __future__ import annotations

import json

from aas_support import FC_MATERIAL, SEM1_SOFT, SEM1_SOLID, THIMBLE, Y4D_MATERIAL
from fc_spec.cli import main as fc_main
from y4d_spec.cli import main as y4d_main


def test_y4d_build_writes_canonical_json_and_reports(tmp_path, capsys):
    out = tmp_path / "env.json"
    assert y4d_main(["aas", "build", str(SEM1_SOLID), "--commons", "solid", "--out", str(out)]) == 0
    text = capsys.readouterr().out
    assert "BillOfMaterials=idta" in text and "Nameplate=madfam" in text
    assert "inputs=1 built=1 submodels=6 idta_claims=1 check_errors=0 read_errors=0" in text
    data = out.read_bytes()
    env = json.loads(data)
    assert data == json.dumps(env, sort_keys=True, separators=(",", ":"),
                              ensure_ascii=False).encode()
    again = tmp_path / "again.json"
    y4d_main(["aas", "build", str(SEM1_SOLID), "--out", str(again)])
    assert again.read_bytes() == data   # byte-identical across runs


def test_y4d_build_to_stdout_keeps_reports_on_stderr(capsys):
    assert y4d_main(["aas", "build", str(THIMBLE)]) == 0
    captured = capsys.readouterr()
    env = json.loads(captured.out)
    assert env["assetAdministrationShells"][0]["idShort"] == "thimble"
    assert "y4d-spec aas build: inputs=1 built=1" in captured.err


def test_build_many_needs_out_dir(tmp_path, capsys):
    assert y4d_main(["aas", "build", str(SEM1_SOLID), str(THIMBLE)]) == 2
    assert y4d_main(["aas", "build", str(SEM1_SOLID), str(THIMBLE),
                     "--out-dir", str(tmp_path)]) == 0
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "sem1-bracket.aas.json", "thimble.aas.json"]


def test_build_reports_a_missing_cartridge(tmp_path, capsys):
    assert y4d_main(["aas", "build", str(tmp_path / "nope"), "--out", str(tmp_path / "x")]) == 2
    assert "cannot build" in capsys.readouterr().out


def test_check_passes_a_built_environment_and_fails_a_broken_one(tmp_path, capsys):
    out = tmp_path / "env.json"
    y4d_main(["aas", "build", str(SEM1_SOLID), "--out", str(out)])
    capsys.readouterr()
    assert y4d_main(["aas", "check", str(out), "--basyx", "off"]) == 0
    assert "files=1 errors=0 warnings=0 read_errors=0 basyx=skipped" in capsys.readouterr().out
    env = json.loads(out.read_text(encoding="utf-8"))
    env["assetAdministrationShells"][0]["idShort"] = "9-bad"
    broken = tmp_path / "broken.json"
    broken.write_text(json.dumps(env), encoding="utf-8")
    assert y4d_main(["aas", "check", str(broken), "--basyx", "off"]) == 1
    (tmp_path / "junk.json").write_text("{", encoding="utf-8")
    assert y4d_main(["aas", "check", str(tmp_path / "junk.json")]) == 2


def test_fc_spec_defaults_to_the_soft_commons(tmp_path, capsys):
    out = tmp_path / "garment.json"
    assert fc_main(["aas", "build", str(SEM1_SOFT), "--out", str(out)]) == 0
    env = json.loads(out.read_text(encoding="utf-8"))
    assert env["assetAdministrationShells"][0]["id"].startswith(
        "https://id.madfam.io/aas/soft/sem1-garment/")
    assert fc_main(["aas", "check", str(out), "--basyx", "off"]) == 0


def test_build_material_for_both_card_shapes(tmp_path, capsys):
    assert fc_main(["aas", "build-material", str(Y4D_MATERIAL), str(FC_MATERIAL),
                    "--out-dir", str(tmp_path)]) == 0
    assert "inputs=2 built=2 submodels=2 idta_claims=2" in capsys.readouterr().out
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "bambu-tpu-95a.aas.json", "manta-cruda.aas.json"]
    bad = tmp_path / "bad.json"
    bad.write_text('{"neither": {}}', encoding="utf-8")
    assert y4d_main(["aas", "build-material", str(bad), "--out", str(tmp_path / "o.json")]) == 2
