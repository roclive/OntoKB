"""Ontology loading and validation.

The YAML defines a controlled Schema.org profile with a single-parent subset
and union domain/range constraints. These are local, closed-world constraints;
they do not claim to implement all of Schema.org, OWL, or SHACL.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


class OntologyError(ValueError):
    pass


@dataclass
class RelationDef:
    name: str
    domain: str | list[str]
    range: str | list[str]
    symmetric: bool = False
    uri: str = ""
    description: str = ""


@dataclass
class Ontology:
    classes: dict[str, dict] = field(default_factory=dict)
    relations: dict[str, RelationDef] = field(default_factory=dict)
    version: int = 1
    class_aliases: dict[str, str] = field(default_factory=dict)
    relation_aliases: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> "Ontology":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        classes = data.get("classes") or {}
        onto = cls(version=data.get("version", 1),
                   class_aliases=data.get("class_aliases", {}),
                   relation_aliases=data.get("relation_aliases", {}))
        for name, spec in classes.items():
            spec = spec or {}
            parent = spec.get("parent")
            if parent is not None and parent not in classes:
                raise OntologyError(f"class {name!r}: unknown parent {parent!r}")
            onto.classes[name] = {
                **spec,
                "parent": parent,
                "properties": list(spec.get("properties") or []),
            }
        for name, spec in (data.get("relations") or {}).items():
            spec = spec or {}
            for side in ("domain", "range"):
                values = spec.get(side)
                values = values if isinstance(values, list) else [values]
                if not values or any(v not in onto.classes for v in values):
                    raise OntologyError(f"relation {name!r}: unknown {side} {spec.get(side)!r}")
            onto.relations[name] = RelationDef(
                name=name,
                domain=spec["domain"],
                range=spec["range"],
                symmetric=bool(spec.get("symmetric", False)),
                uri=spec.get("uri", ""),
                description=spec.get("description", ""),
            )
        for name in onto.classes:
            seen = set()
            cur = name
            while cur is not None:
                if cur in seen:
                    raise OntologyError(f"inheritance cycle at {cur!r}")
                seen.add(cur)
                cur = onto.classes[cur]["parent"]
        for aliases, targets in ((onto.class_aliases, onto.classes),
                                 (onto.relation_aliases, onto.relations)):
            for alias, target in aliases.items():
                if alias in targets or target not in targets:
                    raise OntologyError(f"invalid compatibility alias {alias!r}: {target!r}")
        return onto

    def canonical_class(self, name: str) -> str:
        return self.class_aliases.get(name, name)

    def canonical_relation(self, name: str) -> str:
        return self.relation_aliases.get(name, name)

    def has_class(self, name: str) -> bool:
        return self.canonical_class(name) in self.classes

    def is_subclass(self, cls_name: str, ancestor: str) -> bool:
        """True if cls_name equals ancestor or inherits from it."""
        seen = set()
        ancestor = self.canonical_class(ancestor)
        cur: str | None = self.canonical_class(cls_name)
        while cur is not None and cur not in seen:
            if cur == ancestor:
                return True
            seen.add(cur)
            cur = self.classes.get(cur, {}).get("parent")
        return False

    def validate_entity(self, entity_type: str) -> None:
        if not self.has_class(entity_type):
            raise OntologyError(f"unknown entity class: {entity_type!r}")

    def validate_triple(self, subject_type: str, predicate: str, object_type: str) -> None:
        rel = self.relations.get(self.canonical_relation(predicate))
        if rel is None:
            raise OntologyError(f"unknown relation: {predicate!r}")
        self.validate_entity(subject_type)
        self.validate_entity(object_type)
        domains = rel.domain if isinstance(rel.domain, list) else [rel.domain]
        ranges = rel.range if isinstance(rel.range, list) else [rel.range]
        if not any(self.is_subclass(subject_type, t) for t in domains):
            raise OntologyError(
                f"{predicate}: subject must be {rel.domain}, got {subject_type}"
            )
        if not any(self.is_subclass(object_type, t) for t in ranges):
            raise OntologyError(
                f"{predicate}: object must be {rel.range}, got {object_type}"
            )

    def prompt_summary(self) -> str:
        """Compact description of the ontology for the extraction prompt."""
        lines = ["Entity classes: " + ", ".join(sorted(self.classes))]
        for name, spec in self.classes.items():
            lines.append(f"  {name}: {spec.get('description', '')}")
        lines.append("Use the most specific supported class. Never create new classes. "
                     "Topic/Technology/Content are legacy names; do not emit them.")
        lines.append("Relations (domain -> range):")
        for rel in self.relations.values():
            sym = " (symmetric)" if rel.symmetric else ""
            lines.append(f"  {rel.name}: {rel.domain} -> {rel.range}{sym}. {rel.description}")
        return "\n".join(lines)
