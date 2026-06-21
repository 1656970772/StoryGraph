# Extraction Workflow

Stage 2 is an agent-driven template document generation workflow. Python prepares task packets, validates records, tracks ledgers, enforces output policy, and renders Markdown drafts. Stage 2 agents produce the semantic document content as `stage2-extraction-record.v1` JSON records.

Every future extraction record must cite Stage 1 graph evidence, template requirements, and chunk ranges. Output categories, draft directory, allowed overwrite actions, and render targets come from configuration rather than Python constants.

Each extraction record keeps `coverage_scope.stage1_chunk_ledger` at `coverage/chunk-ledger.json`; agents fill concrete `chunk_ranges` when they cite evidence. Template execution and evidence accounting use these artifact paths:

- `coverage/template-run-ledger.json`
- `coverage/template-evidence-usage.json`
- `coverage/template-gap-report.md`

Evidence categories are read from `stage2_categories` in the active policy. The schema names the sections `facts`, `judgments`, `pending_verifications`, and `not_found_items`, but the displayed category labels are config data.

The default Stage 2 output policy is draft-first. `draft` writes to `<graph_dir>/<stage2_output_policy.default_dir>/<template_name>.md` and does not overwrite an existing formal Markdown document beside the novel. Formal document paths are selected only when `overwrite_policy` is `backup-and-overwrite` or `merge`.

The normal command order is `prepare-stage2` -> `claim-stage2-batches` while dispatching Stage 2 agents -> `ingest-stage2` -> `render-stage2` -> `validate-stage2`. `render-stage2` must not run before agent records have passed `ingest-stage2`.
