"""Forward-chaining rule engine over flat dict facts.

Rules are declared in YAML (see rules/default.yaml). Semantics:

- `when.all` is a list of patterns. The FIRST pattern is the trigger: the rule
  fires once per fact matching it, and "$field" placeholders in actions are
  substituted from that fact. Remaining patterns are existence guards — each
  must match at least one fact in the working set.
- Every fired action is returned AND asserted back into the working set as a
  derived fact {kind: "action", action: <name>, **params}, so rules can chain.
- Iteration stops at fixpoint or after max_iterations rounds.

Pure deterministic code — no LLM calls — so it is fully unit-testable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_OPS = {
    "gte": lambda v, x: v is not None and v >= x,
    "lte": lambda v, x: v is not None and v <= x,
    "gt": lambda v, x: v is not None and v > x,
    "lt": lambda v, x: v is not None and v < x,
    "eq": lambda v, x: v == x,
    "ne": lambda v, x: v != x,
    "in": lambda v, x: v in x,
    "contains": lambda v, x: isinstance(v, (str, list, dict)) and x in v,
}


def _match_field(value: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        return all(_OPS[op](value, arg) for op, arg in expected.items() if op in _OPS)
    return value == expected


def match_pattern(fact: dict, pattern: dict) -> bool:
    return all(_match_field(fact.get(k), v) for k, v in pattern.items())


def _substitute(value: Any, fact: dict) -> Any:
    if isinstance(value, str) and value.startswith("$"):
        return fact.get(value[1:])
    return value


@dataclass
class Rule:
    name: str
    patterns: list[dict]
    actions: list[dict]
    comment: str = ""


@dataclass
class Action:
    action: str
    params: dict
    rule: str

    def as_fact(self) -> dict:
        return {"kind": "action", "action": self.action, "rule": self.rule, **self.params}


@dataclass
class RuleEngine:
    rules: list[Rule]
    max_iterations: int = 10
    fired: list[Action] = field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path) -> "RuleEngine":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        rules = []
        for spec in data.get("rules") or []:
            when = spec.get("when") or {}
            patterns = when.get("all") or []
            if not patterns:
                raise ValueError(f"rule {spec.get('name')!r}: empty when.all")
            actions = spec.get("then") or []
            rules.append(Rule(
                name=spec["name"],
                patterns=patterns,
                actions=actions,
                comment=spec.get("comment", ""),
            ))
        return cls(rules=rules, max_iterations=int(data.get("max_iterations", 10)))

    def run(self, facts: list[dict]) -> list[Action]:
        """Run to fixpoint. Returns all actions fired, in firing order."""
        working = list(facts)
        seen_keys: set[str] = set()
        self.fired = []
        for _ in range(self.max_iterations):
            new_facts: list[dict] = []
            for rule in self.rules:
                trigger, *guards = rule.patterns
                for fact in working:
                    if not match_pattern(fact, trigger):
                        continue
                    if not all(any(match_pattern(f, g) for f in working) for g in guards):
                        continue
                    for action_spec in rule.actions:
                        params = {
                            k: _substitute(v, fact)
                            for k, v in (action_spec.get("with") or {}).items()
                        }
                        action = Action(action=action_spec["action"], params=params, rule=rule.name)
                        key = json.dumps(
                            {"a": action.action, "p": params}, sort_keys=True, ensure_ascii=False
                        )
                        if key in seen_keys:
                            continue
                        seen_keys.add(key)
                        self.fired.append(action)
                        new_facts.append(action.as_fact())
            if not new_facts:
                break
            working.extend(new_facts)
        return self.fired
