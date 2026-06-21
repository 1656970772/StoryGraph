import json

from storygraph_lib.coverage import make_chunk_ledger, write_coverage_outputs
from storygraph_lib.output_writer import OutputWriter


def test_make_chunk_ledger_reads_source_and_returns_chapter_aware_chunk_list(tmp_path):
    source = tmp_path / "novel.txt"
    source.write_text(
        "第一章 开端\n韩立获得小瓶。\n第二章 后续\n小瓶催熟灵草。\n",
        encoding="utf-8",
    )

    chunks = make_chunk_ledger(
        source,
        {
            "mode": "chapter-aware",
            "max_chars": 20,
            "overlap_chars": 0,
            "chapter_heading_patterns": ["^第.+章"],
        },
        processor="pytest",
    )

    assert [chunk["chunk_id"] for chunk in chunks] == ["chunk-0001", "chunk-0002"]
    assert chunks[0]["source_range"] == [0, len("第一章 开端\n韩立获得小瓶。\n")]
    assert chunks[0]["chapter_hint"] == "第一章 开端"
    assert chunks[0]["hash"]
    assert chunks[0]["scanned_at"] is None
    assert chunks[0]["processor"] == "pytest"
    assert chunks[0]["extraction_status"] == "pending"
    assert chunks[0]["failure"] is None
    assert chunks[0]["retry_count"] == 0
    assert chunks[0]["text"] == "第一章 开端\n韩立获得小瓶。\n"
    assert chunks[1]["chapter_hint"] == "第二章 后续"


def test_make_chunk_ledger_normalizes_indented_chapter_headings(tmp_path):
    source = tmp_path / "novel.txt"
    source.write_text(
        "　　第001章 废物南\n楚南受辱。\n  第二章 惊艳\n辰南入城。\n",
        encoding="utf-8",
    )

    chunks = make_chunk_ledger(
        source,
        {
            "mode": "chapter-aware",
            "max_chars": 1000,
            "overlap_chars": 0,
            "chapter_heading_patterns": ["^第.+章"],
        },
        processor="pytest",
    )

    assert [chunk["chapter_hint"] for chunk in chunks] == ["第001章 废物南", "第二章 惊艳"]
    assert chunks[0]["source_range"] == [0, len("　　第001章 废物南\n楚南受辱。\n")]


def test_make_chunk_ledger_default_patterns_cover_common_web_novel_headings(tmp_path):
    source = tmp_path / "novel.txt"
    source.write_text(
        "第一卷 走出神墓\n卷首文字。\n"
        "  第二章 惊艳\n正文一。\n"
        "第003节 旧事\n正文二。\n"
        "番外 修行余波\n正文三。\n",
        encoding="utf-8",
    )

    chunks = make_chunk_ledger(
        source,
        {
            "mode": "chapter-aware",
            "max_chars": 1000,
            "overlap_chars": 0,
        },
        processor="pytest",
    )

    assert [chunk["chapter_hint"] for chunk in chunks] == [
        "第一卷 走出神墓",
        "第二章 惊艳",
        "第003节 旧事",
        "番外 修行余波",
    ]


def test_write_coverage_outputs_uses_writer_for_plan_coverage_artifacts(tmp_path):
    writer = OutputWriter(
        tmp_path,
        [
            "coverage/chunk-ledger.json",
            "coverage/evidence-index.json",
            "coverage/template-readiness.json",
            "coverage/agent-run-ledger.json",
            "coverage/gap-report.md",
        ],
    )

    paths = write_coverage_outputs(
        writer,
        chunks=[{"chunk_id": "chunk-0001"}],
        evidences=[{"evidence_id": "evidence:1"}],
        readiness=[{"template_name": "法宝分析"}],
        agent_runs=[{"run_id": "run-1"}],
        gap_lines=["# Gap Report", "- none"],
    )

    assert json.loads(paths["chunks"].read_text(encoding="utf-8")) == [{"chunk_id": "chunk-0001"}]
    assert json.loads(paths["agent_runs"].read_text(encoding="utf-8")) == [{"run_id": "run-1"}]
    assert paths["gap_report"].read_text(encoding="utf-8") == "# Gap Report\n- none\n"
