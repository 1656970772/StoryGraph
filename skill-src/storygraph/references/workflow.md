# StoryGraph Workflow

1. Validate the skill source with `scripts/storygraph.py validate-skill`.
2. Load `config/storygraph.default.json`, optional `storygraph.local.json`, then CLI overrides in that order.
3. Discover template files from the configured template directory. Existing template files define the integration scope; README-only entries are warnings.
4. Build the Stage 1 graph into `<novel-stem>.storygraph/`.
5. Require the Stage 1 manifest, graphify outputs, requirement matrix, coverage ledgers, and gap report before any Stage 2 extraction.
6. Stage 2 is draft-first. Existing formal Markdown documents are not overwritten unless the configured output policy explicitly allows backup overwrite or merge.
