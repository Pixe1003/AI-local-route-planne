from typing import Any

from pydantic import BaseModel, Field


class EvidenceSnippet(BaseModel):
    doc_id: str
    source_type: str = "poi_profile"
    text: str
    score: float = 0.0


class RetrievalQuery(BaseModel):
    city: str
    text: str | None = None
    top_k: int = 24
    category_filters: list[str] = Field(default_factory=list)
    category_groups: list[str] = Field(default_factory=list)
    source_types: list[str] = Field(default_factory=list)
    budget_per_person: int | None = None
    avoid_queue: bool = False
    preference_terms: list[str] = Field(default_factory=list)
    origin_latitude: float | None = None
    origin_longitude: float | None = None
    radius_meters: int | None = None


class RetrievedPoi(BaseModel):
    poi_id: str
    score: float
    evidence_snippets: list[EvidenceSnippet] = Field(default_factory=list)
    provenance: list[str] = Field(default_factory=list)


class RagDocument(BaseModel):
    doc_id: str
    poi_id: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
