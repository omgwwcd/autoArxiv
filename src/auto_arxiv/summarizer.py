from __future__ import annotations

import json
import os
import time

import requests

from .models import AppConfig, Paper


def enrich_papers(config: AppConfig, papers: list[Paper]) -> None:
    provider = os.getenv("LLM_PROVIDER", "").strip().lower() or "deepseek"
    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    deepseek_model = os.getenv("DEEPSEEK_MODEL", "").strip() or "deepseek-chat"
    deepseek_base_url = os.getenv("DEEPSEEK_BASE_URL", "").rstrip("/") or "https://api.deepseek.com"

    for paper in papers:
        if provider == "deepseek" and deepseek_key:
            try:
                paper.digest = _summarize_with_deepseek(
                    config=config,
                    paper=paper,
                    api_key=deepseek_key,
                    model=deepseek_model,
                    base_url=deepseek_base_url,
                )
            except Exception:
                paper.digest = _fallback_digest(paper)
        else:
            paper.digest = _fallback_digest(paper)

        paper.summary = str(paper.digest.get("final_summary", "")).strip()
        paper.recommendation_reason = str(paper.digest.get("why_it_matters", "")).strip()


def _summarize_with_deepseek(
    config: AppConfig,
    paper: Paper,
    api_key: str,
    model: str,
    base_url: str,
) -> dict:
    prompt = _build_prompt(config, paper)
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
            "response_format": {"type": "json_object"},
        },
        timeout=120,
    )
    response.raise_for_status()
    data = response.json()
    output_text = _extract_deepseek_text(data)
    return _parse_summary_payload(output_text)


def _build_prompt(config: AppConfig, paper: Paper) -> str:
    return (
        f"You are preparing a daily arXiv digest in {config.digest.language}.\n"
        "Return strict JSON only.\n"
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
        '    "why_it_matters": "...",\n'
        '    "how_to_read": "..."\n'
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
        "Base your answer on the paper content excerpt below, not on webpage structure or HTML.\n\n"
        f"Title: {paper.title}\n"
        f"Authors: {', '.join(paper.authors)}\n"
        f"Categories: {', '.join(paper.categories)}\n"
        f"Matched topics: {', '.join(paper.matched_topics)}\n"
        f"Abstract: {paper.abstract}\n\n"
        f"Paper content excerpt:\n{paper.article_text}\n"
    )


def _extract_deepseek_text(payload: dict) -> str:
    choices = payload.get("choices", [])
    if not choices:
        return ""
    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            text = item.get("text")
            if text:
                chunks.append(text)
        return "\n".join(chunks).strip()
    return ""


def _parse_summary_payload(output_text: str) -> dict:
    return json.loads(output_text)


def _post_with_retries(
    url: str,
    headers: dict[str, str],
    payload: dict,
    timeout: int,
    max_attempts: int = 3,
) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return requests.post(
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
            "how_to_read": "优先查看能直接支撑核心结论的主实验图或消融图。",
        },
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
