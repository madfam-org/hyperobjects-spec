"""The docs must not contradict the code.

Every count block in README.md is already generated (`refresh_reader_counts.py
--check` in CI), which is exactly why the numbers were right and the *prose* was
wrong: the parts nobody generates are the parts that drift. On 2026-09-06 an audit
of the docs against `main` found four such drifts, each invisible to every existing
gate and each one that would send a cartridge author the wrong way:

  * README pinned OpenSCAD `2026.02.01` in two places after #18 moved the contract to
    `2026.02.13` — a reader provisioning from the README builds a machine that cannot
    render the commons' BOSL2 pin, and gets an EMPTY STL rather than an error.
  * README's "Scope" and `rules.py`'s docstring both still said cross-kernel parity
    "stays in the platforms" after #19 brought it here, so the one gate a dual-engine
    cartridge most needs read as somebody else's job.
  * The `project-manifest` schema said `constraints[]` is evaluated by `expr-eval`,
    which the Studio dropped on 2026-05-14 for `safeFormula` — a dialect with no
    function calls, whose failures are swallowed rather than raised (that one is
    pinned by `test_schemas.py` instead, next to the schema it guards).
  * README described body counting as `mesh.split()` after #16 replaced it.

These assertions are deliberately about FACTS THE CODE OWNS — a constant, a flag, a
message — never about wording, so the prose stays free to be rewritten. A doc test
that pins sentences is a doc test people delete.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from y4d_spec import parity
from y4d_spec import render_environment as env

REPO = Path(__file__).resolve().parents[1]
README = (REPO / "README.md").read_text(encoding="utf-8")
AGENTS = (REPO / "AGENTS.md").read_text(encoding="utf-8")


def test_readme_quotes_the_pinned_openscad_version_and_no_other_as_the_pin():
    """The version is a contract three other repos read from here. A README that
    prints a different one hands a provisioning script the wrong answer."""
    assert f"`{env.OPENSCAD_VERSION}`" in README
    # The superseded pin may appear ONLY while explaining why it was superseded.
    for line in README.splitlines():
        if "2026.02.01" in line:
            assert "previous pin" in line, line


def test_readme_and_rules_do_not_call_parity_a_platform_only_lane():
    """It moved here in #19. Both documents said otherwise until 2026-09-06."""
    from y4d_spec import rules

    for text, where in ((README, "README.md"), (rules.__doc__ or "", "rules.py")):
        for line in text.splitlines():
            lowered = line.lower()
            if "stay in the platform" in lowered or "stays in the platform" in lowered:
                assert "parity" not in lowered, f"{where}: {line}"


def test_readme_states_the_parity_thresholds_the_code_uses():
    """Four numbers a cartridge author sizes a repair against."""
    assert f"`{parity.PARITY_TOLERANCE}mm`" in README or f"{parity.PARITY_TOLERANCE}mm" in README
    assert f"{parity.AABB_WARN_BAND}mm" in README
    assert f"{parity.PLACEMENT_NOTE_BAND}mm" in README
    assert f"{parity.HAUSDORFF_FLOOR}mm" in README


def test_readme_summary_line_shape_matches_the_cli(capsys):
    """The README shows a `parity=` clause; assert its field ORDER against a real run
    rather than against a copy of the format string."""
    from y4d_spec.cli import main

    main(["check", str(REPO / "tests" / "fixtures" / "y4d" / "thimble")])
    printed = capsys.readouterr().out.strip().splitlines()[-1]
    assert printed.startswith("y4d-spec check: cartridges=")
    for field in ("failures=", "notes=", "geometry=", "renders=", "presets=", "skipped="):
        assert field in printed, field
    # The parity clause is ABSENT without --parity: "parity=0/0" on a run that never
    # compared anything reads like a run that compared and found nothing wrong.
    assert "parity=" not in printed


@pytest.mark.parametrize("mode", parity.PLACEMENT_MODES)
def test_both_placement_modes_are_documented(mode):
    assert f'"{mode}"' in README
    assert f'"{mode}"' in AGENTS


def test_the_agent_guide_names_the_real_constraints_evaluator():
    """`AGENTS.md` is the file an LLM agent reads before touching a cartridge, so the
    expr-eval/safeFormula correction has to land there too, not only in the schema."""
    assert "safeFormula" in AGENTS
    assert "useConstraints" in AGENTS


def test_the_agent_guide_and_readme_agree_on_the_summary_identity():
    """N + K + E + J = M, with placement a SUBSET of N. An exemption that shrank the
    denominator would let a manifest make the bar look cleaner than it is."""
    for text in (README, AGENTS):
        assert "N + K + E + J = M" in text or "N+K+E+J = M" in text
