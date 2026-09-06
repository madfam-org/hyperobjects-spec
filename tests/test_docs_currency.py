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


def test_docs_say_the_graph_transpiler_is_vendored_and_must_not_be_edited():
    """The single most damaging thing an agent can do in this package is "fix" the
    vendored engine — a lint nit, a stray reformat — because the byte-identity IS the
    mechanism and the repair is invisible until a hash guard goes red with no
    explanation. So all three agent-facing documents must carry the rule, and the rule
    must name the guard that enforces it."""
    for text, where in ((README, "README.md"), (AGENTS, "AGENTS.md")):
        lowered = text.lower()
        assert "vendored" in lowered, where
        assert "check_graph_sync.py" in text, where
        assert "byte-identical" in lowered, where


def test_agents_and_llms_name_the_canonical_source_of_the_vendored_engine():
    """A red guard sends the reader somewhere. Every document that mentions the copy
    must say where the original lives, or the instruction is unactionable."""
    llms = (REPO / "llms.txt").read_text(encoding="utf-8")
    llms_full = (REPO / "llms-full.txt").read_text(encoding="utf-8")
    for text, where in ((AGENTS, "AGENTS.md"), (llms, "llms.txt"),
                        (llms_full, "llms-full.txt")):
        assert "graph_engine.py" in text, where
        assert "VENDORED.md" in text, where


def test_docs_do_not_tell_anyone_to_bump_the_spec_pin_while_re_vendoring():
    """Moving the consuming pins is the coordinator's deliberate step, after the
    re-vendor lands. A doc that folds it into the re-vendor recipe would have every
    engine change ship a fleet-wide pin move nobody reviewed."""
    from pathlib import Path as _P

    vendored = (REPO / "src" / "y4d_spec" / "graph" / "VENDORED.md").read_text(
        encoding="utf-8"
    )
    assert "not** part of a re-vendoring PR" in vendored or \
        "not part of a re-vendoring PR" in vendored
    assert "Do not bump" in AGENTS or "do not bump" in AGENTS.lower()
    assert _P(REPO / "src" / "y4d_spec" / "graph" / "graph.lock.json").is_file()


def test_readme_states_the_graph_engine_label_the_code_emits():
    """A render line's engine tag is a fact the code owns: `render_part_graph` sets
    `check.engine = "graph"` and `mode_sources` labels the pair the same. A README
    showing `cadquery` for a graph render would send an author looking in the wrong
    place for the source of a failing mesh."""
    from y4d_spec.geometry import mode_sources

    assert mode_sources({"id": "m", "scad_file": "x.graph.json"})[0][0] == "graph"
    assert ", graph): ok" in README
