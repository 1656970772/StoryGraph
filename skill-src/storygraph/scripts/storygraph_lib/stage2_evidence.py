from __future__ import annotations


def evidence_ids_for_category(
    evidence_index: list[dict], category_id: str, template_names: list[str] | None = None
) -> list[str]:
    selected = _matching_evidence_ids(
        evidence_index,
        lambda support: _support_matches_category(support, category_id),
    )
    if selected:
        return selected
    template_name_set = set(template_names or [])
    return _matching_evidence_ids(
        evidence_index,
        lambda support: _support_matches_template(support, template_name_set),
    )


def _matching_evidence_ids(evidence_index, predicate) -> list[str]:
    selected = []
    for evidence in evidence_index:
        if not isinstance(evidence, dict):
            continue
        supports = evidence.get("supports_templates")
        if not isinstance(supports, list):
            continue
        if any(predicate(support) for support in supports):
            evidence_id = evidence.get("evidence_id")
            if evidence_id and evidence_id not in selected:
                selected.append(evidence_id)
    return selected


def evidence_id_set(evidence_index: list[dict]) -> set[str]:
    return {
        evidence.get("evidence_id")
        for evidence in evidence_index
        if isinstance(evidence, dict) and evidence.get("evidence_id")
    }


def evidence_by_id(evidence_index: list[dict]) -> dict[str, dict]:
    return {
        evidence["evidence_id"]: evidence
        for evidence in evidence_index
        if isinstance(evidence, dict) and evidence.get("evidence_id")
    }


def _support_matches_category(support, category_id: str) -> bool:
    return isinstance(support, dict) and support.get("requirement_id") == category_id


def _support_matches_template(support, template_names: set[str]) -> bool:
    if not isinstance(support, dict):
        return False
    template_name = support.get("template_name")
    if template_name in template_names:
        return True
    requirement_id = support.get("requirement_id")
    return isinstance(requirement_id, str) and any(
        requirement_id.startswith(f"{name}.") for name in template_names
    )
