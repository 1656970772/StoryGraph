# StoryGraph CLI

StoryGraph CLI lives at `skill-src/storygraph/scripts/storygraph.py`.

## Commands

```powershell
python skill-src/storygraph/scripts/storygraph.py --version
python skill-src/storygraph/scripts/storygraph.py validate-skill --skill-root skill-src/storygraph
python skill-src/storygraph/scripts/storygraph.py config-check --config skill-src/storygraph/config/storygraph.default.json --local-override path/to/storygraph.local.json
python skill-src/storygraph/scripts/storygraph.py inspect-templates --template-dir path/to/templates --config path/to/storygraph.default.json --local-override path/to/storygraph.local.json
python skill-src/storygraph/scripts/storygraph.py build-stage1 --source path/to/novel.txt --template-dir path/to/templates --graphify-repo path/to/graphify
python skill-src/storygraph/scripts/storygraph.py validate-graph --graph-dir path/to/novel.storygraph
```

`--local-override` is optional, but an explicitly provided missing override returns exit code `2`.

## Stage 1

`build-stage1` writes `manifest.json`, `requirements/template-requirements.json`, `graphify-out/*`, and coverage ledgers under `<novel>.storygraph`. It returns JSON and exits `0` for `success`, `warning`, or `reused`; other statuses exit `2`.

Stable failure codes include `source_unreadable`, `source_encoding_error`, `chunk_extraction_failure`, `single_writer_conflict`, `unparsable_subagent_json`, `readiness_below_threshold`, `template_without_reliable_evidence`, `graphify_unavailable`, `graphify_failed`, and `graphify_artifact_missing`.

Stage 1 reuses existing output only when the source hash, stage input hash, manifest status, required files, deep graph validation, and graphify failure ledger checks all pass. Source, template, config, graphify repo, graphify command, or chunk strategy changes trigger a rebuild.

## Validation

`validate-graph` checks required Stage 1 outputs, failed ledger records, graph schema, template readiness, chunk coverage, evidence references, manifest stage status, and single-writer scopes. Failed agent ledger entries are reported as `blocking_ledger:<error_code>`.
