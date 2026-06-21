from types import SimpleNamespace


class _ValidationOk:
    ok = True


def test_stage1_idempotency_hash_includes_reviewed_output_manifest():
    from storygraph_lib.state import compute_stage1_input_hash

    base = compute_stage1_input_hash(
        source_hash="source-a",
        config_hash="config-a",
        template_inventory_hash="templates-a",
        task_packet_schema_hash="packet-schema-a",
        requirements_hash="requirements-a",
        reviewed_output_manifest_hash="reviewed-a",
    )
    changed = compute_stage1_input_hash(
        source_hash="source-a",
        config_hash="config-a",
        template_inventory_hash="templates-a",
        task_packet_schema_hash="packet-schema-a",
        requirements_hash="requirements-a",
        reviewed_output_manifest_hash="reviewed-b",
    )

    assert base != changed


def test_stage1_idempotency_hash_includes_requirements_hash():
    from storygraph_lib.state import compute_stage1_input_hash

    base = compute_stage1_input_hash(
        source_hash="source-a",
        config_hash="config-a",
        template_inventory_hash="templates-a",
        task_packet_schema_hash="packet-schema-a",
        requirements_hash="requirements-a",
        reviewed_output_manifest_hash="reviewed-a",
    )
    changed = compute_stage1_input_hash(
        source_hash="source-a",
        config_hash="config-a",
        template_inventory_hash="templates-a",
        task_packet_schema_hash="packet-schema-a",
        requirements_hash="requirements-b",
        reviewed_output_manifest_hash="reviewed-a",
    )

    assert base != changed


def test_stage1_state_rebuilds_on_unreadable_manifest(tmp_path):
    from storygraph_lib.state import stage1_state

    graph_dir = tmp_path / "mini.storygraph"
    graph_dir.mkdir()
    (graph_dir / "manifest.json").write_bytes(b"\xff")

    ctx = SimpleNamespace(graph_dir=graph_dir, source_hash="h")
    result = stage1_state(ctx, "cfg", lambda _: _ValidationOk())

    assert result["action"] == "rebuild"
    assert result["source_state"] == "changed"


def test_stage1_state_rebuilds_on_deep_manifest_json(tmp_path):
    from storygraph_lib.state import stage1_state

    graph_dir = tmp_path / "mini.storygraph"
    graph_dir.mkdir()
    (graph_dir / "manifest.json").write_text("[" * 5000 + "]" * 5000, encoding="utf-8")

    ctx = SimpleNamespace(graph_dir=graph_dir, source_hash="h")
    result = stage1_state(ctx, "cfg", lambda _: _ValidationOk())

    assert result["action"] == "rebuild"
    assert result["source_state"] == "changed"
