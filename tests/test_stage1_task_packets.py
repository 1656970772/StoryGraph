import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "skill-src" / "storygraph" / "config" / "storygraph.default.json"


def _default_config():
    return json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))


def test_prepare_task_packets_writes_one_packet_per_required_lane(tmp_path):
    from storygraph_lib.stage1_packets import build_task_packets

    config = _default_config()
    task_packet_dir = config["stage1_artifacts"]["task_packet_dir"]
    chunks = [
        {
            "chunk_id": "chunk-0001",
            "source_range": [0, 10],
            "chapter_hint": "第一章",
            "chunk_text_path": "intermediate/chunks/chunk-0001.txt",
        }
    ]
    lanes = [
        {
            "lane_id": "entities_resources",
            "required": True,
            "agent_role": "实体道具资源抽取 agent",
            "schema": "lane-output.schema.json",
        },
        {
            "lane_id": "event_causality",
            "required": True,
            "agent_role": "事件因果抽取 agent",
            "schema": "lane-output.schema.json",
        },
    ]

    packets = build_task_packets(
        source_path="book.txt",
        chunks=chunks,
        lanes=lanes,
        template_requirements_path="requirements/template-requirements.json",
        task_packet_dir=task_packet_dir,
    )

    assert len(packets) == 2
    assert packets[0]["stage"] == "stage1"
    assert packets[0]["chunk_id"] == "chunk-0001"
    assert packets[0]["lane_id"] == "entities_resources"
    assert packets[0]["agent_role"] == "实体道具资源抽取 agent"
    assert packets[0]["allowed_output_schema"] == "lane-output.schema.json"
    assert (
        packets[0]["task_packet_path"]
        == f"{task_packet_dir}/chunk-0001/entities_resources.json"
    )


def test_build_task_packets_copies_required_evidence_policy_per_packet():
    from storygraph_lib.stage1_packets import build_task_packets

    shared_policy = {
        "minimum_evidence": {"direct": 1},
        "allowed_confidence": ["EXTRACTED"],
    }

    packets = build_task_packets(
        source_path="book.txt",
        chunks=[
            {"chunk_id": "chunk-0001", "source_range": [0, 1]},
            {"chunk_id": "chunk-0002", "source_range": [1, 2]},
        ],
        lanes=[
            {
                "lane_id": "events",
                "required": True,
                "agent_role": "role",
                "schema": "schema.json",
                "required_evidence_policy": shared_policy,
            }
        ],
        template_requirements_path="requirements/template-requirements.json",
        task_packet_dir=_default_config()["stage1_artifacts"]["task_packet_dir"],
    )

    assert packets[0]["required_evidence_policy"] == shared_policy
    assert packets[0]["required_evidence_policy"] is not shared_policy
    assert packets[1]["required_evidence_policy"] is not shared_policy
    assert (
        packets[0]["required_evidence_policy"]
        is not packets[1]["required_evidence_policy"]
    )

    packets[0]["required_evidence_policy"]["minimum_evidence"]["direct"] = 99

    assert shared_policy["minimum_evidence"]["direct"] == 1
    assert packets[1]["required_evidence_policy"]["minimum_evidence"]["direct"] == 1


def test_build_task_packets_rejects_non_dict_lane_and_chunk():
    from storygraph_lib.stage1_packets import build_task_packets

    valid_chunks = [{"chunk_id": "chunk-0001", "source_range": [0, 1]}]
    valid_lanes = [
        {
            "lane_id": "events",
            "required": True,
            "agent_role": "role",
            "schema": "schema.json",
        }
    ]

    with pytest.raises(ValueError, match="invalid_lane_record"):
        build_task_packets(
            "book.txt",
            valid_chunks,
            ["bad"],
            "requirements/template-requirements.json",
        )

    with pytest.raises(ValueError, match="invalid_chunk_record"):
        build_task_packets(
            "book.txt",
            ["bad"],
            valid_lanes,
            "requirements/template-requirements.json",
        )


@pytest.mark.parametrize(
    ("chunks", "lanes", "expected_code"),
    [
        (
            [{"chunk_id": "../evil", "source_range": [0, 1]}],
            [
                {
                    "lane_id": "events",
                    "required": True,
                    "agent_role": "role",
                    "schema": "schema.json",
                }
            ],
            "invalid_chunk_id",
        ),
        (
            [{"chunk_id": "chunk-0001", "source_range": [0, 1]}],
            [
                {
                    "lane_id": "bad/events",
                    "required": True,
                    "agent_role": "role",
                    "schema": "schema.json",
                }
            ],
            "invalid_lane_id",
        ),
    ],
)
def test_build_task_packets_rejects_unsafe_chunk_and_lane_ids(
    chunks, lanes, expected_code
):
    from storygraph_lib.stage1_packets import build_task_packets

    with pytest.raises(ValueError, match=expected_code):
        build_task_packets(
            "book.txt",
            chunks,
            lanes,
            "requirements/template-requirements.json",
            task_packet_dir=_default_config()["stage1_artifacts"]["task_packet_dir"],
        )


@pytest.mark.parametrize(
    "task_packet_path",
    [
        "../outside.json",
        "/outside.json",
        "C:/outside.json",
        "intermediate/task-packets/chunk-0001/a*.json",
        "intermediate/task-packets/chunk-0001/a?.json",
        "intermediate/task-packets/chunk-0001/bad\0path.json",
    ],
)
def test_build_task_packets_rejects_unsafe_supplied_task_packet_path(
    task_packet_path,
):
    from storygraph_lib.stage1_packets import build_task_packets

    with pytest.raises(ValueError, match="invalid_task_packet_path"):
        build_task_packets(
            "book.txt",
            [{"chunk_id": "chunk-0001", "source_range": [0, 1]}],
            [
                {
                    "lane_id": "events",
                    "required": True,
                    "agent_role": "role",
                    "schema": "schema.json",
                    "task_packet_path": task_packet_path,
                }
            ],
            "requirements/template-requirements.json",
            task_packet_dir=_default_config()["stage1_artifacts"]["task_packet_dir"],
        )


def test_build_task_packets_rejects_bad_source_range_string():
    from storygraph_lib.stage1_packets import build_task_packets

    with pytest.raises(ValueError, match="invalid_source_range"):
        build_task_packets(
            "book.txt",
            [{"chunk_id": "chunk-0001", "source_range": "0-10"}],
            [
                {
                    "lane_id": "events",
                    "required": True,
                    "agent_role": "role",
                    "schema": "schema.json",
                }
            ],
            "requirements/template-requirements.json",
            task_packet_dir=_default_config()["stage1_artifacts"]["task_packet_dir"],
        )


@pytest.mark.parametrize(
    ("chunks", "template_requirements_path", "expected_code"),
    [
        (
            [
                {
                    "chunk_id": "chunk-0001",
                    "source_range": [0, 1],
                    "chunk_text_path": "../chunks/chunk-0001.txt",
                }
            ],
            "requirements/template-requirements.json",
            "invalid_chunk_text_path",
        ),
        (
            [{"chunk_id": "chunk-0001", "source_range": [0, 1]}],
            "../requirements/template-requirements.json",
            "invalid_template_requirements_path",
        ),
    ],
)
def test_build_task_packets_rejects_unsafe_artifact_paths(
    chunks, template_requirements_path, expected_code
):
    from storygraph_lib.stage1_packets import build_task_packets

    with pytest.raises(ValueError, match=expected_code):
        build_task_packets(
            "book.txt",
            chunks,
            [
                {
                    "lane_id": "events",
                    "required": True,
                    "agent_role": "role",
                    "schema": "schema.json",
                }
            ],
            template_requirements_path,
            task_packet_dir=_default_config()["stage1_artifacts"]["task_packet_dir"],
        )


@pytest.mark.parametrize(
    ("chunks", "lanes", "template_requirements_path", "expected_code"),
    [
        (
            [
                {
                    "chunk_id": "chunk-0001",
                    "source_range": [0, 1],
                    "chunk_text_path": 123,
                }
            ],
            [
                {
                    "lane_id": "events",
                    "required": True,
                    "agent_role": "role",
                    "schema": "schema.json",
                }
            ],
            "requirements/template-requirements.json",
            "invalid_chunk_text_path",
        ),
        (
            [{"chunk_id": "chunk-0001", "source_range": [0, 1]}],
            [
                {
                    "lane_id": "events",
                    "required": True,
                    "agent_role": "role",
                    "schema": "schema.json",
                }
            ],
            123,
            "invalid_template_requirements_path",
        ),
        (
            [{"chunk_id": "chunk-0001", "source_range": [0, 1]}],
            [
                {
                    "lane_id": "events",
                    "required": True,
                    "agent_role": "role",
                    "schema": "schema.json",
                    "task_packet_path": 123,
                }
            ],
            "requirements/template-requirements.json",
            "invalid_task_packet_path",
        ),
    ],
)
def test_build_task_packets_rejects_non_string_artifact_paths(
    chunks, lanes, template_requirements_path, expected_code
):
    from storygraph_lib.stage1_packets import build_task_packets

    with pytest.raises(ValueError, match=expected_code):
        build_task_packets(
            "book.txt",
            chunks,
            lanes,
            template_requirements_path,
            task_packet_dir=_default_config()["stage1_artifacts"]["task_packet_dir"],
        )


def test_build_task_packets_rejects_non_string_task_packet_dir():
    from storygraph_lib.stage1_packets import build_task_packets

    with pytest.raises(ValueError, match="invalid_task_packet_path"):
        build_task_packets(
            "book.txt",
            [{"chunk_id": "chunk-0001", "source_range": [0, 1]}],
            [
                {
                    "lane_id": "events",
                    "required": True,
                    "agent_role": "role",
                    "schema": "schema.json",
                }
            ],
            "requirements/template-requirements.json",
            task_packet_dir=123,
        )


@pytest.mark.parametrize("source_path", [123, "", "book\0.txt"])
def test_build_task_packets_rejects_invalid_source_path(source_path):
    from storygraph_lib.stage1_packets import build_task_packets

    with pytest.raises(ValueError, match="invalid_source_path"):
        build_task_packets(
            source_path,
            [{"chunk_id": "chunk-0001", "source_range": [0, 1]}],
            [
                {
                    "lane_id": "events",
                    "required": True,
                    "agent_role": "role",
                    "schema": "schema.json",
                }
            ],
            "requirements/template-requirements.json",
            task_packet_dir=_default_config()["stage1_artifacts"][
                "task_packet_dir"
            ],
        )


@pytest.mark.parametrize("source_range", [[-1, 1], [10, 1]])
def test_build_task_packets_rejects_invalid_source_range_bounds(source_range):
    from storygraph_lib.stage1_packets import build_task_packets

    with pytest.raises(ValueError, match="invalid_source_range"):
        build_task_packets(
            "book.txt",
            [{"chunk_id": "chunk-0001", "source_range": source_range}],
            [
                {
                    "lane_id": "events",
                    "required": True,
                    "agent_role": "role",
                    "schema": "schema.json",
                }
            ],
            "requirements/template-requirements.json",
            task_packet_dir=_default_config()["stage1_artifacts"]["task_packet_dir"],
        )


def test_chunk_ledger_records_lane_statuses_without_semantic_completion(tmp_path):
    from storygraph_lib.coverage import make_chunk_ledger

    source = tmp_path / "novel.txt"
    source.write_text("第一章\n韩立获得小瓶。", encoding="utf-8")

    chunks = make_chunk_ledger(
        source,
        {
            "mode": "chapter-aware",
            "max_chars": 100,
            "overlap_chars": 0,
            "chapter_heading_patterns": ["^第.+章"],
        },
        processor="storygraph-stage1",
        target_lane_ids=["entities_resources", "event_causality"],
        required_lane_ids=["entities_resources", "event_causality"],
    )

    assert chunks[0]["extraction_status"] == "pending_agent_outputs"
    assert chunks[0]["target_lane_ids"] == ["entities_resources", "event_causality"]
    assert chunks[0]["required_lane_ids"] == ["entities_resources", "event_causality"]
    assert chunks[0]["lane_statuses"] == {
        "entities_resources": "pending_agent_outputs",
        "event_causality": "pending_agent_outputs",
    }


def test_chunk_ledger_keeps_legacy_pending_status_without_lane_tracking(tmp_path):
    from storygraph_lib.coverage import make_chunk_ledger

    source = tmp_path / "novel.txt"
    source.write_text("第一章\n韩立获得小瓶。", encoding="utf-8")

    chunks = make_chunk_ledger(
        source,
        {
            "mode": "chapter-aware",
            "max_chars": 100,
            "overlap_chars": 0,
            "chapter_heading_patterns": ["^第.+章"],
        },
        processor="storygraph-stage1",
    )

    assert chunks[0]["extraction_status"] == "pending"
    assert "target_lane_ids" not in chunks[0]
    assert "required_lane_ids" not in chunks[0]
    assert "lane_statuses" not in chunks[0]


def test_default_config_accepts_dynamic_stage1_managed_paths(tmp_path):
    import json
    from pathlib import Path

    from storygraph_lib.output_writer import validate_managed_output_path

    config = json.loads(
        Path("skill-src/storygraph/config/storygraph.default.json").read_text(
            encoding="utf-8"
        )
    )
    managed_outputs = config["writer_policy"]["managed_outputs"]
    dynamic_paths = [
        "intermediate/task-packets/chunk-0042/relation_network.json",
        "intermediate/lane-outputs/chunk-0042/relation_network/run-007.json",
        "intermediate/reviewed-bundles/chunk-0042.json",
    ]

    for rel_path in dynamic_paths:
        result = validate_managed_output_path(
            graph_dir=tmp_path / "mini_novel.storygraph",
            relative_path=rel_path,
            managed_outputs=managed_outputs,
        )
        assert result.ok is True


def test_default_config_rejects_unsafe_dynamic_stage1_output_paths(tmp_path):
    import json
    from pathlib import Path

    from storygraph_lib.output_writer import validate_managed_output_path

    config = json.loads(
        Path("skill-src/storygraph/config/storygraph.default.json").read_text(
            encoding="utf-8"
        )
    )
    managed_outputs = config["writer_policy"]["managed_outputs"]

    for rel_path in [
        "../intermediate/task-packets/chunk-0042/relation_network.json",
        "/intermediate/task-packets/chunk-0042/relation_network.json",
        "intermediate/task-packets/chunk-0042/relation_network\0.json",
    ]:
        result = validate_managed_output_path(
            graph_dir=tmp_path / "mini_novel.storygraph",
            relative_path=rel_path,
            managed_outputs=managed_outputs,
        )
        assert result.ok is False


def test_default_config_rejects_deeper_dynamic_stage1_output_paths(tmp_path):
    import json
    from pathlib import Path

    from storygraph_lib.output_writer import validate_managed_output_path

    config = json.loads(
        Path("skill-src/storygraph/config/storygraph.default.json").read_text(
            encoding="utf-8"
        )
    )
    managed_outputs = config["writer_policy"]["managed_outputs"]

    for rel_path in [
        "intermediate/task-packets/chunk-0001/subdir/characters.json",
        "intermediate/lane-outputs/chunk-0001/characters/deeper/run-001.json",
        "intermediate/reviewed-bundles/chunk-0001/deeper.json",
    ]:
        result = validate_managed_output_path(
            graph_dir=tmp_path / "mini_novel.storygraph",
            relative_path=rel_path,
            managed_outputs=managed_outputs,
        )
        assert result.ok is False


def test_validate_managed_output_path_rejects_wildcards_in_actual_output_path(tmp_path):
    from storygraph_lib.output_writer import validate_managed_output_path

    managed_outputs = ["intermediate/task-packets/*/*.json"]

    for rel_path in [
        "intermediate/task-packets/chunk-0001/a*.json",
        "intermediate/task-packets/chunk-0001/a?.json",
    ]:
        result = validate_managed_output_path(
            graph_dir=tmp_path / "mini_novel.storygraph",
            relative_path=rel_path,
            managed_outputs=managed_outputs,
        )
        assert result.ok is False
        assert result.errors == [f"unmanaged_output:{rel_path}"]


def test_validate_managed_output_path_rejects_non_string_actual_output_path(tmp_path):
    from storygraph_lib.output_writer import validate_managed_output_path

    result = validate_managed_output_path(
        graph_dir=tmp_path / "mini_novel.storygraph",
        relative_path=123,
        managed_outputs=["*"],
    )

    assert result.ok is False
    assert result.normalized_path is None
    assert result.errors == ["unmanaged_output:123"]


def test_validate_managed_output_path_rejects_windows_ads_colon_path(tmp_path):
    from storygraph_lib.output_writer import validate_managed_output_path

    rel_path = "intermediate/task-packets/chunk-0001/events:ads.json"
    result = validate_managed_output_path(
        graph_dir=tmp_path / "mini_novel.storygraph",
        relative_path=rel_path,
        managed_outputs=["intermediate/task-packets/*/*.json"],
    )

    assert result.ok is False
    assert result.errors == [f"unmanaged_output:{rel_path}"]
