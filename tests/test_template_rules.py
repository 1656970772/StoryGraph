from storygraph_lib.template_rules import parse_template_requirements


RULES = {
    "field_headings": ["字段"],
    "table_markers": ["|", "表格"],
    "card_markers": ["卡片"],
    "case_markers": ["案例"],
    "evidence_markers": ["证据", "原文"],
    "gap_markers": ["缺口", "待核验"],
}


def test_parse_template_extracts_fields_tables_cards_cases_evidence_and_gap_rules():
    text = """# 法宝分析模板
## 字段
- 法宝名称
- 持有者
## 表格
| 名称 | 等级 |
| --- | --- |
## 法宝卡片
- 来源
## 案例
- 小瓶反复改变资源获取方式
## 证据要求
- 原文位置
## 缺口规则
- 无原文时标记待核验
"""
    parsed = parse_template_requirements("法宝分析", text, RULES)
    assert parsed["required_fields"] == ["法宝名称", "持有者"]
    assert parsed["required_tables"] == ["名称|等级"]
    assert parsed["required_cards"] == ["法宝卡片"]
    assert parsed["required_case_patterns"] == ["小瓶反复改变资源获取方式"]
    assert parsed["required_evidence_fields"] == ["原文位置"]
    assert parsed["gap_rules"]["markers"] == ["无原文时标记待核验"]
