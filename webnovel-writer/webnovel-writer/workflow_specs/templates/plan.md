Produce a volume or chapter plan as structured JSON grounded in the project's outline and constraints.

Hard requirements:
- Return exactly one complete JSON object only.
- Do not output markdown fences, commentary, or any prose outside the JSON object.
- Keep every field concise enough to avoid truncation.
- Do not rename contract keys or omit required fields.
- Before finishing, verify that the full response is valid JSON with all strings properly closed.
