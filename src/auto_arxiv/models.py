from __future__ import annotations

from typing import Any
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class TopicRule:
    name: str
    categories: list[str]
    include_keywords: list[str]
    exclude_keywords: list[str]
    required_keyword_groups: list[list[str]]


@dataclass(slots=True)
class DigestSettings:
    project_name: str
    target_day_offset: int
    max_papers_per_run: int
    max_candidates: int
    language: str
    timezone: str


@dataclass(slots=True)
class AppConfig:
    digest: DigestSettings
    topics: list[TopicRule]


@dataclass(slots=True)
class Paper:
    arxiv_id: str
    title: str
    abstract: str
    article_text: str
    published: datetime
    updated: datetime
    authors: list[str]
    categories: list[str]
    abs_url: str
    pdf_url: str
    matched_topics: list[str] = field(default_factory=list)
    relevance_score: int = 0
    summary: str = ""
    recommendation_reason: str = ""
    digest: dict[str, Any] = field(default_factory=dict)
    digest_quality_score: int = 0
    figure_bytes: bytes | None = None
    figure_subtype: str = ""
    figure_content_id: str = ""
