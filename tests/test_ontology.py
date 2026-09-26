from pathlib import Path

import pytest

from ontokb.ontology import Ontology, OntologyError

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def onto():
    return Ontology.load(ROOT / "ontology" / "core.yaml")


def test_loads_classes_and_relations(onto):
    assert "DefinedTerm" in onto.classes
    assert "Topic" not in onto.classes
    assert onto.canonical_class("Topic") == "DefinedTerm"
    assert "mentions" in onto.relations
    assert onto.relations["contradicts"].symmetric


def test_inheritance(onto):
    assert onto.is_subclass("Person", "Thing")
    assert not onto.is_subclass("Thing", "Person")


def test_valid_triple(onto):
    onto.validate_triple("Content", "mentions", "Technology")  # range is Thing
    onto.validate_triple("Organization", "develops", "Technology")
    onto.validate_triple("Person", "doesNotParticipateIn", "Event")


def test_invalid_predicate(onto):
    with pytest.raises(OntologyError):
        onto.validate_triple("Content", "eats", "Topic")


def test_domain_violation(onto):
    with pytest.raises(OntologyError):
        onto.validate_triple("Person", "develops", "Technology")


def test_unknown_class(onto):
    with pytest.raises(OntologyError):
        onto.validate_entity("Spaceship")
