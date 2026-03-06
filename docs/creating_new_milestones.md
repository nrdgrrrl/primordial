not:
roadmap -> all milestone tasks at once

But:
roadmap -> implementation program -> current spec -> Pass A -> tasks -> code -> validate -> next spec

That is much safer.
The reason is simple: once Pass A looks at the real code, it may discover that your neat milestone boundary is slightly wrong. If you pre-generate everything too early, you end up planning fiction.

After Milestone 1, I’d include a short implementation summary in the prompt, something like:
_____________________________
Milestone 1 outcome summary:
- fixed-step sim loop implemented
- variable render cadence added
- timing instrumentation added for sim/render/frame
- benchmark output updated
- known issue: [whatever]
- architecture note: [whatever]
- constraints discovered: [whatever]

Now draft SPEC_M2_HEADROOM_AND_LIGHT_OBSERVABILITY.md using that reality, not just the original plan.
_________________________

Next milestone:
________________________
I’m working on a staged development plan for an evolutionary simulation project.

Please use the attached documents as the source of truth:
- roadmap
- IMPLEMENTATION_PROGRAM.md
- [completed milestone spec, if relevant]
- [summary of what was actually implemented in the previous milestone]

We have completed Milestone 1, or are close enough to move forward. I now want you to draft:

SPEC_M2_HEADROOM_AND_LIGHT_OBSERVABILITY.md

Requirements:
- Base it on the implementation program and current roadmap.
- Reflect any lessons or constraints discovered during Milestone 1.
- Keep the scope bounded to Milestone 2 only.
- Include: purpose, objective, why this milestone exists, in-scope work, non-goals, invariants, desired implementation shape, risks/failure modes, affected subsystems to inspect, acceptance criteria, validation plan, recommended AI agent execution sequence, and guidance for task-file generation.
- Do not drift into Milestone 3 or later.
- Do not turn this into a vague essay. Write it as an execution-facing spec for an AI coding agent.
_______________________________

