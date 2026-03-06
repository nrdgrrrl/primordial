For code tasks like TASK_M1_02_FIXED_STEP_SCAFFOLD.md

Your prompt is almost fine, but I would still tighten it so the agent does not edit the task file itself.

Use this instead:

Use these documents as the source of truth:
- roadmap.md
- IMPLEMENTATION_PROGRAM.md
- SPEC_M1_FIXED_STEP_AND_INSTRUMENTATION.md
- TASK_M1_02_FIXED_STEP_SCAFFOLD.md

The task file is an instruction document, not the output file.
Do not modify the task file itself unless I explicitly ask you to.

You are implementing the code changes required by this task only.

Requirements:
- Stay strictly within the task scope.
- Do not implement later tasks.
- Do not mix in unrelated cleanup or refactors.
- Read the relevant files first and confirm which files you will touch.
- If the task appears to require broader changes than the task file allows, stop and explain instead of improvising.

Deliver:
1. a short summary of the task in your own words
2. the files you will modify
3. the code changes for this task only
4. a concise explanation of what changed
5. validation steps I should run
6. any follow-on risks or notes, without implementing them

That is much safer.

For audit or documentation tasks

Use a different prompt.

Example:

Use these documents as the source of truth:
- roadmap.md
- IMPLEMENTATION_PROGRAM.md
- SPEC_M1_FIXED_STEP_AND_INSTRUMENTATION.md
- TASK_M1_01_LOOP_AUDIT.md

The task file is an instruction document, not the output file.
Do not modify the task file itself unless I explicitly ask you to.

This is an audit/documentation task, not a code implementation task.

Your job is to complete the audit described by the task and provide the findings in chat.
Do not modify runtime code.
Do not write patches.
Do not implement later tasks.

Deliver:
1. a short summary of the audit goal
2. the files you inspected
3. the audit findings
4. risks and hidden dependencies
5. validation or follow-up checks
6. whether a separate checked-in findings document would be useful


  1. 
  2. 
  3. TASK_M1_03_TIMING_INSTRUMENTATION.md
  4. TASK_M1_04_MAIN_LOOP_INTEGRATION.md
  5. TASK_M1_05_VALIDATION_AND_BENCHMARK.md
