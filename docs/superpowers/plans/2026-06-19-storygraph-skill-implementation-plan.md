# StoryGraph Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 创建一个可安装的 `storygraph` Codex skill，用模板感知的方式为整部小说生成可追溯、可校验、可复用的知识图谱，并为阶段 2 的动态模板集合全文抽取建立结构化基础；当前 CultivationWorld 样例集成检查的模板数为 37，但通用完整性契约不得写死该数量。

**Architecture:** 采用 Skill 指令层、配置层、脚本工具层分离的本地源码仓库方案。核心执行流使用 Pipeline 模式串联路径解析、模板需求、图构建、覆盖账本和验证；通过 Adapter 模式复用 graphify，通过 Strategy 配置分块、覆盖、写入和子 agent 策略。

**Tech Stack:** PowerShell 5.1+ safe commands, Python 3.11+ standard library, pytest, JSON files, Codex skill filesystem layout, local graphify adapter.

---

## File Structure

计划实施完成后的文件结构如下。所有可变路径、模板目录、graphify 来源、阈值、阶段开关和写入策略必须来自配置或命令参数，不写成本机默认硬编码。

```text
E:\AI_Projects\StoryGraph\
  .gitignore
  pyproject.toml
  skill-src\
    storygraph\
      SKILL.md
      agents\
        openai.yaml
      config\
        storygraph.default.json
      references\
        workflow.md
        graph-schema.md
        extraction-workflow.md
      scripts\
        storygraph.py
        sync-skill.ps1
        storygraph_lib\
          __init__.py
          agent_ledger.py
          cli.py
          config.py
          coverage.py
          graph_schema.py
          graphify_adapter.py
          ids.py
          manifest.py
          output_writer.py
          paths.py
          stage1.py
          stage2_schema.py
          state.py
          template_aware.py
          template_rules.py
          templates.py
          validation.py
  tests\
    fixtures\
      mini_novel.txt
      templates\
        README.md
        有限视角与叙事日志模板.md
        角色AI行为参考模板.md
    test_agent_ledger.py
    test_config.py
    test_graph_schema.py
    test_graphify_adapter.py
    test_paths_manifest.py
    test_skill_structure.py
    test_stage1.py
    test_stage1_idempotency.py
    test_stage2_schema.py
    test_stage2_policy.py
    test_template_aware.py
    test_template_rules.py
    test_templates.py
    test_validation_cli.py
  docs\
    storygraph-cli.md
    superpowers\
      specs\
        2026-06-19-storygraph-skill-design.md
      plans\
        2026-06-19-storygraph-skill-implementation-plan.md
```

Responsibility map:

- `skill-src/storygraph/SKILL.md`: skill 触发场景、入口流程、阶段边界、必须读取的 reference 文件。
- `skill-src/storygraph/config/storygraph.default.json`: 便携默认配置；不包含本机绝对路径。
- `storygraph_lib/config.py`: 默认配置、项目本地覆盖、命令参数覆盖的合并策略。
- `storygraph_lib/paths.py`: 小说路径解析、图目录命名、源文件哈希和安全写入路径。
- `storygraph_lib/templates.py`: 模板发现、README 缺失项告警、动态模板需求矩阵装配；37 仅作为当前 CultivationWorld 样例集成检查值。
- `storygraph_lib/template_rules.py`: 可配置 Markdown 模板解析规则，提取字段、表格、卡片、案例、证据字段和 gap rules。
- `storygraph_lib/template_aware.py`: 基于模板需求矩阵和小说分块生成补充节点、边、事件、evidence 和逐需求 coverage 状态。
- `storygraph_lib/graphify_adapter.py`: graphify CLI/Python 能力的外层适配，不修改 graphify 源码。
- `storygraph_lib/graph_schema.py`: canonical graph schema、稳定 ID、StoryGraph 扩展合并。
- `storygraph_lib/coverage.py`: `chunk-ledger.json`、`evidence-index.json`、`template-readiness.json`、gap report。
- `storygraph_lib/agent_ledger.py`: 动态子 agent 运行记录 schema 和 single-writer 约束。
- `storygraph_lib/output_writer.py`: 受管输出路径注册表，阻止 Stage 1/2 写入未声明产物。
- `storygraph_lib/stage1.py`: 阶段 1 pipeline 编排。
- `storygraph_lib/stage2_schema.py`: 阶段 2 extraction JSON schema 和 Markdown 证据规则骨架。
- `storygraph_lib/state.py`: 幂等复用、原文 hash 改变检测、no-overwrite/draft 写入策略。
- `storygraph_lib/validation.py`: skill 结构、配置、模板矩阵、图 schema、coverage、幂等验证。
- `scripts/storygraph.py`: CLI 入口，只做参数解析和调用 `storygraph_lib.cli.main()`。
- `scripts/sync-skill.ps1`: 从源码目录同步到个人 skill 安装目录；默认不删除用户临时文件。
- `docs/storygraph-cli.md`: 本地开发、验证、同步安装和阶段运行命令。

## Cross-Cutting Architecture Checks

- 通用架构检查：每个任务都必须保持 Skill 指令层、配置层、脚本工具层分离；阶段 1 建图与阶段 2 模板抽取分离；graphify adapter 与 StoryGraph 小说领域逻辑分离。
- 设计模式适配检查：Pipeline 用于阶段执行，Adapter 用于 graphify，Strategy 用于分块、覆盖、写入和 agent 策略，Single-writer 用于关键 JSON 产物写入。
- 配置化覆盖检查：模板目录、graphify 仓库、图目录后缀、支持扩展名、分块参数、覆盖阈值、覆盖写入策略、阶段开关、agent 并发数、README 缺失模板策略都必须能从默认配置、local override 或 CLI 参数获得。

PowerShell 命令统一使用下列 UTF-8 前缀，任务中的命令均可直接复制执行：

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null
```

### Task 1: Baseline Repository And Skill Source Structure

**Files:**
- Create: `E:\AI_Projects\StoryGraph\.gitignore`
- Create: `E:\AI_Projects\StoryGraph\pyproject.toml`
- Create: `E:\AI_Projects\StoryGraph\skill-src\storygraph\SKILL.md`
- Create: `E:\AI_Projects\StoryGraph\skill-src\storygraph\agents\openai.yaml`
- Create: `E:\AI_Projects\StoryGraph\skill-src\storygraph\references\workflow.md`
- Create: `E:\AI_Projects\StoryGraph\skill-src\storygraph\references\graph-schema.md`
- Create: `E:\AI_Projects\StoryGraph\skill-src\storygraph\references\extraction-workflow.md`
- Create: `E:\AI_Projects\StoryGraph\skill-src\storygraph\scripts\storygraph.py`
- Create: `E:\AI_Projects\StoryGraph\skill-src\storygraph\scripts\storygraph_lib\__init__.py`
- Create: `E:\AI_Projects\StoryGraph\skill-src\storygraph\scripts\storygraph_lib\cli.py`
- Test: `E:\AI_Projects\StoryGraph\tests\test_skill_structure.py`

- [ ] **Step 1: Initialize git and write the failing structure test**

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; git init -b main
```

```python
# tests/test_skill_structure.py
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skill-src" / "storygraph"

def test_skill_source_structure_exists():
    required = [
        "SKILL.md",
        "agents/openai.yaml",
        "references/workflow.md",
        "references/graph-schema.md",
        "references/extraction-workflow.md",
        "scripts/storygraph.py",
        "scripts/storygraph_lib/__init__.py",
        "scripts/storygraph_lib/cli.py",
    ]
    missing = [path for path in required if not (SKILL / path).exists()]
    assert missing == []
```

- [ ] **Step 2: Run structure test and confirm it fails**

Run:

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python -m pytest tests\test_skill_structure.py::test_skill_source_structure_exists -v
```

Expected: `FAIL` with missing skill files listed.

- [ ] **Step 3: Create minimal skill files with correct boundaries**

```markdown
<!-- skill-src/storygraph/SKILL.md -->
---
name: storygraph
description: Build a template-aware novel knowledge graph for downstream worldbuilding reference extraction.
---

# StoryGraph

Use when the user provides a novel source path and asks to build, validate, reuse, or extract from a StoryGraph graph.

Read in order:
1. `references/workflow.md`
2. `references/graph-schema.md`
3. `references/extraction-workflow.md`

Run `scripts/storygraph.py validate-skill` before reporting the skill source as ready.
```

```yaml
# skill-src/storygraph/agents/openai.yaml
name: storygraph
model: gpt-5
role: storygraph-skill-worker
description: Build and validate template-aware novel graphs before any downstream extraction.
instructions:
  - Read SKILL.md and the referenced workflow documents before running commands.
  - Treat graph construction, template analysis, coverage review, and extraction as separate stages.
  - Write only through configured StoryGraph output writers; never overwrite user-authored documents by default.
  - Record every stage in coverage/agent-run-ledger.json with assigned inputs, outputs, status, and errors.
```

```markdown
<!-- skill-src/storygraph/references/workflow.md -->
# StoryGraph Workflow

1. Validate the skill source with `scripts/storygraph.py validate-skill`.
2. Load `config/storygraph.default.json`, optional `storygraph.local.json`, then CLI overrides in that order.
3. Discover template files from the configured template directory. Existing template files define the integration scope; README-only entries are warnings.
4. Build the Stage 1 graph into `<novel-stem>.storygraph/`.
5. Require the Stage 1 manifest, graphify outputs, requirement matrix, coverage ledgers, and gap report before any Stage 2 extraction.
6. Stage 2 is draft-first. Existing formal Markdown documents are not overwritten unless the configured output policy explicitly allows backup overwrite or merge.
```

```markdown
<!-- skill-src/storygraph/references/graph-schema.md -->
# StoryGraph Graph Schema

The canonical graph preserves graphify-native fields and adds StoryGraph template-aware fields.

Required top-level fields:
- `nodes`
- `edges`
- `hyperedges`
- `events`
- `evidence_index`
- `metadata`

StoryGraph extension nodes, edges, events, and evidence records require:
- stable `id` or `evidence_id`
- source location or source range
- `evidence_ids` where applicable
- `supports_templates`
- `confidence`
- `verification_status`

Graphify-native nodes may remain in the graph without StoryGraph-only fields before merge. Any node, edge, event, or evidence item created or modified by StoryGraph must pass the full StoryGraph validation contract.
```

```markdown
<!-- skill-src/storygraph/references/extraction-workflow.md -->
# Extraction Workflow

Stage 2 is a schema scaffold in this plan, not a complete extraction implementation.

Every future extraction record must cite Stage 1 graph evidence, template requirements, and chunk ranges. Output categories, draft directory, allowed overwrite actions, and render targets come from configuration rather than Python constants.
```

```python
# skill-src/storygraph/scripts/storygraph.py
from storygraph_lib.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
```

```python
# skill-src/storygraph/scripts/storygraph_lib/cli.py
def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="storygraph")
    parser.add_argument("--version", action="store_true")
    args = parser.parse_args(argv)
    if args.version:
        print("storygraph 0.1.0")
    return 0
```

```python
# skill-src/storygraph/scripts/storygraph_lib/__init__.py
"""StoryGraph skill runtime helpers."""

__all__ = ["__version__"]
__version__ = "0.1.0"
```

- [ ] **Step 4: Add project metadata and ignored local artifacts**

```toml
# pyproject.toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["skill-src/storygraph/scripts"]
```

```gitignore
# .gitignore
__pycache__/
.pytest_cache/
*.pyc
storygraph.local.json
*.storygraph/
```

- [ ] **Step 5: Run structure test and confirm it passes**

Run:

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python -m pytest tests\test_skill_structure.py -v
```

Expected: `1 passed`.

- [ ] **Step 6: Commit baseline structure**

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; git -c core.quotePath=false add .gitignore pyproject.toml skill-src tests; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; git commit -m "chore: add storygraph skill source skeleton"; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

### Task 2: Sync And Install Workflow

**Files:**
- Create: `E:\AI_Projects\StoryGraph\skill-src\storygraph\scripts\sync-skill.ps1`
- Create: `E:\AI_Projects\StoryGraph\skill-src\storygraph\scripts\storygraph_lib\validation.py`
- Modify: `E:\AI_Projects\StoryGraph\skill-src\storygraph\scripts\storygraph_lib\cli.py`
- Test: `E:\AI_Projects\StoryGraph\tests\test_validation_cli.py`

- [ ] **Step 1: Write failing validation tests for syncable structure**

```python
# tests/test_validation_cli.py
from pathlib import Path
from storygraph_lib.validation import validate_skill_tree

def test_validate_skill_tree_requires_core_directories(tmp_path):
    root = tmp_path / "storygraph"
    (root / "references").mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / "config").mkdir()
    (root / "agents").mkdir()
    (root / "SKILL.md").write_text("# StoryGraph\n", encoding="utf-8")
    (root / "agents" / "openai.yaml").write_text("name: storygraph\n", encoding="utf-8")
    (root / "config" / "storygraph.default.json").write_text("{}", encoding="utf-8")
    (root / "references" / "workflow.md").write_text("# Workflow\n", encoding="utf-8")
    (root / "references" / "graph-schema.md").write_text("# Graph Schema\n", encoding="utf-8")
    (root / "references" / "extraction-workflow.md").write_text("# Extraction Workflow\n", encoding="utf-8")
    (root / "scripts" / "storygraph.py").write_text("print('ok')\n", encoding="utf-8")
    (root / "scripts" / "sync-skill.ps1").write_text("Write-Output 'ok'\n", encoding="utf-8")
    result = validate_skill_tree(root)
    assert result.ok is True
    assert result.missing == []

def test_sync_clean_script_contains_destination_boundary_guard():
    script = Path("skill-src/storygraph/scripts/sync-skill.ps1").read_text(encoding="utf-8")
    assert "[IO.Path]::GetFullPath($Destination).TrimEnd('\\')" in script
    assert ".codex\\skills\\storygraph" in script
    assert "if ($Clean -and $destinationRoot -ne $expectedResolved)" in script
    assert "Remove-Item -LiteralPath $target -Recurse -Force" in script

def test_sync_clean_refuses_unexpected_destination(tmp_path):
    source = tmp_path / "source"
    destination = tmp_path / "not-storygraph"
    source.mkdir()
    destination.mkdir()
    script = Path("skill-src/storygraph/scripts/sync-skill.ps1")
    result = __import__("subprocess").run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-Source", str(source), "-Destination", str(destination), "-Clean"], capture_output=True, text=True)
    assert result.returncode != 0
    assert "Refusing to clean unexpected destination" in (result.stderr + result.stdout)

def test_sync_without_clean_allows_custom_destination(tmp_path):
    source = tmp_path / "source"
    destination = tmp_path / "custom-storygraph"
    (source / "scripts").mkdir(parents=True)
    (source / "SKILL.md").write_text("# StoryGraph\n", encoding="utf-8")
    script = Path("skill-src/storygraph/scripts/sync-skill.ps1")
    result = __import__("subprocess").run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-Source", str(source), "-Destination", str(destination)], capture_output=True, text=True)
    assert result.returncode == 0
    assert (destination / "SKILL.md").exists()
```

- [ ] **Step 2: Run validation test and confirm it fails**

Run:

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python -m pytest tests\test_validation_cli.py::test_validate_skill_tree_requires_core_directories tests\test_validation_cli.py::test_sync_clean_refuses_unexpected_destination -v
```

Expected: `FAIL` because `storygraph_lib.validation` is not defined.

- [ ] **Step 3: Implement minimal skill tree validator and CLI command**

```python
# skill-src/storygraph/scripts/storygraph_lib/validation.py
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    missing: list[str]

def validate_skill_tree(root: Path) -> ValidationResult:
    required = [
        "SKILL.md",
        "agents/openai.yaml",
        "config/storygraph.default.json",
        "references/workflow.md",
        "references/graph-schema.md",
        "references/extraction-workflow.md",
        "scripts/storygraph.py",
        "scripts/sync-skill.ps1"
    ]
    missing = [item for item in required if not (root / item).exists()]
    return ValidationResult(ok=not missing, missing=missing)
```

```python
# skill-src/storygraph/scripts/storygraph_lib/cli.py
from pathlib import Path
from .validation import validate_skill_tree

def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="storygraph")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate-skill")
    validate.add_argument("--skill-root", default=str(Path(__file__).resolve().parents[2]))
    args = parser.parse_args(argv)
    if args.command == "validate-skill":
        result = validate_skill_tree(Path(args.skill_root))
        if not result.ok:
            print({"ok": False, "missing": result.missing})
            return 2
        print({"ok": True, "missing": []})
        return 0
    return 2
```

- [ ] **Step 4: Add safe sync script that preserves unrelated install files by default**

```powershell
# skill-src/storygraph/scripts/sync-skill.ps1
param(
  [string]$Source = (Resolve-Path -LiteralPath "$PSScriptRoot\..").Path,
  [string]$Destination = "$env:USERPROFILE\.codex\skills\storygraph",
  [switch]$Clean
)
$ErrorActionPreference = "Stop"
$items = @("SKILL.md", "agents", "references", "scripts", "config")
$sourceRoot = (Resolve-Path -LiteralPath $Source).Path
New-Item -ItemType Directory -Path $Destination -Force | Out-Null
$destinationRoot = [IO.Path]::GetFullPath($Destination).TrimEnd('\')
$expectedRoot = Join-Path $env:USERPROFILE ".codex\skills\storygraph"
$expectedResolved = [IO.Path]::GetFullPath($expectedRoot).TrimEnd('\')
if ($Clean -and $destinationRoot -ne $expectedResolved) {
  throw "Refusing to clean unexpected destination: $destinationRoot"
}
if ($Clean) {
  foreach ($item in $items) {
    $target = Join-Path $destinationRoot $item
    $resolvedParent = Split-Path -Parent $target
    $resolvedParentFull = [IO.Path]::GetFullPath($resolvedParent).TrimEnd('\')
    if ($resolvedParentFull -ne $destinationRoot) {
      throw "Refusing to remove path outside destination: $target"
    }
    if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Recurse -Force }
  }
}
foreach ($item in $items) {
  $from = Join-Path $sourceRoot $item
  if (Test-Path -LiteralPath $from) {
    Copy-Item -LiteralPath $from -Destination $destinationRoot -Recurse -Force
  }
}
Write-Output "Synced StoryGraph skill to $destinationRoot"
```

- [ ] **Step 5: Run validation and sync dry target test**

Run:

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python -m pytest tests\test_validation_cli.py -v
```

Expected: pytest reports `4 passed`. Full `validate-skill --skill-root skill-src\storygraph` is run in Task 3 after the default config file exists.

- [ ] **Step 6: Commit sync workflow**

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; git -c core.quotePath=false add skill-src\storygraph\scripts tests\test_validation_cli.py; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; git commit -m "feat: add storygraph skill sync validation"; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

### Task 3: Portable Config And Local Override

**Files:**
- Create: `E:\AI_Projects\StoryGraph\skill-src\storygraph\config\storygraph.default.json`
- Create: `E:\AI_Projects\StoryGraph\skill-src\storygraph\scripts\storygraph_lib\config.py`
- Modify: `E:\AI_Projects\StoryGraph\skill-src\storygraph\scripts\storygraph_lib\cli.py`
- Test: `E:\AI_Projects\StoryGraph\tests\test_config.py`

- [ ] **Step 1: Write failing tests for default config and local override merge**

```python
# tests/test_config.py
import json
from pathlib import Path
from storygraph_lib.config import load_config

def test_default_config_is_portable_and_local_override_wins(tmp_path):
    default = tmp_path / "storygraph.default.json"
    local = tmp_path / "storygraph.local.json"
    default.write_text(json.dumps({"graph_dir_suffix": ".storygraph", "paths": {"template_dir": None}, "agent_policy": {"max_parallel": 6}, "template_parser_rules": {"field_headings": ["字段"]}}), encoding="utf-8")
    local.write_text(json.dumps({"paths": {"template_dir": "E:/Templates"}, "agent_policy": {"max_parallel": 2}}), encoding="utf-8")
    config = load_config(default, local_override=local)
    assert config["paths"]["template_dir"] == "E:/Templates"
    assert config["agent_policy"]["max_parallel"] == 2
    assert config["template_parser_rules"]["field_headings"] == ["字段"]
    assert "E:/Templates" not in default.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run config test and confirm it fails**

Run:

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python -m pytest tests\test_config.py::test_default_config_is_portable_and_local_override_wins -v
```

Expected: `FAIL` because `storygraph_lib.config` is not defined.

- [ ] **Step 3: Add portable default config**

```json
{
  "graph_dir_suffix": ".storygraph",
  "paths": {
    "template_dir": null,
    "graphify_repo": null,
    "project_override_file": "storygraph.local.json"
  },
  "supported_source_exts": [".txt", ".md"],
  "output_language": "zh-CN",
  "template_discovery": {
    "glob": "*模板.md",
    "exclude_files": ["README.md"],
    "readme_index_file": "README.md",
    "readme_missing_policy": "warn",
    "require_all_templates_scope": "existing_template_files"
  },
  "stages": {
    "build_template_aware_graph": true,
    "extract_template_documents": false
  },
  "graphify_adapter": {
    "mode": "local-repo-or-cli",
    "allowed_modes": ["local-repo", "cli", "local-repo-or-cli"],
    "canonical_graph_policy": "merge-template-aware-supplements",
    "command": ["python", "-m", "graphify.cli", "build", "--input", "{source}", "--output", "{output_dir}"],
    "timeout_seconds": 1800
  },
  "status_enums": {
    "requirement_statuses": ["covered", "needs_review", "not_found_in_source"],
    "verification_statuses": ["verified", "needs_review", "rejected"],
    "confidence_levels": ["EXTRACTED", "INFERRED", "AMBIGUOUS"]
  },
  "template_count_policy": {
    "scope": "existing_template_files",
    "expected_existing_templates": 37,
    "enforce_integration_count": true
  },
  "template_parser_rules": {
    "field_headings": ["字段", "字段说明", "核心字段", "输出字段"],
    "table_markers": ["|", "表格", "清单"],
    "card_markers": ["卡片", "档案", "条目卡"],
    "case_markers": ["案例", "示例", "样例", "场景"],
    "evidence_markers": ["证据", "原文", "引用", "依据"],
    "gap_markers": ["缺口", "待核验", "未见可靠证据"]
  },
  "template_graph_mappings": {
    "有限视角与叙事日志": {
      "graph_node_mapping": ["perspective"],
      "graph_event_mapping": ["narrative_view"],
      "graph_relation_mapping": ["known_unknown"]
    },
    "角色AI行为参考": {
      "graph_node_mapping": ["decision", "resource_constraint"],
      "graph_event_mapping": ["action_chain"],
      "graph_relation_mapping": ["constraint_outcome"]
    },
    "记忆情绪与执念": {
      "graph_node_mapping": ["emotion_memory"],
      "graph_event_mapping": ["emotion_trigger"],
      "graph_relation_mapping": ["long_term_influence"]
    },
    "相遇剧情与对话设计": {
      "graph_node_mapping": ["scene_dialogue"],
      "graph_event_mapping": ["encounter"],
      "graph_relation_mapping": ["attitude_change", "information_exchange"]
    },
    "动态事件与机会点": {
      "graph_node_mapping": ["opportunity"],
      "graph_event_mapping": ["time_causality"],
      "graph_relation_mapping": ["trigger_effect"]
    },
    "事件因果链（长程因果图）": {
      "graph_node_mapping": ["timepoint"],
      "graph_event_mapping": ["time_causality"],
      "graph_relation_mapping": ["precondition", "delayed_effect"]
    },
    "default_mapping": {
      "graph_node_mapping": ["template_specific_node"],
      "graph_event_mapping": ["template_specific_event"],
      "graph_relation_mapping": ["template_specific_relation"]
    }
  },
  "supplemental_graph_policy": {
    "write_to_canonical_graph": true,
    "sidecar_dir": "template-graph",
    "fail_stage_if_canonical_merge_fails": true
  },
  "chunk_strategy": {
    "mode": "chapter-aware",
    "allowed_modes": ["chapter-aware", "bounded-chars"],
    "fallback_mode": "bounded-chars",
    "max_chars": 20000,
    "overlap_chars": 1200,
    "chapter_heading_patterns": ["^第.+章", "^Chapter\\s+\\d+"]
  },
  "evidence_matching_strategy": {
    "mode": "substring",
    "allowed_modes": ["substring", "regex", "external-reranker"],
    "case_sensitive": false,
    "minimum_confidence": "EXTRACTED"
  },
  "template_requirements_strategy": {
    "mode": "auto-from-templates",
    "allow_manual_overrides": true
  },
  "stage2_categories": {
    "facts": "原作事实",
    "judgments": "我的判断",
    "pending_verifications": "待核验",
    "not_found_items": "未见可靠证据"
  },
  "overwrite_policy": "draft",
  "stage2_output_policy": {
    "default_dir": "drafts",
    "allow_overwrite_existing_docs": false,
    "existing_document_action": "write_versioned_draft",
    "allowed_policies": ["draft", "backup-and-overwrite", "merge"],
    "draft_action": "write_draft"
  },
  "writer_policy": {
    "mode": "single-writer",
    "managed_outputs": [
      "manifest.json",
      "graphify-out/graph.json",
      "graphify-out/GRAPH_REPORT.md",
      "graphify-out/graph.html",
      "requirements/template-requirements.json",
      "coverage/chunk-ledger.json",
      "coverage/evidence-index.json",
      "coverage/template-readiness.json",
      "coverage/agent-run-ledger.json",
      "coverage/gap-report.md",
      "coverage/template-run-ledger.json",
      "coverage/template-evidence-usage.json",
      "coverage/template-gap-report.md"
    ]
  },
  "agent_policy": {
    "enabled": true,
    "max_parallel": 6,
    "write_conflict_policy": "single-writer"
  },
  "coverage_thresholds": {
    "require_all_templates": true,
    "require_all_chunks_scanned": true,
    "readiness_warning_threshold": 0.8,
    "block_on_missing_requirement_mapping": true,
    "block_on_low_readiness": true,
    "block_on_template_without_reliable_evidence": true,
    "block_on_unparsable_subagent_json": true
  }
}
```

以上 `template_count_policy.expected_existing_templates: 37` 只用于当前 CultivationWorld 样例目录的集成检查；通用实现和单元测试必须以发现到的 `requirements.templates` 动态集合、`requirements.template_count` 和 readiness 记录为准。

真实模板集合的逐模板映射来自 `template_graph_mappings`、本地 override、或模板解析生成的配置化规则；不得把完整模板映射表写成 Python 常量。`default_mapping` 只允许作为临时配置 fallback，并且集成验证必须证明动态发现到的模板都有非空、非泛型、可配置 mapping；当前 CultivationWorld 样例可配置检查值为 37，但实现逻辑不得写死该数量。

- [ ] **Step 4: Implement recursive config merge**

```python
# skill-src/storygraph/scripts/storygraph_lib/config.py
import json
from pathlib import Path

def _deep_merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged

def load_config(default_path: Path, local_override: Path | None = None, cli_overrides: dict | None = None) -> dict:
    config = json.loads(default_path.read_text(encoding="utf-8"))
    if local_override and local_override.exists():
        config = _deep_merge(config, json.loads(local_override.read_text(encoding="utf-8")))
    if cli_overrides:
        config = _deep_merge(config, cli_overrides)
    return config
```

- [ ] **Step 5: Add `config-check` CLI and run tests**

```python
# replace skill-src/storygraph/scripts/storygraph_lib/cli.py after adding config-check
from pathlib import Path
from .config import load_config
from .validation import validate_skill_tree

def _default_config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "storygraph.default.json"

def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="storygraph")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate-skill")
    validate.add_argument("--skill-root", default=str(Path(__file__).resolve().parents[2]))
    config_check = sub.add_parser("config-check")
    config_check.add_argument("--local-override")
    args = parser.parse_args(argv)
    if args.command == "validate-skill":
        result = validate_skill_tree(Path(args.skill_root))
        print({"ok": result.ok, "missing": result.missing})
        return 0 if result.ok else 2
    if args.command == "config-check":
        local = Path(args.local_override) if args.local_override else None
        config = load_config(_default_config_path(), local_override=local)
        print({"ok": True, "graph_dir_suffix": config["graph_dir_suffix"]})
        return 0
    return 2
```

The command must be registered in `main`; an uncalled helper is not sufficient.

```python
# tests/test_config.py
def test_config_check_command_is_registered(capsys):
    from storygraph_lib.cli import main
    assert main(["config-check"]) == 0
    assert "graph_dir_suffix" in capsys.readouterr().out
```

Run:

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python -m pytest tests\test_config.py -v
```

Expected: config merge and registered `config-check` tests pass; pytest reports `2 passed`.

- [ ] **Step 6: Commit config layer**

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; git -c core.quotePath=false add skill-src\storygraph\config skill-src\storygraph\scripts\storygraph_lib tests\test_config.py .gitignore; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; git commit -m "feat: add portable storygraph config"; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

### Task 4: Phase 1 Path Parsing, Graph Directory, And Manifest

**Files:**
- Create: `E:\AI_Projects\StoryGraph\skill-src\storygraph\scripts\storygraph_lib\paths.py`
- Create: `E:\AI_Projects\StoryGraph\skill-src\storygraph\scripts\storygraph_lib\manifest.py`
- Test: `E:\AI_Projects\StoryGraph\tests\fixtures\mini_novel.txt`
- Test: `E:\AI_Projects\StoryGraph\tests\test_paths_manifest.py`

- [ ] **Step 1: Write failing tests for novel parsing and graph dir creation**

```python
# tests/test_paths_manifest.py
import json
from pathlib import Path
from storygraph_lib.paths import resolve_novel_context
from storygraph_lib.manifest import write_manifest

def test_resolve_novel_context_creates_independent_graph_dir(tmp_path):
    novel = tmp_path / "凡人修仙传.txt"
    novel.write_text("第一章 开端\n韩立进山。", encoding="utf-8")
    ctx = resolve_novel_context(novel, graph_dir_suffix=".storygraph", create=True)
    assert ctx.novel_name == "凡人修仙传"
    assert ctx.graph_dir == tmp_path / "凡人修仙传.storygraph"
    assert ctx.graph_dir.exists()

def test_manifest_records_source_hash_and_stage_status(tmp_path):
    novel = tmp_path / "mini.txt"
    novel.write_text("正文", encoding="utf-8")
    ctx = resolve_novel_context(novel, ".storygraph", create=True)
    manifest = write_manifest(ctx, config_hash="cfg", graphify_source="local")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["source_path"] == str(novel)
    assert data["stage_status"]["stage1"] == "initialized"
```

- [ ] **Step 2: Run path tests and confirm they fail**

Run:

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python -m pytest tests\test_paths_manifest.py -v
```

Expected: `FAIL` because `resolve_novel_context` and `write_manifest` are not defined.

- [ ] **Step 3: Implement path context and source hash**

```python
# skill-src/storygraph/scripts/storygraph_lib/paths.py
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

@dataclass(frozen=True)
class NovelContext:
    source_path: Path
    source_hash: str
    source_size: int
    novel_name: str
    novel_dir: Path
    graph_dir: Path

def file_sha256(path: Path) -> str:
    h = sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def resolve_novel_context(source_path: Path, graph_dir_suffix: str, create: bool = False) -> NovelContext:
    source = source_path.expanduser().resolve()
    graph_dir = source.parent / f"{source.stem}{graph_dir_suffix}"
    if create:
        graph_dir.mkdir(parents=True, exist_ok=True)
    return NovelContext(source, file_sha256(source), source.stat().st_size, source.stem, source.parent, graph_dir)
```

- [ ] **Step 4: Implement manifest writer with idempotent status fields**

```python
# skill-src/storygraph/scripts/storygraph_lib/manifest.py
import json
from datetime import datetime, timezone
from pathlib import Path
from .paths import NovelContext

def write_manifest(ctx: NovelContext, config_hash: str, graphify_source: str) -> Path:
    path = ctx.graph_dir / "manifest.json"
    now = datetime.now(timezone.utc).isoformat()
    data = {
        "source_path": str(ctx.source_path),
        "source_hash": ctx.source_hash,
        "source_size": ctx.source_size,
        "novel_name": ctx.novel_name,
        "graph_dir": str(ctx.graph_dir),
        "config_hash": config_hash,
        "graphify_repo": graphify_source,
        "graphify_version_or_commit": None,
        "created_at": now,
        "updated_at": now,
        "stage_status": {"stage1": "initialized", "stage2": "not_requested"}
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
```

- [ ] **Step 5: Run tests and a manual graph-dir smoke command**

Run:

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python -m pytest tests\test_paths_manifest.py -v
```

Expected: `2 passed`.

- [ ] **Step 6: Commit path and manifest layer**

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; git -c core.quotePath=false add skill-src\storygraph\scripts\storygraph_lib tests\test_paths_manifest.py tests\fixtures; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; git commit -m "feat: add storygraph path context and manifest"; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

### Task 5: Configurable Template Parsing And Dynamic Template Requirement Matrix

**Files:**
- Create: `E:\AI_Projects\StoryGraph\skill-src\storygraph\scripts\storygraph_lib\template_rules.py`
- Create: `E:\AI_Projects\StoryGraph\skill-src\storygraph\scripts\storygraph_lib\templates.py`
- Modify: `E:\AI_Projects\StoryGraph\skill-src\storygraph\scripts\storygraph_lib\cli.py`
- Modify: `E:\AI_Projects\StoryGraph\skill-src\storygraph\references\workflow.md`
- Test: `E:\AI_Projects\StoryGraph\tests\test_template_rules.py`
- Test: `E:\AI_Projects\StoryGraph\tests\test_templates.py`

- [ ] **Step 1: Write failing tests for rules-based parsing, README warnings, and dynamic template completeness**

```python
# tests/test_template_rules.py
from storygraph_lib.template_rules import parse_template_requirements

RULES = {
    "field_headings": ["字段"],
    "table_markers": ["|", "表格"],
    "card_markers": ["卡片"],
    "case_markers": ["案例"],
    "evidence_markers": ["证据", "原文"],
    "gap_markers": ["缺口", "待核验"]
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
```

```python
# tests/test_templates.py
import json
import os
from pathlib import Path
import pytest
from storygraph_lib.templates import discover_templates, build_requirement_matrix

def test_discover_templates_uses_existing_files_and_warns_missing_readme_items(tmp_path):
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "有限视角与叙事日志模板.md").write_text("# 有限视角与叙事日志模板\n## 字段\n- 视角持有者", encoding="utf-8")
    (template_dir / "角色AI行为参考模板.md").write_text("# 角色AI行为参考模板\n## 字段\n- 角色目标", encoding="utf-8")
    (template_dir / "README.md").write_text("- 有限视角与叙事日志模板.md\n- 缺失模板.md", encoding="utf-8")
    result = discover_templates(template_dir, glob="*模板.md", readme_index_file="README.md")
    assert [t.name for t in result.templates] == ["有限视角与叙事日志", "角色AI行为参考"]
    assert result.warnings == [{"code": "missing_template_file", "file": "缺失模板.md"}]

def test_build_requirement_matrix_uses_configured_non_generic_mappings(tmp_path):
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "法宝分析模板.md").write_text("# 法宝分析模板\n## 字段\n- 法宝\n## 证据要求\n- 原文位置", encoding="utf-8")
    discovery = discover_templates(template_dir, glob="*模板.md", readme_index_file="README.md")
    mappings = {
        "法宝分析": {
            "graph_node_mapping": ["artifact"],
            "graph_event_mapping": ["artifact_transfer"],
            "graph_relation_mapping": ["owner_artifact"]
        },
        "default_mapping": {
            "graph_node_mapping": ["template_specific_node"],
            "graph_event_mapping": ["template_specific_event"],
            "graph_relation_mapping": ["template_specific_relation"]
        }
    }
    matrix = build_requirement_matrix(discovery.templates, rules=None, mappings=mappings)
    record = matrix["templates"][0]
    assert record["graph_node_mapping"] == ["artifact"]
    assert record["mapping_source"] == "configured"
    assert record["required_card_headings"] == []
    assert record["required_card_fields"] == []

def test_build_requirement_matrix_derives_non_generic_mapping_from_template_parse_result(tmp_path):
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "丹药谱系模板.md").write_text("# 丹药谱系模板\n## 字段\n- 丹药\n## 案例\n- 筑基丹", encoding="utf-8")
    discovery = discover_templates(template_dir, glob="*模板.md", readme_index_file="README.md")
    matrix = build_requirement_matrix(discovery.templates, rules=None, mappings={"default_mapping": {"graph_node_mapping": ["template_specific_node"], "graph_event_mapping": ["template_specific_event"], "graph_relation_mapping": ["template_specific_relation"]}})
    record = matrix["templates"][0]
    assert record["mapping_source"] == "template_parse_result"
    assert record["graph_node_mapping"] == ["丹药谱系.node"]
    assert record["graph_event_mapping"] == ["丹药谱系.event"]
    assert record["graph_relation_mapping"] == ["丹药谱系.relation"]

def test_real_cultivationworld_templates_matrix_is_optional_integration_not_hermetic_pytest():
    template_root = os.environ.get("STORYGRAPH_REAL_TEMPLATE_DIR")
    if not template_root:
        pytest.skip("Set STORYGRAPH_REAL_TEMPLATE_DIR for local integration verification.")
    mappings_json = os.environ.get("STORYGRAPH_TEMPLATE_MAPPINGS_JSON")
    if not mappings_json:
        pytest.skip("Set STORYGRAPH_TEMPLATE_MAPPINGS_JSON so the integration test does not hard-code mappings.")
    template_dir = Path(template_root)
    discovery = discover_templates(template_dir, glob="*模板.md", readme_index_file="README.md")
    matrix = build_requirement_matrix(discovery.templates, rules=None, mappings=json.loads(mappings_json))
    assert matrix["template_count"] == len(discovery.templates)
    for record in matrix["templates"]:
        assert record["required_fields"] or record["required_tables"] or record["required_cards"] or record["required_case_patterns"]
        assert record["required_evidence_fields"]
        assert record["gap_rules"]["status_enum"] == ["covered", "needs_review", "not_found_in_source"]
        assert record["graph_node_mapping"]
        assert record["graph_event_mapping"]
        assert record["graph_relation_mapping"]
        assert record["mapping_source"] in {"configured", "template_parse_result"}
```

- [ ] **Step 2: Run template tests and confirm they fail**

Run:

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python -m pytest tests\test_template_rules.py tests\test_templates.py -v
```

Expected: `FAIL` because `storygraph_lib.template_rules` and `storygraph_lib.templates` are not defined.

- [ ] **Step 3: Implement configurable Markdown parser for fields, tables, cards, cases, evidence fields, and gap rules**

```python
# skill-src/storygraph/scripts/storygraph_lib/template_rules.py
def _heading(line: str) -> str | None:
    stripped = line.strip()
    return stripped.lstrip("# ").strip() if stripped.startswith("#") else None

def parse_template_requirements(template_name: str, text: str, rules: dict | None) -> dict:
    rules = rules or {
        "field_headings": ["字段", "字段说明", "核心字段", "输出字段"],
        "table_markers": ["|", "表格", "清单"],
        "card_markers": ["卡片", "档案", "条目卡"],
        "case_markers": ["案例", "示例", "样例", "场景"],
        "evidence_markers": ["证据", "原文", "引用", "依据"],
        "gap_markers": ["缺口", "待核验", "未见可靠证据"]
    }
    parsed = {"required_sections": [], "required_fields": [], "required_tables": [], "required_card_headings": [], "required_card_fields": [], "required_cards": [], "required_case_patterns": [], "required_evidence_fields": [], "gap_rules": {"markers": [], "status_enum": ["covered", "needs_review", "not_found_in_source"]}}
    section = ""
    table_header = None
    for raw in text.splitlines():
        line = raw.strip()
        title = _heading(line)
        if title:
            section = title
            parsed["required_sections"].append(title)
            if any(marker in title for marker in rules["card_markers"]):
                parsed["required_card_headings"].append(title)
                parsed["required_cards"].append(title)
            continue
        if line.startswith("|") and "|" in line.strip("|"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if cells and not all(set(cell) <= {"-"} for cell in cells):
                table_header = "|".join(cells)
                if table_header not in parsed["required_tables"]:
                    parsed["required_tables"].append(table_header)
            continue
        if line.startswith("- "):
            item = line[2:].strip()
            if any(marker in section for marker in rules["evidence_markers"]):
                parsed["required_evidence_fields"].append(item)
            elif any(marker in section for marker in rules["gap_markers"]):
                parsed["gap_rules"]["markers"].append(item)
            elif any(marker in section for marker in rules["case_markers"]):
                parsed["required_case_patterns"].append(item)
            elif any(marker in section for marker in rules["field_headings"]):
                parsed["required_fields"].append(item)
            elif any(marker in section for marker in rules["card_markers"]):
                parsed["required_card_fields"].append(item)
    if not parsed["required_evidence_fields"]:
        parsed["required_evidence_fields"] = ["source_path", "source_range", "fact_summary", "confidence", "verification_status"]
    if not (parsed["required_fields"] or parsed["required_tables"] or parsed["required_cards"] or parsed["required_case_patterns"]):
        parsed["required_fields"] = [template_name]
    return parsed
```

- [ ] **Step 4: Implement discovery and matrix assembly with explicit graph-layer mappings**

```python
# skill-src/storygraph/scripts/storygraph_lib/templates.py
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from .template_rules import parse_template_requirements

@dataclass(frozen=True)
class TemplateFile:
    name: str
    path: Path
    file_hash: str
    text: str

@dataclass(frozen=True)
class TemplateDiscovery:
    templates: list[TemplateFile]
    warnings: list[dict]

def _hash_text(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()

def discover_templates(template_dir: Path, glob: str = "*模板.md", readme_index_file: str = "README.md") -> TemplateDiscovery:
    files = sorted(template_dir.glob(glob), key=lambda p: p.name)
    templates = [TemplateFile(p.stem.removesuffix("模板"), p, _hash_text(p.read_text(encoding="utf-8")), p.read_text(encoding="utf-8")) for p in files]
    warnings = []
    readme = template_dir / readme_index_file
    if readme.exists():
        existing = {p.name for p in files}
        for line in readme.read_text(encoding="utf-8").splitlines():
            item = line.strip().lstrip("- ").strip()
            if item.endswith("模板.md") and item not in existing:
                warnings.append({"code": "missing_template_file", "file": item})
    return TemplateDiscovery(templates, warnings)

def _derive_mapping_from_template_parse(template_name: str, parsed: dict) -> dict | None:
    if parsed.get("required_sections") or parsed.get("required_fields") or parsed.get("required_case_patterns"):
        return {
            "graph_node_mapping": [f"{template_name}.node"],
            "graph_event_mapping": [f"{template_name}.event"],
            "graph_relation_mapping": [f"{template_name}.relation"]
        }
    return None

def _resolve_mapping(template_name: str, mappings: dict, parsed: dict) -> tuple[dict, str]:
    if template_name in mappings:
        return mappings[template_name], "configured"
    derived = _derive_mapping_from_template_parse(template_name, parsed)
    if derived:
        return derived, "template_parse_result"
    if "default_mapping" in mappings:
        return mappings["default_mapping"], "default_mapping"
    raise ValueError(f"missing_template_graph_mapping:{template_name}")

def build_requirement_matrix(templates: list[TemplateFile], rules: dict | None, mappings: dict, status_enums: dict | None = None, output_language: str = "zh-CN") -> dict:
    statuses = (status_enums or {}).get("requirement_statuses", ["covered", "needs_review", "not_found_in_source"])
    records = []
    for template in templates:
        parsed = parse_template_requirements(template.name, template.text, rules)
        mapping, mapping_source = _resolve_mapping(template.name, mappings, parsed)
        if not mapping.get("graph_node_mapping") or not mapping.get("graph_event_mapping") or not mapping.get("graph_relation_mapping"):
            raise ValueError(f"empty_template_graph_mapping:{template.name}")
        parsed["gap_rules"]["status_enum"] = statuses
        records.append({
            "template_name": template.name,
            "template_file": str(template.path),
            "template_file_hash": template.file_hash,
            "template_status": "available",
            "output_language": output_language,
            **parsed,
            "required_entity_types": mapping["graph_node_mapping"],
            "required_event_types": mapping["graph_event_mapping"],
            "required_relation_types": mapping["graph_relation_mapping"],
            **mapping,
            "mapping_source": mapping_source,
            "output_sections": parsed["required_sections"],
            "coverage_rules": {"statuses": parsed["gap_rules"]["status_enum"]}
        })
    return {"template_count": len(records), "templates": records}
```

- [ ] **Step 5: Replace CLI with registered `inspect-templates` command**

```python
# replace skill-src/storygraph/scripts/storygraph_lib/cli.py after Task 5
import json
from pathlib import Path
from .config import load_config
from .templates import build_requirement_matrix, discover_templates
from .validation import validate_skill_tree

def _default_config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "storygraph.default.json"

def _print_json(data):
    print(json.dumps(data, ensure_ascii=False, indent=2))

def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="storygraph")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate-skill")
    validate.add_argument("--skill-root", default=str(Path(__file__).resolve().parents[2]))
    config_check = sub.add_parser("config-check")
    config_check.add_argument("--local-override")
    inspect = sub.add_parser("inspect-templates")
    inspect.add_argument("--template-dir", required=True)
    args = parser.parse_args(argv)
    if args.command == "validate-skill":
        result = validate_skill_tree(Path(args.skill_root))
        _print_json({"ok": result.ok, "missing": result.missing})
        return 0 if result.ok else 2
    if args.command == "config-check":
        local = Path(args.local_override) if args.local_override else None
        config = load_config(_default_config_path(), local_override=local)
        _print_json({"ok": True, "graph_dir_suffix": config["graph_dir_suffix"]})
        return 0
    if args.command == "inspect-templates":
        config = load_config(_default_config_path())
        discovery = discover_templates(Path(args.template_dir), config["template_discovery"]["glob"], config["template_discovery"]["readme_index_file"])
        matrix = build_requirement_matrix(discovery.templates, config["template_parser_rules"], config["template_graph_mappings"], config["status_enums"], config["output_language"])
        template_details = [
            {
                "template_name": t["template_name"],
                "mapping_source": t["mapping_source"],
                "uses_default_mapping": t["mapping_source"] == "default_mapping",
                "graph_node_mapping": t["graph_node_mapping"],
                "graph_event_mapping": t["graph_event_mapping"],
                "graph_relation_mapping": t["graph_relation_mapping"],
            }
            for t in matrix["templates"]
        ]
        has_default_mapping = any(t["uses_default_mapping"] for t in template_details)
        _print_json({"template_count": matrix["template_count"], "warnings": discovery.warnings, "templates": template_details, "has_default_mapping": has_default_mapping})
        return 2 if has_default_mapping else 0
    return 2
```

Run:

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python skill-src\storygraph\scripts\storygraph.py inspect-templates --template-dir 'E:\AI_Projects\CultivationWorld\docs\世界观参考\模板'; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

Expected: JSON output contains the dynamically discovered `template_count`; for the current CultivationWorld sample that count is `37`. README-only missing files are warning objects with `code` equal to `missing_template_file`; every template record includes `template_name`, `mapping_source`, `uses_default_mapping`, `graph_node_mapping`, `graph_event_mapping`, and `graph_relation_mapping`; every discovered template reports `mapping_source` as `configured` or `template_parse_result`, not `default_mapping`; the command exits nonzero if the current CultivationWorld sample set uses any `default_mapping`.

- [ ] **Step 6: Run tests and commit template matrix**

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python -m pytest tests\test_template_rules.py tests\test_templates.py -v; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; git -c core.quotePath=false add skill-src\storygraph\scripts\storygraph_lib skill-src\storygraph\references tests\test_template_rules.py tests\test_templates.py; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; git commit -m "feat: add configurable template requirement matrix"; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

Expected: all hermetic tests in `test_template_rules.py` and `test_templates.py` pass. The real CultivationWorld sample completeness check is run through `STORYGRAPH_REAL_TEMPLATE_DIR` or the Final Review Gate CLI, not as a normal local-path-dependent pytest.

### Task 6: Canonical Graph Schema, Deep Validation, And Graphify Adapter

**Files:**
- Create: `E:\AI_Projects\StoryGraph\skill-src\storygraph\scripts\storygraph_lib\ids.py`
- Create: `E:\AI_Projects\StoryGraph\skill-src\storygraph\scripts\storygraph_lib\graph_schema.py`
- Create: `E:\AI_Projects\StoryGraph\skill-src\storygraph\scripts\storygraph_lib\graphify_adapter.py`
- Modify: `E:\AI_Projects\StoryGraph\skill-src\storygraph\references\graph-schema.md`
- Test: `E:\AI_Projects\StoryGraph\tests\test_graph_schema.py`
- Test: `E:\AI_Projects\StoryGraph\tests\test_graphify_adapter.py`

- [ ] **Step 1: Write failing tests for stable IDs, merge, and deep schema validation**

```python
# tests/test_graph_schema.py
from storygraph_lib.ids import stable_node_id, stable_edge_id, stable_event_id, stable_evidence_id
from storygraph_lib.graph_schema import merge_template_supplements, validate_canonical_graph

def test_stable_ids_are_repeatable_and_type_scoped():
    assert stable_node_id("凡人修仙传", "韩立", "person") == stable_node_id("凡人修仙传", "韩立", "person")
    assert stable_node_id("凡人修仙传", "韩立", "person") != stable_node_id("凡人修仙传", "韩立", "faction")
    assert stable_edge_id("凡人修仙传", "node:a", "node:b", "owns").startswith("edge:owns:")
    assert stable_event_id("凡人修仙传", "resource_gain", "韩立", [0, 12]).startswith("event:resource_gain:")
    assert stable_evidence_id("凡人修仙传", "chunk-0001", [0, 12]).startswith("evidence:")

def test_deep_validation_rejects_missing_evidence_and_bad_status():
    graph = {"nodes": [{"id": "node:person:abc", "label": "韩立", "node_type": "person", "evidence_ids": [], "supports_templates": [{"template_name": "法宝分析", "requirement_id": "法宝分析.required_fields.法宝", "status": "maybe"}], "confidence": "EXTRACTED", "verification_status": "verified"}], "edges": [], "hyperedges": [], "events": [], "evidence_index": [], "metadata": {}}
    result = validate_canonical_graph(graph)
    assert result.ok is False
    assert "missing:schema_version" in result.errors
    assert "missing:graphify_schema_version" in result.errors
    assert "missing:storygraph_schema_version" in result.errors
    assert "bad_requirement_status:maybe" in result.errors
    assert "node_without_evidence:node:person:abc" in result.errors

def test_deep_validation_requires_top_level_schema_versions():
    graph = {"nodes": [], "edges": [], "hyperedges": [], "events": [], "evidence_index": [], "metadata": {"graphify_schema_version": "x"}}
    errors = validate_canonical_graph(graph).errors
    assert "missing:schema_version" in errors
    assert "missing:graphify_schema_version" in errors
    assert "missing:storygraph_schema_version" in errors

def test_merge_template_supplements_preserves_graphify_fields_and_requires_non_empty_supports():
    base = {"nodes": [{"id": "node:person:abc", "label": "韩立"}], "edges": [], "hyperedges": [], "metadata": {"graphify_schema_version": "x"}}
    supplement = {"nodes": [{"id": "node:person:abc", "node_type": "person", "evidence_ids": ["evidence:1"], "supports_templates": [{"template_name": "法宝分析", "requirement_id": "法宝分析.required_fields.法宝", "status": "covered"}], "confidence": "EXTRACTED", "verification_status": "verified"}], "edges": [], "events": [], "evidence_index": [{"evidence_id": "evidence:1", "source_range": [0, 8], "fact_summary": "韩立获得小瓶", "confidence": "EXTRACTED", "verification_status": "verified", "supports_templates": [{"template_name": "法宝分析", "requirement_id": "法宝分析.required_fields.法宝", "status": "covered"}]}]}
    graph = merge_template_supplements(base, supplement)
    assert graph["nodes"][0]["label"] == "韩立"
    assert graph["metadata"]["graphify_schema_version"] == "x"
    assert validate_canonical_graph(graph).ok is True

def test_deep_validation_rejects_bad_edges_events_evidence_and_unknown_evidence():
    graph = {
        "nodes": [{"id": "node:item:1", "label": "小瓶", "node_type": "artifact", "evidence_ids": ["evidence:missing"], "supports_templates": [{"template_name": "法宝分析", "requirement_id": "r1", "status": "covered"}], "confidence": "EXTRACTED", "verification_status": "verified"}],
        "edges": [{"id": "edge:owns:1", "source": "node:item:1", "target": "node:missing", "edge_type": "owns", "evidence_ids": ["evidence:missing"], "supports_templates": [{"template_name": "法宝分析", "requirement_id": "r2", "status": "covered"}], "confidence": "CERTAIN", "verification_status": "verified"}],
        "hyperedges": [],
        "events": [{"id": "event:gain:1", "event_type": "gain", "participants": ["node:missing"], "evidence_ids": [], "supports_templates": [{"template_name": "法宝分析", "requirement_id": "r3", "status": "unknown"}], "confidence": "EXTRACTED", "verification_status": "bad"}],
        "evidence_index": [{"evidence_id": "bad", "source_range": [], "fact_summary": "", "confidence": "EXTRACTED", "verification_status": "verified", "supports_templates": []}],
        "metadata": {}
    }
    errors = validate_canonical_graph(graph).errors
    assert "node_unknown_evidence:node:item:1" in errors
    assert "edge_unknown_node:edge:owns:1" in errors
    assert "bad_confidence:CERTAIN" in errors
    assert "event_without_evidence:event:gain:1" in errors
    assert "bad_requirement_status:unknown" in errors
    assert "bad_evidence_id:bad" in errors
```

- [ ] **Step 2: Write failing adapter tests for unavailable graphify, real external command contract, and failure ledger payload**

```python
# tests/test_graphify_adapter.py
import json
import sys
from pathlib import Path
from storygraph_lib.graphify_adapter import GraphifyAdapter

def test_adapter_reports_unavailable_graphify_without_modifying_repo(tmp_path):
    adapter = GraphifyAdapter(graphify_repo=tmp_path / "missing", command=["python", "-c", "print('unused')"], timeout_seconds=5, mode="local-repo")
    result = adapter.build_graph(source_path=tmp_path / "novel.txt", output_dir=tmp_path / "out")
    assert result.ok is False
    assert result.error["code"] == "graphify_unavailable"

def test_adapter_local_repo_or_cli_fails_when_explicit_repo_is_missing(tmp_path):
    adapter = GraphifyAdapter(graphify_repo=tmp_path / "missing", command=["python", "-c", "print('would otherwise succeed')"], timeout_seconds=5, mode="local-repo-or-cli")
    result = adapter.build_graph(source_path=tmp_path / "novel.txt", output_dir=tmp_path / "out")
    assert result.ok is False
    assert result.error["code"] == "graphify_unavailable"

def test_adapter_invokes_configured_external_command_and_requires_graph_json(tmp_path):
    repo = tmp_path / "graphify"
    repo.mkdir()
    script = repo / "fake_graphify.py"
    script.write_text("import json, pathlib, sys\nout=pathlib.Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True); (out/'graph.json').write_text(json.dumps({'nodes': [], 'edges': [], 'hyperedges': [], 'metadata': {'fake': True}}), encoding='utf-8')\n", encoding="utf-8")
    source = tmp_path / "novel.txt"
    source.write_text("正文", encoding="utf-8")
    adapter = GraphifyAdapter(graphify_repo=repo, command=[sys.executable, "fake_graphify.py", "{source}", "{output_dir}"], timeout_seconds=5, mode="local-repo-or-cli")
    result = adapter.build_graph(source, tmp_path / "out")
    assert result.ok is True
    assert json.loads(result.graph_path.read_text(encoding="utf-8"))["metadata"]["fake"] is True

def test_adapter_cli_mode_does_not_require_local_repo(tmp_path):
    source = tmp_path / "novel.txt"
    source.write_text("正文", encoding="utf-8")
    command = [sys.executable, "-c", "import json,pathlib,sys; out=pathlib.Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True); (out/'graph.json').write_text(json.dumps({'nodes': [], 'edges': [], 'hyperedges': [], 'metadata': {'cli': True}}), encoding='utf-8')", "{source}", "{output_dir}"]
    adapter = GraphifyAdapter(graphify_repo=None, command=command, timeout_seconds=5, mode="cli")
    result = adapter.build_graph(source, tmp_path / "out")
    assert result.ok is True

def test_adapter_command_exit_zero_but_missing_required_artifact_is_structured_error(tmp_path):
    source = tmp_path / "novel.txt"
    source.write_text("正文", encoding="utf-8")
    command = [sys.executable, "-c", "import pathlib,sys; pathlib.Path(sys.argv[2]).mkdir(parents=True, exist_ok=True)", "{source}", "{output_dir}"]
    adapter = GraphifyAdapter(graphify_repo=None, command=command, timeout_seconds=5, mode="cli")
    result = adapter.build_graph(source, tmp_path / "out")
    assert result.ok is False
    assert result.error["code"] == "graphify_artifact_missing"
    assert set(result.error["missing"]) == {"graph.json", "GRAPH_REPORT.md", "graph.html"}
```

- [ ] **Step 3: Run schema and adapter tests and confirm they fail**

Run:

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python -m pytest tests\test_graph_schema.py tests\test_graphify_adapter.py -v
```

Expected: `FAIL` because graph schema and adapter modules are not defined.

- [ ] **Step 4: Implement stable IDs, canonical merge, and deep graph validation**

```python
# skill-src/storygraph/scripts/storygraph_lib/ids.py
from hashlib import sha256

def _slug(*parts: object) -> str:
    return sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:16]

def stable_node_id(novel_name: str, canonical_name: str, node_type: str) -> str:
    return f"node:{node_type}:{_slug(novel_name, canonical_name, node_type)}"

def stable_edge_id(novel_name: str, source: str, target: str, relation: str) -> str:
    return f"edge:{relation}:{_slug(novel_name, source, target, relation)}"

def stable_event_id(novel_name: str, event_type: str, actor: str, source_range: list[int]) -> str:
    return f"event:{event_type}:{_slug(novel_name, event_type, actor, source_range)}"

def stable_evidence_id(novel_name: str, chunk_id: str, source_range: list[int]) -> str:
    return f"evidence:{_slug(novel_name, chunk_id, source_range)}"
```

```python
# skill-src/storygraph/scripts/storygraph_lib/graph_schema.py
from dataclasses import dataclass

DEFAULT_STATUS_ENUMS = {
    "requirement_statuses": ["covered", "needs_review", "not_found_in_source"],
    "verification_statuses": ["verified", "needs_review", "rejected"],
    "confidence_levels": ["EXTRACTED", "INFERRED", "AMBIGUOUS"]
}

@dataclass(frozen=True)
class SchemaValidation:
    ok: bool
    errors: list[str]

def merge_template_supplements(base: dict, supplement: dict) -> dict:
    graph = {**base}
    for key, default in {"nodes": [], "edges": [], "hyperedges": [], "events": [], "evidence_index": [], "metadata": {}}.items():
        graph.setdefault(key, default.copy() if isinstance(default, list) else dict(default))
    graph.setdefault("schema_version", "1.0")
    graph.setdefault("graphify_schema_version", graph.get("metadata", {}).get("graphify_schema_version", "preserved"))
    graph.setdefault("storygraph_schema_version", "1.0")
    by_id = {node["id"]: dict(node) for node in graph["nodes"]}
    for node in supplement.get("nodes", []):
        by_id[node["id"]] = {**by_id.get(node["id"], {}), **node}
    graph["nodes"] = list(by_id.values())
    graph["edges"].extend(supplement.get("edges", []))
    graph["events"].extend(supplement.get("events", []))
    graph["evidence_index"].extend(supplement.get("evidence_index", []))
    return graph

def _check_supports(owner: str, item: dict, errors: list[str]) -> None:
    supports = item.get("supports_templates", [])
    if not supports:
        errors.append(f"{owner}_without_supports:{item.get('id') or item.get('evidence_id')}")
    for support in supports:
        status = support.get("status")
        if status not in _ACTIVE_ENUMS["requirement_statuses"]:
            errors.append(f"bad_requirement_status:{status}")

def _is_storygraph_item(item: dict) -> bool:
    return any(key in item for key in ["node_type", "edge_type", "event_type", "evidence_ids", "supports_templates", "confidence", "verification_status"])

_ACTIVE_ENUMS = DEFAULT_STATUS_ENUMS

def validate_canonical_graph(graph: dict, status_enums: dict | None = None) -> SchemaValidation:
    global _ACTIVE_ENUMS
    _ACTIVE_ENUMS = status_enums or DEFAULT_STATUS_ENUMS
    errors = [f"missing:{key}" for key in ["schema_version", "graphify_schema_version", "storygraph_schema_version", "nodes", "edges", "hyperedges", "events", "evidence_index", "metadata"] if key not in graph]
    evidence_ids = {e.get("evidence_id") for e in graph.get("evidence_index", [])}
    node_ids = {n.get("id") for n in graph.get("nodes", [])}
    for node in graph.get("nodes", []):
        if not _is_storygraph_item(node):
            continue
        if not node.get("id", "").startswith("node:"):
            errors.append(f"bad_node_id:{node.get('id')}")
        for key in ["node_type", "evidence_ids", "supports_templates", "confidence", "verification_status"]:
            if key not in node:
                errors.append(f"node_missing:{node.get('id')}:{key}")
        if not node.get("evidence_ids"):
            errors.append(f"node_without_evidence:{node.get('id')}")
        if any(eid not in evidence_ids for eid in node.get("evidence_ids", [])):
            errors.append(f"node_unknown_evidence:{node.get('id')}")
        if node.get("verification_status") not in _ACTIVE_ENUMS["verification_statuses"]:
            errors.append(f"bad_verification_status:{node.get('verification_status')}")
        if node.get("confidence") not in _ACTIVE_ENUMS["confidence_levels"]:
            errors.append(f"bad_confidence:{node.get('confidence')}")
        _check_supports("node", node, errors)
    for edge in graph.get("edges", []):
        if not _is_storygraph_item(edge):
            continue
        for key in ["id", "source", "target", "edge_type", "evidence_ids", "supports_templates", "confidence", "verification_status"]:
            if key not in edge:
                errors.append(f"edge_missing:{edge.get('id')}:{key}")
        if edge.get("source") not in node_ids or edge.get("target") not in node_ids:
            errors.append(f"edge_unknown_node:{edge.get('id')}")
        if any(eid not in evidence_ids for eid in edge.get("evidence_ids", [])):
            errors.append(f"edge_unknown_evidence:{edge.get('id')}")
        if edge.get("verification_status") not in _ACTIVE_ENUMS["verification_statuses"]:
            errors.append(f"bad_verification_status:{edge.get('verification_status')}")
        if edge.get("confidence") not in _ACTIVE_ENUMS["confidence_levels"]:
            errors.append(f"bad_confidence:{edge.get('confidence')}")
        _check_supports("edge", edge, errors)
    for event in graph.get("events", []):
        for key in ["id", "event_type", "participants", "evidence_ids", "supports_templates", "confidence", "verification_status"]:
            if key not in event:
                errors.append(f"event_missing:{event.get('id')}:{key}")
        if not event.get("id", "").startswith("event:"):
            errors.append(f"bad_event_id:{event.get('id')}")
        if not event.get("evidence_ids"):
            errors.append(f"event_without_evidence:{event.get('id')}")
        if any(eid not in evidence_ids for eid in event.get("evidence_ids", [])):
            errors.append(f"event_unknown_evidence:{event.get('id')}")
        if any(pid not in node_ids for pid in event.get("participants", [])):
            errors.append(f"event_unknown_node:{event.get('id')}")
        if event.get("verification_status") not in _ACTIVE_ENUMS["verification_statuses"]:
            errors.append(f"bad_verification_status:{event.get('verification_status')}")
        if event.get("confidence") not in _ACTIVE_ENUMS["confidence_levels"]:
            errors.append(f"bad_confidence:{event.get('confidence')}")
        _check_supports("event", event, errors)
    for evidence in graph.get("evidence_index", []):
        if not evidence.get("evidence_id", "").startswith("evidence:"):
            errors.append(f"bad_evidence_id:{evidence.get('evidence_id')}")
        for key in ["source_range", "fact_summary", "confidence", "verification_status", "supports_templates"]:
            if key not in evidence:
                errors.append(f"evidence_missing:{evidence.get('evidence_id')}:{key}")
        if evidence.get("verification_status") not in _ACTIVE_ENUMS["verification_statuses"]:
            errors.append(f"bad_evidence_verification:{evidence.get('verification_status')}")
        if evidence.get("confidence") not in _ACTIVE_ENUMS["confidence_levels"]:
            errors.append(f"bad_confidence:{evidence.get('confidence')}")
        _check_supports("evidence", evidence, errors)
    return SchemaValidation(ok=not errors, errors=errors)
```

Graphify 原生节点、边和 metadata 可以保留原始字段，不强制补齐 StoryGraph 扩展字段。边界规则是：任何由 StoryGraph 创建、合并、或带有 `supports_templates`、`evidence_ids`、`confidence`、`verification_status` 的节点/边/事件/证据，都必须通过上述 StoryGraph 深度校验；如果 merge 阶段补齐原生节点，也必须在写入前补齐字段。

- [ ] **Step 5: Implement graphify adapter as a verifiable external command wrapper**

```python
# skill-src/storygraph/scripts/storygraph_lib/graphify_adapter.py
from dataclasses import dataclass
from pathlib import Path
import subprocess

@dataclass(frozen=True)
class GraphifyResult:
    ok: bool
    graph_path: Path | None
    error: dict | None
    command: list[str]

class GraphifyAdapter:
    def __init__(self, graphify_repo: Path | None, command: list[str], timeout_seconds: int, mode: str = "local-repo-or-cli"):
        self.graphify_repo = graphify_repo
        self.command = command
        self.timeout_seconds = timeout_seconds
        self.mode = mode

    def build_graph(self, source_path: Path, output_dir: Path) -> GraphifyResult:
        if self.mode not in {"local-repo", "cli", "local-repo-or-cli"}:
            return GraphifyResult(False, None, {"code": "graphify_bad_mode", "mode": self.mode}, self.command)
        cwd = None
        if self.mode in {"local-repo", "local-repo-or-cli"} and self.graphify_repo and self.graphify_repo.exists():
            cwd = self.graphify_repo
        elif self.mode == "local-repo" or (self.mode == "local-repo-or-cli" and self.graphify_repo is not None):
            return GraphifyResult(False, None, {"code": "graphify_unavailable", "path": str(self.graphify_repo)}, self.command)
        output_dir.mkdir(parents=True, exist_ok=True)
        command = [part.format(source=str(source_path), output_dir=str(output_dir)) for part in self.command]
        completed = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=self.timeout_seconds)
        required = ["graph.json", "GRAPH_REPORT.md", "graph.html"]
        missing = [name for name in required if not (output_dir / name).exists()]
        if completed.returncode != 0:
            return GraphifyResult(False, None, {"code": "graphify_failed", "returncode": completed.returncode, "stderr": completed.stderr[-4000:]}, command)
        if missing:
            return GraphifyResult(False, None, {"code": "graphify_artifact_missing", "missing": missing, "stdout": completed.stdout[-4000:]}, command)
        graph_path = output_dir / "graph.json"
        return GraphifyResult(True, graph_path, None, command)
```

- [ ] **Step 6: Run tests and commit graph layer**

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python -m pytest tests\test_graph_schema.py tests\test_graphify_adapter.py -v; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; git -c core.quotePath=false add skill-src\storygraph\scripts\storygraph_lib skill-src\storygraph\references tests\test_graph_schema.py tests\test_graphify_adapter.py; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; git commit -m "feat: add deep graph validation and graphify adapter"; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

Expected: schema tests reject bad statuses and missing evidence; adapter tests prove an external command is invoked and graphify failures return structured ledger-ready errors.

### Task 7: Template-Aware Supplements, Evidence Index, Coverage Ledgers, And Agent Ledger

**Files:**
- Create: `E:\AI_Projects\StoryGraph\skill-src\storygraph\scripts\storygraph_lib\coverage.py`
- Create: `E:\AI_Projects\StoryGraph\skill-src\storygraph\scripts\storygraph_lib\template_aware.py`
- Create: `E:\AI_Projects\StoryGraph\skill-src\storygraph\scripts\storygraph_lib\agent_ledger.py`
- Create: `E:\AI_Projects\StoryGraph\skill-src\storygraph\scripts\storygraph_lib\output_writer.py`
- Modify: `E:\AI_Projects\StoryGraph\skill-src\storygraph\references\workflow.md`
- Test: `E:\AI_Projects\StoryGraph\tests\test_agent_ledger.py`
- Test: `E:\AI_Projects\StoryGraph\tests\test_template_aware.py`

- [ ] **Step 1: Write failing tests for agent ledger, chunks, and real template-aware supplements**

```python
# tests/test_agent_ledger.py
from storygraph_lib.agent_ledger import make_agent_run_record, make_stage_agent_records, validate_single_writer
from storygraph_lib.output_writer import OutputWriter

def test_agent_run_record_contains_required_contract_fields():
    record = make_agent_run_record("run-1", "模板需求分析", "stage1", ["chunk-0001"], ["法宝分析"], ["novel.txt"], ["requirements.json"], "requirements/template-requirements.json")
    assert record["status"] == "pending"
    assert record["merge_owner"] == "single-writer"
    assert validate_single_writer([record]).ok is True

def test_single_writer_detects_conflicting_outputs():
    a = make_agent_run_record("run-1", "A", "stage1", [], [], [], ["manifest.json"], "manifest.json")
    b = make_agent_run_record("run-2", "B", "stage1", [], [], [], ["manifest.json"], "other-scope")
    assert validate_single_writer([a, b]).ok is False

def test_agent_ledger_includes_all_stage1_roles():
    records = make_stage_agent_records(["chunk-0001"], ["法宝分析"])
    assert [r["agent_role"] for r in records] == ["模板需求分析", "图抽取", "覆盖审查", "质量审查"]
    assert all(r["input_paths"] for r in records)
    assert all(r["output_paths"] for r in records)
    assert all(r["write_scope"] for r in records)

def test_output_writer_registry_blocks_unmanaged_outputs(tmp_path):
    writer = OutputWriter(tmp_path, managed_outputs=["manifest.json", "coverage/agent-run-ledger.json"])
    writer.write_json("manifest.json", {"ok": True})
    try:
        writer.write_json("graphify-out/graph.json", {})
    except ValueError as exc:
        assert "unmanaged_output" in str(exc)
    else:
        raise AssertionError("unmanaged output should be rejected")
```

```python
# tests/test_template_aware.py
from storygraph_lib.coverage import make_chunk_ledger
from storygraph_lib.template_aware import extract_template_aware_supplements

def test_template_aware_extraction_creates_nodes_edges_events_evidence_and_requirement_statuses(tmp_path):
    source = tmp_path / "novel.txt"
    source.write_text("第一章\n韩立获得小瓶。小瓶影响法宝资源获取。", encoding="utf-8")
    chunks = make_chunk_ledger(source, {"mode": "chapter-aware", "fallback_mode": "bounded-chars", "max_chars": 200, "overlap_chars": 0}, processor="test")
    matrix = {"templates": [{"template_name": "法宝分析", "required_fields": ["法宝"], "required_tables": ["名称|能力"], "required_cards": ["法宝卡片"], "required_case_patterns": ["小瓶"], "required_entity_types": ["item"], "required_event_types": ["resource_gain"], "required_relation_types": ["influences"], "required_evidence_fields": ["source_range", "fact_summary"], "graph_node_mapping": ["item"], "graph_event_mapping": ["resource_gain"], "graph_relation_mapping": ["influences"], "gap_rules": {"status_enum": ["covered", "needs_review", "not_found_in_source"]}}]}
    supplement, readiness = extract_template_aware_supplements("凡人修仙传", source, chunks, matrix, {"mode": "substring"})
    assert supplement["nodes"]
    assert supplement["edges"]
    assert supplement["events"]
    assert supplement["evidence_index"]
    assert readiness[0]["requirement_statuses"]
    assert {r["status"] for r in readiness[0]["requirement_statuses"]} <= {"covered", "needs_review", "not_found_in_source"}
    assert supplement["nodes"][0]["supports_templates"][0]["template_name"] == "法宝分析"
    assert any(node["node_type"] == "event" for node in supplement["nodes"])
```

- [ ] **Step 2: Run ledger and template-aware tests and confirm they fail**

Run:

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python -m pytest tests\test_agent_ledger.py tests\test_template_aware.py -v
```

Expected: `FAIL` because `coverage`, `template_aware`, and `agent_ledger` modules are not defined.

- [ ] **Step 3: Implement dynamic sub-agent ledger and chunk ledger**

```python
# skill-src/storygraph/scripts/storygraph_lib/agent_ledger.py
from collections import Counter
from dataclasses import dataclass

@dataclass(frozen=True)
class LedgerValidation:
    ok: bool
    errors: list[str]

def make_agent_run_record(run_id, agent_role, stage, chunk_ids, template_names, input_paths, output_paths, write_scope):
    return {"run_id": run_id, "agent_role": agent_role, "stage": stage, "assigned_chunk_ids": chunk_ids, "assigned_template_names": template_names, "input_paths": input_paths, "output_paths": output_paths, "write_scope": write_scope, "status": "pending", "errors": [], "merge_owner": "single-writer", "reviewer_status": "not_reviewed", "started_at": None, "finished_at": None}

def make_stage_agent_records(chunk_ids, template_names):
    return [
        make_agent_run_record("stage1-template-requirements", "模板需求分析", "stage1", [], template_names, ["source-novel", "template-dir"], ["requirements/template-requirements.json"], "requirements/template-requirements.json"),
        make_agent_run_record("stage1-graph-extraction", "图抽取", "stage1", chunk_ids, template_names, ["source-novel", "coverage/chunk-ledger.json", "requirements/template-requirements.json"], ["graphify-out/graph.json", "coverage/evidence-index.json"], "graphify-out/graph.json"),
        make_agent_run_record("stage1-coverage-review", "覆盖审查", "stage1", chunk_ids, template_names, ["requirements/template-requirements.json", "coverage/chunk-ledger.json", "coverage/evidence-index.json", "graphify-out/graph.json"], ["coverage/template-readiness.json", "coverage/gap-report.md"], "coverage/template-readiness.json"),
        make_agent_run_record("stage1-quality-review", "质量审查", "stage1", chunk_ids, template_names, ["manifest.json", "requirements/template-requirements.json", "coverage/chunk-ledger.json", "coverage/template-readiness.json", "coverage/gap-report.md"], ["coverage/agent-run-ledger.json"], "coverage/agent-run-ledger.json")
    ]

def validate_single_writer(records):
    scopes = Counter(record["write_scope"] for record in records if record["write_scope"])
    outputs = Counter(path for record in records for path in record.get("output_paths", []))
    conflicts = [f"write_scope:{scope}" for scope, count in scopes.items() if count > 1]
    conflicts.extend(f"output_path:{path}" for path, count in outputs.items() if count > 1)
    return LedgerValidation(ok=not conflicts, errors=[f"write_conflict:{scope}" for scope in conflicts])
```

```python
# skill-src/storygraph/scripts/storygraph_lib/coverage.py
import json
from datetime import datetime, timezone
from hashlib import sha256

def _chunk_ranges_chapter_aware(text: str, max_chars: int, overlap_chars: int) -> list[tuple[int, int]]:
    # Minimal default strategy: split on bounded chars, but preserve chapter heading hints in ledger.
    ranges, start = [], 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        ranges.append((start, end))
        if end == len(text):
            break
        start = max(0, end - overlap_chars)
    return ranges

def make_chunk_ledger(source_path, strategy: dict, processor: str) -> list[dict]:
    text = source_path.read_text(encoding="utf-8")
    if strategy.get("mode") not in {"chapter-aware", "bounded-chars"}:
        raise ValueError(f"unsupported_chunk_strategy:{strategy.get('mode')}")
    ranges = _chunk_ranges_chapter_aware(text, strategy["max_chars"], strategy.get("overlap_chars", 0))
    chunks = []
    for index, (start, end) in enumerate(ranges, 1):
        body = text[start:end]
        chunks.append({"chunk_id": f"chunk-{index:04d}", "source_range": [start, end], "chapter_hint": body.splitlines()[0] if body else None, "hash": sha256(body.encode("utf-8")).hexdigest(), "scanned_at": datetime.now(timezone.utc).isoformat(), "processor": processor, "extraction_status": "pending", "failure": {"code": None, "message": None, "retryable": False}, "retry_count": 0})
    return chunks

def write_coverage_outputs(writer, chunks, evidences, readiness, agent_runs, gap_lines):
    writer.write_json("coverage/chunk-ledger.json", chunks)
    writer.write_json("coverage/evidence-index.json", evidences)
    writer.write_json("coverage/template-readiness.json", readiness)
    writer.write_json("coverage/agent-run-ledger.json", agent_runs)
    writer.write_text("coverage/gap-report.md", "# StoryGraph Gap Report\n\n" + "\n".join(gap_lines) + "\n")
```

```python
# skill-src/storygraph/scripts/storygraph_lib/output_writer.py
import json

class OutputWriter:
    def __init__(self, graph_dir, managed_outputs):
        self.graph_dir = graph_dir
        self.managed_outputs = set(managed_outputs)
        self.written = set()

    def _resolve(self, relative_path: str):
        if relative_path not in self.managed_outputs:
            raise ValueError(f"unmanaged_output:{relative_path}")
        if relative_path in self.written:
            raise ValueError(f"duplicate_output_write:{relative_path}")
        path = self.graph_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.written.add(relative_path)
        return path

    def write_json(self, relative_path: str, data) -> None:
        self._resolve(relative_path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def write_text(self, relative_path: str, text: str) -> None:
        self._resolve(relative_path).write_text(text, encoding="utf-8")
```

- [ ] **Step 4: Implement template-aware supplement extraction with per-requirement statuses**

```python
# skill-src/storygraph/scripts/storygraph_lib/template_aware.py
from .ids import stable_edge_id, stable_event_id, stable_evidence_id, stable_node_id

def _requirements(record):
    for kind in ["required_fields", "required_tables", "required_cards", "required_case_patterns"]:
        for item in record.get(kind, []):
            yield kind, item

def _support(template_name, requirement_id, status):
    return {"template_name": template_name, "requirement_id": requirement_id, "status": status}

def _find_evidence_chunk(requirement, chunks, text, strategy):
    if strategy.get("mode", "substring") == "substring":
        return next((chunk for chunk in chunks if requirement and requirement in text[chunk["source_range"][0]:chunk["source_range"][1]]), None)
    raise ValueError(f"unsupported_evidence_matching_strategy:{strategy.get('mode')}")

def extract_template_aware_supplements(novel_name, source_path, chunks, matrix, evidence_strategy):
    text = source_path.read_text(encoding="utf-8")
    nodes, edges, events, evidences, readiness = [], [], [], [], []
    for template in matrix["templates"]:
        statuses = []
        template_nodes, template_edges, template_events, template_evidence = 0, 0, 0, 0
        for kind, requirement in _requirements(template):
            requirement_id = f"{template['template_name']}.{kind}.{requirement}"
            match_chunk = _find_evidence_chunk(requirement, chunks, text, evidence_strategy)
            if match_chunk:
                status = "covered"
                evidence_id = stable_evidence_id(novel_name, match_chunk["chunk_id"], match_chunk["source_range"])
                node_id = stable_node_id(novel_name, requirement, template["required_entity_types"][0])
                event_id = stable_event_id(novel_name, template["required_event_types"][0], requirement, match_chunk["source_range"])
                event_node_id = stable_node_id(novel_name, f"{template['required_event_types'][0]}:{requirement}:{match_chunk['source_range']}", "event")
                edge_id = stable_edge_id(novel_name, node_id, event_node_id, template["required_relation_types"][0])
                support = _support(template["template_name"], requirement_id, status)
                evidences.append({"evidence_id": evidence_id, "source_path": str(source_path), "chunk_id": match_chunk["chunk_id"], "source_range": match_chunk["source_range"], "chapter_hint": match_chunk["chapter_hint"], "fact_summary": f"{requirement} appears in source chunk", "linked_node_ids": [node_id, event_node_id], "linked_edge_ids": [edge_id], "linked_event_ids": [event_id], "supports_templates": [support], "confidence": "EXTRACTED", "verification_status": "verified"})
                nodes.append({"id": node_id, "label": requirement, "node_type": template["required_entity_types"][0], "source_file": str(source_path), "source_location": match_chunk["source_range"], "evidence_ids": [evidence_id], "supports_templates": [support], "confidence": "EXTRACTED", "verification_status": "verified"})
                nodes.append({"id": event_node_id, "label": requirement, "node_type": "event", "source_file": str(source_path), "source_location": match_chunk["source_range"], "evidence_ids": [evidence_id], "supports_templates": [support], "confidence": "EXTRACTED", "verification_status": "verified"})
                events.append({"id": event_id, "label": requirement, "event_type": template["required_event_types"][0], "participants": [node_id], "locations": [], "source_file": str(source_path), "source_range": match_chunk["source_range"], "evidence_ids": [evidence_id], "causes": [], "effects": [], "supports_templates": [support], "confidence": "EXTRACTED", "verification_status": "verified"})
                edges.append({"id": edge_id, "source": node_id, "target": event_node_id, "relation": template["required_relation_types"][0], "edge_type": template["required_relation_types"][0], "source_file": str(source_path), "evidence_ids": [evidence_id], "supports_templates": [support], "confidence": "EXTRACTED", "confidence_score": 1.0, "verification_status": "verified"})
                template_nodes += 2; template_edges += 1; template_events += 1; template_evidence += 1
                statuses.append({"requirement_id": requirement_id, "requirement_kind": kind, "status": status, "linked_node_ids": [node_id, event_node_id], "linked_edge_ids": [edge_id], "linked_event_ids": [event_id], "evidence_ids": [evidence_id], "notes": []})
            else:
                status = "not_found_in_source"
                statuses.append({"requirement_id": requirement_id, "requirement_kind": kind, "status": status, "linked_node_ids": [], "linked_edge_ids": [], "linked_event_ids": [], "evidence_ids": [], "notes": []})
        readiness.append({"template_name": template["template_name"], "readiness_score": template_evidence / max(1, len(statuses)), "supporting_node_count": template_nodes, "supporting_edge_count": template_edges, "supporting_event_count": template_events, "evidence_count": template_evidence, "missing_requirement_types": [s["requirement_kind"] for s in statuses if s["status"] != "covered"], "requirement_statuses": statuses, "notes": []})
    return {"nodes": nodes, "edges": edges, "events": events, "evidence_index": evidences}, readiness
```

- [ ] **Step 5: Add coverage assertions for complete dynamic-template readiness**

```python
# add to tests/test_template_aware.py
def test_readiness_has_one_record_per_template_and_each_requirement_has_status(tmp_path):
    source = tmp_path / "novel.txt"
    source.write_text("法宝 丹药 阵法", encoding="utf-8")
    chunks = make_chunk_ledger(source, {"mode": "chapter-aware", "fallback_mode": "bounded-chars", "max_chars": 200, "overlap_chars": 0}, processor="test")
    template_count = 5
    matrix = {"template_count": template_count, "templates": [{"template_name": f"模板{i}", "required_fields": ["法宝"], "required_tables": [], "required_cards": [], "required_case_patterns": [], "required_entity_types": ["entity"], "required_event_types": ["event"], "required_relation_types": ["relation"], "graph_node_mapping": ["entity"], "graph_event_mapping": ["event"], "graph_relation_mapping": ["relation"], "required_evidence_fields": ["source_range"], "gap_rules": {"status_enum": ["covered", "needs_review", "not_found_in_source"]}} for i in range(template_count)]}
    supplement, readiness = extract_template_aware_supplements("凡人修仙传", source, chunks, matrix, {"mode": "substring"})
    assert len(readiness) == matrix["template_count"]
    assert all(record["requirement_statuses"] for record in readiness)
    assert supplement["nodes"] and supplement["events"] and supplement["evidence_index"]
```

- [ ] **Step 6: Run tests and commit template-aware coverage layer**

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python -m pytest tests\test_agent_ledger.py tests\test_template_aware.py -v; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; git -c core.quotePath=false add skill-src\storygraph\scripts\storygraph_lib skill-src\storygraph\references tests\test_agent_ledger.py tests\test_template_aware.py; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; git commit -m "feat: add template-aware graph supplements and coverage"; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

Expected: template-aware tests prove non-empty nodes, edges, events, evidence, `supports_templates`, and one readiness record per template.

### Task 8: Stage 1 Pipeline, Idempotency, Failure Ledgers, And Deep Validation Commands

**Files:**
- Create: `E:\AI_Projects\StoryGraph\skill-src\storygraph\scripts\storygraph_lib\stage1.py`
- Create: `E:\AI_Projects\StoryGraph\skill-src\storygraph\scripts\storygraph_lib\state.py`
- Modify: `E:\AI_Projects\StoryGraph\skill-src\storygraph\scripts\storygraph_lib\cli.py`
- Modify: `E:\AI_Projects\StoryGraph\skill-src\storygraph\scripts\storygraph_lib\validation.py`
- Modify: `E:\AI_Projects\StoryGraph\docs\storygraph-cli.md`
- Test: `E:\AI_Projects\StoryGraph\tests\test_stage1.py`
- Test: `E:\AI_Projects\StoryGraph\tests\test_stage1_idempotency.py`
- Test: `E:\AI_Projects\StoryGraph\tests\test_validation_cli.py`

- [ ] **Step 1: Write failing tests for non-empty stage 1 outputs, idempotency, source hash changes, and graphify failure ledger**

```python
# tests/test_stage1.py
import json
import sys
from pathlib import Path
from storygraph_lib.stage1 import build_stage1_graph
from storygraph_lib.validation import validate_graph_dir

def _config(template_dir, graphify_repo=None):
    return {"graph_dir_suffix": ".storygraph", "output_language": "zh-CN", "paths": {"template_dir": str(template_dir), "graphify_repo": str(graphify_repo) if graphify_repo else None}, "template_discovery": {"glob": "*模板.md", "readme_index_file": "README.md"}, "template_parser_rules": {"field_headings": ["字段"], "table_markers": ["|", "表格"], "card_markers": ["卡片"], "case_markers": ["案例"], "evidence_markers": ["证据", "原文"], "gap_markers": ["缺口", "待核验"]}, "template_graph_mappings": {"法宝分析": {"graph_node_mapping": ["artifact"], "graph_event_mapping": ["artifact_gain"], "graph_relation_mapping": ["artifact_influence"]}, "default_mapping": {"graph_node_mapping": ["template_specific_node"], "graph_event_mapping": ["template_specific_event"], "graph_relation_mapping": ["template_specific_relation"]}}, "status_enums": {"requirement_statuses": ["covered", "needs_review", "not_found_in_source"], "verification_statuses": ["verified", "needs_review", "rejected"], "confidence_levels": ["EXTRACTED", "INFERRED", "AMBIGUOUS"]}, "graphify_adapter": {"mode": "local-repo-or-cli", "command": [sys.executable, "-c", "import json,pathlib,sys; out=pathlib.Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True); (out/'graph.json').write_text(json.dumps({'schema_version': '1.0', 'graphify_schema_version': 'test', 'storygraph_schema_version': '1.0', 'nodes': [], 'edges': [], 'hyperedges': [], 'events': [], 'evidence_index': [], 'metadata': {'graphify_schema_version': 'test'}}), encoding='utf-8'); (out/'GRAPH_REPORT.md').write_text('# Graph Report\\n', encoding='utf-8'); (out/'graph.html').write_text('<!doctype html><title>graph</title>', encoding='utf-8')", "{source}", "{output_dir}"], "timeout_seconds": 5}, "chunk_strategy": {"mode": "chapter-aware", "fallback_mode": "bounded-chars", "max_chars": 100, "overlap_chars": 0}, "evidence_matching_strategy": {"mode": "substring"}, "coverage_thresholds": {"require_all_chunks_scanned": True, "readiness_warning_threshold": 0.8, "block_on_low_readiness": True, "block_on_template_without_reliable_evidence": True, "block_on_unparsable_subagent_json": True}, "agent_policy": {"sub_agent_json_payloads": []}, "writer_policy": {"managed_outputs": ["manifest.json", "graphify-out/graph.json", "graphify-out/GRAPH_REPORT.md", "graphify-out/graph.html", "requirements/template-requirements.json", "coverage/chunk-ledger.json", "coverage/evidence-index.json", "coverage/template-readiness.json", "coverage/agent-run-ledger.json", "coverage/gap-report.md"]}}

def test_stage1_build_merges_real_template_aware_supplements(tmp_path):
    novel = tmp_path / "mini_novel.txt"
    novel.write_text("第一章\n韩立获得小瓶。小瓶影响法宝资源获取。", encoding="utf-8")
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    graphify_repo = tmp_path / "graphify"
    graphify_repo.mkdir()
    (template_dir / "法宝分析模板.md").write_text("# 法宝分析模板\n## 字段\n- 法宝\n## 法宝卡片\n- 小瓶\n## 证据要求\n- 原文位置", encoding="utf-8")
    result = build_stage1_graph(novel, _config(template_dir, graphify_repo))
    graph_dir = tmp_path / "mini_novel.storygraph"
    graph = json.loads((graph_dir / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
    readiness = json.loads((graph_dir / "coverage" / "template-readiness.json").read_text(encoding="utf-8"))
    ledger = json.loads((graph_dir / "coverage" / "agent-run-ledger.json").read_text(encoding="utf-8"))
    assert result["status"] == "success"
    assert graph["nodes"] and graph["edges"] and graph["events"] and graph["evidence_index"]
    assert readiness[0]["requirement_statuses"]
    assert {record["status"] for record in ledger} == {"completed"}

def test_stage1_graphify_unavailable_is_blocking_failed(tmp_path):
    novel = tmp_path / "mini_novel.txt"
    novel.write_text("法宝", encoding="utf-8")
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "法宝分析模板.md").write_text("# 法宝分析模板\n## 字段\n- 法宝", encoding="utf-8")
    result = build_stage1_graph(novel, _config(template_dir, tmp_path / "missing-graphify"))
    second = build_stage1_graph(novel, _config(template_dir, tmp_path / "missing-graphify"))
    ledger = json.loads((tmp_path / "mini_novel.storygraph" / "coverage" / "agent-run-ledger.json").read_text(encoding="utf-8"))
    assert result["status"] == "failed"
    assert second["status"] == "failed"
    assert not (tmp_path / "mini_novel.storygraph" / "graphify-out" / "graph.json").exists()
    failed = next(record for record in ledger if record["status"] == "failed")
    assert failed["agent_role"] == "图抽取"
    assert failed["errors"][0]["code"] == "graphify_unavailable"

def test_stage1_readiness_below_threshold_and_template_without_reliable_evidence_fail(tmp_path):
    novel = tmp_path / "mini_novel.txt"
    novel.write_text("完全无关正文", encoding="utf-8")
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    graphify_repo = tmp_path / "graphify"
    graphify_repo.mkdir()
    (template_dir / "法宝分析模板.md").write_text("# 法宝分析模板\n## 字段\n- 法宝", encoding="utf-8")
    result = build_stage1_graph(novel, _config(template_dir, graphify_repo))
    graph_dir = tmp_path / "mini_novel.storygraph"
    manifest = json.loads((graph_dir / "manifest.json").read_text(encoding="utf-8"))
    gap = (graph_dir / "coverage" / "gap-report.md").read_text(encoding="utf-8")
    ledger = json.loads((graph_dir / "coverage" / "agent-run-ledger.json").read_text(encoding="utf-8"))
    assert result["status"] == "failed"
    assert manifest["stage_status"]["stage1"] == "failed"
    assert "readiness_below_threshold" in gap
    assert "template_without_reliable_evidence" in gap
    assert any(error["code"] == "readiness_below_threshold" for record in ledger for error in record["errors"])

def test_stage1_chunk_extraction_failure_writes_failed_chunk_ledger(tmp_path, monkeypatch):
    import storygraph_lib.stage1 as stage1_mod
    novel = tmp_path / "mini_novel.txt"
    novel.write_text("法宝", encoding="utf-8")
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    graphify_repo = tmp_path / "graphify"
    graphify_repo.mkdir()
    (template_dir / "法宝分析模板.md").write_text("# 法宝分析模板\n## 字段\n- 法宝", encoding="utf-8")
    monkeypatch.setattr(stage1_mod, "make_chunk_ledger", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("chunk boom")))
    result = build_stage1_graph(novel, _config(template_dir, graphify_repo))
    graph_dir = tmp_path / "mini_novel.storygraph"
    chunks = json.loads((graph_dir / "coverage" / "chunk-ledger.json").read_text(encoding="utf-8"))
    manifest = json.loads((graph_dir / "manifest.json").read_text(encoding="utf-8"))
    assert result["status"] == "failed"
    assert manifest["stage_status"]["stage1"] == "failed"
    assert chunks[0]["extraction_status"] == "failed"
    assert chunks[0]["failure"]["code"] == "chunk_extraction_failure"

def test_stage1_unparsable_subagent_json_fails_and_records_ledger(tmp_path):
    novel = tmp_path / "mini_novel.txt"
    novel.write_text("法宝", encoding="utf-8")
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    graphify_repo = tmp_path / "graphify"
    graphify_repo.mkdir()
    (template_dir / "法宝分析模板.md").write_text("# 法宝分析模板\n## 字段\n- 法宝", encoding="utf-8")
    config = _config(template_dir, graphify_repo)
    config["agent_policy"]["sub_agent_json_payloads"] = ["{not json"]
    result = build_stage1_graph(novel, config)
    graph_dir = tmp_path / "mini_novel.storygraph"
    ledger = json.loads((graph_dir / "coverage" / "agent-run-ledger.json").read_text(encoding="utf-8"))
    gap = (graph_dir / "coverage" / "gap-report.md").read_text(encoding="utf-8")
    assert result["status"] == "failed"
    assert any(error["code"] == "unparsable_subagent_json" for record in ledger for error in record["errors"])
    assert "unparsable_subagent_json" in gap

def test_stage1_single_writer_conflict_fails_before_success_outputs(tmp_path, monkeypatch):
    import storygraph_lib.stage1 as stage1_mod
    from storygraph_lib.agent_ledger import make_agent_run_record
    novel = tmp_path / "mini_novel.txt"
    novel.write_text("法宝", encoding="utf-8")
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    graphify_repo = tmp_path / "graphify"
    graphify_repo.mkdir()
    (template_dir / "法宝分析模板.md").write_text("# 法宝分析模板\n## 字段\n- 法宝", encoding="utf-8")
    def conflicting_records(chunk_ids, template_names):
        return [
            make_agent_run_record("run-a", "模板需求分析", "stage1", [], template_names, ["source-novel"], ["manifest.json"], "manifest.json"),
            make_agent_run_record("run-b", "图抽取", "stage1", chunk_ids, template_names, ["source-novel"], ["manifest.json"], "graphify-out/graph.json"),
        ]
    monkeypatch.setattr(stage1_mod, "make_stage_agent_records", conflicting_records)
    result = build_stage1_graph(novel, _config(template_dir, graphify_repo))
    graph_dir = tmp_path / "mini_novel.storygraph"
    manifest = json.loads((graph_dir / "manifest.json").read_text(encoding="utf-8"))
    assert result["status"] == "failed"
    assert manifest["stage_status"]["stage1"] == "failed"
    assert not (graph_dir / "graphify-out" / "graph.json").exists()

def test_stage1_missing_source_returns_structured_error_and_writes_failure_outputs_when_graph_dir_is_known(tmp_path):
    source = tmp_path / "missing_novel.txt"
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "法宝分析模板.md").write_text("# 法宝分析模板\n## 字段\n- 法宝", encoding="utf-8")
    result = build_stage1_graph(source, _config(template_dir, tmp_path / "graphify"))
    graph_dir = tmp_path / "missing_novel.storygraph"
    manifest = json.loads((graph_dir / "manifest.json").read_text(encoding="utf-8"))
    ledger = json.loads((graph_dir / "coverage" / "agent-run-ledger.json").read_text(encoding="utf-8"))
    gap = (graph_dir / "coverage" / "gap-report.md").read_text(encoding="utf-8")
    assert result["status"] == "failed"
    assert result["error"]["code"] == "source_unreadable"
    assert manifest["stage_status"]["stage1"] == "failed"
    assert any(error["code"] == "source_unreadable" for record in ledger for error in record.get("errors", []))
    assert "source_unreadable" in gap

def test_stage1_cli_source_unreadable_returns_json_even_when_graph_dir_cannot_be_inferred(tmp_path, capsys, monkeypatch):
    import storygraph_lib.cli as cli_mod
    import storygraph_lib.stage1 as stage1_mod
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "法宝分析模板.md").write_text("# 法宝分析模板\n## 字段\n- 法宝", encoding="utf-8")
    monkeypatch.setattr(stage1_mod, "_infer_novel_context_without_reading", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("bad source path")))
    exit_code = cli_mod.main(["build-stage1", "--source", "<bad-source>", "--template-dir", str(template_dir)])
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["status"] == "failed"
    assert payload["error"]["code"] == "source_unreadable"
    assert payload["graph_dir"] is None
    assert payload["manifest_written"] is False

def test_stage1_invalid_utf8_source_uses_stable_encoding_error_code(tmp_path):
    novel = tmp_path / "bad_encoding.txt"
    novel.write_bytes(b"\xff\xfe\xfa")
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    graphify_repo = tmp_path / "graphify"
    graphify_repo.mkdir()
    (template_dir / "法宝分析模板.md").write_text("# 法宝分析模板\n## 字段\n- 法宝", encoding="utf-8")
    result = build_stage1_graph(novel, _config(template_dir, graphify_repo))
    graph_dir = tmp_path / "bad_encoding.storygraph"
    manifest = json.loads((graph_dir / "manifest.json").read_text(encoding="utf-8"))
    ledger = json.loads((graph_dir / "coverage" / "agent-run-ledger.json").read_text(encoding="utf-8"))
    assert result["status"] == "failed"
    assert result["error"]["code"] == "source_encoding_error"
    assert manifest["stage_status"]["stage1"] == "failed"
    assert any(error["code"] == "source_encoding_error" for record in ledger for error in record.get("errors", []))

def test_stage1_graphify_exit_zero_missing_artifacts_fails_manifest_and_validate_graph_blocks(tmp_path):
    novel = tmp_path / "mini_novel.txt"
    novel.write_text("法宝", encoding="utf-8")
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "法宝分析模板.md").write_text("# 法宝分析模板\n## 字段\n- 法宝", encoding="utf-8")
    config = _config(template_dir, graphify_repo=None)
    config["graphify_adapter"] = {"mode": "cli", "command": [sys.executable, "-c", "import pathlib,sys; pathlib.Path(sys.argv[2]).mkdir(parents=True, exist_ok=True)", "{source}", "{output_dir}"], "timeout_seconds": 5}
    result = build_stage1_graph(novel, config)
    graph_dir = tmp_path / "mini_novel.storygraph"
    manifest = json.loads((graph_dir / "manifest.json").read_text(encoding="utf-8"))
    ledger = json.loads((graph_dir / "coverage" / "agent-run-ledger.json").read_text(encoding="utf-8"))
    validation = validate_graph_dir(graph_dir)
    assert result["status"] == "failed"
    assert result["error"]["code"] == "graphify_artifact_missing"
    assert manifest["stage_status"]["stage1"] == "failed"
    assert any(error["code"] == "graphify_artifact_missing" for record in ledger for error in record.get("errors", []))
    assert "blocking_ledger:graphify_artifact_missing" in validation.errors
```

```python
# tests/test_stage1_idempotency.py
import json
import sys
from pathlib import Path
from storygraph_lib.stage1 import build_stage1_graph

def _write_sample_templates(template_dir: Path, template_count: int):
    for index in range(template_count):
        (template_dir / f"模板{index:02d}模板.md").write_text(f"# 模板{index:02d}模板\n## 字段\n- 法宝\n## 证据要求\n- 原文位置", encoding="utf-8")

def _config(template_dir: Path, graphify_repo: Path, template_count: int):
    mappings = {f"模板{index:02d}": {"graph_node_mapping": [f"template_{index:02d}_node"], "graph_event_mapping": [f"template_{index:02d}_event"], "graph_relation_mapping": [f"template_{index:02d}_relation"]} for index in range(template_count)}
    mappings["default_mapping"] = {"graph_node_mapping": ["template_specific_node"], "graph_event_mapping": ["template_specific_event"], "graph_relation_mapping": ["template_specific_relation"]}
    return {
        "graph_dir_suffix": ".storygraph",
        "output_language": "zh-CN",
        "paths": {"template_dir": str(template_dir), "graphify_repo": str(graphify_repo)},
        "template_discovery": {"glob": "*模板.md", "readme_index_file": "README.md"},
        "template_parser_rules": None,
        "template_graph_mappings": mappings,
        "status_enums": {"requirement_statuses": ["covered", "needs_review", "not_found_in_source"], "verification_statuses": ["verified", "needs_review", "rejected"], "confidence_levels": ["EXTRACTED", "INFERRED", "AMBIGUOUS"]},
        "graphify_adapter": {"mode": "local-repo-or-cli", "command": [sys.executable, "-c", "import json,pathlib,sys; out=pathlib.Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True); (out/'graph.json').write_text(json.dumps({'schema_version': '1.0', 'graphify_schema_version': 'test', 'storygraph_schema_version': '1.0', 'nodes': [], 'edges': [], 'hyperedges': [], 'events': [], 'evidence_index': [], 'metadata': {'graphify_schema_version': 'test'}}), encoding='utf-8'); (out/'GRAPH_REPORT.md').write_text('# Graph Report\\n', encoding='utf-8'); (out/'graph.html').write_text('<!doctype html><title>graph</title>', encoding='utf-8')", "{source}", "{output_dir}"], "timeout_seconds": 5},
        "chunk_strategy": {"mode": "chapter-aware", "fallback_mode": "bounded-chars", "max_chars": 100, "overlap_chars": 0},
        "evidence_matching_strategy": {"mode": "substring"},
        "writer_policy": {"managed_outputs": ["manifest.json", "graphify-out/graph.json", "graphify-out/GRAPH_REPORT.md", "graphify-out/graph.html", "requirements/template-requirements.json", "coverage/chunk-ledger.json", "coverage/evidence-index.json", "coverage/template-readiness.json", "coverage/agent-run-ledger.json", "coverage/gap-report.md"]}
    }

def test_stage1_reuses_graph_when_source_hash_is_unchanged(tmp_path):
    novel = tmp_path / "mini.txt"
    novel.write_text("法宝 小瓶", encoding="utf-8")
    template_dir = tmp_path / "templates"; template_dir.mkdir()
    sample_template_count = 37  # 当前 CultivationWorld 样例 fixture 数量，不是通用契约。
    _write_sample_templates(template_dir, sample_template_count)
    graphify_repo = tmp_path / "graphify"; graphify_repo.mkdir()
    config = _config(template_dir, graphify_repo, sample_template_count)
    first = build_stage1_graph(novel, config)
    second = build_stage1_graph(novel, config)
    assert first["status"] == "success"
    assert second["status"] == "reused"

def test_stage1_marks_source_changed_when_hash_changes(tmp_path):
    novel = tmp_path / "mini.txt"
    novel.write_text("法宝", encoding="utf-8")
    template_dir = tmp_path / "templates"; template_dir.mkdir()
    sample_template_count = 37  # 当前 CultivationWorld 样例 fixture 数量，不是通用契约。
    _write_sample_templates(template_dir, sample_template_count)
    graphify_repo = tmp_path / "graphify"; graphify_repo.mkdir()
    config = _config(template_dir, graphify_repo, sample_template_count)
    build_stage1_graph(novel, config)
    novel.write_text("法宝 小瓶", encoding="utf-8")
    result = build_stage1_graph(novel, config)
    assert result["source_state"] == "changed"

def test_stage1_marks_changed_when_template_file_hash_changes(tmp_path):
    novel = tmp_path / "mini.txt"
    novel.write_text("法宝", encoding="utf-8")
    template_dir = tmp_path / "templates"; template_dir.mkdir()
    sample_template_count = 37  # 当前 CultivationWorld 样例 fixture 数量，不是通用契约。
    _write_sample_templates(template_dir, sample_template_count)
    graphify_repo = tmp_path / "graphify"; graphify_repo.mkdir()
    config = _config(template_dir, graphify_repo, sample_template_count)
    build_stage1_graph(novel, config)
    (template_dir / "模板00模板.md").write_text("# 模板00模板\n## 字段\n- 丹药\n## 证据要求\n- 原文位置", encoding="utf-8")
    result = build_stage1_graph(novel, config)
    assert result["source_state"] == "changed"

def test_stage1_marks_changed_when_graphify_source_changes(tmp_path):
    novel = tmp_path / "mini.txt"
    novel.write_text("法宝", encoding="utf-8")
    template_dir = tmp_path / "templates"; template_dir.mkdir()
    sample_template_count = 37  # 当前 CultivationWorld 样例 fixture 数量，不是通用契约。
    _write_sample_templates(template_dir, sample_template_count)
    graphify_a = tmp_path / "graphify-a"; graphify_a.mkdir()
    graphify_b = tmp_path / "graphify-b"; graphify_b.mkdir()
    config = _config(template_dir, graphify_a, sample_template_count)
    build_stage1_graph(novel, config)
    config["paths"]["graphify_repo"] = str(graphify_b)
    result = build_stage1_graph(novel, config)
    assert result["source_state"] == "changed"
```

- [ ] **Step 2: Run stage 1 tests and confirm they fail**

Run:

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python -m pytest tests\test_stage1.py tests\test_stage1_idempotency.py -v
```

Expected: `FAIL` because `build_stage1_graph` and idempotency state logic are not defined.

- [ ] **Step 3: Implement idempotency state and no-rebuild decision**

```python
# skill-src/storygraph/scripts/storygraph_lib/state.py
import json

REQUIRED_STAGE1_FILES = ["manifest.json", "graphify-out/graph.json", "graphify-out/GRAPH_REPORT.md", "graphify-out/graph.html", "requirements/template-requirements.json", "coverage/chunk-ledger.json", "coverage/evidence-index.json", "coverage/template-readiness.json", "coverage/agent-run-ledger.json", "coverage/gap-report.md"]

def _has_blocking_failure(graph_dir):
    ledger_path = graph_dir / "coverage" / "agent-run-ledger.json"
    if not ledger_path.exists():
        return False
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    return any(record.get("status") == "failed" and any(error.get("code", "").startswith("graphify_") for error in record.get("errors", [])) for record in ledger)

def stage1_state(ctx, config_hash: str, graph_validator):
    manifest_path = ctx.graph_dir / "manifest.json"
    missing = [item for item in REQUIRED_STAGE1_FILES if not (ctx.graph_dir / item).exists()]
    if not manifest_path.exists() or missing:
        return {"action": "build", "source_state": "new", "missing": missing}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    stage_success = manifest.get("stage_status", {}).get("stage1") == "success"
    graph_ok = graph_validator(ctx.graph_dir).ok
    if manifest.get("source_hash") == ctx.source_hash and manifest.get("config_hash") == config_hash and stage_success and graph_ok and not _has_blocking_failure(ctx.graph_dir):
        return {"action": "reuse", "source_state": "unchanged", "missing": []}
    return {"action": "rebuild", "source_state": "changed", "missing": missing}
```

- [ ] **Step 4: Implement Stage 1 orchestration with real supplement merge and graphify failure ledger**

```python
# skill-src/storygraph/scripts/storygraph_lib/stage1.py
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from .agent_ledger import make_stage_agent_records, validate_single_writer
from .coverage import make_chunk_ledger, write_coverage_outputs
from .graph_schema import merge_template_supplements, validate_canonical_graph
from .graphify_adapter import GraphifyAdapter
from .manifest import write_manifest
from .output_writer import OutputWriter
from .paths import resolve_novel_context
from .state import stage1_state
from .template_aware import extract_template_aware_supplements
from .templates import build_requirement_matrix, discover_templates
from .validation import validate_graph_dir

@dataclass(frozen=True)
class PreflightNovelContext:
    source_path: Path
    source_hash: str | None
    source_size: int
    novel_name: str
    novel_dir: Path
    graph_dir: Path

def _infer_novel_context_without_reading(source_path: Path, graph_dir_suffix: str, create: bool = False) -> PreflightNovelContext:
    source = source_path.expanduser().resolve(strict=False)
    if not source.name or source.name in {".", ".."}:
        raise OSError("cannot_infer_graph_dir")
    graph_dir = source.parent / f"{source.stem}{graph_dir_suffix}"
    if create:
        graph_dir.mkdir(parents=True, exist_ok=True)
    return PreflightNovelContext(source, None, 0, source.stem, source.parent, graph_dir)

def _failed_chunk(ctx, error: Exception) -> list[dict]:
    return [{"chunk_id": "chunk-0001", "source_range": [0, ctx.source_size], "chapter_hint": None, "hash": None, "scanned_at": None, "processor": "storygraph-stage1", "extraction_status": "failed", "failure": {"code": "chunk_extraction_failure", "message": str(error), "retryable": True}, "retry_count": 0}]

def _append_error(agent_runs, role, error):
    target = next((record for record in agent_runs if record["agent_role"] == role), agent_runs[-1])
    target["status"] = "failed"
    target.setdefault("errors", []).append(error)

def _mark_completed(agent_runs):
    for record in agent_runs:
        if record["status"] == "pending":
            record["status"] = "completed"
            record["reviewer_status"] = "passed"

def _parse_subagent_payloads(config, agent_runs, gap_lines):
    errors = []
    warnings = []
    blocking = config.get("coverage_thresholds", {}).get("block_on_unparsable_subagent_json", True)
    for index, payload in enumerate(config.get("agent_policy", {}).get("sub_agent_json_payloads", []), 1):
        try:
            json.loads(payload)
        except json.JSONDecodeError as exc:
            error = {"code": "unparsable_subagent_json", "payload_index": index, "message": str(exc)}
            if blocking:
                errors.append(error)
                _append_error(agent_runs, "质量审查", error)
            else:
                warnings.append(error)
            gap_lines.append(f"- unparsable_subagent_json: payload {index}")
    return {"errors": errors, "warnings": warnings}

def _evaluate_coverage_failures(readiness, chunks, config, agent_runs, gap_lines):
    errors = []
    warnings = []
    thresholds = config.get("coverage_thresholds", {})
    readiness_threshold = thresholds.get("readiness_warning_threshold", 0)
    for record in readiness:
        if record.get("readiness_score", 0) < readiness_threshold:
            error = {"code": "readiness_below_threshold", "template_name": record["template_name"], "readiness_score": record.get("readiness_score", 0), "threshold": readiness_threshold}
            gap_lines.append(f"- readiness_below_threshold: {record['template_name']} {record.get('readiness_score', 0)} < {readiness_threshold}")
            if thresholds.get("block_on_low_readiness", True):
                errors.append(error)
                _append_error(agent_runs, "覆盖审查", error)
            else:
                warnings.append(error)
        if thresholds.get("block_on_template_without_reliable_evidence", True) and record.get("evidence_count", 0) == 0:
            error = {"code": "template_without_reliable_evidence", "template_name": record["template_name"]}
            errors.append(error)
            gap_lines.append(f"- template_without_reliable_evidence: {record['template_name']}")
            _append_error(agent_runs, "覆盖审查", error)
        elif record.get("evidence_count", 0) == 0:
            error = {"code": "template_without_reliable_evidence", "template_name": record["template_name"]}
            warnings.append(error)
            gap_lines.append(f"- template_without_reliable_evidence: {record['template_name']}")
    if thresholds.get("require_all_chunks_scanned", True):
        for chunk in chunks:
            if chunk.get("extraction_status") != "completed":
                error = {"code": "chunk_extraction_failure", "chunk_id": chunk.get("chunk_id"), "failure": chunk.get("failure")}
                errors.append(error)
                gap_lines.append(f"- chunk_extraction_failure: {chunk.get('chunk_id')}")
                _append_error(agent_runs, "图抽取", error)
    return {"errors": errors, "warnings": warnings}

def _write_failure_manifest(manifest_path, status):
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_data["stage_status"]["stage1"] = status
    manifest_path.write_text(json.dumps(manifest_data, ensure_ascii=False, indent=2), encoding="utf-8")

def _write_preflight_failure(ctx, config, error, role="图抽取") -> None:
    writer = OutputWriter(ctx.graph_dir, config["writer_policy"]["managed_outputs"])
    manifest = {
        "schema": "storygraph-manifest.v1",
        "source_path": str(ctx.source_path),
        "source_hash": ctx.source_hash,
        "source_size": ctx.source_size,
        "novel_name": ctx.novel_name,
        "graph_dir": str(ctx.graph_dir),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config_hash": None,
        "graphify_source": str(config.get("paths", {}).get("graphify_repo")),
        "stage_status": {"stage1": "failed", "stage2": "not_started"}
    }
    chunks = [{"chunk_id": "chunk-0001", "source_range": [0, ctx.source_size], "chapter_hint": None, "hash": None, "scanned_at": None, "processor": "storygraph-stage1", "extraction_status": "failed", "failure": error, "retry_count": 0}]
    agent_runs = make_stage_agent_records([chunks[0]["chunk_id"]], [])
    _append_error(agent_runs, role, error)
    writer.write_json("manifest.json", manifest)
    write_coverage_outputs(writer, chunks, [], [], agent_runs, [f"- {error['code']}: {error.get('message', '')}"])

def _source_failure_response(source_path, graph_dir, error, manifest_written):
    return {"status": "failed", "source_state": "unknown", "graph_dir": str(graph_dir) if graph_dir else None, "manifest_written": manifest_written, "error": error, "validation_errors": [error["code"]]}

def graphify_source_fingerprint(config: dict) -> dict:
    repo = Path(config["paths"]["graphify_repo"]) if config["paths"].get("graphify_repo") else None
    commit = None
    if repo and (repo / ".git").exists():
        completed = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True)
        commit = completed.stdout.strip() if completed.returncode == 0 else None
    return {
        "graphify_repo": str(repo) if repo else None,
        "graphify_commit": commit,
        "adapter_command": config["graphify_adapter"]["command"],
        "adapter_timeout_seconds": config["graphify_adapter"]["timeout_seconds"]
    }

def stable_stage_input_hash(config: dict, templates: list) -> str:
    relevant = {
        "graph_dir_suffix": config["graph_dir_suffix"],
        "template_discovery": config["template_discovery"],
        "template_parser_rules": config.get("template_parser_rules"),
        "graphify_source": graphify_source_fingerprint(config),
        "templates": [{"template_name": template.name, "template_file": str(template.path), "template_file_hash": template.file_hash} for template in templates],
        "chunk_strategy": config["chunk_strategy"],
        "template_count_policy": config.get("template_count_policy"),
        "supplemental_graph_policy": config.get("supplemental_graph_policy")
    }
    return sha256(json.dumps(relevant, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

def build_stage1_graph(source_path: Path, config: dict) -> dict:
    # Error contract: unreadable source, UnicodeDecodeError, graphify artifact loss,
    # chunk extraction failure, readiness below threshold, missing reliable evidence,
    # and unparsable sub-agent JSON all mark manifest stage1 as failed.
    try:
        preflight_ctx = _infer_novel_context_without_reading(Path(source_path), config["graph_dir_suffix"], create=True)
    except (OSError, ValueError) as exc:
        error = {"code": "source_unreadable", "message": str(exc), "source_path": str(source_path)}
        return _source_failure_response(source_path, None, error, manifest_written=False)
    try:
        ctx = resolve_novel_context(Path(source_path), config["graph_dir_suffix"], create=True)
    except (FileNotFoundError, PermissionError) as exc:
        error = {"code": "source_unreadable", "message": str(exc), "source_path": str(preflight_ctx.source_path)}
        _write_preflight_failure(preflight_ctx, config, error)
        return _source_failure_response(source_path, preflight_ctx.graph_dir, error, manifest_written=True)
    except UnicodeDecodeError as exc:
        error = {"code": "source_encoding_error", "message": str(exc), "source_path": str(preflight_ctx.source_path)}
        _write_preflight_failure(preflight_ctx, config, error)
        return _source_failure_response(source_path, preflight_ctx.graph_dir, error, manifest_written=True)
    discovery = discover_templates(Path(config["paths"]["template_dir"]), config["template_discovery"]["glob"], config["template_discovery"]["readme_index_file"])
    config_hash = stable_stage_input_hash(config, discovery.templates)
    current_state = stage1_state(ctx, config_hash, validate_graph_dir)
    if current_state["action"] == "reuse":
        return {"status": "reused", "source_state": "unchanged", "graph_dir": str(ctx.graph_dir)}
    manifest_path = write_manifest(ctx, config_hash=config_hash, graphify_source=str(config.get("paths", {}).get("graphify_repo")))
    writer = OutputWriter(ctx.graph_dir, config["writer_policy"]["managed_outputs"])
    matrix = build_requirement_matrix(discovery.templates, config.get("template_parser_rules"), config["template_graph_mappings"], config["status_enums"], config["output_language"])
    count_policy = config.get("template_count_policy", {})
    if count_policy.get("enforce_integration_count") and matrix["template_count"] != count_policy.get("expected_existing_templates"):
        raise ValueError(f"template_count_mismatch:{matrix['template_count']}:{count_policy.get('expected_existing_templates')}")
    writer.write_json("requirements/template-requirements.json", matrix)
    try:
        chunks = make_chunk_ledger(ctx.source_path, config["chunk_strategy"], processor="storygraph-stage1")
    except UnicodeDecodeError as exc:
        error = {"code": "source_encoding_error", "message": str(exc), "source_path": str(ctx.source_path)}
        _write_preflight_failure(ctx, config, error)
        return _source_failure_response(source_path, ctx.graph_dir, error, manifest_written=True)
    except Exception as exc:
        chunks = _failed_chunk(ctx, exc)
        readiness = [{"template_name": t["template_name"], "readiness_score": 0, "supporting_node_count": 0, "supporting_edge_count": 0, "supporting_event_count": 0, "evidence_count": 0, "missing_requirement_types": ["chunk_extraction"], "requirement_statuses": [], "notes": ["chunk_extraction_failure"]} for t in matrix["templates"]]
        agent_runs = make_stage_agent_records([c["chunk_id"] for c in chunks], [t["template_name"] for t in matrix["templates"]])
        gap_lines = [f"- chunk_extraction_failure: {exc}"]
        _append_error(agent_runs, "图抽取", {"code": "chunk_extraction_failure", "message": str(exc)})
        write_coverage_outputs(writer, chunks, [], readiness, agent_runs, gap_lines)
        _write_failure_manifest(manifest_path, "failed")
        return {"status": "failed", "source_state": current_state["source_state"], "graph_dir": str(ctx.graph_dir), "warnings": discovery.warnings, "validation_errors": ["chunk_extraction_failure"]}
    agent_runs = make_stage_agent_records([c["chunk_id"] for c in chunks], [t["template_name"] for t in matrix["templates"]])
    single_writer = validate_single_writer(agent_runs)
    if not single_writer.ok:
        for error in single_writer.errors:
            _append_error(agent_runs, "质量审查", {"code": "single_writer_conflict", "detail": error})
        write_coverage_outputs(writer, chunks, [], [], agent_runs, [f"- single_writer_conflict: {error}" for error in single_writer.errors])
        _write_failure_manifest(manifest_path, "failed")
        return {"status": "failed", "source_state": current_state["source_state"], "graph_dir": str(ctx.graph_dir), "warnings": discovery.warnings, "validation_errors": single_writer.errors}
    try:
        supplement, readiness = extract_template_aware_supplements(ctx.novel_name, ctx.source_path, chunks, matrix, config["evidence_matching_strategy"])
    except UnicodeDecodeError as exc:
        error = {"code": "source_encoding_error", "message": str(exc), "source_path": str(ctx.source_path)}
        _write_preflight_failure(ctx, config, error)
        _write_failure_manifest(manifest_path, "failed")
        return _source_failure_response(source_path, ctx.graph_dir, error, manifest_written=True)
    for chunk in chunks:
        if chunk.get("extraction_status") == "pending":
            chunk["extraction_status"] = "completed"
    gap_lines = [f"- warning: {w['code']} {w['file']}" for w in discovery.warnings]
    coverage_contract = _evaluate_coverage_failures(readiness, chunks, config, agent_runs, gap_lines)
    contract_errors = coverage_contract["errors"]
    contract_warnings = coverage_contract["warnings"]
    subagent_contract = _parse_subagent_payloads(config, agent_runs, gap_lines)
    contract_errors.extend(subagent_contract["errors"])
    contract_warnings.extend(subagent_contract["warnings"])
    graphify_out = ctx.graph_dir / "graphify-out"; graphify_out.mkdir(parents=True, exist_ok=True)
    adapter = GraphifyAdapter(Path(config["paths"]["graphify_repo"]) if config["paths"].get("graphify_repo") else None, config["graphify_adapter"]["command"], config["graphify_adapter"]["timeout_seconds"], config["graphify_adapter"]["mode"])
    adapter_result = adapter.build_graph(ctx.source_path, graphify_out)
    if not adapter_result.ok:
        agent_runs[1]["status"] = "failed"
        agent_runs[1]["errors"] = [adapter_result.error]
        validation = type("Validation", (), {"ok": False, "errors": [adapter_result.error["code"]]})()
        gap_lines.append(f"- graphify error: {adapter_result.error['code']}")
        write_coverage_outputs(writer, chunks, [], readiness, agent_runs, gap_lines)
        status = "failed"
    else:
        required_graphify = ["graph.json", "GRAPH_REPORT.md", "graph.html"]
        missing_graphify = [name for name in required_graphify if not (graphify_out / name).exists()]
        if missing_graphify:
            agent_runs[1]["status"] = "failed"
            agent_runs[1]["errors"] = [{"code": "graphify_artifact_missing", "missing": missing_graphify}]
            validation = type("Validation", (), {"ok": False, "errors": ["graphify_artifact_missing"]})()
            gap_lines.append(f"- graphify_artifact_missing: {missing_graphify}")
            status = "failed"
        else:
            base = json.loads(adapter_result.graph_path.read_text(encoding="utf-8"))
            graph = merge_template_supplements(base, supplement)
            validation = validate_canonical_graph(graph, config["status_enums"])
            writer.write_json("graphify-out/graph.json", graph)
            writer.write_text("graphify-out/GRAPH_REPORT.md", (graphify_out / "GRAPH_REPORT.md").read_text(encoding="utf-8"))
            writer.write_text("graphify-out/graph.html", (graphify_out / "graph.html").read_text(encoding="utf-8"))
            status = "success" if validation.ok and not contract_errors and not contract_warnings else ("warning" if validation.ok and not contract_errors else "failed")
        gap_lines = [f"- validation error: {error}" for error in validation.errors] + gap_lines
        if status in {"success", "warning"}:
            _mark_completed(agent_runs)
        write_coverage_outputs(writer, chunks, supplement["evidence_index"], readiness, agent_runs, gap_lines)
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_data["stage_status"]["stage1"] = status
    manifest_path.write_text(json.dumps(manifest_data, ensure_ascii=False, indent=2), encoding="utf-8")
    result = {"status": status, "source_state": current_state["source_state"], "graph_dir": str(ctx.graph_dir), "warnings": discovery.warnings, "validation_errors": validation.errors}
    if status == "failed" and validation.errors:
        result["error"] = {"code": validation.errors[0]}
    return result
```

Stage 1 failure handling is part of the implementation contract:
- Before the formal `resolve_novel_context` call, infer `graph_dir` and `novel_name` without reading source contents. If that preflight inference fails, CLI must still return structured JSON with `status: failed`, `error.code: source_unreadable`, `graph_dir: null`, and `manifest_written: false`.
- If the source file is missing or unreadable after `graph_dir` can be inferred, return nonzero from CLI, write `manifest.json`, `coverage\agent-run-ledger.json`, and `coverage\gap-report.md` when possible, set `manifest.stage_status.stage1` to `failed`, and use stable error code `source_unreadable`.
- If the source raises `UnicodeDecodeError`, do not collapse it into a generic chunk or pipeline exception; return/write stable error code `source_encoding_error`, failed manifest, blocking ledger, and gap report.
- If graphify exits nonzero or exits zero while omitting `graph.json`, `GRAPH_REPORT.md`, or `graph.html`, do not write a merged `graphify-out\graph.json` that appears successful; record `graphify_failed` or `graphify_artifact_missing` in `agent-run-ledger.json`.
- If a chunk extraction fails, preserve its `chunk_id`, `source_range`, `scanned_at`, `processor`, and `failure` fields in `chunk-ledger.json`.
- If `validate_single_writer(agent_runs)` reports duplicate `write_scope` or `output_paths`, record `single_writer_conflict`, write failure ledgers, set `manifest.stage_status.stage1` to `failed`, and stop before graphify or any success graph output is written.
- `validate-graph` / `validate_graph_dir` must treat any `coverage\agent-run-ledger.json` record with `status: failed` as blocking by adding `blocking_ledger:<error_code>` to validation errors.
- `coverage_thresholds.require_all_chunks_scanned` controls whether failed chunks are blocking.
- `coverage_thresholds.readiness_warning_threshold` defines the minimum readiness score; `block_on_low_readiness` controls whether below-threshold readiness marks Stage 1 `failed` or `warning`.
- `coverage_thresholds.block_on_template_without_reliable_evidence` controls whether a template with zero reliable evidence marks Stage 1 `failed` or `warning`.
- `coverage_thresholds.block_on_unparsable_subagent_json` defaults to blocking; any unparsable sub-agent JSON payload records `unparsable_subagent_json` in `gap-report.md` and `agent-run-ledger.json`.

- [ ] **Step 5: Replace CLI with fully registered build, inspect, and deep validate commands**

```python
# replace skill-src/storygraph/scripts/storygraph_lib/cli.py after Task 8
import json
from pathlib import Path
from .config import load_config
from .graph_schema import validate_canonical_graph
from .stage1 import build_stage1_graph
from .templates import build_requirement_matrix, discover_templates
from .validation import validate_graph_dir, validate_skill_tree

def _default_config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "storygraph.default.json"

def _print_json(data):
    print(json.dumps(data, ensure_ascii=False, indent=2))

def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="storygraph")
    sub = parser.add_subparsers(dest="command", required=True)
    config_check = sub.add_parser("config-check"); config_check.add_argument("--config"); config_check.add_argument("--local-override")
    validate = sub.add_parser("validate-skill"); validate.add_argument("--skill-root", default=str(Path(__file__).resolve().parents[2]))
    inspect = sub.add_parser("inspect-templates"); inspect.add_argument("--config"); inspect.add_argument("--local-override"); inspect.add_argument("--template-dir", required=True)
    build = sub.add_parser("build-stage1"); build.add_argument("--config"); build.add_argument("--local-override"); build.add_argument("--source", required=True); build.add_argument("--template-dir", required=True); build.add_argument("--graphify-repo")
    graph = sub.add_parser("validate-graph"); graph.add_argument("--graph-dir", required=True)
    args = parser.parse_args(argv)
    default_config = Path(getattr(args, "config", None)) if getattr(args, "config", None) else _default_config_path()
    local_override = Path(args.local_override) if getattr(args, "local_override", None) else None
    config = load_config(default_config, local_override=local_override)
    if args.command == "config-check":
        _print_json({"ok": True, "graph_dir_suffix": config["graph_dir_suffix"]}); return 0
    if args.command == "validate-skill":
        result = validate_skill_tree(Path(args.skill_root)); _print_json({"ok": result.ok, "missing": result.missing}); return 0 if result.ok else 2
    if args.command == "inspect-templates":
        discovery = discover_templates(Path(args.template_dir), config["template_discovery"]["glob"], config["template_discovery"]["readme_index_file"])
        matrix = build_requirement_matrix(discovery.templates, config["template_parser_rules"], config["template_graph_mappings"], config["status_enums"], config["output_language"])
        template_details = [
            {
                "template_name": t["template_name"],
                "mapping_source": t["mapping_source"],
                "uses_default_mapping": t["mapping_source"] == "default_mapping",
                "graph_node_mapping": t["graph_node_mapping"],
                "graph_event_mapping": t["graph_event_mapping"],
                "graph_relation_mapping": t["graph_relation_mapping"],
            }
            for t in matrix["templates"]
        ]
        has_default_mapping = any(t["uses_default_mapping"] for t in template_details)
        _print_json({"template_count": matrix["template_count"], "warnings": discovery.warnings, "templates": template_details, "has_default_mapping": has_default_mapping})
        return 2 if has_default_mapping else 0
    if args.command == "build-stage1":
        config["paths"]["template_dir"] = args.template_dir
        config["paths"]["graphify_repo"] = args.graphify_repo
        result = build_stage1_graph(Path(args.source), config)
        _print_json(result)
        return 0 if result["status"] in {"success", "warning", "reused"} else 2
    if args.command == "validate-graph":
        result = validate_graph_dir(Path(args.graph_dir))
        _print_json({"ok": result.ok, "errors": result.errors}); return 0 if result.ok else 2
    return 2
```

```python
# add to skill-src/storygraph/scripts/storygraph_lib/validation.py
import json
from pathlib import Path
from dataclasses import dataclass
from .agent_ledger import validate_single_writer
from .graph_schema import validate_canonical_graph

@dataclass(frozen=True)
class GraphDirValidation:
    ok: bool
    errors: list[str]

def validate_graph_dir(graph_dir: Path) -> GraphDirValidation:
    required = ["manifest.json", "graphify-out/graph.json", "graphify-out/GRAPH_REPORT.md", "graphify-out/graph.html", "requirements/template-requirements.json", "coverage/chunk-ledger.json", "coverage/evidence-index.json", "coverage/template-readiness.json", "coverage/agent-run-ledger.json", "coverage/gap-report.md"]
    errors = [f"missing:{item}" for item in required if not (graph_dir / item).exists()]
    agent_ledger_path = graph_dir / "coverage" / "agent-run-ledger.json"
    agent_ledger = json.loads(agent_ledger_path.read_text(encoding="utf-8")) if agent_ledger_path.exists() else []
    for record in agent_ledger:
        if record.get("status") == "failed":
            for error in record.get("errors", []):
                errors.append(f"blocking_ledger:{error.get('code', 'unknown')}")
    if errors:
        return GraphDirValidation(False, errors)
    manifest = json.loads((graph_dir / "manifest.json").read_text(encoding="utf-8"))
    graph = json.loads((graph_dir / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
    requirements = json.loads((graph_dir / "requirements" / "template-requirements.json").read_text(encoding="utf-8"))
    chunks = json.loads((graph_dir / "coverage" / "chunk-ledger.json").read_text(encoding="utf-8"))
    coverage_evidence = json.loads((graph_dir / "coverage" / "evidence-index.json").read_text(encoding="utf-8"))
    schema = validate_canonical_graph(graph)
    readiness = json.loads((graph_dir / "coverage" / "template-readiness.json").read_text(encoding="utf-8"))
    single_writer = validate_single_writer(agent_ledger)
    if not single_writer.ok:
        errors.extend(single_writer.errors)
    allowed_statuses = {"covered", "needs_review", "not_found_in_source"}
    template_count = requirements.get("template_count")
    requirement_records = requirements.get("templates", [])
    requirement_templates = {record["template_name"] for record in requirement_records}
    readiness_templates = set()
    for record in readiness:
        template_name = record["template_name"]
        if template_name in readiness_templates:
            errors.append(f"duplicate_readiness_template_name:{template_name}")
        readiness_templates.add(template_name)
    if template_count != len(requirement_records):
        errors.append("requirements_template_count_mismatch")
    if len(readiness) != template_count:
        errors.append("requirements_readiness_count_mismatch")
    if requirement_templates != readiness_templates:
        errors.append("requirements_readiness_template_mismatch")
    expected_requirement_ids = set()
    for record in requirements["templates"]:
        for kind in ["required_fields", "required_tables", "required_cards", "required_case_patterns"]:
            for item in record.get(kind, []):
                expected_requirement_ids.add(f"{record['template_name']}.{kind}.{item}")
    actual_requirement_ids = {status["requirement_id"] for record in readiness for status in record.get("requirement_statuses", [])}
    if expected_requirement_ids != actual_requirement_ids:
        errors.append("requirements_readiness_id_mismatch")
    if any(not record.get("requirement_statuses") for record in readiness):
        errors.append("readiness_without_requirement_statuses")
    for record in readiness:
        for status in record.get("requirement_statuses", []):
            if status.get("status") not in allowed_statuses:
                errors.append(f"bad_readiness_status:{status.get('status')}")
    if chunks:
        ordered = sorted(chunks, key=lambda chunk: chunk["source_range"][0])
        if ordered[0]["source_range"][0] != 0 or ordered[-1]["source_range"][1] != manifest["source_size"]:
            errors.append("chunk_ledger_does_not_cover_full_source")
        for previous, current in zip(ordered, ordered[1:]):
            if current["source_range"][0] > previous["source_range"][1]:
                errors.append("chunk_ledger_has_gap")
        for chunk in ordered:
            if chunk.get("extraction_status") != "completed":
                errors.append(f"chunk_not_completed:{chunk.get('chunk_id')}:{chunk.get('extraction_status')}")
    else:
        errors.append("chunk_ledger_empty")
    graph_evidence_ids = {item["evidence_id"] for item in graph.get("evidence_index", [])}
    coverage_evidence_ids = {item["evidence_id"] for item in coverage_evidence}
    if graph_evidence_ids != coverage_evidence_ids:
        errors.append("graph_coverage_evidence_mismatch")
    for item in graph.get("nodes", []) + graph.get("edges", []) + graph.get("events", []):
        if any(eid not in graph_evidence_ids for eid in item.get("evidence_ids", [])):
            errors.append(f"unknown_evidence_reference:{item.get('id')}")
    if any(record.get("status") == "failed" for record in agent_ledger):
        errors.append("blocking_failure_ledger")
    if manifest.get("stage_status", {}).get("stage1") != "success":
        errors.append(f"stage1_not_success:{manifest.get('stage_status', {}).get('stage1')}")
    if manifest.get("stage_status", {}).get("stage1") == "success" and any(record.get("status") != "completed" for record in agent_ledger):
        errors.append("agent_run_not_completed")
    errors.extend(schema.errors)
    return GraphDirValidation(ok=not errors, errors=errors)
```

- [ ] **Step 6: Run automated and external-output verification, then commit stage 1 pipeline**

Run:

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python -m pytest tests\test_stage1.py tests\test_stage1_idempotency.py tests\test_validation_cli.py -v
```

Expected: tests pass, including idempotent reuse and source hash change detection.

Run:

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python skill-src\storygraph\scripts\storygraph.py build-stage1 --source 'E:\AI_Projects\CultivationWorld\docs\世界观参考\凡人修仙传\凡人修仙传.txt' --template-dir 'E:\AI_Projects\CultivationWorld\docs\世界观参考\模板' --graphify-repo 'E:\Github_Projects\graphify'; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; python skill-src\storygraph\scripts\storygraph.py validate-graph --graph-dir 'E:\AI_Projects\CultivationWorld\docs\世界观参考\凡人修仙传\凡人修仙传.storygraph'; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

Expected: this intentionally creates or reuses the external `.storygraph` directory beside the novel. Re-running the same command without changing the novel reports `"status": "reused"`; `validate-graph` performs deep schema/readiness/evidence validation and exits `0`.

Commit:

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; git -c core.quotePath=false add skill-src\storygraph\scripts\storygraph_lib skill-src\storygraph\scripts\storygraph.py docs\storygraph-cli.md tests; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; git commit -m "feat: add storygraph stage1 pipeline and validation"; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

### Task 9: Stage 2 Extraction Schema, No-Overwrite Draft Policy, Docs, And Final Verification

This task is a Stage 2 schema scaffold only. It defines executable contracts for future extraction, ledgers, evidence usage, output policy, and validation; it does not implement full template rendering or content generation.

**Files:**
- Create: `E:\AI_Projects\StoryGraph\skill-src\storygraph\scripts\storygraph_lib\stage2_schema.py`
- Modify: `E:\AI_Projects\StoryGraph\skill-src\storygraph\references\extraction-workflow.md`
- Modify: `E:\AI_Projects\StoryGraph\docs\storygraph-cli.md`
- Modify: `E:\AI_Projects\StoryGraph\skill-src\storygraph\SKILL.md`
- Test: `E:\AI_Projects\StoryGraph\tests\test_stage2_schema.py`
- Test: `E:\AI_Projects\StoryGraph\tests\test_stage2_policy.py`

- [ ] **Step 1: Write failing tests for stage 2 extraction contract and no-overwrite output policy**

```python
# tests/test_stage2_schema.py
from storygraph_lib.stage2_schema import make_extraction_record, make_template_evidence_usage, make_template_gap_report, make_template_run_ledger, validate_extraction_record

def test_stage2_extraction_record_requires_evidence_categories():
    config = {"output_language": "zh-CN", "stage2_categories": {"facts": "原作事实", "judgments": "我的判断", "pending_verifications": "待核验", "not_found_items": "未见可靠证据"}, "stage2_output_policy": {"default_dir": "drafts", "allowed_policies": ["draft", "backup-and-overwrite", "merge"], "draft_action": "write_draft"}}
    record = make_extraction_record(
        template_name="法宝分析",
        template_file="法宝分析模板.md",
        source_graph="凡人修仙传.storygraph/graphify-out/graph.json",
        source_novel="凡人修仙传.txt",
        requirement_id="法宝分析.required_fields.法宝",
        evidence_id="evidence:abc",
        policy=config
    )
    assert record["facts"][0]["category"] == "原作事实"
    assert record["judgments"][0]["category"] == "我的判断"
    assert record["pending_verifications"][0]["category"] == "待核验"
    assert record["not_found_items"][0]["category"] == "未见可靠证据"
    assert record["coverage_scope"]["stage1_chunk_ledger"] == "coverage/chunk-ledger.json"
    assert record["coverage_scope"]["chunk_ranges"] == []
    assert validate_extraction_record(record).ok is True

def test_stage2_scaffold_ledgers_cover_each_template_and_evidence_usage():
    templates = [f"模板{i:02d}" for i in range(5)]
    ledger = make_template_run_ledger(templates, chunk_ranges=[{"chunk_id": "chunk-0001", "source_range": [0, 100]}])
    usage = make_template_evidence_usage("模板00", "evidence:abc", "chunk-0001", [0, 100])
    gap = make_template_gap_report("模板00", "模板00.required_fields.法宝", "not_found_in_source")
    assert len(ledger["template_tasks"]) == len(templates)
    assert ledger["artifact_paths"]["template_run_ledger"] == "coverage/template-run-ledger.json"
    assert ledger["artifact_paths"]["template_evidence_usage"] == "coverage/template-evidence-usage.json"
    assert ledger["artifact_paths"]["template_gap_report"] == "coverage/template-gap-report.md"
    assert ledger["coverage_scope"]["stage1_chunk_ledger"] == "coverage/chunk-ledger.json"
    assert ledger["coverage_scope"]["chunk_ranges"][0]["source_range"] == [0, 100]
    assert usage["evidence_id"] == "evidence:abc"
    assert gap["gaps"][0]["status"] == "not_found_in_source"
```

```python
# tests/test_stage2_policy.py
from pathlib import Path
from storygraph_lib.stage2_schema import resolve_render_target

POLICY = {"default_dir": "drafts", "allowed_policies": ["draft", "backup-and-overwrite", "merge"], "draft_action": "write_draft", "existing_document_action": "write_versioned_draft"}

def test_default_policy_writes_draft_and_does_not_overwrite_existing_formal_doc(tmp_path):
    graph_dir = tmp_path / "凡人修仙传.storygraph"
    novel_dir = tmp_path
    graph_dir.mkdir()
    formal = novel_dir / "法宝分析.md"
    formal.write_text("用户已有文档", encoding="utf-8")
    decision = resolve_render_target(graph_dir, novel_dir, "法宝分析", POLICY, overwrite_policy="draft")
    assert decision["target_path"] == str(graph_dir / "drafts" / "法宝分析.md")
    assert decision["action"] == "write_draft"
    assert decision["will_overwrite"] is False
    assert formal.read_text(encoding="utf-8") == "用户已有文档"

def test_formal_target_can_only_be_used_by_backup_overwrite_or_merge_policy(tmp_path):
    graph_dir = tmp_path / "凡人修仙传.storygraph"
    novel_dir = tmp_path
    graph_dir.mkdir()
    formal = novel_dir / "法宝分析.md"
    formal.write_text("用户已有文档", encoding="utf-8")
    backup = resolve_render_target(graph_dir, novel_dir, "法宝分析", POLICY, overwrite_policy="backup-and-overwrite")
    merge = resolve_render_target(graph_dir, novel_dir, "法宝分析", POLICY, overwrite_policy="merge")
    assert backup["target_path"] == str(formal)
    assert backup["backup_path"].endswith("法宝分析.md.bak")
    assert backup["will_overwrite"] is True
    assert merge["target_path"] == str(formal)
    assert merge["action"] == "merge_existing"
    assert merge["will_overwrite"] is True
```

- [ ] **Step 2: Run stage 2 schema test and confirm it fails**

Run:

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python -m pytest tests\test_stage2_schema.py tests\test_stage2_policy.py -v
```

Expected: `FAIL` because `storygraph_lib.stage2_schema` and `resolve_render_target` are not defined.

- [ ] **Step 3: Implement extraction record schema helpers and no-overwrite render target policy**

```python
# skill-src/storygraph/scripts/storygraph_lib/stage2_schema.py
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class ExtractionValidation:
    ok: bool
    errors: list[str]

def make_extraction_record(template_name, template_file, source_graph, source_novel, requirement_id, evidence_id, policy):
    categories = policy["stage2_categories"]
    fulfilled = {"requirement_id": requirement_id, "requirement_kind": "field", "status": "covered", "linked_node_ids": [], "linked_edge_ids": [], "linked_event_ids": [], "evidence_ids": [evidence_id], "notes": []}
    return {
        "template_name": template_name,
        "template_file": template_file,
        "source_graph": source_graph,
        "source_novel": source_novel,
        "output_language": policy["output_language"],
        "coverage_scope": {"scope": "whole_novel", "stage1_chunk_ledger": "coverage/chunk-ledger.json", "chunk_ranges": [], "ledger_path": "coverage/template-run-ledger.json"},
        "fulfilled_sections": [fulfilled],
        "fulfilled_fields": [fulfilled],
        "fulfilled_tables": [],
        "fulfilled_cards": [],
        "fulfilled_cases": [],
        "facts": [{"content": "原作事实需引用证据", "category": categories["facts"], "evidence_ids": [evidence_id], "source_locations": [], "confidence": "EXTRACTED"}],
        "judgments": [{"content": "基于证据的分析判断", "category": categories["judgments"], "evidence_ids": [evidence_id], "source_locations": [], "confidence": "INFERRED"}],
        "pending_verifications": [{"content": "证据不足的条目", "category": categories["pending_verifications"], "evidence_ids": [], "source_locations": [], "confidence": "AMBIGUOUS"}],
        "not_found_items": [{"content": "全文图和分块账本未见可靠证据", "category": categories["not_found_items"], "evidence_ids": [], "source_locations": [], "confidence": "AMBIGUOUS"}],
        "evidence_citations": [evidence_id],
        "gap_items": [],
        "render_target": policy["stage2_output_policy"]["default_dir"],
        "overwrite_policy": "draft"
    }

def make_template_run_ledger(template_names, chunk_ranges):
    return {
        "schema": "template-run-ledger.json",
        "artifact_paths": {"template_run_ledger": "coverage/template-run-ledger.json", "template_evidence_usage": "coverage/template-evidence-usage.json", "template_gap_report": "coverage/template-gap-report.md"},
        "coverage_scope": {"scope": "whole_novel", "stage1_chunk_ledger": "coverage/chunk-ledger.json", "chunk_ranges": chunk_ranges},
        "template_tasks": [{"template_name": name, "status": "pending", "assigned_chunks": [c["chunk_id"] for c in chunk_ranges], "output_record": None, "errors": []} for name in template_names]
    }

def make_template_evidence_usage(template_name, evidence_id, chunk_id, source_range):
    return {"schema": "template-evidence-usage.json", "template_name": template_name, "evidence_id": evidence_id, "chunk_id": chunk_id, "source_range": source_range, "used_by_fields": [], "used_by_sections": []}

def make_template_gap_report(template_name, requirement_id, status):
    return {"schema": "template-gap-report.md", "artifact_path": "coverage/template-gap-report.md", "gaps": [{"template_name": template_name, "requirement_id": requirement_id, "status": status, "evidence_ids": [], "notes": []}]}

def resolve_render_target(graph_dir: Path, novel_dir: Path, template_name: str, output_policy: dict, overwrite_policy: str = "draft") -> dict:
    if overwrite_policy not in output_policy["allowed_policies"]:
        raise ValueError(f"unsupported overwrite_policy: {overwrite_policy}")
    formal = novel_dir / f"{template_name}.md"
    draft = graph_dir / output_policy["default_dir"] / f"{template_name}.md"
    if overwrite_policy == "draft":
        return {"target_path": str(draft), "backup_path": None, "action": "write_draft", "will_overwrite": False}
    if overwrite_policy == "backup-and-overwrite":
        return {"target_path": str(formal), "backup_path": str(formal.with_name(formal.name + ".bak")) if formal.exists() else None, "action": "backup_and_overwrite" if formal.exists() else "write_new_formal", "will_overwrite": formal.exists()}
    if overwrite_policy == "merge":
        return {"target_path": str(formal), "backup_path": None, "action": "merge_existing" if formal.exists() else "write_new_formal", "will_overwrite": formal.exists()}
    raise ValueError(f"unsupported overwrite_policy: {overwrite_policy}")

def validate_extraction_record(record):
    required = ["template_name", "source_graph", "coverage_scope", "fulfilled_sections", "facts", "judgments", "pending_verifications", "not_found_items", "evidence_citations", "overwrite_policy"]
    errors = [f"missing:{key}" for key in required if key not in record]
    scope = record.get("coverage_scope")
    if not isinstance(scope, dict) or scope.get("stage1_chunk_ledger") != "coverage/chunk-ledger.json":
        errors.append("invalid_coverage_scope")
    for fact in record.get("facts", []):
        if fact.get("category") == "原作事实" and not fact.get("evidence_ids"):
            errors.append("fact_without_evidence")
    return ExtractionValidation(ok=not errors, errors=errors)
```

- [ ] **Step 4: Update docs and skill references with validation workflow**

````markdown
<!-- docs/storygraph-cli.md -->
# StoryGraph CLI

## Validate skill

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python skill-src\storygraph\scripts\storygraph.py validate-skill --skill-root skill-src\storygraph; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

## Build stage 1 graph

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python skill-src\storygraph\scripts\storygraph.py build-stage1 --source '<novel.txt>' --template-dir '<template-dir>' --graphify-repo '<graphify-repo>'; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

## Stage 2 output policy

Default rendering writes to `graph_dir\drafts\<模板名>.md`. Existing formal documents in the novel directory are never overwritten under `draft` policy. Formal-target writes are allowed only when `overwrite_policy` is `backup-and-overwrite` or `merge`.
````

- [ ] **Step 5: Run complete test and validation suite**

Run:

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python -m pytest -v
```

Expected: every test file in `tests\` passes.

Run:

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python -m pytest tests\test_stage2_schema.py tests\test_stage2_policy.py -v; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; python skill-src\storygraph\scripts\storygraph.py validate-skill --skill-root skill-src\storygraph; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

Expected: stage 2 tests pass; `validate-skill` prints `{'ok': True, 'missing': []}` and exits `0`.

- [ ] **Step 6: Commit docs and stage 2 schema scaffolding**

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; git -c core.quotePath=false add skill-src docs tests\test_stage2_schema.py tests\test_stage2_policy.py; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; git commit -m "feat: add stage2 extraction schema and output policy"; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

## Final Review Gate For Implementers

Before marking implementation work ready for user review, run these checks and attach command output:

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python -m pytest -v
```

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python skill-src\storygraph\scripts\storygraph.py validate-skill --skill-root skill-src\storygraph; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python skill-src\storygraph\scripts\storygraph.py inspect-templates --template-dir 'E:\AI_Projects\CultivationWorld\docs\世界观参考\模板'; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python skill-src\storygraph\scripts\storygraph.py build-stage1 --source 'E:\AI_Projects\CultivationWorld\docs\世界观参考\凡人修仙传\凡人修仙传.txt' --template-dir 'E:\AI_Projects\CultivationWorld\docs\世界观参考\模板' --graphify-repo 'E:\Github_Projects\graphify'; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; python skill-src\storygraph\scripts\storygraph.py validate-graph --graph-dir 'E:\AI_Projects\CultivationWorld\docs\世界观参考\凡人修仙传\凡人修仙传.storygraph'; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python skill-src\storygraph\scripts\storygraph.py build-stage1 --source 'E:\AI_Projects\CultivationWorld\docs\世界观参考\凡人修仙传\凡人修仙传.txt' --template-dir 'E:\AI_Projects\CultivationWorld\docs\世界观参考\模板' --graphify-repo 'E:\Github_Projects\graphify'; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; Copy-Item -LiteralPath 'E:\AI_Projects\CultivationWorld\docs\世界观参考\凡人修仙传\凡人修仙传.txt' -Destination "$env:TEMP\storygraph-hash-change.txt" -Force; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; Add-Content -LiteralPath "$env:TEMP\storygraph-hash-change.txt" -Value "`n临时hash变化验证" -Encoding UTF8; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; python skill-src\storygraph\scripts\storygraph.py build-stage1 --source "$env:TEMP\storygraph-hash-change.txt" --template-dir 'E:\AI_Projects\CultivationWorld\docs\世界观参考\模板' --graphify-repo 'E:\Github_Projects\graphify'; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; Add-Content -LiteralPath "$env:TEMP\storygraph-hash-change.txt" -Value "`n第二次变化" -Encoding UTF8; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; python skill-src\storygraph\scripts\storygraph.py build-stage1 --source "$env:TEMP\storygraph-hash-change.txt" --template-dir 'E:\AI_Projects\CultivationWorld\docs\世界观参考\模板' --graphify-repo 'E:\Github_Projects\graphify'; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python skill-src\storygraph\scripts\storygraph.py build-stage1 --source 'E:\AI_Projects\CultivationWorld\docs\世界观参考\凡人修仙传\凡人修仙传.txt' --template-dir 'E:\AI_Projects\CultivationWorld\docs\世界观参考\模板' --graphify-repo 'E:\AI_Projects\StoryGraph\missing-graphify-for-ledger'; if ($LASTEXITCODE -eq 0) { throw 'Expected graphify failure command to exit nonzero' }
```

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python -m pytest tests\test_stage2_policy.py tests\test_template_aware.py tests\test_templates.py -v
```

Expected review evidence:

- `validate-skill` exits `0` and reports no missing skill structure.
- `inspect-templates` reports `template_count` from the dynamically discovered existing `*模板.md` files; for the current CultivationWorld sample this value is `37`. It records README-only missing template files as `missing_template_file` warnings, and proves every discovered template uses non-empty, non-generic graph mappings from config or template parsing rules rather than Python constants or `default_mapping`.
- `build-stage1` creates or reuses the intentional external `.storygraph` directory beside the CultivationWorld source novel and writes `manifest.json`, `graphify-out\graph.json`, `graphify-out\GRAPH_REPORT.md`, `graphify-out\graph.html`, `requirements\template-requirements.json`, `coverage\chunk-ledger.json`, `coverage\evidence-index.json`, `coverage\template-readiness.json`, `coverage\agent-run-ledger.json`, and `coverage\gap-report.md`.
- `validate-graph` performs deep canonical validation for nodes, edges, events, evidence, `supports_templates`, status enums, stable ID prefixes, graphify-compatible fields, and readiness completeness against the dynamic requirements template set.
- Error handling evidence covers unreadable source with `source_unreadable`, invalid UTF-8 source with `source_encoding_error`, missing graphify artifacts with `graphify_artifact_missing`, chunk extraction failure, readiness below threshold, template without reliable evidence, and unparsable sub-agent JSON; failures must set `manifest.stage_status.stage1` to `failed` and must not write a `graphify-out\graph.json` that appears successful after graphify failure.
- The immediate second `build-stage1` run with unchanged source reports `"status": "reused"`, proving idempotent no-rebuild behavior.
- The hash-change command reports `"source_state": "changed"` after the temporary source text is modified.
- The missing graphify command exits nonzero, returns `"status": "failed"`, writes a failed graphify adapter record into `coverage\agent-run-ledger.json` with `graphify_unavailable`, `graphify_failed`, or `graphify_artifact_missing`, and `validate-graph` treats that ledger record as blocking via `blocking_ledger:<error_code>`.
- `coverage\agent-run-ledger.json` includes at least the key Stage 1 roles: 模板需求分析、图抽取、覆盖审查、质量审查, with input paths, output paths, assigned chunks/templates, status, errors, and single-writer ownership.
- `test_stage2_policy.py` proves default output goes to `drafts\`, existing formal Markdown is not overwritten, and formal overwrites happen only under `backup-and-overwrite` or `merge`.
- Stage 2 scaffold evidence includes schemas or tests for `coverage\template-run-ledger.json`, `coverage\template-evidence-usage.json`, one template task record per dynamically discovered template, chunk-ledger full-range references, and `coverage\template-gap-report.md`.
- `template-readiness.json` contains one record per discovered template, has no duplicate `template_name`, and every requirement status is one of `covered`, `needs_review`, or `not_found_in_source`.
- No implementation step modifies `E:\Github_Projects\graphify`; graphify is only read or invoked through adapter configuration.
- No committed config file contains the local absolute template path, local graphify path, test novel path, repository name, or install destination as a global default.
