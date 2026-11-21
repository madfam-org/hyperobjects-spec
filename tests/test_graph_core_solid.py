"""The solid pack moved behind the core without changing a byte of any commons graph.

Every `.graph.json` in the solid commons (fifteen, copied byte-identically under
tests/fixtures; see tests/fixtures/graph-core/NOTICE.md) is validated by the core with
zero problems, and the program the core produces is byte-identical to the vendored engine
called directly AND to the digest pinned at this engine lock. The same check runs against a
live commons checkout with `scripts/qa/check_graph_core_solid.py --commons <path>`.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "check_graph_core_solid", ROOT / "scripts" / "qa" / "check_graph_core_solid.py"
)
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)

GRAPHS = check.graphs_under(check.FIXTURE_ROOTS)
GOLDEN = json.loads(check.GOLDEN.read_text(encoding="utf-8"))


def test_all_fifteen_commons_graphs_are_here():
    assert len(GRAPHS) == 15
    assert set(GOLDEN["programs"]) == {f"{g.parent.name}/{g.name}" for g in GRAPHS}


def test_the_golden_was_pinned_at_this_engine():
    lock = json.loads((ROOT / "src/y4d_spec/graph/graph.lock.json").read_text())
    assert GOLDEN["engine_sha256"] == lock["hashes"]["graph_engine.py"], (
        "the engine was re-vendored: run scripts/qa/check_graph_core_solid.py "
        "--update-golden and review which graphs' emission moved"
    )


@pytest.mark.parametrize("graph", GRAPHS, ids=lambda g: g.parent.name)
def test_byte_identical_through_the_core(graph):
    key, digest, problems = check.judge(graph)
    assert problems == []
    assert digest == GOLDEN["programs"][key]
