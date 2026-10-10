"""The shipped-LICENSE body check (hyperobjects_licenses, note-first).

Fixtures are REAL files from solid-hyperobjects (tests/fixtures/licenses/README.md
names the commit each came from), plus the short notice already vendored with the
assembly golden. Anything synthetic here is derived from the vendored SPDX texts
themselves (re-wrapping, one documented variant at a time), never typed by hand.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import textwrap
from importlib import resources
from pathlib import Path

import pytest

from hyperobjects_licenses import (
    BODY_MATCH_FLOOR,
    CANONICAL_IDS,
    DOCUMENTED_VARIANTS,
    canonical_text,
    classify_license_file,
    classify_license_text,
    lock,
    normalize,
    summary_clause,
)
from hyperobjects_licenses.cli import collect_license_files, declared_for
from y4d_spec import check_cartridge, structure

HERE = Path(__file__).parent
LICENSES = HERE / "fixtures" / "licenses"
S_UNDER_W = LICENSES / "s-body-under-w-title" / "LICENSE"
W_PARAPHRASE = LICENSES / "w-paraphrase" / "LICENSE"
W_GITHUB = LICENSES / "w-full-github-variants" / "LICENSE"
# Byte-identical to solid-hyperobjects ab-drive/LICENSE (the 27 one-slash notices).
W_NOTICE = HERE / "fixtures" / "assembly-golden" / "commons" / "ab-drive" / "LICENSE"
THIMBLE = HERE / "fixtures" / "y4d" / "thimble"
W = "CERN-OHL-W-2.0"
S = "CERN-OHL-S-2.0"
P = "CERN-OHL-P-2.0"


# ── the vendored texts and their lock ────────────────────────────────────────
def test_vendored_texts_match_their_lock():
    """A hand-edit of a canonical text would quietly redefine "canonical"."""
    data = lock()
    assert re.fullmatch(r"[0-9a-f]{40}", data["commit"])
    assert data["source"] == "https://github.com/spdx/license-list-data"
    texts = resources.files("hyperobjects_licenses").joinpath("texts")
    on_disk = sorted(p.name for p in texts.iterdir() if p.name.endswith(".txt"))
    assert on_disk == sorted(f"{sid}.txt" for sid in data["files"])
    for sid, entry in data["files"].items():
        raw = texts.joinpath(f"{sid}.txt").read_bytes()
        assert hashlib.sha256(raw).hexdigest() == entry["sha256"], sid
        assert len(raw) == entry["bytes"], sid
        assert entry["path"] == f"text/{sid}.txt"
        blob = hashlib.sha1(b"blob %d\0" % len(raw) + raw).hexdigest()
        assert blob == entry["git_blob_sha1"], sid


def test_the_vendored_set_covers_the_commons_declarations():
    """CERN-OHL-W-2.0 is every cartridge's commons_license; S and P are the texts a W
    file is most often confused with; the rest are the upstream licences solid
    manifests cite in attribution (Apache-2.0, CC-BY-SA-4.0, CC-BY-NC-ND-4.0, GPL-2.0)."""
    for sid in (W, S, P, "Apache-2.0", "CC-BY-SA-4.0", "CC-BY-NC-ND-4.0", "GPL-2.0-only"):
        assert sid in CANONICAL_IDS


def test_vendored_md_is_shipped_with_the_package():
    assert resources.files("hyperobjects_licenses").joinpath("VENDORED.md").is_file()


# ── canonical ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("sid", CANONICAL_IDS)
def test_every_vendored_text_is_canonical_for_itself(sid):
    v = classify_license_text(canonical_text(sid), sid)
    assert (v.kind, v.license, v.findings, v.variants) == ("canonical", sid, (), ())
    assert v.clean


def test_rewrapping_crlf_bom_and_blank_lines_are_not_differences():
    text = canonical_text(W)
    wrapped = "\n\n".join(
        textwrap.fill(p, 55, break_on_hyphens=False, break_long_words=False)
        for p in text.split("\n\n")
    )
    mangled = "﻿\r\n\r\n" + wrapped.replace("\n", "\r\n") + "\r\n\r\n\r\n"
    v = classify_license_text(mangled, W)
    assert v.kind == "canonical" and v.clean


def test_nfc_normalisation():
    # A decomposed character equals its composed form after NFC.
    assert normalize("Licencé") == normalize("Licencé")


# ── the documented variants: explicit, small, each tested ────────────────────
def test_the_variant_list_is_small_and_each_entry_is_anchored():
    assert len(DOCUMENTED_VARIANTS) == 3
    w_norm = normalize(canonical_text(W))
    for v in DOCUMENTED_VARIANTS:
        assert w_norm.count(v.spdx) == 1, v.spdx  # one place, not a global respelling
        assert v.alternative not in w_norm, v.alternative
        assert v.why


@pytest.mark.parametrize("variant", DOCUMENTED_VARIANTS, ids=lambda v: v.alternative)
def test_each_documented_variant_alone_is_tolerated(variant):
    text = normalize(canonical_text(W)).replace(variant.spdx, variant.alternative)
    v = classify_license_text(text, W)
    assert v.kind == "canonical" and v.clean
    assert v.variants == (variant.why,)


def test_an_undocumented_respelling_is_a_mismatch_that_names_the_spot():
    """"licence" -> "license" is tolerated in ONE documented place, not anywhere."""
    text = normalize(canonical_text(W)).replace("under this Licence", "under this License", 1)
    v = classify_license_text(text, W)
    assert v.kind == "mismatch" and v.license == W
    assert v.similarity >= BODY_MATCH_FLOOR
    (msg,) = v.findings
    assert "not the canonical text" in msg and "SPDX 'Licence." in msg
    assert "vs shipped 'License." in msg


# ── the real defective files ─────────────────────────────────────────────────
def test_github_rendering_of_w_is_canonical_with_three_variants():
    """solid custom-msh/LICENSE: the full W text as GitHub's catalogue renders it."""
    v = classify_license_file(W_GITHUB, W)
    assert v.kind == "canonical" and v.license == W and v.clean
    assert len(v.variants) == 3


def test_s_body_under_w_title_is_reported_as_the_s_body():
    """solid-hyperobjects' root LICENSE before #177 — the defect this check exists for.
    The title check passed it; the body check names the body."""
    v = classify_license_file(S_UNDER_W, W)
    assert v.kind == "mismatch" and v.license == S
    assert v.similarity >= BODY_MATCH_FLOOR
    (msg,) = v.findings
    assert f"body is {S}" in msg and f"not the declared {W}" in msg
    assert "'Strongly' vs shipped 'Weakly'" in msg
    # and the title-line rule really does pass it, which is why this module exists
    assert structure._license_matches(W, S_UNDER_W.read_text(encoding="utf-8")[:4000])


def test_the_paraphrase_is_not_a_canonical_text_and_names_the_nearest():
    """The 184-line reworded W (10 solid cartridges, soft's root LICENSE)."""
    v = classify_license_file(W_PARAPHRASE, W)
    assert v.kind == "mismatch" and v.license == W
    assert v.similarity < BODY_MATCH_FLOOR
    (msg,) = v.findings
    assert "is not a canonical licence text" in msg and f"closest canonical text is {W}" in msg


def test_the_one_slash_notice_is_a_notice_with_a_url_finding():
    v = classify_license_file(W_NOTICE, W)
    assert v.kind == "notice" and v.license == W
    (msg,) = v.findings
    assert "malformed URL 'https:/cern.ch/cern-ohl'" in msg
    assert not v.clean


def test_the_same_notice_with_a_well_formed_url_is_clean():
    text = W_NOTICE.read_text(encoding="utf-8").replace("https:/cern", "https://cern")
    v = classify_license_text(text, W)
    assert v.kind == "notice" and v.clean


def test_a_notice_without_a_url_is_still_a_notice_and_says_so():
    text = W_NOTICE.read_text(encoding="utf-8").replace(" (https:/cern.ch/cern-ohl)", "")
    v = classify_license_text(text, W)
    assert v.kind == "notice"
    assert any("names no URL" in f for f in v.findings)


def test_a_notice_for_another_variant_is_a_mismatch():
    v = classify_license_file(W_NOTICE, S)
    assert v.kind == "mismatch" and v.license == W
    assert f"short {W} notice, not one for the declared {S}" in v.findings[0]


def test_a_notice_whose_title_and_body_disagree_is_not_a_notice():
    text = W_NOTICE.read_text(encoding="utf-8").replace("Weakly Reciprocal", "Strongly Reciprocal")
    v = classify_license_text(text, W)
    assert v.kind == "mismatch"


def test_a_title_line_alone_is_not_a_notice():
    v = classify_license_text("CERN Open Hardware Licence Version 2 - Weakly Reciprocal\n", W)
    assert v.kind == "mismatch"


# ── declared-licence handling ────────────────────────────────────────────────
def test_canonical_text_of_another_licence_is_a_mismatch():
    v = classify_license_text(canonical_text(W), S)
    assert v.kind == "mismatch" and v.license == W and v.similarity == 1.0
    assert f"body is the canonical {W} text, not the declared {S}" in v.findings[0]


def test_an_undeclared_file_is_judged_against_every_vendored_text():
    assert classify_license_text(canonical_text(P)).kind == "canonical"
    assert classify_license_file(S_UNDER_W).license == S


def test_a_declared_licence_with_no_vendored_text_is_unjudged_not_passed():
    v = classify_license_text("MIT License\n\nPermission is hereby granted ...", "MIT")
    assert v.kind == "unjudged" and not v.clean
    assert "not judged" in v.findings[0]


def test_deprecated_gpl_id_resolves_to_its_only_text():
    assert classify_license_text(canonical_text("GPL-2.0-only"), "GPL-2.0").kind == "canonical"


def test_html_is_called_html():
    v = classify_license_text("<!DOCTYPE html><html>404 Not Found</html>", W)
    assert v.kind == "mismatch" and "is HTML" in v.findings[0]


def test_summary_clause_accounts_for_every_file():
    verdicts = [
        classify_license_file(W_GITHUB, W),
        classify_license_file(W_NOTICE, W),
        classify_license_file(S_UNDER_W, W),
        classify_license_file(W_PARAPHRASE, W),
        classify_license_text("x", "MIT"),
    ]
    assert summary_clause(verdicts) == (
        "licence-body: files=5 canonical=1 notices=1 mismatched=2 unjudged=1"
    )
    assert summary_clause([]) == (
        "licence-body: files=0 canonical=0 notices=0 mismatched=0 unjudged=0"
    )


# ── wiring: y4d-spec check (note-first) ──────────────────────────────────────
def _cartridge_with(tmp_path: Path, license_file: Path) -> Path:
    cart = tmp_path / "thimble"
    shutil.copytree(THIMBLE, cart)
    shutil.copy(license_file, cart / "LICENSE")
    return cart


def test_a_mismatched_body_is_a_note_and_never_a_failure(tmp_path):
    cart = _cartridge_with(tmp_path, S_UNDER_W)
    result = check_cartridge(cart)
    assert result.ok, result.problems
    assert any(n.startswith("LICENSE: licence body — body is CERN-OHL-S-2.0") for n in result.notes)
    assert [v.kind for v in result.license_bodies] == ["mismatch"]


def test_a_canonical_body_adds_no_note(tmp_path):
    cart = _cartridge_with(tmp_path, W_GITHUB)
    result = check_cartridge(cart)
    assert result.ok and not any("licence body" in n for n in result.notes)
    assert [v.kind for v in result.license_bodies] == ["canonical"]


def test_shipped_license_bodies_reads_the_declared_commons_license(tmp_path):
    cart = _cartridge_with(tmp_path, W_NOTICE)
    doc = json.loads((cart / "project.json").read_text(encoding="utf-8"))
    assert doc["hyperobject"]["commons_license"] == W
    (v,) = structure.shipped_license_bodies(cart, doc)
    assert (v.path, v.declared, v.kind) == ("LICENSE", W, "notice")
    assert structure.shipped_license_bodies(THIMBLE, doc) == []


def test_check_summary_appends_the_licence_body_clause(tmp_path, capsys):
    from y4d_spec.cli import main

    cart = _cartridge_with(tmp_path, W_PARAPHRASE)
    assert main(["check", str(cart), str(THIMBLE)]) == 0
    last = capsys.readouterr().out.strip().splitlines()[-1]
    assert last.endswith("licence-body: files=1 canonical=0 notices=0 mismatched=1 unjudged=0")


def test_check_summary_has_no_clause_when_no_licence_file_ships(capsys):
    from y4d_spec.cli import main

    assert main(["check", str(THIMBLE)]) == 0
    assert "licence-body:" not in capsys.readouterr().out


# ── wiring: the license-body subcommand on both tools ────────────────────────
@pytest.mark.parametrize("tool", ["y4d", "fc"])
def test_license_body_command_is_note_first(tool, capsys):
    from fc_spec.cli import main as fc_main
    from y4d_spec.cli import main as y4d_main

    main, prog = (y4d_main, "y4d-spec") if tool == "y4d" else (fc_main, "fc-spec")
    assert main(["license-body", str(LICENSES), "--declared", W]) == 0
    out = capsys.readouterr().out.rstrip().splitlines()
    assert out[-1] == (
        f"{prog} licence-body: files=3 canonical=1 notices=0 mismatched=2 unjudged=0"
    )
    assert sum(line.startswith("  note ") for line in out) == 2


def test_license_body_command_refuses_to_check_nothing(tmp_path, capsys):
    from y4d_spec.cli import main

    assert main(["license-body", str(tmp_path / "missing")]) == 2
    assert main(["license-body", str(tmp_path)]) == 2
    assert "no LICENSE*/COPYING* file found" in capsys.readouterr().out


def test_collect_and_declared_for(tmp_path):
    cart = _cartridge_with(tmp_path, W_NOTICE)
    (tmp_path / "LICENSE").write_text(canonical_text(W), encoding="utf-8")
    (tmp_path / "node_modules" / "x").mkdir(parents=True)
    (tmp_path / "node_modules" / "x" / "LICENSE").write_text("MIT", encoding="utf-8")
    files = collect_license_files([tmp_path])
    assert files == [tmp_path / "LICENSE", cart / "LICENSE"]
    assert declared_for(cart / "LICENSE", None) == W
    assert declared_for(tmp_path / "LICENSE", "CERN-OHL-S-2.0") == "CERN-OHL-S-2.0"
