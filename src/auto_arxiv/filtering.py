from __future__ import annotations

from .models import AppConfig, Paper, TopicRule


def select_papers(config: AppConfig, papers: list[Paper], seen_ids: set[str]) -> list[Paper]:
    for topic in config.topics:
        selected_for_topic: list[Paper] = []
        for paper in papers:
            if paper.arxiv_id in seen_ids:
                continue

            score = _score_topic_match(paper, topic)
            if score <= 0:
                continue

            paper.matched_topics = [topic.name]
            paper.relevance_score = score
            selected_for_topic.append(paper)

        selected_for_topic.sort(key=lambda item: (-item.relevance_score, -item.published.timestamp()))
        if selected_for_topic:
            return selected_for_topic[: config.digest.max_papers_per_run]

    return []


def _score_topic_match(paper: Paper, topic: TopicRule) -> int:
    title = paper.title.lower()
    abstract = paper.abstract.lower()
    text = f"{title}\n{abstract}"
    categories = set(paper.categories)

    if topic.categories and not categories.intersection(topic.categories):
        return 0

    if any(keyword in text for keyword in topic.exclude_keywords):
        return 0

    for group in topic.required_keyword_groups:
        if not any(keyword in text for keyword in group):
            return 0

    score = 0
    for keyword in topic.include_keywords:
        if keyword in title:
            score += 4
        elif keyword in abstract:
            score += 2

    if categories.intersection(topic.categories):
        score += 1

    # 至少要有一个关键词命中（标题或摘要）
    if score == 0:
        return 0

    return score
