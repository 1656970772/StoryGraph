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

Stage 2 is currently a schema scaffold. Use configured `stage2_categories`, `stage2_output_policy`, and `overwrite_policy`; the default `draft` policy writes under the graph draft directory and must not overwrite existing formal Markdown documents.

Run `scripts/storygraph.py validate-skill` before reporting the skill source as ready.
