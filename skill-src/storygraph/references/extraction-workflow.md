# Extraction Workflow

Stage 2 is a schema scaffold in this plan, not a complete extraction implementation.

Every future extraction record must cite Stage 1 graph evidence, template requirements, and chunk ranges. Output categories, draft directory, allowed overwrite actions, and render targets come from configuration rather than Python constants.

The scaffold record keeps `coverage_scope.stage1_chunk_ledger` at `coverage/chunk-ledger.json` and starts with an empty `chunk_ranges` list until extraction assigns concrete ranges. Template execution and evidence accounting use these artifact paths:

- `coverage/template-run-ledger.json`
- `coverage/template-evidence-usage.json`
- `coverage/template-gap-report.md`

Evidence categories are read from `stage2_categories` in the active policy. The schema names the sections `facts`, `judgments`, `pending_verifications`, and `not_found_items`, but the displayed category labels are config data.

The default Stage 2 output policy is draft-first. `draft` writes to `<graph_dir>/<stage2_output_policy.default_dir>/<template_name>.md` and does not overwrite an existing formal Markdown document beside the novel. Formal document paths are selected only when `overwrite_policy` is `backup-and-overwrite` or `merge`.
