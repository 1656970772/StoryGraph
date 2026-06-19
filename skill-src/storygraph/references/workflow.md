# StoryGraph Workflow

1. Validate the skill source with `scripts/storygraph.py validate-skill`.
2. Load `config/storygraph.default.json`, optional `storygraph.local.json`, then CLI overrides in that order.
3. Run `scripts/storygraph.py inspect-templates --template-dir <template-dir>` before Stage 1 to verify template discovery, requirement parsing, and graph mappings.
4. Discover template files from the configured template directory. Existing template files define the integration scope; README-only entries are warnings.
5. Build the Stage 1 graph into `<novel-stem>.storygraph/`.
6. Require the Stage 1 manifest, graphify outputs, requirement matrix, coverage ledgers, agent-run ledger, and gap report before any Stage 2 extraction.
7. Write Stage 1 artifacts through the configured single-writer output registry so unmanaged paths and duplicate writes fail early.
8. Stage 2 is draft-first. Existing formal Markdown documents are not overwritten unless the configured output policy explicitly allows backup overwrite or merge.
