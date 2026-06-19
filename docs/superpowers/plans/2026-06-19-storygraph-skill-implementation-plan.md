# StoryGraph Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 创建一个可安装的 `storygraph` Codex skill，用模板感知的方式为整部小说生成可追溯、可校验、可复用的知识图谱，并为阶段 2 的 37 个模板全文抽取建立结构化基础。

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
- `storygraph_lib/templates.py`: 模板发现、README 缺失项告警、37 模板需求矩阵装配。
- `storygraph_lib/template_rules.py`: 可配置 Markdown 模板解析规则，提取字段、表格、卡片、案例、证据字段和 gap rules。
- `storygraph_lib/template_aware.py`: 基于模板需求矩阵和小说分块生成补充节点、边、事件、evidence 和逐需求 coverage 状态。
- `storygraph_lib/graphify_adapter.py`: graphify CLI/Python 能力的外层适配，不修改 graphify 源码。
- `storygraph_lib/graph_schema.py`: canonical graph schema、稳定 ID、StoryGraph 扩展合并。
- `storygraph_lib/coverage.py`: `chunk-ledger.json`、`evidence-index.json`、`template-readiness.json`、gap report。
- `storygraph_lib/agent_ledger.py`: 动态子 agent 运行记录 schema 和 single-writer 约束。
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
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; git -c core.quotePath=false add .gitignore pyproject.toml skill-src tests; git commit -m "chore: add storygraph skill source skeleton"
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
    assert "Resolve-Path -LiteralPath $Destination" in script
    assert ".codex\\skills\\storygraph" in script
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
$destinationRoot = (Resolve-Path -LiteralPath $Destination).Path
$expectedRoot = Join-Path $env:USERPROFILE ".codex\skills\storygraph"
$expectedResolved = (Resolve-Path -LiteralPath $expectedRoot).Path
if ($destinationRoot -ne $expectedResolved) {
  throw "Refusing to clean unexpected destination: $destinationRoot"
}
if ($Clean) {
  foreach ($item in $items) {
    $target = Join-Path $destinationRoot $item
    $resolvedParent = Split-Path -Parent $target
    if ((Resolve-Path -LiteralPath $resolvedParent).Path -ne $destinationRoot) {
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

Expected: pytest reports `3 passed`. Full `validate-skill --skill-root skill-src\storygraph` is run in Task 3 after the default config file exists.

- [ ] **Step 6: Commit sync workflow**

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; git -c core.quotePath=false add skill-src\storygraph\scripts tests\test_validation_cli.py; git commit -m "feat: add storygraph skill sync validation"
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
    "canonical_graph_policy": "merge-template-aware-supplements",
    "command": ["python", "-m", "graphify.cli", "build", "--input", "{source}", "--output", "{output_dir}"],
    "timeout_seconds": 1800
  },
  "template_parser_rules": {
    "field_headings": ["字段", "字段说明", "核心字段", "输出字段"],
    "table_markers": ["|", "表格", "清单"],
    "card_markers": ["卡片", "档案", "条目卡"],
    "case_markers": ["案例", "示例", "样例", "场景"],
    "evidence_markers": ["证据", "原文", "引用", "依据"],
    "gap_markers": ["缺口", "待核验", "未见可靠证据"]
  },
  "supplemental_graph_policy": {
    "write_to_canonical_graph": true,
    "sidecar_dir": "template-graph",
    "fail_stage_if_canonical_merge_fails": true
  },
  "chunk_strategy": {
    "mode": "chapter-aware",
    "max_chars": 20000,
    "overlap_chars": 1200
  },
  "template_requirements_strategy": {
    "mode": "auto-from-templates",
    "allow_manual_overrides": true
  },
  "overwrite_policy": "draft",
  "stage2_output_policy": {
    "default_dir": "drafts",
    "allow_overwrite_existing_docs": false,
    "existing_document_action": "write_versioned_draft"
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
    "block_on_missing_requirement_mapping": true
  }
}
```

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
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; git -c core.quotePath=false add skill-src\storygraph\config skill-src\storygraph\scripts\storygraph_lib tests\test_config.py .gitignore; git commit -m "feat: add portable storygraph config"
```

### Task 4: Phase 1 Path Parsing, Graph Directory, And Manifest

**Files:**
- Create: `E:\AI_Projects\StoryGraph\skill-src\storygraph\scripts\storygraph_lib\paths.py`
- Create: `E:\AI_Projects\StoryGraph\skill-src\storygraph\scripts\storygraph_lib\manifest.py`
- Modify: `E:\AI_Projects\StoryGraph\skill-src\storygraph\scripts\storygraph_lib\stage1.py`
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
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; git -c core.quotePath=false add skill-src\storygraph\scripts\storygraph_lib tests\test_paths_manifest.py tests\fixtures; git commit -m "feat: add storygraph path context and manifest"
```

### Task 5: Configurable Template Parsing And 37-Template Requirement Matrix

**Files:**
- Create: `E:\AI_Projects\StoryGraph\skill-src\storygraph\scripts\storygraph_lib\template_rules.py`
- Create: `E:\AI_Projects\StoryGraph\skill-src\storygraph\scripts\storygraph_lib\templates.py`
- Modify: `E:\AI_Projects\StoryGraph\skill-src\storygraph\scripts\storygraph_lib\cli.py`
- Modify: `E:\AI_Projects\StoryGraph\skill-src\storygraph\references\workflow.md`
- Test: `E:\AI_Projects\StoryGraph\tests\test_template_rules.py`
- Test: `E:\AI_Projects\StoryGraph\tests\test_templates.py`

- [ ] **Step 1: Write failing tests for rules-based parsing, README warnings, and real 37-template completeness**

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
from pathlib import Path
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

def test_real_37_templates_matrix_has_non_empty_requirement_categories():
    template_dir = Path(r"E:\AI_Projects\CultivationWorld\docs\世界观参考\模板")
    discovery = discover_templates(template_dir, glob="*模板.md", readme_index_file="README.md")
    matrix = build_requirement_matrix(discovery.templates, rules=None)
    assert matrix["template_count"] == 37
    for record in matrix["templates"]:
        assert record["required_fields"] or record["required_tables"] or record["required_cards"] or record["required_case_patterns"]
        assert record["required_evidence_fields"]
        assert record["gap_rules"]["status_enum"] == ["covered", "needs_review", "not_found_in_source"]
        assert record["graph_node_mapping"]
        assert record["graph_event_mapping"]
        assert record["graph_relation_mapping"]
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
    parsed = {"required_sections": [], "required_fields": [], "required_tables": [], "required_cards": [], "required_case_patterns": [], "required_evidence_fields": [], "gap_rules": {"markers": [], "status_enum": ["covered", "needs_review", "not_found_in_source"]}}
    section = ""
    table_header = None
    for raw in text.splitlines():
        line = raw.strip()
        title = _heading(line)
        if title:
            section = title
            parsed["required_sections"].append(title)
            if any(marker in title for marker in rules["card_markers"]):
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
                parsed["required_cards"].append(item)
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

SPECIAL_MAPPINGS = {
    "有限视角与叙事日志": {"graph_node_mapping": ["perspective"], "graph_event_mapping": ["narrative_view"], "graph_relation_mapping": ["known_unknown"]},
    "角色AI行为参考": {"graph_node_mapping": ["decision", "resource_constraint"], "graph_event_mapping": ["action_chain"], "graph_relation_mapping": ["constraint_outcome"]},
    "记忆情绪与执念": {"graph_node_mapping": ["emotion_memory"], "graph_event_mapping": ["emotion_trigger"], "graph_relation_mapping": ["long_term_influence"]},
    "相遇剧情与对话设计": {"graph_node_mapping": ["scene_dialogue"], "graph_event_mapping": ["encounter"], "graph_relation_mapping": ["attitude_change", "information_exchange"]},
    "动态事件与机会点": {"graph_node_mapping": ["opportunity"], "graph_event_mapping": ["time_causality"], "graph_relation_mapping": ["trigger_effect"]},
    "事件因果链（长程因果图）": {"graph_node_mapping": ["timepoint"], "graph_event_mapping": ["time_causality"], "graph_relation_mapping": ["precondition", "delayed_effect"]}
}

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

def build_requirement_matrix(templates: list[TemplateFile], rules: dict | None) -> dict:
    records = []
    for template in templates:
        parsed = parse_template_requirements(template.name, template.text, rules)
        mapping = SPECIAL_MAPPINGS.get(template.name, {"graph_node_mapping": ["entity"], "graph_event_mapping": ["event"], "graph_relation_mapping": ["relation"]})
        records.append({
            "template_name": template.name,
            "template_file": str(template.path),
            "template_file_hash": template.file_hash,
            "template_status": "available",
            "output_language": "zh-CN",
            **parsed,
            "required_entity_types": mapping["graph_node_mapping"],
            "required_event_types": mapping["graph_event_mapping"],
            "required_relation_types": mapping["graph_relation_mapping"],
            **mapping,
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
        matrix = build_requirement_matrix(discovery.templates, config["template_parser_rules"])
        _print_json({"template_count": matrix["template_count"], "warnings": discovery.warnings, "templates": [t["template_name"] for t in matrix["templates"]]})
        return 0
    return 2
```

Run:

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python skill-src\storygraph\scripts\storygraph.py inspect-templates --template-dir 'E:\AI_Projects\CultivationWorld\docs\世界观参考\模板'
```

Expected: JSON output contains `"template_count": 37`; README-only missing files are warning objects with `code` equal to `missing_template_file`.

- [ ] **Step 6: Run tests and commit template matrix**

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python -m pytest tests\test_template_rules.py tests\test_templates.py -v; git -c core.quotePath=false add skill-src\storygraph\scripts\storygraph_lib skill-src\storygraph\references tests\test_template_rules.py tests\test_templates.py; git commit -m "feat: add configurable template requirement matrix"
```

Expected: all tests in `test_template_rules.py` and `test_templates.py` pass, including the real 37-template completeness test.

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
    assert "bad_requirement_status:maybe" in result.errors
    assert "node_without_evidence:node:person:abc" in result.errors

def test_merge_template_supplements_preserves_graphify_fields_and_requires_non_empty_supports():
    base = {"nodes": [{"id": "node:person:abc", "label": "韩立"}], "edges": [], "hyperedges": [], "metadata": {"graphify_schema_version": "x"}}
    supplement = {"nodes": [{"id": "node:person:abc", "node_type": "person", "evidence_ids": ["evidence:1"], "supports_templates": [{"template_name": "法宝分析", "requirement_id": "法宝分析.required_fields.法宝", "status": "covered"}], "confidence": "EXTRACTED", "verification_status": "verified"}], "edges": [], "events": [], "evidence_index": [{"evidence_id": "evidence:1", "source_range": [0, 8], "fact_summary": "韩立获得小瓶", "confidence": "EXTRACTED", "verification_status": "verified", "supports_templates": [{"template_name": "法宝分析", "requirement_id": "法宝分析.required_fields.法宝", "status": "covered"}]}]}
    graph = merge_template_supplements(base, supplement)
    assert graph["nodes"][0]["label"] == "韩立"
    assert graph["metadata"]["graphify_schema_version"] == "x"
    assert validate_canonical_graph(graph).ok is True
```

- [ ] **Step 2: Write failing adapter tests for unavailable graphify, real external command contract, and failure ledger payload**

```python
# tests/test_graphify_adapter.py
import json
import sys
from pathlib import Path
from storygraph_lib.graphify_adapter import GraphifyAdapter

def test_adapter_reports_unavailable_graphify_without_modifying_repo(tmp_path):
    adapter = GraphifyAdapter(graphify_repo=tmp_path / "missing", command=["python", "-c", "print('unused')"], timeout_seconds=5)
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
    adapter = GraphifyAdapter(graphify_repo=repo, command=[sys.executable, "fake_graphify.py", "{source}", "{output_dir}"], timeout_seconds=5)
    result = adapter.build_graph(source, tmp_path / "out")
    assert result.ok is True
    assert json.loads(result.graph_path.read_text(encoding="utf-8"))["metadata"]["fake"] is True
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

REQ_STATUSES = {"covered", "needs_review", "not_found_in_source"}
VERIFY_STATUSES = {"verified", "needs_review", "rejected"}
CONFIDENCES = {"EXTRACTED", "INFERRED", "AMBIGUOUS"}

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
        if status not in REQ_STATUSES:
            errors.append(f"bad_requirement_status:{status}")

def validate_canonical_graph(graph: dict) -> SchemaValidation:
    errors = [f"missing:{key}" for key in ["nodes", "edges", "hyperedges", "events", "evidence_index", "metadata"] if key not in graph]
    evidence_ids = {e.get("evidence_id") for e in graph.get("evidence_index", [])}
    node_ids = {n.get("id") for n in graph.get("nodes", [])}
    for node in graph.get("nodes", []):
        if not node.get("id", "").startswith("node:"):
            errors.append(f"bad_node_id:{node.get('id')}")
        if not node.get("evidence_ids"):
            errors.append(f"node_without_evidence:{node.get('id')}")
        if any(eid not in evidence_ids for eid in node.get("evidence_ids", [])):
            errors.append(f"node_unknown_evidence:{node.get('id')}")
        if node.get("verification_status") not in VERIFY_STATUSES:
            errors.append(f"bad_verification_status:{node.get('verification_status')}")
        if node.get("confidence") not in CONFIDENCES:
            errors.append(f"bad_confidence:{node.get('confidence')}")
        _check_supports("node", node, errors)
    for edge in graph.get("edges", []):
        if edge.get("source") not in node_ids or edge.get("target") not in node_ids:
            errors.append(f"edge_unknown_node:{edge.get('id')}")
        _check_supports("edge", edge, errors)
    for event in graph.get("events", []):
        if not event.get("id", "").startswith("event:"):
            errors.append(f"bad_event_id:{event.get('id')}")
        if not event.get("evidence_ids"):
            errors.append(f"event_without_evidence:{event.get('id')}")
        _check_supports("event", event, errors)
    for evidence in graph.get("evidence_index", []):
        if not evidence.get("evidence_id", "").startswith("evidence:"):
            errors.append(f"bad_evidence_id:{evidence.get('evidence_id')}")
        if evidence.get("verification_status") not in VERIFY_STATUSES:
            errors.append(f"bad_evidence_verification:{evidence.get('verification_status')}")
        _check_supports("evidence", evidence, errors)
    return SchemaValidation(ok=not errors, errors=errors)
```

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
    def __init__(self, graphify_repo: Path | None, command: list[str], timeout_seconds: int):
        self.graphify_repo = graphify_repo
        self.command = command
        self.timeout_seconds = timeout_seconds

    def build_graph(self, source_path: Path, output_dir: Path) -> GraphifyResult:
        if not self.graphify_repo or not self.graphify_repo.exists():
            return GraphifyResult(False, None, {"code": "graphify_unavailable", "path": str(self.graphify_repo)}, self.command)
        output_dir.mkdir(parents=True, exist_ok=True)
        command = [part.format(source=str(source_path), output_dir=str(output_dir)) for part in self.command]
        completed = subprocess.run(command, cwd=self.graphify_repo, capture_output=True, text=True, timeout=self.timeout_seconds)
        graph_path = output_dir / "graph.json"
        if completed.returncode != 0:
            return GraphifyResult(False, None, {"code": "graphify_failed", "returncode": completed.returncode, "stderr": completed.stderr[-4000:]}, command)
        if not graph_path.exists():
            return GraphifyResult(False, None, {"code": "graphify_missing_graph_json", "stdout": completed.stdout[-4000:]}, command)
        return GraphifyResult(True, graph_path, None, command)
```

- [ ] **Step 6: Run tests and commit graph layer**

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python -m pytest tests\test_graph_schema.py tests\test_graphify_adapter.py -v; git -c core.quotePath=false add skill-src\storygraph\scripts\storygraph_lib skill-src\storygraph\references tests\test_graph_schema.py tests\test_graphify_adapter.py; git commit -m "feat: add deep graph validation and graphify adapter"
```

Expected: schema tests reject bad statuses and missing evidence; adapter tests prove an external command is invoked and graphify failures return structured ledger-ready errors.

### Task 7: Template-Aware Supplements, Evidence Index, Coverage Ledgers, And Agent Ledger

**Files:**
- Create: `E:\AI_Projects\StoryGraph\skill-src\storygraph\scripts\storygraph_lib\coverage.py`
- Create: `E:\AI_Projects\StoryGraph\skill-src\storygraph\scripts\storygraph_lib\template_aware.py`
- Create: `E:\AI_Projects\StoryGraph\skill-src\storygraph\scripts\storygraph_lib\agent_ledger.py`
- Modify: `E:\AI_Projects\StoryGraph\skill-src\storygraph\references\workflow.md`
- Test: `E:\AI_Projects\StoryGraph\tests\test_agent_ledger.py`
- Test: `E:\AI_Projects\StoryGraph\tests\test_template_aware.py`
- Test: `E:\AI_Projects\StoryGraph\tests\test_stage1.py`

- [ ] **Step 1: Write failing tests for agent ledger, chunks, and real template-aware supplements**

```python
# tests/test_agent_ledger.py
from storygraph_lib.agent_ledger import make_agent_run_record, validate_single_writer

def test_agent_run_record_contains_required_contract_fields():
    record = make_agent_run_record("run-1", "模板需求分析", "stage1", ["chunk-0001"], ["法宝分析"], ["novel.txt"], ["requirements.json"], "requirements/template-requirements.json")
    assert record["status"] == "pending"
    assert record["merge_owner"] == "single-writer"
    assert validate_single_writer([record]).ok is True

def test_single_writer_detects_conflicting_outputs():
    a = make_agent_run_record("run-1", "A", "stage1", [], [], [], ["manifest.json"], "manifest.json")
    b = make_agent_run_record("run-2", "B", "stage1", [], [], [], ["manifest.json"], "manifest.json")
    assert validate_single_writer([a, b]).ok is False
```

```python
# tests/test_template_aware.py
from storygraph_lib.coverage import make_chunk_ledger
from storygraph_lib.template_aware import extract_template_aware_supplements

def test_template_aware_extraction_creates_nodes_edges_events_evidence_and_requirement_statuses(tmp_path):
    source = tmp_path / "novel.txt"
    source.write_text("第一章\n韩立获得小瓶。小瓶影响法宝资源获取。", encoding="utf-8")
    chunks = make_chunk_ledger(source, max_chars=200, overlap_chars=0)
    matrix = {"templates": [{"template_name": "法宝分析", "required_fields": ["法宝"], "required_tables": ["名称|能力"], "required_cards": ["法宝卡片"], "required_case_patterns": ["小瓶"], "required_entity_types": ["item"], "required_event_types": ["resource_gain"], "required_relation_types": ["influences"], "required_evidence_fields": ["source_range", "fact_summary"], "graph_node_mapping": ["item"], "graph_event_mapping": ["resource_gain"], "graph_relation_mapping": ["influences"], "gap_rules": {"status_enum": ["covered", "needs_review", "not_found_in_source"]}}]}
    supplement, readiness = extract_template_aware_supplements("凡人修仙传", source, chunks, matrix)
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
    return {"run_id": run_id, "agent_role": agent_role, "stage": stage, "assigned_chunk_ids": chunk_ids, "assigned_template_names": template_names, "input_paths": input_paths, "output_paths": output_paths, "write_scope": write_scope, "status": "pending", "errors": [], "merge_owner": "single-writer", "reviewer_status": "not_reviewed"}

def validate_single_writer(records):
    counts = Counter(record["write_scope"] for record in records if record["write_scope"])
    conflicts = [scope for scope, count in counts.items() if count > 1]
    return LedgerValidation(ok=not conflicts, errors=[f"write_conflict:{scope}" for scope in conflicts])
```

```python
# skill-src/storygraph/scripts/storygraph_lib/coverage.py
import json
from hashlib import sha256

def make_chunk_ledger(source_path, max_chars: int, overlap_chars: int) -> list[dict]:
    text = source_path.read_text(encoding="utf-8")
    chunks, start, index = [], 0, 1
    while start < len(text):
        end = min(len(text), start + max_chars)
        body = text[start:end]
        chunks.append({"chunk_id": f"chunk-{index:04d}", "source_range": [start, end], "chapter_hint": body.splitlines()[0] if body else None, "hash": sha256(body.encode("utf-8")).hexdigest(), "scanned_at": None, "extraction_status": "pending", "failed_reason": None, "retry_count": 0})
        if end == len(text):
            break
        start, index = max(0, end - overlap_chars), index + 1
    return chunks

def write_coverage_outputs(graph_dir, chunks, evidences, readiness, agent_runs, gap_lines):
    coverage_dir = graph_dir / "coverage"
    coverage_dir.mkdir(parents=True, exist_ok=True)
    for name, data in {"chunk-ledger.json": chunks, "evidence-index.json": evidences, "template-readiness.json": readiness, "agent-run-ledger.json": agent_runs}.items():
        (coverage_dir / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (coverage_dir / "gap-report.md").write_text("# StoryGraph Gap Report\n\n" + "\n".join(gap_lines) + "\n", encoding="utf-8")
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

def extract_template_aware_supplements(novel_name, source_path, chunks, matrix):
    text = source_path.read_text(encoding="utf-8")
    nodes, edges, events, evidences, readiness = [], [], [], [], []
    for template in matrix["templates"]:
        statuses = []
        template_nodes, template_edges, template_events, template_evidence = 0, 0, 0, 0
        for kind, requirement in _requirements(template):
            requirement_id = f"{template['template_name']}.{kind}.{requirement}"
            match_chunk = next((chunk for chunk in chunks if requirement and requirement in text[chunk["source_range"][0]:chunk["source_range"][1]]), None)
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

- [ ] **Step 5: Add coverage assertions for complete 37-template readiness**

```python
# add to tests/test_template_aware.py
def test_readiness_has_one_record_per_template_and_each_requirement_has_status(tmp_path):
    source = tmp_path / "novel.txt"
    source.write_text("法宝 丹药 阵法", encoding="utf-8")
    chunks = make_chunk_ledger(source, max_chars=200, overlap_chars=0)
    matrix = {"templates": [{"template_name": f"模板{i}", "required_fields": ["法宝"], "required_tables": [], "required_cards": [], "required_case_patterns": [], "required_entity_types": ["entity"], "required_event_types": ["event"], "required_relation_types": ["relation"], "graph_node_mapping": ["entity"], "graph_event_mapping": ["event"], "graph_relation_mapping": ["relation"], "required_evidence_fields": ["source_range"], "gap_rules": {"status_enum": ["covered", "needs_review", "not_found_in_source"]}} for i in range(37)]}
    supplement, readiness = extract_template_aware_supplements("凡人修仙传", source, chunks, matrix)
    assert len(readiness) == 37
    assert all(record["requirement_statuses"] for record in readiness)
    assert supplement["nodes"] and supplement["events"] and supplement["evidence_index"]
```

- [ ] **Step 6: Run tests and commit template-aware coverage layer**

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python -m pytest tests\test_agent_ledger.py tests\test_template_aware.py -v; git -c core.quotePath=false add skill-src\storygraph\scripts\storygraph_lib skill-src\storygraph\references tests\test_agent_ledger.py tests\test_template_aware.py; git commit -m "feat: add template-aware graph supplements and coverage"
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

def _config(template_dir, graphify_repo=None):
    return {"graph_dir_suffix": ".storygraph", "paths": {"template_dir": str(template_dir), "graphify_repo": str(graphify_repo) if graphify_repo else None}, "template_discovery": {"glob": "*模板.md", "readme_index_file": "README.md"}, "template_parser_rules": {"field_headings": ["字段"], "table_markers": ["|", "表格"], "card_markers": ["卡片"], "case_markers": ["案例"], "evidence_markers": ["证据", "原文"], "gap_markers": ["缺口", "待核验"]}, "graphify_adapter": {"command": [sys.executable, "-c", "import json,pathlib,sys; out=pathlib.Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True); (out/'graph.json').write_text(json.dumps({'nodes': [], 'edges': [], 'hyperedges': [], 'metadata': {'graphify_schema_version': 'test'}}), encoding='utf-8')", "{source}", "{output_dir}"], "timeout_seconds": 5}, "chunk_strategy": {"max_chars": 100, "overlap_chars": 0}}

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
    assert result["status"] == "success"
    assert graph["nodes"] and graph["edges"] and graph["events"] and graph["evidence_index"]
    assert readiness[0]["requirement_statuses"]

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
    assert ledger[0]["status"] == "failed"
    assert ledger[0]["errors"][0]["code"] == "graphify_unavailable"
```

```python
# tests/test_stage1_idempotency.py
import json
import sys
from pathlib import Path
from storygraph_lib.stage1 import build_stage1_graph

def _write_37_templates(template_dir: Path):
    for index in range(37):
        (template_dir / f"模板{index:02d}模板.md").write_text(f"# 模板{index:02d}模板\n## 字段\n- 法宝\n## 证据要求\n- 原文位置", encoding="utf-8")

def test_stage1_reuses_graph_when_source_hash_is_unchanged(tmp_path):
    novel = tmp_path / "mini.txt"
    novel.write_text("法宝 小瓶", encoding="utf-8")
    template_dir = tmp_path / "templates"; template_dir.mkdir()
    _write_37_templates(template_dir)
    graphify_repo = tmp_path / "graphify"; graphify_repo.mkdir()
    config = {"graph_dir_suffix": ".storygraph", "paths": {"template_dir": str(template_dir), "graphify_repo": str(graphify_repo)}, "template_discovery": {"glob": "*模板.md", "readme_index_file": "README.md"}, "template_parser_rules": None, "graphify_adapter": {"command": [sys.executable, "-c", "import json,pathlib,sys; out=pathlib.Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True); (out/'graph.json').write_text(json.dumps({'nodes': [], 'edges': [], 'hyperedges': [], 'metadata': {'graphify_schema_version': 'test'}}), encoding='utf-8')", "{source}", "{output_dir}"], "timeout_seconds": 5}, "chunk_strategy": {"max_chars": 100, "overlap_chars": 0}}
    first = build_stage1_graph(novel, config)
    second = build_stage1_graph(novel, config)
    assert first["status"] == "success"
    assert second["status"] == "reused"

def test_stage1_marks_source_changed_when_hash_changes(tmp_path):
    novel = tmp_path / "mini.txt"
    novel.write_text("法宝", encoding="utf-8")
    template_dir = tmp_path / "templates"; template_dir.mkdir()
    _write_37_templates(template_dir)
    graphify_repo = tmp_path / "graphify"; graphify_repo.mkdir()
    config = {"graph_dir_suffix": ".storygraph", "paths": {"template_dir": str(template_dir), "graphify_repo": str(graphify_repo)}, "template_discovery": {"glob": "*模板.md", "readme_index_file": "README.md"}, "template_parser_rules": None, "graphify_adapter": {"command": [sys.executable, "-c", "import json,pathlib,sys; out=pathlib.Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True); (out/'graph.json').write_text(json.dumps({'nodes': [], 'edges': [], 'hyperedges': [], 'metadata': {'graphify_schema_version': 'test'}}), encoding='utf-8')", "{source}", "{output_dir}"], "timeout_seconds": 5}, "chunk_strategy": {"max_chars": 100, "overlap_chars": 0}}
    build_stage1_graph(novel, config)
    novel.write_text("法宝 小瓶", encoding="utf-8")
    result = build_stage1_graph(novel, config)
    assert result["source_state"] == "changed"

def test_stage1_marks_changed_when_template_file_hash_changes(tmp_path):
    novel = tmp_path / "mini.txt"
    novel.write_text("法宝", encoding="utf-8")
    template_dir = tmp_path / "templates"; template_dir.mkdir()
    _write_37_templates(template_dir)
    graphify_repo = tmp_path / "graphify"; graphify_repo.mkdir()
    config = {"graph_dir_suffix": ".storygraph", "paths": {"template_dir": str(template_dir), "graphify_repo": str(graphify_repo)}, "template_discovery": {"glob": "*模板.md", "readme_index_file": "README.md"}, "template_parser_rules": None, "graphify_adapter": {"command": [sys.executable, "-c", "import json,pathlib,sys; out=pathlib.Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True); (out/'graph.json').write_text(json.dumps({'nodes': [], 'edges': [], 'hyperedges': [], 'metadata': {'graphify_schema_version': 'test'}}), encoding='utf-8')", "{source}", "{output_dir}"], "timeout_seconds": 5}, "chunk_strategy": {"max_chars": 100, "overlap_chars": 0}}
    build_stage1_graph(novel, config)
    (template_dir / "模板00模板.md").write_text("# 模板00模板\n## 字段\n- 丹药\n## 证据要求\n- 原文位置", encoding="utf-8")
    result = build_stage1_graph(novel, config)
    assert result["source_state"] == "changed"

def test_stage1_marks_changed_when_graphify_source_changes(tmp_path):
    novel = tmp_path / "mini.txt"
    novel.write_text("法宝", encoding="utf-8")
    template_dir = tmp_path / "templates"; template_dir.mkdir()
    _write_37_templates(template_dir)
    graphify_a = tmp_path / "graphify-a"; graphify_a.mkdir()
    graphify_b = tmp_path / "graphify-b"; graphify_b.mkdir()
    config = {"graph_dir_suffix": ".storygraph", "paths": {"template_dir": str(template_dir), "graphify_repo": str(graphify_a)}, "template_discovery": {"glob": "*模板.md", "readme_index_file": "README.md"}, "template_parser_rules": None, "graphify_adapter": {"command": [sys.executable, "-c", "import json,pathlib,sys; out=pathlib.Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True); (out/'graph.json').write_text(json.dumps({'nodes': [], 'edges': [], 'hyperedges': [], 'metadata': {'graphify_schema_version': 'test'}}), encoding='utf-8')", "{source}", "{output_dir}"], "timeout_seconds": 5}, "chunk_strategy": {"max_chars": 100, "overlap_chars": 0}}
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

REQUIRED_STAGE1_FILES = ["manifest.json", "graphify-out/graph.json", "requirements/template-requirements.json", "coverage/chunk-ledger.json", "coverage/evidence-index.json", "coverage/template-readiness.json", "coverage/agent-run-ledger.json"]

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
from hashlib import sha256
from pathlib import Path
from .agent_ledger import make_agent_run_record
from .coverage import make_chunk_ledger, write_coverage_outputs
from .graph_schema import merge_template_supplements, validate_canonical_graph
from .graphify_adapter import GraphifyAdapter
from .manifest import write_manifest
from .paths import resolve_novel_context
from .state import stage1_state
from .template_aware import extract_template_aware_supplements
from .templates import build_requirement_matrix, discover_templates
from .validation import validate_graph_dir

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
        "supplemental_graph_policy": config.get("supplemental_graph_policy")
    }
    return sha256(json.dumps(relevant, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

def build_stage1_graph(source_path: Path, config: dict) -> dict:
    ctx = resolve_novel_context(Path(source_path), config["graph_dir_suffix"], create=True)
    discovery = discover_templates(Path(config["paths"]["template_dir"]), config["template_discovery"]["glob"], config["template_discovery"]["readme_index_file"])
    config_hash = stable_stage_input_hash(config, discovery.templates)
    current_state = stage1_state(ctx, config_hash, validate_graph_dir)
    if current_state["action"] == "reuse":
        return {"status": "reused", "source_state": "unchanged", "graph_dir": str(ctx.graph_dir)}
    manifest_path = write_manifest(ctx, config_hash=config_hash, graphify_source=str(config.get("paths", {}).get("graphify_repo")))
    matrix = build_requirement_matrix(discovery.templates, config.get("template_parser_rules"))
    requirements_dir = ctx.graph_dir / "requirements"; requirements_dir.mkdir(parents=True, exist_ok=True)
    (requirements_dir / "template-requirements.json").write_text(json.dumps(matrix, ensure_ascii=False, indent=2), encoding="utf-8")
    chunks = make_chunk_ledger(ctx.source_path, config["chunk_strategy"]["max_chars"], config["chunk_strategy"]["overlap_chars"])
    supplement, readiness = extract_template_aware_supplements(ctx.novel_name, ctx.source_path, chunks, matrix)
    for chunk in chunks:
        chunk["extraction_status"] = "completed"
    graphify_out = ctx.graph_dir / "graphify-out"; graphify_out.mkdir(parents=True, exist_ok=True)
    adapter = GraphifyAdapter(Path(config["paths"]["graphify_repo"]) if config["paths"].get("graphify_repo") else None, config["graphify_adapter"]["command"], config["graphify_adapter"]["timeout_seconds"])
    adapter_result = adapter.build_graph(ctx.source_path, graphify_out)
    base = json.loads(adapter_result.graph_path.read_text(encoding="utf-8")) if adapter_result.ok else {"nodes": [], "edges": [], "hyperedges": [], "metadata": {"graphify_error": adapter_result.error}}
    graph = merge_template_supplements(base, supplement)
    validation = validate_canonical_graph(graph)
    (graphify_out / "graph.json").write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    agent_runs = [make_agent_run_record("graphify-0001", "graphify_adapter", "stage1", [], [], [str(ctx.source_path)], [str(graphify_out / "graph.json")], "graphify-out/graph.json")]
    if not adapter_result.ok:
        agent_runs[0]["status"] = "failed"
        agent_runs[0]["errors"] = [adapter_result.error]
    gap_lines = [f"- validation error: {error}" for error in validation.errors] + [f"- warning: {w['code']} {w['file']}" for w in discovery.warnings]
    write_coverage_outputs(ctx.graph_dir, chunks, supplement["evidence_index"], readiness, agent_runs, gap_lines)
    status = "success" if adapter_result.ok and validation.ok else "failed"
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_data["stage_status"]["stage1"] = status
    manifest_path.write_text(json.dumps(manifest_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": status, "source_state": current_state["source_state"], "graph_dir": str(ctx.graph_dir), "warnings": discovery.warnings, "validation_errors": validation.errors}
```

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
    sub.add_parser("config-check").add_argument("--local-override")
    validate = sub.add_parser("validate-skill"); validate.add_argument("--skill-root", default=str(Path(__file__).resolve().parents[2]))
    inspect = sub.add_parser("inspect-templates"); inspect.add_argument("--template-dir", required=True)
    build = sub.add_parser("build-stage1"); build.add_argument("--source", required=True); build.add_argument("--template-dir", required=True); build.add_argument("--graphify-repo")
    graph = sub.add_parser("validate-graph"); graph.add_argument("--graph-dir", required=True)
    args = parser.parse_args(argv)
    config = load_config(_default_config_path())
    if args.command == "config-check":
        _print_json({"ok": True, "graph_dir_suffix": config["graph_dir_suffix"]}); return 0
    if args.command == "validate-skill":
        result = validate_skill_tree(Path(args.skill_root)); _print_json({"ok": result.ok, "missing": result.missing}); return 0 if result.ok else 2
    if args.command == "inspect-templates":
        discovery = discover_templates(Path(args.template_dir), config["template_discovery"]["glob"], config["template_discovery"]["readme_index_file"])
        matrix = build_requirement_matrix(discovery.templates, config["template_parser_rules"])
        _print_json({"template_count": matrix["template_count"], "warnings": discovery.warnings}); return 0
    if args.command == "build-stage1":
        config["paths"]["template_dir"] = args.template_dir
        config["paths"]["graphify_repo"] = args.graphify_repo
        result = build_stage1_graph(Path(args.source), config)
        _print_json(result)
        return 0 if result["status"] in {"success", "reused"} else 2
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
from .graph_schema import validate_canonical_graph

@dataclass(frozen=True)
class GraphDirValidation:
    ok: bool
    errors: list[str]

def validate_graph_dir(graph_dir: Path) -> GraphDirValidation:
    required = ["manifest.json", "graphify-out/graph.json", "requirements/template-requirements.json", "coverage/chunk-ledger.json", "coverage/evidence-index.json", "coverage/template-readiness.json", "coverage/agent-run-ledger.json"]
    errors = [f"missing:{item}" for item in required if not (graph_dir / item).exists()]
    if errors:
        return GraphDirValidation(False, errors)
    manifest = json.loads((graph_dir / "manifest.json").read_text(encoding="utf-8"))
    graph = json.loads((graph_dir / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
    requirements = json.loads((graph_dir / "requirements" / "template-requirements.json").read_text(encoding="utf-8"))
    chunks = json.loads((graph_dir / "coverage" / "chunk-ledger.json").read_text(encoding="utf-8"))
    coverage_evidence = json.loads((graph_dir / "coverage" / "evidence-index.json").read_text(encoding="utf-8"))
    schema = validate_canonical_graph(graph)
    readiness = json.loads((graph_dir / "coverage" / "template-readiness.json").read_text(encoding="utf-8"))
    agent_ledger = json.loads((graph_dir / "coverage" / "agent-run-ledger.json").read_text(encoding="utf-8"))
    allowed_statuses = {"covered", "needs_review", "not_found_in_source"}
    requirement_templates = {record["template_name"] for record in requirements["templates"]}
    readiness_templates = {record["template_name"] for record in readiness}
    if requirements.get("template_count") != 37 or len(readiness) != 37:
        errors.append("template_readiness_count_not_37")
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
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python skill-src\storygraph\scripts\storygraph.py build-stage1 --source 'E:\AI_Projects\CultivationWorld\docs\世界观参考\凡人修仙传\凡人修仙传.txt' --template-dir 'E:\AI_Projects\CultivationWorld\docs\世界观参考\模板' --graphify-repo 'E:\Github_Projects\graphify'; python skill-src\storygraph\scripts\storygraph.py validate-graph --graph-dir 'E:\AI_Projects\CultivationWorld\docs\世界观参考\凡人修仙传\凡人修仙传.storygraph'
```

Expected: this intentionally creates or reuses the external `.storygraph` directory beside the novel. Re-running the same command without changing the novel reports `"status": "reused"`; `validate-graph` performs deep schema/readiness/evidence validation and exits `0`.

Commit:

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; git -c core.quotePath=false add skill-src\storygraph\scripts\storygraph_lib skill-src\storygraph\scripts\storygraph.py docs\storygraph-cli.md tests; git commit -m "feat: add storygraph stage1 pipeline and validation"
```

### Task 9: Stage 2 Extraction Schema, No-Overwrite Draft Policy, Docs, And Final Verification

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
from storygraph_lib.stage2_schema import make_extraction_record, validate_extraction_record

def test_stage2_extraction_record_requires_evidence_categories():
    record = make_extraction_record(
        template_name="法宝分析",
        template_file="法宝分析模板.md",
        source_graph="凡人修仙传.storygraph/graphify-out/graph.json",
        source_novel="凡人修仙传.txt",
        requirement_id="法宝分析.required_fields.法宝",
        evidence_id="evidence:abc"
    )
    assert record["facts"][0]["category"] == "原作事实"
    assert record["judgments"][0]["category"] == "我的判断"
    assert record["pending_verifications"][0]["category"] == "待核验"
    assert record["not_found_items"][0]["category"] == "未见可靠证据"
    assert validate_extraction_record(record).ok is True
```

```python
# tests/test_stage2_policy.py
from pathlib import Path
from storygraph_lib.stage2_schema import resolve_render_target

def test_default_policy_writes_draft_and_does_not_overwrite_existing_formal_doc(tmp_path):
    graph_dir = tmp_path / "凡人修仙传.storygraph"
    novel_dir = tmp_path
    graph_dir.mkdir()
    formal = novel_dir / "法宝分析.md"
    formal.write_text("用户已有文档", encoding="utf-8")
    decision = resolve_render_target(graph_dir, novel_dir, "法宝分析", overwrite_policy="draft")
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
    backup = resolve_render_target(graph_dir, novel_dir, "法宝分析", overwrite_policy="backup-and-overwrite")
    merge = resolve_render_target(graph_dir, novel_dir, "法宝分析", overwrite_policy="merge")
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

def make_extraction_record(template_name, template_file, source_graph, source_novel, requirement_id, evidence_id):
    fulfilled = {"requirement_id": requirement_id, "requirement_kind": "field", "status": "covered", "linked_node_ids": [], "linked_edge_ids": [], "linked_event_ids": [], "evidence_ids": [evidence_id], "notes": []}
    return {
        "template_name": template_name,
        "template_file": template_file,
        "source_graph": source_graph,
        "source_novel": source_novel,
        "output_language": "zh-CN",
        "coverage_scope": "whole_novel",
        "fulfilled_sections": [fulfilled],
        "fulfilled_fields": [fulfilled],
        "fulfilled_tables": [],
        "fulfilled_cards": [],
        "fulfilled_cases": [],
        "facts": [{"content": "原作事实需引用证据", "category": "原作事实", "evidence_ids": [evidence_id], "source_locations": [], "confidence": "EXTRACTED"}],
        "judgments": [{"content": "基于证据的分析判断", "category": "我的判断", "evidence_ids": [evidence_id], "source_locations": [], "confidence": "INFERRED"}],
        "pending_verifications": [{"content": "证据不足的条目", "category": "待核验", "evidence_ids": [], "source_locations": [], "confidence": "AMBIGUOUS"}],
        "not_found_items": [{"content": "全文图和分块账本未见可靠证据", "category": "未见可靠证据", "evidence_ids": [], "source_locations": [], "confidence": "AMBIGUOUS"}],
        "evidence_citations": [evidence_id],
        "gap_items": [],
        "render_target": "drafts",
        "overwrite_policy": "draft"
    }

def resolve_render_target(graph_dir: Path, novel_dir: Path, template_name: str, overwrite_policy: str = "draft") -> dict:
    formal = novel_dir / f"{template_name}.md"
    draft = graph_dir / "drafts" / f"{template_name}.md"
    if overwrite_policy == "draft":
        return {"target_path": str(draft), "backup_path": None, "action": "write_draft", "will_overwrite": False}
    if overwrite_policy == "backup-and-overwrite":
        return {"target_path": str(formal), "backup_path": str(formal.with_name(formal.name + ".bak")) if formal.exists() else None, "action": "backup_and_overwrite" if formal.exists() else "write_new_formal", "will_overwrite": formal.exists()}
    if overwrite_policy == "merge":
        return {"target_path": str(formal), "backup_path": None, "action": "merge_existing" if formal.exists() else "write_new_formal", "will_overwrite": formal.exists()}
    raise ValueError(f"unsupported overwrite_policy: {overwrite_policy}")

def validate_extraction_record(record):
    required = ["template_name", "source_graph", "coverage_scope", "facts", "evidence_citations", "overwrite_policy"]
    errors = [f"missing:{key}" for key in required if key not in record]
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
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python skill-src\storygraph\scripts\storygraph.py validate-skill --skill-root skill-src\storygraph
```

## Build stage 1 graph

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python skill-src\storygraph\scripts\storygraph.py build-stage1 --source '<novel.txt>' --template-dir '<template-dir>' --graphify-repo '<graphify-repo>'
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
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python -m pytest tests\test_stage2_schema.py tests\test_stage2_policy.py -v; python skill-src\storygraph\scripts\storygraph.py validate-skill --skill-root skill-src\storygraph
```

Expected: stage 2 tests pass; `validate-skill` prints `{'ok': True, 'missing': []}` and exits `0`.

- [ ] **Step 6: Commit docs and stage 2 schema scaffolding**

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; git -c core.quotePath=false add skill-src docs tests\test_stage2_schema.py tests\test_stage2_policy.py; git commit -m "feat: add stage2 extraction schema and output policy"
```

## Final Review Gate For Implementers

Before marking implementation work ready for user review, run these checks and attach command output:

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python -m pytest -v
```

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python skill-src\storygraph\scripts\storygraph.py validate-skill --skill-root skill-src\storygraph
```

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python skill-src\storygraph\scripts\storygraph.py inspect-templates --template-dir 'E:\AI_Projects\CultivationWorld\docs\世界观参考\模板'
```

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python skill-src\storygraph\scripts\storygraph.py build-stage1 --source 'E:\AI_Projects\CultivationWorld\docs\世界观参考\凡人修仙传\凡人修仙传.txt' --template-dir 'E:\AI_Projects\CultivationWorld\docs\世界观参考\模板' --graphify-repo 'E:\Github_Projects\graphify'; python skill-src\storygraph\scripts\storygraph.py validate-graph --graph-dir 'E:\AI_Projects\CultivationWorld\docs\世界观参考\凡人修仙传\凡人修仙传.storygraph'
```

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python skill-src\storygraph\scripts\storygraph.py build-stage1 --source 'E:\AI_Projects\CultivationWorld\docs\世界观参考\凡人修仙传\凡人修仙传.txt' --template-dir 'E:\AI_Projects\CultivationWorld\docs\世界观参考\模板' --graphify-repo 'E:\Github_Projects\graphify'
```

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; Copy-Item -LiteralPath 'E:\AI_Projects\CultivationWorld\docs\世界观参考\凡人修仙传\凡人修仙传.txt' -Destination "$env:TEMP\storygraph-hash-change.txt" -Force; Add-Content -LiteralPath "$env:TEMP\storygraph-hash-change.txt" -Value "`n临时hash变化验证" -Encoding UTF8; python skill-src\storygraph\scripts\storygraph.py build-stage1 --source "$env:TEMP\storygraph-hash-change.txt" --template-dir 'E:\AI_Projects\CultivationWorld\docs\世界观参考\模板' --graphify-repo 'E:\Github_Projects\graphify'; Add-Content -LiteralPath "$env:TEMP\storygraph-hash-change.txt" -Value "`n第二次变化" -Encoding UTF8; python skill-src\storygraph\scripts\storygraph.py build-stage1 --source "$env:TEMP\storygraph-hash-change.txt" --template-dir 'E:\AI_Projects\CultivationWorld\docs\世界观参考\模板' --graphify-repo 'E:\Github_Projects\graphify'
```

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python skill-src\storygraph\scripts\storygraph.py build-stage1 --source 'E:\AI_Projects\CultivationWorld\docs\世界观参考\凡人修仙传\凡人修仙传.txt' --template-dir 'E:\AI_Projects\CultivationWorld\docs\世界观参考\模板' --graphify-repo 'E:\AI_Projects\StoryGraph\missing-graphify-for-ledger'; if ($LASTEXITCODE -eq 0) { throw 'Expected graphify failure command to exit nonzero' }
```

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null; python -m pytest tests\test_stage2_policy.py tests\test_template_aware.py tests\test_templates.py -v
```

Expected review evidence:

- `validate-skill` exits `0` and reports no missing skill structure.
- `inspect-templates` reports `template_count` as `37` for existing `*模板.md` files and records README-only missing template files as `missing_template_file` warnings.
- `build-stage1` creates or reuses the intentional external `.storygraph` directory beside the CultivationWorld source novel and writes `manifest.json`, `graphify-out\graph.json`, `requirements\template-requirements.json`, `coverage\chunk-ledger.json`, `coverage\evidence-index.json`, `coverage\template-readiness.json`, `coverage\agent-run-ledger.json`, and `coverage\gap-report.md`.
- `validate-graph` performs deep canonical validation for nodes, edges, events, evidence, `supports_templates`, status enums, stable ID prefixes, graphify-compatible fields, and 37-template readiness completeness.
- The immediate second `build-stage1` run with unchanged source reports `"status": "reused"`, proving idempotent no-rebuild behavior.
- The hash-change command reports `"source_state": "changed"` after the temporary source text is modified.
- The missing graphify command exits nonzero, returns `"status": "failed"`, writes a failed graphify adapter record into `coverage\agent-run-ledger.json` with `graphify_unavailable` or `graphify_failed`, and `validate-graph` treats that ledger record as blocking.
- `test_stage2_policy.py` proves default output goes to `drafts\`, existing formal Markdown is not overwritten, and formal overwrites happen only under `backup-and-overwrite` or `merge`.
- `template-readiness.json` contains 37 records, one per discovered template, and every requirement status is one of `covered`, `needs_review`, or `not_found_in_source`.
- No implementation step modifies `E:\Github_Projects\graphify`; graphify is only read or invoked through adapter configuration.
- No committed config file contains the local absolute template path, local graphify path, test novel path, repository name, or install destination as a global default.
