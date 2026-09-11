# Track A conversation architecture

Implementation target: Track A, local Docker delivery and a streaming cascade first, as requested by the user. Continue implementation in WSL. Realtime comparison is deferred until time permits; no live voice tests have run.

## Required outcome and implemented baseline

The assignment requires English-only real-time Daily/Pipecat conversation, relevant follow-ups, corrections, consistent cards, visible/testable arithmetic, an honest 30-day plan and a check of user understanding. Track A adds depth in conversational intelligence and evidence from real conversations. Core tests remain required; a separate Track B evaluation platform is out of scope.

The current foundation provides login, protected APIs, an empty responsive workspace and a typed Next.js-to-Python connection. Financial persistence, calculations, voice and final plans remain unimplemented. Compose defines web, agent and Postgres. Hosted databases and cloud deployment are out of scope. Local operation still needs internet for Daily and AI providers.

## Proposed first architecture

Use one streaming cascade: Daily transport -> Pipecat turn handling -> streaming STT -> GPT-5.6 Luna through OpenRouter -> streaming TTS -> Daily. Luna is selected for the spoken loop because it prioritizes low turn latency; a deeper model such as Terra belongs in a later planning/tool path, not on every spoken turn. Use ElevenLabs realtime STT and streaming TTS as the initial quality-oriented candidate, following the user's preference. Compare Sarvam's realtime STT and TTS as the cost-oriented candidate when the first path works. Provider preference is not evidence of relative measured quality or cost.

Pipecat coordinates streams, interruptions and context. A single conversational LLM asks questions and proposes tools. Python tools validate changes, compute integer-paise/date-based results and persist a revision in local Postgres. Both speech and cards use that revision. Streaming ordinary conversational text to TTS is allowed; numeric conclusions wait for committed tool results. Cancel stale generation and audio after a correction. Track what was actually played so interrupted, unheard speech is not treated as acknowledged information.

Keep provider/model selection in configuration and pin it for a session. OpenRouter makes changing text models practical, but tool schemas, reasoning settings and streaming behavior still need compatibility checks. Do not introduce a supervisor model, a second planner LLM or automatic model switching on every turn for the initial slice.

The alternative is Daily -> Pipecat -> direct OpenAI Realtime (`gpt-realtime-2.1-mini`) with the same financial tools and persistence. It can satisfy the brief and Track A. It has direct access to audio cues and may improve conversational latency, but that must be measured through our actual Daily/Pipecat path. Native audio does not itself ensure correct facts, good questions or card consistency. Do not bypass mandatory Daily by connecting the browser straight to OpenAI.

## Evidence and limits

- [OpenAI Luna model](https://developers.openai.com/api/docs/models/gpt-5.6-luna): text/image input and text output, streaming and function calling. It is not an audio model; the cascade supplies STT/TTS around it. OpenRouter model access needs a live account check before depending on it. Terra remains a candidate for later, slower planning work.
- [OpenAI Realtime Mini model](https://developers.openai.com/api/docs/models/gpt-realtime-2.1-mini): audio/text input and output and function calling; structured outputs are not supported. Validate tool arguments on the server in either architecture. The generic model-card streaming field should not be treated as a prohibition on Realtime audio: the documented service provides real-time audio sessions.
- [OpenAI voice architectures](https://developers.openai.com/api/docs/guides/voice-agents): chained workflows expose intermediate text and allow independent component replacement.
- [Pipecat Realtime service](https://docs.pipecat.ai/api-reference/server/services/s2s/openai): instructions, tools and turn detection are configurable. Exact requested-model compatibility still needs a live test with our pinned version.
- [Pipecat Smart Turn](https://docs.pipecat.ai/api-reference/server/utilities/turn-detection/smart-turn-overview): turn completion uses learned audio cues, not silence alone. A cascade is not inherently a rigid questionnaire or limited to a fixed silence timeout.
- [Pipecat ElevenLabs STT](https://docs.pipecat.ai/api-reference/server/services/stt/elevenlabs) and [TTS](https://docs.pipecat.ai/api-reference/server/services/tts/elevenlabs): use streaming services, not file-upload transcription. An account-accessible voice ID is needed for TTS.
- [Sarvam realtime STT](https://docs.sarvam.ai/api/api-guides-tutorials/speech-to-text/realtime-streaming) and [Pipecat Sarvam](https://docs.pipecat.ai/api-reference/server/services/stt/sarvam): distinguish current realtime streaming from the legacy streaming endpoint; adapter/model-version compatibility must be verified.
- [OpenRouter tool calling](https://openrouter.ai/docs/guides/features/tool-calling): our application executes its financial tools and returns results; model-generated arguments are not permission or proof of execution.

The supplied [Gradium article](https://gradium.ai/content/cascaded-voice-agent-vs-speech-to-speech-2026) is useful for the modularity and audio-information tradeoff. Its broad claims that speech-to-speech lacks production APIs or conventional instructions/tool support do not describe the documented OpenAI Realtime API. Its cascade/VAD restriction is also too broad given semantic turn detectors. It is a provider perspective, not a head-to-head test of our chosen models.

The other supplied AI discussion contains useful corrections, but several comparisons remain unsupported: no architecture guarantees better number recognition; interruption cancellation must be tested end to end; a single audio model does not automatically synchronize financial state. A transcript-only test cannot establish whether real spoken hesitations and accents are understood. Both architectures require audio tests as well as tool and calculation checks. A rubric threshold is a legitimate acceptance rule, but an 85% aggregate score cannot excuse critical financial errors, and neither exact-match grading nor a structured schema makes an LLM deterministic.

## Conversation policy: intent before intake

Begin with the user's immediate goal. If the opening utterance already states it, use it rather than asking again. Treat onboarding, urgent questions and resumed plans as context, not mandatory sequential screens. On resumption, check whether previous amounts and dates still apply before relying on them.

Useful context is progressive and purpose-limited:

| Context | Why it can matter | When to ask |
| --- | --- | --- |
| Current ask and urgency | Determines the next useful question | First if not already stated |
| Accessible cash and dates | Determines whether a near-term payment can be covered | Before a feasibility conclusion |
| Income amount, timing, reliability and net/gross basis | Avoids counting uncertain or unavailable money | When relevant to the horizon |
| Obligations, due dates and paid status | Avoids missing or double-counting a payment | As relevant to the task, then broaden before a complete plan |
| Responsibilities and protected spending | Preserves the user's constraints | Before proposing allocation changes |
| Employment/business/household situation | Explains income and ownership of money | When it changes interpretation, without inventing values |
| Age/life stage | May explain a stated pension, dependent or work transition | Only when material; do not require exact age to answer an EMI question |
| Knowledge gaps and understanding | Prevents repeated pressure for unknown values | During clarification and final review |

One question at a time, chosen by material impact: an imminent payment gap, a conflicting fact that changes the answer, missing timing/amount, then wider completeness. This is a prioritization policy, not a scripted sequence. Explain a question's purpose briefly when it helps the user. Repetition may signal confusion; use stored facts and clarify the meaning rather than duplicating entries or repeating the entire intake.

Example: user says, "My EMI is due Friday and salary comes Monday." A relevant next question is accessible money before Friday, unless already supplied. Exact age or a count of all loans is not the first blocker. A narrow answer must stay conditional on other essentials and obligations not yet checked; a complete 30-day plan needs wider coverage.

Ambiguous numbers stay unresolved. Explicit corrections replace the identified fact; ambiguous targets require clarification. User uncertainty remains uncertainty rather than a fabricated midpoint. Stop questioning when the requested answer has enough support, or offer a provisional answer naming what is missing. Check understanding of the actual shortfall or next action, not merely whether the user says "yes."

## Small selection experiment and demo targets

Before committing to the full voice implementation, compare short cascaded and Realtime spikes using the same tools and synthetic audio cases. This is an implementation choice check within Track A, not a second optional track or two complete products.

1. Hesitation and self-correction: salary/gig amount changed from 30,000 to 25,000 without duplicate income.
2. Repetition and ambiguous numbers: clarify the amount, preserve uncertainty, avoid repeated intake.
3. Urgent specific ask: prioritize Friday EMI versus Monday salary, then obtain only missing material facts.
4. Uncertain receivable and protected spending: label conditional money, preserve spending choices and explain any unresolved gap.
5. Interrupt a numeric explanation: stop stale audio, apply the correction once, update cards and revise the spoken conclusion.
6. Disconnect or provider failure: preserve committed state, communicate interruption, avoid fabricated success.

Use exact assertions for calculation outputs and committed facts, human review for question relevance/naturalness and recorded audio for actual speech handling. Track end-of-user-turn to first audible response, interruption-to-silence, spoken/card agreement, failures and provider usage. Compare cost per completed scenario, including STT, LLM, TTS or realtime audio and Daily; text token rates alone are not call cost. No measured winner or latency claim exists yet.
