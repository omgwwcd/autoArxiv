from __future__ import annotations

from pathlib import Path
import tomllib

from .models import AppConfig, DigestSettings, TopicRule


def load_config(config_path: str | Path) -> AppConfig:
    path = Path(config_path)
    raw = tomllib.loads(path.read_text(encoding="utf-8"))

    digest = raw.get("digest", {})
    topics = raw.get("topics", [])
    if not topics:
        raise ValueError("config/topics.toml must define at least one topic")

    settings = DigestSettings(
        project_name=digest.get("project_name", "Auto arXiv Digest"),
        target_day_offset=int(digest.get("target_day_offset", 1)),
        max_papers_per_run=int(digest.get("max_papers_per_run", 5)),
        max_candidates=int(digest.get("max_candidates", 60)),
        language=digest.get("language", "zh-CN"),
        timezone=digest.get("timezone", "Asia/Shanghai"),
    )

    topic_rules = [
        TopicRule(
            name=topic["name"],
            categories=list(topic.get("categories", [])),
            include_keywords=[item.lower() for item in topic.get("include_keywords", [])],
            exclude_keywords=[item.lower() for item in topic.get("exclude_keywords", [])],
            required_keyword_groups=[
                [item.lower() for item in group]
                for group in topic.get("required_keyword_groups", [])
            ],
        )
        for topic in topics
    ]
    return AppConfig(digest=settings, topics=topic_rules)
