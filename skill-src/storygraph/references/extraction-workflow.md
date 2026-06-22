# Extraction Workflow

Stage 2 is an agent-driven template document generation workflow. Python prepares one task packet per template document, validates records, tracks ledgers, enforces output policy, builds review drafts, filters/merges final entries, and renders Markdown. Stage 2 agents produce semantic extraction content as `stage2-extraction-record.v1` JSON records.

Every future extraction record must cite Stage 1 graph evidence, template requirements, and chunk ranges. Output categories, draft directory, allowed overwrite actions, render targets, draft kept fields, final admission rules, dedupe keys, confidence thresholds, and review-only classifications come from configuration rather than Python constants.

Each extraction record keeps `coverage_scope.stage1_chunk_ledger` at `coverage/chunk-ledger.json`; agents fill concrete `chunk_ranges` when they cite evidence. Template execution and evidence accounting use these artifact paths:

- `coverage/template-run-ledger.json`
- `coverage/template-evidence-usage.json`
- `coverage/template-gap-report.md`

Evidence categories are read from `stage2_categories` in the active policy. The schema names the sections `facts`, `judgments`, `pending_verifications`, and `not_found_items`, but the displayed category labels are config data.

The default Stage 2 output policy is draft-first. `draft` writes to `<graph_dir>/<stage2_output_policy.default_dir>/<template_name>.md` and does not overwrite an existing formal Markdown document beside the novel. Draft Markdown is a compact review surface: concrete extracted entries plus source range, source excerpt, evidence ids, confidence, and review status. It must not copy agent-written prose sections, preambles, template explanations, or source lists.

`backup-and-overwrite` writes the formal document beside the novel, first copying an existing formal Markdown file to the configured `.bak` path. Formal rendering reads only the template path and hash stored by template discovery in the run ledger, not any path supplied by an agent record. It verifies the template hash, reads the original template Markdown headings, and then emits only entries that pass the configured final admission rules after dedupe/merge. If any merged duplicate is low-confidence or review-only, the merged entry remains out of the formal body. Unnamed, composite, low-confidence, under-evidenced, incomplete, or review-only entries remain out of the formal body. `merge` remains fail-closed until a separate merge contract exists.

The normal command order is `prepare-stage2` -> `claim-stage2-batches` while dispatching one Stage 2 agent per template document through a sliding window -> `ingest-stage2` -> `render-stage2` -> `validate-stage2`. `render-stage2` must not run before agent records have passed `ingest-stage2`.
