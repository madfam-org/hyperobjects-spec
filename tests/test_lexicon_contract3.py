"""Term contract 3 (SEM-1 §4): exact_match / close_match and the derived concept IRI.

Contract 3 is additive over 2, so every shipped term stays valid unchanged; what these
tests pin is the new surface — the identifier forms the schema accepts, the declaration a
contract-3 field requires, and an IRI that is derived from the id and never stored.
"""

import copy

import pytest

from hyperobjects_lexicon import CONCEPT_NAMESPACE, CONTRACT_VERSION, concept_iri, load_lexicon
from hyperobjects_lexicon.lexicon import check_term
from hyperobjects_schemas import load as load_schema


@pytest.fixture(scope="module")
def lexicon():
    return load_lexicon()


@pytest.fixture
def a_term(lexicon):
    term = copy.deepcopy(lexicon["bolt-pattern"])
    term["spec_version"] = 3
    return term


def test_the_contract_marker_is_at_least_three():
    """Contract 3 introduced these fields; contract 4 (the sheet commons) is additive over
    it, so the marker only moves up and the schema's maximum always equals it."""
    assert CONTRACT_VERSION >= 3
    assert load_schema("lexicon-term")["properties"]["spec_version"]["maximum"] == CONTRACT_VERSION


def test_every_shipped_term_is_still_valid(lexicon):
    for term_id, doc in lexicon.items():
        assert not check_term(doc), term_id


def test_no_term_stores_its_own_iri():
    """The IRI is derived; a stored copy is a second spelling of the id that can drift."""
    props = load_schema("lexicon-term")["properties"]
    assert "iri" not in props and "concept_iri" not in props


@pytest.mark.parametrize(
    "identifier",
    [
        "https://admin-shell.io/idta/SubmodelTemplate/DigitalNameplate/3/0",
        "http://emmo.info/emmo#Polymer",
        "urn:iso:std:iso:52900",
        "0173-1#02-AAO677#002",
    ],
)
def test_an_external_identifier_is_accepted(a_term, identifier):
    a_term["exact_match"] = [identifier]
    assert not check_term(a_term)


@pytest.mark.parametrize(
    "identifier",
    ["bolt pattern", "0173-1#02-AAO677", "www.example.org/x", "ftp://has space"],
)
def test_a_malformed_identifier_is_refused(a_term, identifier):
    a_term["close_match"] = [identifier]
    assert check_term(a_term)


def test_a_contract_3_field_needs_a_contract_3_declaration(a_term):
    a_term["exact_match"] = ["http://emmo.info/emmo#Polymer"]
    a_term["spec_version"] = 2
    assert any("spec_version 3" in p for p in check_term(a_term))


def test_an_identifier_cannot_be_both_exact_and_close(a_term):
    a_term["exact_match"] = ["http://emmo.info/emmo#Polymer"]
    a_term["close_match"] = ["http://emmo.info/emmo#Polymer"]
    assert any("both exact_match and close_match" in p for p in check_term(a_term))


def test_concept_iri_is_derived_from_the_id(lexicon):
    assert concept_iri("bolt-pattern") == f"{CONCEPT_NAMESPACE}bolt-pattern"
    assert CONCEPT_NAMESPACE == "https://id.madfam.io/concept/"
    for term_id in lexicon:
        assert concept_iri(term_id).endswith(f"/concept/{term_id}")


@pytest.mark.parametrize("bad", ["", "a", "Bolt-Pattern", "bolt_pattern", "bolt/pattern", None])
def test_concept_iri_refuses_a_non_term_id(bad):
    with pytest.raises(ValueError):
        concept_iri(bad)
