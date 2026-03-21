Rewrite the target chapter as structured JSON for a local repair task.
Use `repair-plan` as the authoritative issue contract: repair only the requested problem, follow the provided guardrails, and preserve the established plot direction.
Hard requirements:
- Return exactly one complete JSON object only.
- Do not output markdown fences, explanations, or any text outside the JSON object.
- `chapter_file`, `content`, `word_count`, and `change_summary` are all required.
- `chapter_file` is a reference field only; keep it aligned with the current request chapter and do not remap chapters.
- Perform a single-chapter local rewrite only. Do not redesign the volume outline, create cross-chapter retcons, or change character voice without necessity.
- Keep names, setting rules, chronology, and spatial relationships consistent with the provided project references.
- `change_summary` should briefly list the concrete local fixes that were applied.
- Ensure the full response is valid JSON before finishing.
