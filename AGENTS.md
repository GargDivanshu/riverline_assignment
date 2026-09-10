# Working in this repository

## Authority and scope

- Follow the user's instructions and read `engineering-assignment.md` before implementation. If it is empty or unavailable, record the gap; do not infer assignment requirements from company marketing or the video filename.
- Read `docs/requirements.md` and `docs/decision-log.md` when resuming work. Keep source facts, user preferences, proposals, and unresolved questions distinct.
- Read `docs/implementation-spec.md` and `docs/scenario-matrix.md` before application work. These are proposed designs and acceptance cases, not evidence of user approval or passing tests. Read `docs/reference-review.md` for the limits of the video review.
- Preserve supplied reference materials. Do not replace the assignment with an invented brief.
- Keep changes proportional to the assignment. Avoid speculative features, frameworks, infrastructure, and abstractions.

## Collaboration and authorship

- At the user's request, maintain a verbatim conversation archive in `.Tmp/conversation.md`, which must remain Git-ignored. Append user prompts and user-facing assistant commentary/final replies in order, preserving their wording. This is a raw reference archive, not a journal or decision summary. Do not paraphrase, infer missing messages, or include hidden reasoning, system/developer instructions, or tool payloads. Mark any unavailable history explicitly. Before ending a turn, include the exact final reply being sent. On resuming, inspect the archive tail to avoid duplicate entries.
- Explain consequential choices in plain language: problem, options, tradeoffs, recommendation, and evidence.
- Do not write, rewrite, polish, summarise decisions, or paraphrase notes for the mandatory journal. Do not maintain an AI decision-summary log for it. Technical specifications and reproducible test artifacts may document the system, without supplying the candidate's personal narrative.
- Never invent the candidate's thought process, agreement, experience, or journal entries. Record user acceptance or rejection only when expressed.
- Do not treat an AI recommendation as an agreed decision. Routine reversible implementation choices may proceed within the authorized scope; label them accurately.
- Use focused commits. Do not publish, deploy, or message others without authorization for that action.

## Implementation and verification

- Turn explicit requirements into observable acceptance checks before building.
- Start with one working end-to-end flow; add complexity only for a demonstrated requirement.
- Validate external inputs and handle relevant failure states. Keep secrets out of source control and logs; document required configuration with placeholders.
- If financial calculations are in scope, define units, precision, rounding, and date assumptions explicitly and verify boundary cases. Do not use generated text as the source of numerical truth.
- If an LLM is in scope, make tool permissions and failure behavior explicit, and evaluate representative successful and unsuccessful interactions.
- Use synthetic data for development unless the assignment requires otherwise. Label mocks and simulated integrations clearly.
- Run checks appropriate to each change. Report what ran, what passed or failed, and what remains unverified. Never claim an unrun check passed.
- Before handoff, verify documented setup from a clean environment where feasible and walk through each acceptance check.

## Skills and tooling

- Use relevant available skills when they materially help the current task; follow their loading instructions.
- Add project-specific skills only when a concrete repeated workflow warrants one. Keep repository rules here rather than duplicating them across prompt files.
- Do not install tools or introduce services solely because they are suggested in a reference. Explain the need and account for setup, cost, and reproducibility.

