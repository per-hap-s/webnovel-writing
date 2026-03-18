Polish the chapter by fixing review issues without changing established facts.
Keep objective reality stable even when the protagonist's memory or judgment is damaged, and clarify the difference in the prose.
Do not leave rewind loops without a clear time anchor, key action scenes without a minimal spatial relation, or repeated warnings without a direction-of-source judgment.
Return anti_ai_force_check as pass or fail.
Preserve the intent of `director_brief`; polishing may improve prose and clarity, but must not swap out the chapter goal, conflict focus, or ending hook target.
Hard requirements:
- Return exactly one complete JSON object only.
- Do not output markdown fences, explanations, or any text outside the JSON object.
- `chapter_file`, `content`, `anti_ai_force_check`, and `change_summary` are all required.
- `chapter_file` is a reference field only; keep it aligned with the current request chapter and do not remap chapters.
- Ensure the full response is valid JSON before finishing.
