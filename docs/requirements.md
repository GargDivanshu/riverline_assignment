# Requirements

Source: `engineering-assignment.md`, read in full on 2026-09-10. The authentication/workspace scaffold is implemented; the assignment?s voice and financial acceptance checks remain pending. See [foundation verification](verification.md). See the [reference review](reference-review.md) for video observations and limitations, and the [proposed implementation spec](implementation-spec.md) for design details.

## Acceptance mapping

| ID | Requirement | Acceptance evidence |
| --- | --- | --- |
| R1 | Web application | Start/end voice, live information, final plan review. |
| R2 | Pipecat and Daily, real-time audio | Actual live conversation using both; no recorded-message exchange. |
| R3 | English-only adaptive conversation | Useful follow-ups, retained facts, clarification and corrections without a fixed questionnaire. |
| R4 | Honest uncertainty | Missing, uncertain and conflicting information distinguished from confirmed facts; no guesses presented as facts. |
| R5 | Consistent live cards | A correction updates every affected card and calculation. Card types are implementation choices. |
| R6 | Realistic 30-day plan | Dated income/payments, essentials, optional expenses, priorities, and unaffordable scenarios handled explicitly. |
| R7 | Visible, testable calculations | Figures trace to inputs and can be reproduced in tests. |
| R8 | Financial restrictions | No invented numbers/offers, promised approvals, recommendations for another loan, or false claims of completed actions. |
| R9 | Explain and confirm | Simple final explanation and confirmation of user understanding. |
| R10 | One-command startup | Configured application starts completely with `docker compose up --build`, without extra terminals. |
| R11 | Configuration documentation | README includes exact local address, startup command, variable purposes/required status and API-key setup. `.env.example` covers all required variables. No committed secrets. |
| R12 | Submission artifacts | Repository, Docker README, short demo video, candidate-authored journal, test/evaluation results, and lists of what works, what does not, next work, and good/poor AI contributions. |

## Evaluation

One strong complete journey matters more than many unfinished features. Evaluation covers end-to-end behavior, useful questions, calculation correctness, realistic plans, corrections/missing information, voice/card consistency, sensible tradeoffs, testing and simplicity.

The candidate must explain and modify the code live without AI and defend any statistical methodology used.

## Journal

Entirely candidate-authored, written during the work. AI must not write, rewrite, polish, summarise decisions, or paraphrase notes for it. Missing or AI-generated journal content disqualifies the submission.

## Reference and optional work

Watch the reference before implementation. It illustrates real-time voice, live cards and a financial outcome. Do not copy its interface, questions or conversation flow.

Choose at most one optional track after completing the core:

- A: Conversational intelligence, demonstrated through real conversations.
- B: Evaluation/regression testing, including a discovered failure, a change, and evidence of improvement.

Core testing and conversation quality remain required whichever track is chosen. No optional track is selected.

## Outstanding information

- Deadline is in the hiring email, not this brief.
- Full audio transcription and precise demo card values remain unverified; the visual/sampled audio review is documented separately.
- Available credentials and service budget.
- Remaining stack, date/currency assumptions, data model and prioritisation policy.

Deployment is not required. Submission uses the company form; its URL is not supplied in the brief.
