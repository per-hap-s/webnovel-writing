Generate the chapter context execution package.
Preserve continuity with existing project state and only use facts grounded in the project files and prior structured outputs.
Return exactly one JSON object only. Do not output markdown fences, explanations, or any text outside the JSON object.
Keep `task_brief` and `contract_v2` concise and focused on the current chapter execution needs.
`draft_prompt` must be a short plain-text string for the next step to consume, not a full long-form design memo.
Treat `story_plan` as the authoritative multi-chapter roadmap for the current rolling horizon.
Treat `director_brief` as the highest-priority single-chapter execution contract.
Copy `story_plan` through to the output as a structured object without changing its intent.
Copy `director_brief` through to the output as a structured object without changing its intent.
`task_brief`, `contract_v2`, and `draft_prompt` must operationalize `story_plan` and `director_brief`, not replace them.
If line breaks are needed inside `draft_prompt`, use escaped `\n` within the JSON string.
When the chapter involves memory loss, rewind, or cognition damage, explicitly separate objective facts from the protagonist's mistaken perception.
For any second-pass action after a rewind, provide at least one explicit time anchor.
For any key countermeasure or confrontation scene, include at least one concrete spatial relation.
If the same warning or signal appears multiple times, include the protagonist's current judgment on whether the source is same-source, different-source, or still undetermined.
