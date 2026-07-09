"""Pydantic models shared across the pipeline. These double as the LLM
structured-output schemas, so keep them strict and JSON-schema friendly."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ContentItem(BaseModel):
    """One item in the ingest queue (a video or an article)."""

    id: str
    kind: Literal["video", "article"]
    source: Literal["youtube", "netease", "other"]
    url: str
    title: str = ""
    published_at: Optional[str] = None
    duration_seconds: Optional[int] = None
    raw_text: str = ""  # transcription or article body, filled by M2


class Property(BaseModel):
    key: str
    value: str


class ExtractedEntity(BaseModel):
    name: str = Field(description="Canonical entity name")
    type: str = Field(description="Ontology class, e.g. Person / Organization / Technology / Topic / Claim")
    aliases: list[str] = Field(default_factory=list)
    properties: dict[str, str] = Field(default_factory=dict)


class ExtractedTriple(BaseModel):
    subject: str = Field(description="Entity name matching one of the extracted entities")
    predicate: str = Field(description="Ontology relation name")
    object: str = Field(description="Entity name matching one of the extracted entities")
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)
    evidence: str = Field(default="", description="Short quote from the source supporting this triple")


class ProcessedContent(BaseModel):
    """LLM output for one content item: summary + key points + knowledge."""

    content_id: str
    summary: str
    key_points: list[str]
    topics: list[str] = Field(description="Topic entity names this content is about")
    relevance: dict[str, float] = Field(
        default_factory=dict,
        description="Relevance score (0-1) per configured interest",
    )
    entities: list[ExtractedEntity] = Field(default_factory=list)
    triples: list[ExtractedTriple] = Field(default_factory=list)


class RelevanceScore(BaseModel):
    interest: str
    score: float = Field(ge=0.0, le=1.0)


class LLMEntity(BaseModel):
    """LLM-facing entity: open maps are not allowed by structured outputs,
    so properties are key/value pairs here and converted to a dict later."""

    name: str
    type: str
    aliases: list[str] = Field(default_factory=list)
    properties: list[Property] = Field(default_factory=list)

    def to_extracted(self) -> ExtractedEntity:
        return ExtractedEntity(
            name=self.name,
            type=self.type,
            aliases=self.aliases,
            properties={p.key: p.value for p in self.properties},
        )


class ExtractionResult(BaseModel):
    """Schema handed to the LLM as structured output (without content_id)."""

    summary: str
    key_points: list[str]
    topics: list[str]
    relevance: list[RelevanceScore] = Field(default_factory=list)
    entities: list[LLMEntity] = Field(default_factory=list)
    triples: list[ExtractedTriple] = Field(default_factory=list)

    def to_processed(self, content_id: str) -> ProcessedContent:
        return ProcessedContent(
            content_id=content_id,
            summary=self.summary,
            key_points=self.key_points,
            topics=self.topics,
            relevance={r.interest: r.score for r in self.relevance},
            entities=[e.to_extracted() for e in self.entities],
            triples=self.triples,
        )
