Write the chapter draft as structured JSON.
Do not invent settings that conflict with the provided project references.
Hard requirements:
- Return exactly one complete JSON object only.
- Do not output markdown fences, explanations, or any text outside the JSON object.
- `chapter_file`, `content`, and `word_count` are all required.
- `chapter_file` is a reference field only; keep it aligned with the current request chapter and do not remap chapters.
- Follow `director_brief` as the authoritative single-chapter objective, conflict, and hook contract.
- Do not silently replace or bypass `director_brief`; if a target cannot be fully completed, defer it instead of inventing a different chapter goal.
- Ensure the full response is valid JSON before finishing.
