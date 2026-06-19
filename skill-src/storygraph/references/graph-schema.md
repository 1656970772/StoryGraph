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
