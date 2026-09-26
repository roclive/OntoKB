from pathlib import Path

import pytest

from ontokb.rules import Rule, RuleEngine

ROOT = Path(__file__).resolve().parents[1]


def test_load_default_rules():
    engine = RuleEngine.load(ROOT / "rules" / "default.yaml")
    assert engine.max_iterations == 10
    assert any(r.name == "hot-topic-wiki" for r in engine.rules)


def test_operator_matching_and_substitution():
    engine = RuleEngine.load(ROOT / "rules" / "default.yaml")
    facts = [
        {"kind": "entity", "name": "AI agents", "type": "DefinedTerm", "degree": 7},
        {"kind": "entity", "name": "cold topic", "type": "DefinedTerm", "degree": 1},
    ]
    actions = engine.run(facts)
    wiki = [a for a in actions if a.action == "create_wiki_page"]
    assert len(wiki) == 1
    assert wiki[0].params == {"entity": "AI agents"}


def test_chaining_wiki_to_report():
    engine = RuleEngine.load(ROOT / "rules" / "default.yaml")
    facts = [{"kind": "entity", "name": "端侧 AI", "type": "DefinedTerm", "degree": 5}]
    actions = engine.run(facts)
    names = [(a.rule, a.action) for a in actions]
    assert ("hot-topic-wiki", "create_wiki_page") in names
    # second-round chained rule fires on the derived action fact
    assert ("wiki-into-report", "queue_report") in names


def test_dedup_no_double_fire():
    engine = RuleEngine.load(ROOT / "rules" / "default.yaml")
    facts = [{"kind": "entity", "name": "X", "type": "DefinedTerm", "degree": 9}]
    actions = engine.run(facts)
    keys = [(a.action, tuple(sorted(a.params.items()))) for a in actions]
    assert len(keys) == len(set(keys))


def test_max_iterations_bounds_runaway():
    # a -> b and b -> a with changing payloads would loop forever without the cap;
    # dedup makes identical actions stop, so craft rules that echo the round-trip.
    rules = [
        Rule(name="ping", patterns=[{"kind": "action", "action": "pong"}],
             actions=[{"action": "ping", "with": {"n": "$n"}}]),
        Rule(name="pong", patterns=[{"kind": "seed"}],
             actions=[{"action": "pong", "with": {"n": "1"}}]),
    ]
    engine = RuleEngine(rules=rules, max_iterations=3)
    actions = engine.run([{"kind": "seed"}])
    assert len(actions) <= 3


def test_guard_pattern_requires_existence():
    rules = [
        Rule(
            name="guarded",
            patterns=[{"kind": "entity", "type": "DefinedTerm"},
                      {"kind": "content", "relevance": {"gte": 0.5}}],
            actions=[{"action": "noop", "with": {"who": "$name"}}],
        )
    ]
    engine = RuleEngine(rules=rules)
    assert engine.run([{"kind": "entity", "type": "DefinedTerm", "name": "t"}]) == []
    fired = engine.run([
        {"kind": "entity", "type": "DefinedTerm", "name": "t"},
        {"kind": "content", "relevance": 0.8},
    ])
    assert [a.params for a in fired] == [{"who": "t"}]
