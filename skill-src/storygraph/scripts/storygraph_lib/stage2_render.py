from __future__ import annotations


def render_template_draft(
    record: dict,
    evidence_index: dict[str, dict],
    render_policy: dict | None = None,
    *,
    review_status: str | None = None,
) -> str:
    render_policy = render_policy or {}
    lines = [f"# {record['template_name']}", ""]
    if render_policy.get("include_unreviewed_warning", True) and review_status:
        lines.extend(
            [
                "> Stage 1 review_status: "
                f"{review_status}，本文件是 Stage 2 草稿，正式覆盖前需要人工或 merge agent 复核。",
                "",
            ]
        )

    sections = record.get("document_sections") or []
    for section in sections:
        heading = str(section.get("heading", "")).strip() or "未命名章节"
        lines.extend([f"## {heading}", "", str(section.get("markdown", "")).strip(), ""])
        citations = _format_citations(
            section.get("evidence_ids", []),
            evidence_index,
            render_policy.get("citation_format", "[{evidence_id}]"),
        )
        if citations:
            lines.extend(["证据：" + " ".join(citations), ""])

    if record.get("facts"):
        lines.extend(["## 证据事实", ""])
        for item in record["facts"]:
            lines.append(f"- {item.get('content', '')}")
        lines.append("")

    gaps = list(record.get("gap_items") or [])
    gaps.extend(item.get("content", "") for item in record.get("not_found_items", []))
    if gaps:
        lines.extend(["## 缺口与待核验", ""])
        for gap in gaps:
            if gap:
                lines.append(f"- {gap}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _format_citations(evidence_ids, evidence_index, citation_format):
    citations = []
    for evidence_id in evidence_ids:
        evidence = evidence_index.get(evidence_id, {})
        citations.append(
            citation_format.format(
                evidence_id=evidence_id,
                chunk_id=evidence.get("chunk_id", ""),
                source_range=evidence.get("source_range", ""),
            )
        )
    return citations
