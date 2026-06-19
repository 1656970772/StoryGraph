# StoryGraph Graph Schema

The canonical graph preserves graphify-native fields and adds StoryGraph template-aware fields.

Required top-level fields:
- `schema_version`
- `graphify_schema_version`
- `storygraph_schema_version`
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

Graphify-native nodes, edges, and events may remain in the graph without StoryGraph-only fields before merge. Any node, edge, event, or evidence item created or modified by StoryGraph must pass the full StoryGraph validation contract.

Deep validation requires StoryGraph-marked items to use stable ID prefixes, known node and evidence references, non-empty `supports_templates`, configured requirement statuses, configured confidence levels, and configured verification statuses. StoryGraph nodes, edges, and events must also carry `source_location` or `source_range`; missing source locators are reported as `<item>_without_source_location:<id>`.
