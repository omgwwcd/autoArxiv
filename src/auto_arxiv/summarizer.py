from __future__ import annotations

import json
import logging
import os
import time
from typing import Optional

import requests

from .models import AppConfig, Paper

# 强制添加 handler 确保日志输出
logger = logging.getLogger("llm")
logger.setLevel(logging.INFO)
_ch = logging.StreamHandler()
_ch.setLevel(logging.INFO)
_ch.setFormatter(logging.Formatter("[LLM] %(asctime)s %(message)s", datefmt="%H:%M:%S"))
logger.addHandler(_ch)
# 避免重复
logger.handlers = [_ch]

QUALITY_THRESHOLD = 90
MAX_REWRITE_ROUNDS = 5


def enrich_papers(config: AppConfig, papers: list[Paper]) -> None:
    provider = os.getenv("LLM_PROVIDER", "").strip().lower() or "deepseek"
    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    deepseek_model = os.getenv("DEEPSEEK_MODEL", "").strip() or "deepseek-chat"
    deepseek_base_url = os.getenv("DEEPSEEK_BASE_URL", "").rstrip("/") or "https://api.deepseek.com"

    logger.info(f"enrich_papers called with {len(papers)} papers")
    logger.info(f"Provider: {provider}, Model: {deepseek_model}, BaseURL: {deepseek_base_url}")

    for i, paper in enumerate(papers):
        logger.info(f"=== Processing paper {i+1}/{len(papers)}: {paper.title[:50]} ===")
        if provider == "deepseek" and deepseek_key:
            try:
                paper.digest, paper.digest_quality_score = _summarize_with_deepseek(
                    config=config,
                    paper=paper,
                    api_key=deepseek_key,
                    model=deepseek_model,
                    base_url=deepseek_base_url,
                )
                logger.info(f"Final digest score: {paper.digest_quality_score}")
            except Exception as e:
                logger.error(f"LLM summarization failed: {e}")
                paper.digest = _fallback_digest(paper)
                paper.digest_quality_score = 0
        else:
            paper.digest = _fallback_digest(paper)
            paper.digest_quality_score = 0

        paper.summary = str(paper.digest.get("final_summary", "")).strip()
        paper.recommendation_reason = str(paper.digest.get("why_it_matters", "")).strip()


def _summarize_with_deepseek(
    config: AppConfig,
    paper: Paper,
    api_key: str,
    model: str,
    base_url: str,
) -> tuple[dict, int]:
    logger.info("=== Starting LLM summarization ===")
    logger.info(f"Paper: {paper.title[:60]}")
    logger.info(f"Model: {model} @ {base_url}")
    previous_digest: dict | None = None
    review_feedback = ""
    best_digest: dict | None = None
    best_score = -1

    for round_i in range(MAX_REWRITE_ROUNDS):
        logger.info(f"--- Round {round_i + 1}/{MAX_REWRITE_ROUNDS} ---")
        prompt = _build_prompt(config, paper, previous_digest, review_feedback)
        logger.info(f"Prompt length: {len(prompt)} chars")

        digest = _generate_digest(prompt, api_key, model, base_url)
        logger.info(f"Generate returned keys: {list(digest.keys())}")

        score, feedback = _review_digest(config, paper, digest, api_key, model, base_url)
        logger.info(f"Review score: {score}/100 | feedback: {feedback[:80] if feedback else '(none)'}...")

        if score > best_score:
            best_digest = digest
            best_score = score
            logger.info(f"New best score: {score}")

        if score >= QUALITY_THRESHOLD:
            logger.info(f"=== SUCCESS: score {score} >= {QUALITY_THRESHOLD}, returning ===")
            return digest, score

        previous_digest = digest
        review_feedback = feedback

    if best_digest is None or not best_digest:
        logger.error("=== FAILED: all rounds returned empty digest ===")
        raise RuntimeError("failed to produce a digest")
    logger.warning(f"=== TIMEOUT: best score {best_score} < {QUALITY_THRESHOLD}, returning best ===")
    return best_digest, best_score


def _build_prompt(
    config: AppConfig,
    paper: Paper,
    previous_digest: dict | None = None,
    review_feedback: str = "",
) -> str:
    prompt = (
        f"You are preparing a daily arXiv digest in {config.digest.language}.\n"
        "Return strict JSON only.\n"
        "All prose fields must be written in Simplified Chinese.\n"
        "Use this exact schema:\n"
        "{\n"
        '  "topics": ["..."],\n'
        '  "venue_or_year": "...",\n'
        '  "code_link": "...",\n'
        '  "one_line_takeaway": "...",\n'
        '  "why_it_matters": "...",\n'
        '  "research_questions": ["...", "..."],\n'
        '  "background_and_problem_setting": "...",\n'
        '  "method_overview": {\n'
        '    "task_environment": "...",\n'
        '    "condition_intervention_design": "...",\n'
        '    "evaluation_metrics": "...",\n'
        '    "model_comparison": "...",\n'
        '    "my_understanding": "..."\n'
        "  },\n"
        '  "key_findings": [\n'
        '    {"title": "...", "detail": "..."}\n'
        "  ],\n"
        '  "most_important_figure": {\n'
        '    "figure_source": "...",\n'
        '    "why_it_matters": "..."\n'
        "  },\n"
        '  "how_to_read_this_figure": "...",\n'
        '  "second_important_figure": {\n'
        '    "why_it_matters": "..."\n'
        "  },\n"
        '  "related_recent_papers": [\n'
        '    {"title": "...", "why_important": "...", "core_contribution": "...", "relation_to_current_work": "..."}\n'
        "  },\n"
        '  "implications": {\n'
        '    "for_agent_systems": "...",\n'
        '    "for_skill": "...",\n'
        '    "for_memory": "...",\n'
        '    "for_evaluation": "..."\n'
        "  },\n"
        '  "limitations": ["...", "..."],\n'
        '  "my_take": "...",\n'
        '  "final_summary": "..."\n'
        "}\n"
        "Keep it concise but information-dense. If venue or code is unknown, use an empty string.\n"
        "Do not answer in English unless a paper title, metric name, or method name must remain in English.\n"
        "For related_recent_papers, include up to 3 papers only when you are reasonably confident they are cited or strongly connected based on the provided content; otherwise return an empty list.\n"
        "Base your answer on the paper content excerpt below, not on webpage structure or HTML.\n\n"
        f"Title: {paper.title}\n"
        f"Authors: {', '.join(paper.authors)}\n"
        f"Categories: {', '.join(paper.categories)}\n"
        f"Matched topics: {', '.join(paper.matched_topics)}\n"
        f"Abstract: {paper.abstract}\n\n"
        f"Paper content excerpt:\n{paper.article_text}\n"
    )
    if previous_digest and review_feedback:
        prompt += (
            "\nPrevious draft JSON:\n"
            f"{json.dumps(previous_digest, ensure_ascii=False)}\n\n"
            "Reviewer feedback to address in the rewrite:\n"
            f"{review_feedback}\n"
            "Rewrite the digest so it is more accurate, more specific, better structured, and more useful."
        )
    return prompt


def _generate_digest(prompt: str, api_key: str, model: str, base_url: str) -> dict:
    logger.info(f"POST {base_url}/chat/completions")
    response = _post_with_retries(
        f"{base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        payload={
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You generate concise academic digests and must output valid JSON only.",
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            "temperature": 0.2,
        },
        timeout=300,
    )
    logger.info(f"Response status: {response.status_code}")
    response.raise_for_status()
    data = response.json()
    output_text = _extract_deepseek_text(data)
    logger.info(f"Extracted text length: {len(output_text)} chars")
    logger.info(f"Text preview: {output_text[:200]!r}")
    parsed = _parse_summary_payload(output_text)
    logger.info(f"Parsed keys: {list(parsed.keys())}")
    return parsed


def _review_digest(
    config: AppConfig,
    paper: Paper,
    digest: dict,
    api_key: str,
    model: str,
    base_url: str,
) -> tuple[int, str]:
    prompt = (
        f"You are reviewing a paper digest written in {config.digest.language}.\n"
        "Return strict JSON only with keys: score, feedback.\n"
        "score must be an integer from 0 to 100.\n"
        "feedback must be concise but concrete, focusing on factual specificity, structure, usefulness, and whether the digest really reflects the paper.\n"
        "Use Simplified Chinese.\n\n"
        f"Paper title: {paper.title}\n"
        f"Matched topics: {', '.join(paper.matched_topics)}\n"
        f"Abstract: {paper.abstract}\n\n"
        f"Paper content excerpt:\n{paper.article_text}\n\n"
        "Digest JSON to review:\n"
        f"{json.dumps(digest, ensure_ascii=False)}\n"
    )
    response = _post_with_retries(
        f"{base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        payload={
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a strict academic digest reviewer and must output valid JSON only.",
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            "temperature": 0.1,
        },
        timeout=300,
    )
    logger.info(f"Review response status: {response.status_code}")
    response.raise_for_status()
    data = response.json()
    output_text = _extract_deepseek_text(data)
    logger.info(f"Review text: {output_text[:200]!r}")
    parsed = json.loads(output_text)
    score = int(parsed.get("score", 0))
    feedback = str(parsed.get("feedback", "")).strip()
    score = max(0, min(100, score))
    logger.info(f"Review parsed: score={score}, feedback_len={len(feedback)}")
    return score, feedback


def _extract_deepseek_text(payload: dict) -> str:
    choices = payload.get("choices", [])
    if not choices:
        return ""
    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, str):
        text = content.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            if len(lines) >= 2:
                text = "\n".join(lines[1:-1])  # Remove first (```lang) and last (```) lines
            else:
                text = ""
        return text.strip()
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            text = item.get("text")
            if text:
                chunks.append(text)
        return "\n".join(chunks).strip()
    return ""


def _parse_summary_payload(output_text: str) -> dict:
    text = output_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if len(lines) >= 2:
            text = "\n".join(lines[1:-1])
        text = text.strip()
    try:
        result = json.loads(text)
        logger.info(f"JSON parse OK, {len(result)} keys")
        return result
    except json.JSONDecodeError as e:
        logger.warning(f"JSON parse failed: {e}")
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                result = json.loads(text[start:end])
                logger.info(f"JSON extraction OK, {len(result)} keys")
                return result
            except json.JSONDecodeError as e2:
                logger.warning(f"JSON extraction also failed: {e2}")
        logger.error("All JSON parsing attempts failed, returning empty dict")
        return {}


def _post_with_retries(
    url: str,
    headers: dict[str, str],
    payload: dict,
    timeout: int,
    max_attempts: int = 3,
) -> requests.Response:
    last_error: Exception | None = None
    session = requests.Session()
    session.trust_env = False
    for attempt in range(max_attempts):
        try:
            return session.post(
                url,
                headers=headers,
                json=payload,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            last_error = exc
            if attempt < max_attempts - 1:
                time.sleep(2 * (attempt + 1))
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"request failed without an exception: {url}")


def _fallback_digest(paper: Paper) -> dict:
    excerpt = paper.article_text[:700].rstrip()
    return {
        "topics": paper.matched_topics,
        "venue_or_year": str(paper.published.year),
        "code_link": "",
        "one_line_takeaway": f"这篇论文围绕 {paper.title} 展开，核心内容与 {', '.join(paper.matched_topics)} 相关。",
        "why_it_matters": f"它之所以值得关注，是因为它与 {', '.join(paper.matched_topics)} 方向直接相关，且关键词匹配分数为 {paper.relevance_score}。",
        "research_questions": [
            "这篇论文试图解决什么问题？",
            "作者的方法与已有工作相比有什么不同？",
            "结果是否支持其核心主张？",
        ],
        "background_and_problem_setting": excerpt,
        "method_overview": {
            "task_environment": "自动回退摘要未能完整识别任务环境。",
            "condition_intervention_design": "自动回退摘要未能完整识别控制变量。",
            "evaluation_metrics": "自动回退摘要未能完整识别评价指标。",
            "model_comparison": "自动回退摘要未能完整识别对比模型。",
            "my_understanding": "建议查看原文进一步确认方法细节。",
        },
        "key_findings": [
            {
                "title": "自动回退摘要",
                "detail": f"当前仅基于正文抽取片段生成摘要，建议结合原文确认：{excerpt}",
            }
        ],
        "most_important_figure": {
            "figure_source": "",
            "why_it_matters": "当前版本未自动抽取图像，但建议人工查看论文主结果图。",
        },
        "how_to_read_this_figure": "优先查看横轴、纵轴和关键对比组，确认图是否直接支撑论文的核心主张。",
        "second_important_figure": {
            "why_it_matters": "如果论文中存在失败案例图、消融图或模型差异图，这类图通常是第二重要的辅助证据。",
        },
        "related_recent_papers": [],
        "implications": {
            "for_agent_systems": "如果论文与 agent 相关，应重点关注其对任务规划、工具使用或可靠性的启发。",
            "for_skill": "如果论文涉及 skill，应关注技能是否可组合、可复用、可验证。",
            "for_memory": "如果论文涉及 memory，应关注记忆存储、检索和更新机制。",
            "for_evaluation": "建议关注论文采用的评价指标是否真的衡量了目标能力。",
        },
        "limitations": [
            "当前条目为自动回退摘要，细节可能不完整。",
            "未自动抽取图像与代码仓库信息。",
        ],
        "my_take": "这条摘要来自回退路径，适合作为初筛，不适合作为最终精读结论。",
        "final_summary": f"总体来看，这篇论文与 {', '.join(paper.matched_topics)} 相关，建议根据正文和主结果图进一步确认其真实贡献。",
    }
