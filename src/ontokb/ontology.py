"""Ontology loading and validation.

The ontology is a YAML file defining entity classes (with single inheritance)
and typed relations with domain/range constraints. Extraction output must
validate here before it is written to the graph.
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
    domain: str
    range: str
    symmetric: bool = False


@dataclass
class Ontology:
    classes: dict[str, dict] = field(default_factory=dict)
    relations: dict[str, RelationDef] = field(default_factory=dict)
    version: int = 1

    @classmethod
    def load(cls, path: str | Path) -> "Ontology":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        classes = data.get("classes") or {}
        onto = cls(version=data.get("version", 1))
        for name, spec in classes.items():
            spec = spec or {}
            parent = spec.get("parent")
            if parent is not None and parent not in classes:
                raise OntologyError(f"class {name!r}: unknown parent {parent!r}")
            onto.classes[name] = {
                "parent": parent,
                "properties": list(spec.get("properties") or []),
            }
        for name, spec in (data.get("relations") or {}).items():
            spec = spec or {}
            for side in ("domain", "range"):
                if spec.get(side) not in onto.classes:
                    raise OntologyError(f"relation {name!r}: unknown {side} {spec.get(side)!r}")
            onto.relations[name] = RelationDef(
                name=name,
                domain=spec["domain"],
                range=spec["range"],
                symmetric=bool(spec.get("symmetric", False)),
            )
        return onto

    def has_class(self, name: str) -> bool:
        return name in self.classes

    def is_subclass(self, cls_name: str, ancestor: str) -> bool:
        """True if cls_name equals ancestor or inherits from it."""
        seen = set()
        cur: str | None = cls_name
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
        rel = self.relations.get(predicate)
        if rel is None:
            raise OntologyError(f"unknown relation: {predicate!r}")
        self.validate_entity(subject_type)
        self.validate_entity(object_type)
        if not self.is_subclass(subject_type, rel.domain):
            raise OntologyError(
                f"{predicate}: subject must be {rel.domain}, got {subject_type}"
            )
        if not self.is_subclass(object_type, rel.range):
            raise OntologyError(
                f"{predicate}: object must be {rel.range}, got {object_type}"
            )

    def prompt_summary(self) -> str:
        """Compact description of the ontology for the extraction prompt."""
        lines = ["Entity classes: " + ", ".join(sorted(self.classes))]
        lines.append("Relations (domain -> range):")
        for rel in self.relations.values():
            sym = " (symmetric)" if rel.symmetric else ""
            lines.append(f"  {rel.name}: {rel.domain} -> {rel.range}{sym}")
        return "\n".join(lines)
