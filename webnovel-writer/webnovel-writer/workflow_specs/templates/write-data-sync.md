Produce the structured `data-sync` payload for chapter writeback.

Hard requirements:
- `files_written` must list every file that should exist after writeback.
- `summary_file` must point to the chapter summary markdown path.
- `state_updated` and `index_updated` must reflect the intended writeback.
- Do not claim success if the payload only contains booleans and file paths.
- The request chapter is authoritative. Do not remap writeback to a different chapter file or summary path.

Return JSON only. Prefer explicit structured fields over prose.

Include, when grounded in the chapter or planning context:
- `chapter_meta`: `title`, `location`, `characters`
- `organizations`: faction or institution entries
- `locations`: important places introduced or updated
- `world_rules`: power rules, setting constraints, costs, irreversible consequences
- `setting_entries`: extra normalized setting rows when category matters
- `entities_new`
- `entities_appeared`
- `relationships_new`
- `state_changes`
- `uncertain`
- `foreshadowing_items`
- `timeline_events`
- `character_arcs`
- `knowledge_states`

Entry rules:
- Each setting entry should use a stable `name` and a short `summary`.
- `setting_entries[].category` must be one of `faction`, `location`, `rule`.
- `state_changes` should only include concrete changes that are actually supported by the text.
- `timeline_events` must be objective facts that happened in the chapter, not guesses or interpretations.
- `knowledge_states` must describe what a character believes, not what is objectively true unless the text proves it.
- `foreshadowing_items` should only capture explicit recoverable promises, signals, or unresolved setup worth tracking.
- `character_arcs` should be limited to grounded updates for core characters whose inner trajectory changed or became clearer in this chapter.
- If a field has no grounded data, return an empty array instead of inventing content.
