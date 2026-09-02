"""Tests for article frontmatter — the encyclopaedia layer's checkable half (G2).

The shipped exemplar is a heritage article on purpose: heritage entries are the set that
exercises every rule the contract has, which is why RFC 0039 §8 names them as G2's
exemplar set. The failure-class half then shows each rule firing on its own.
"""

import copy
import json

import pytest

from hyperobjects_lexicon import bundled_catalog_slugs, load_lexicon
from hyperobjects_lexicon.articles import (
    article_status,
    check_article,
    check_articles,
    language_coverage,
    load_article,
)

EXEMPLAR = "examples/chaleco-charro.article.json"


@pytest.fixture(scope="module")
def exemplar():
    return load_article(EXEMPLAR)


@pytest.fixture
def article(exemplar):
    return copy.deepcopy(exemplar)


# --------------------------------------------------------------------- the exemplar


def test_the_exemplar_conforms(exemplar):
    result = check_articles({EXEMPLAR: exemplar}, catalog=bundled_catalog_slugs())
    assert result.ok, "\n".join(result.problems)
    assert result.catalog_checked


def test_the_exemplar_points_at_the_readme_and_carries_no_article_body(exemplar):
    """RFC 0039 §2: the README is single-source, and a body duplicated here would be a
    second corpus to keep in step."""
    assert exemplar["article"]["path"].endswith("docs/README.md")
    assert "body" not in exemplar
    assert "content" not in exemplar


def test_the_exemplar_pays_the_heritage_price(exemplar):
    """Two things, not one: the citation §7 asks for, and a statement of what the
    cartridge deliberately does not draw."""
    assert exemplar["heritage"] is True
    assert exemplar["sources"]
    assert exemplar["excludes"]
    assert exemplar["provenance"]["custodians"]


def test_the_exemplars_terms_all_resolve(exemplar):
    lexicon = load_lexicon()
    for term in exemplar["related"]["terms"]:
        assert term in lexicon, term


def test_the_exemplar_does_not_claim_an_editorial_review(exemplar):
    assert exemplar["review_status"]["state"] == "generated"


def test_status_reports_the_language_backfill_rather_than_failing_it(exemplar):
    """The lexicon is born quadrilingual because that is free at authoring time; the
    catalogs are not, and G-L is the backfill. A lane that failed en/es articles today
    would stop G2 until G-L finished."""
    docs = {EXEMPLAR: exemplar}
    assert check_articles(docs).ok
    coverage = language_coverage(docs)
    assert coverage["en"] == 1 and coverage["es"] == 1
    assert coverage["fr"] == 0 and coverage["pt"] == 0
    assert "fr=0" in article_status(docs)


# ------------------------------------------------------------------- failure classes


def test_validator_catches_an_uncited_heritage_claim(article):
    article.pop("sources")
    assert any("sources" in p for p in check_article(article))


def test_validator_catches_a_heritage_article_that_states_no_boundary(article):
    """A boundary a platform cannot read is a boundary a platform will cross."""
    article.pop("excludes")
    assert any("excludes" in p for p in check_article(article))


def test_a_non_heritage_article_needs_neither(article):
    """The bar is the price of the heritage flag, not a tax on every article: a bracket
    has no provenance to cite."""
    for field in ("heritage", "sources", "excludes", "provenance", "era"):
        article.pop(field, None)
    assert not check_article(article)


def test_validator_catches_a_dangling_term(article):
    article["related"]["terms"] = ["no-such-term"]
    problems = check_article(article, known_terms={"tape-edge"})
    assert any("no-such-term" in p for p in problems)


def test_validator_catches_an_unresolvable_object(article):
    problems = check_article(article, catalog={"fashion-cabinet/something-else"})
    assert any("chaleco-charro" in p for p in problems)


def test_validator_catches_an_article_path_that_escapes_the_repo(article):
    article["article"]["path"] = "../../etc/passwd.md"
    assert any("escapes the repository" in p for p in check_article(article))


def test_validator_catches_a_non_markdown_article(article):
    article["article"]["path"] = "projects/chaleco-charro/docs/README.txt"
    assert check_article(article)


def test_validator_catches_a_title_in_no_language(article):
    article["title"] = {}
    assert check_article(article)


def test_validator_catches_a_bad_object_slug(article):
    article["object"] = "chaleco-charro"
    assert check_article(article)


def test_validator_catches_an_unknown_field(article):
    article["provenence"] = "typo"
    assert check_article(article)


def test_two_articles_for_one_object_are_a_corpus_level_failure(article):
    """One object, one article, or the two will drift — and the README is single-source,
    so a second article is by definition a second reading of the same prose."""
    other = copy.deepcopy(article)
    result = check_articles({"a.json": article, "b.json": other})
    assert not result.ok
    assert any("already has an article" in p for p in result.problems)


# ------------------------------------------------------------------------------ CLI


@pytest.mark.parametrize("prog", ["fc-spec", "y4d-spec"])
def test_article_is_exposed_on_both_clis(prog, capsys):
    main = (
        __import__("fc_spec.cli", fromlist=["main"]).main
        if prog == "fc-spec"
        else __import__("y4d_spec.cli", fromlist=["main"]).main
    )
    assert main(["article", EXEMPLAR, "--catalog", "bundled"]) == 0
    out = capsys.readouterr().out
    assert f"{prog} article:" in out
    assert "objects=resolved" in out
    assert "article_status:" in out


def test_cli_scans_a_directory(capsys):
    from fc_spec.cli import main

    assert main(["article", "examples", "-v"]) == 0
    out = capsys.readouterr().out
    assert "fashion-cabinet/chaleco-charro [heritage]" in out


def test_cli_says_so_when_objects_were_not_resolved(capsys):
    from y4d_spec.cli import main

    assert main(["article", EXEMPLAR]) == 0
    assert "NOT resolved" in capsys.readouterr().out


def test_cli_refuses_a_directory_with_no_frontmatter(tmp_path, capsys):
    from fc_spec.cli import main

    assert main(["article", str(tmp_path)]) == 2
    assert "articles=0" in capsys.readouterr().out


def test_cli_fails_on_a_broken_article(tmp_path, capsys):
    path = tmp_path / "broken.article.json"
    path.write_text(json.dumps({"object": "fashion-cabinet/x"}), encoding="utf-8")
    from fc_spec.cli import main

    assert main(["article", str(tmp_path)]) == 1
    assert "FAIL" in capsys.readouterr().out
