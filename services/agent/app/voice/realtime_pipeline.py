"""Speech-to-speech alternative to the cascade, using OpenAI's Realtime API.

This branch swaps the STT -> LLM -> TTS cascade for one bidirectional model that
handles audio in, audio out, turn detection, and tool calls itself. The financial
tools, prompt content, and session/tracing plumbing are unchanged and reused
directly from the cascade (`app.voice.pipeline`) rather than duplicated — only the
voice engine and how it plugs into the pipeline differ.

Compared to the cascade, this sidesteps an entire class of bug the cascade hit:
there is no local turn-detection or STT-commit-strategy configuration to get
wrong, because OpenAI's own server-side VAD decides when the user has finished
speaking and drives the response directly. What is untested here: overall
latency, voice quality, and whether its tool-calling is any more reliable than
Luna's was — that comparison is the point of this branch.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from loguru import logger
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.transcript_processor import TranscriptProcessor
from pipecat.services.openai.realtime import events
from pipecat.services.openai.realtime.llm import OpenAIRealtimeLLMService
from pipecat.transports.daily.transport import DailyParams, DailyTransport
from pipecat.turns.user_start.transcription_user_turn_start_strategy import (
    TranscriptionUserTurnStartStrategy,
)
from pipecat.turns.user_stop.speech_timeout_user_turn_stop_strategy import (
    SpeechTimeoutUserTurnStopStrategy,
)
from pipecat.turns.user_turn_strategies import UserTurnStrategies

from app.config import Settings
from app.errors import classify_voice_error, log_voice_error
from app.voice.activity import VoiceActivityProcessor
from app.voice.pipeline import (
    INSTRUCTIONS,
    NEW_OPENING,
    RETURNING_OPENING,
    TOOLS,
    ResponseStallWatchdog,
    _get_snapshot,
    _record_fact,
    _trace,
    conversation_instruction,
    existing_facts_context,
)


def _opening_instruction(mode: str) -> str:
    opening = NEW_OPENING if mode == "new" else RETURNING_OPENING
    return (
        f"The instant this session starts, before the person has said anything, speak "
        f'this greeting first and only then wait for them to respond: "{opening}"'
    )


async def run_realtime(session, settings: Settings) -> None:
    logger.info("voice_pipeline_stage session_id={} stage=creating_transport", session.id)
    transport = DailyTransport(
        session.room_url,
        session.bot_token,
        "Riverline",
        DailyParams(audio_in_enabled=True, audio_out_enabled=True, video_out_enabled=False),
    )

    logger.info("voice_pipeline_stage session_id={} stage=creating_realtime_llm", session.id)
    llm = OpenAIRealtimeLLMService(
        api_key=settings.openai_api_key,
        settings=OpenAIRealtimeLLMService.Settings(
            model=settings.realtime_model,
            session_properties=events.SessionProperties(
                audio=events.AudioConfiguration(
                    input=events.AudioInput(
                        transcription=events.InputAudioTranscription(),
                        turn_detection=events.TurnDetection(
                            type="server_vad", silence_duration_ms=600
                        ),
                    ),
                    output=events.AudioOutput(voice=settings.realtime_voice),
                ),
            ),
        ),
    )
    llm.register_function(
        "record_financial_fact", lambda params: _record_fact(params, session), timeout_secs=8
    )
    llm.register_function(
        "get_financial_snapshot", lambda params: _get_snapshot(params, session), timeout_secs=8
    )

    facts_context = await existing_facts_context(session)
    context = LLMContext(
        [
            {
                "role": "system",
                "content": (
                    f"Today is {datetime.now(ZoneInfo('Asia/Kolkata')).date().isoformat()}.\n"
                    f"{_opening_instruction(session.conversation_mode)}\n"
                    f"{conversation_instruction(session.conversation_mode)}\n{INSTRUCTIONS}{facts_context}"
                ),
            }
        ],
        tools=TOOLS,
    )
    user, assistant = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            user_turn_strategies=UserTurnStrategies(
                start=[TranscriptionUserTurnStartStrategy()],
                stop=[SpeechTimeoutUserTurnStopStrategy(user_speech_timeout=0.6)],
            ),
        ),
    )
    transcript = TranscriptProcessor()
    # stall_watchdog is assigned once `task` exists, below. This callback only fires
    # once real audio starts, well after that assignment has happened.
    stall_watchdog: ResponseStallWatchdog | None = None
    activity = VoiceActivityProcessor(
        session, on_bot_started_speaking=lambda: stall_watchdog and stall_watchdog.on_assistant_turn()
    )

    task = PipelineTask(
        Pipeline(
            [
                transport.input(),
                user,
                # Confirmed by reading the library source: OpenAIRealtimeLLMService
                # pushes TranscriptionFrame/InterimTranscriptionFrame UPSTREAM (toward
                # transport.input()), while TTSTextFrame/LLMTextFrame (the assistant's
                # side) push DOWNSTREAM as usual. transcript.user() must therefore sit
                # BEFORE llm to catch the upstream frames on their way back; putting it
                # after llm (as a prior fix did, reasoning from the cascade's shape
                # where everything flows one direction) left it downstream of where
                # user frames actually travel, so it never received one. Verified: a
                # full real conversation still had zero user-role trace rows.
                transcript.user(),
                llm,
                transcript.assistant(),
                transport.output(),
                activity,
                assistant,
            ]
        ),
        params=PipelineParams(audio_in_sample_rate=16000, audio_out_sample_rate=24000),
        enable_rtvi=False,
        idle_timeout_secs=0,
    )
    session.pipeline = task
    logger.info("voice_pipeline_stage session_id={} stage=running", session.id)

    stall_watchdog = ResponseStallWatchdog(session, task)

    @transcript.event_handler("on_transcript_update")
    async def transcript_update(_processor, frame):
        for message in frame.messages:
            if message.role in {"user", "assistant"} and message.content.strip():
                if message.role == "user":
                    session.user_transcript_received.set()
                    session.last_user_utterance = message.content.strip()
                    stall_watchdog.on_user_turn()
                await _trace(
                    session, "transcript", role=message.role, content=message.content.strip()
                )

    @transport.event_handler("on_joined")
    async def transport_joined(_transport, _data):
        logger.info("voice_bot_joined session_id={}", session.id)
        await _trace(session, "bot_joined", role="system")

    @transport.event_handler("on_first_participant_joined")
    async def joined(_transport, _participant):
        session.status = "active"
        session.activity = "thinking"
        logger.info("voice_participant_joined session_id={}", session.id)
        await _trace(session, "participant_joined", role="system")
        # The user-side context aggregator never pushes its initial context frame on
        # its own (confirmed by reading its _start(): it only sets up turn
        # controllers) — and that context frame is the only thing that makes
        # OpenAIRealtimeLLMService actually generate a response at all
        # (_handle_context -> _create_response(); nothing else triggers it, and
        # LLMMessagesAppendFrame is an unimplemented stub in this pipecat version).
        # Without this explicit push the bot joins and never speaks a word.
        await user.push_context_frame()

    @transport.event_handler("on_participant_left")
    async def left(_transport, _participant, _reason):
        logger.info("voice_participant_left session_id={}", session.id)
        await _trace(session, "participant_left", role="system")
        await task.cancel()

    @task.event_handler("on_pipeline_error")
    async def failed(_task, frame):
        source = getattr(getattr(frame, "processor", None), "name", None)
        public = classify_voice_error(
            getattr(frame, "exception", None),
            source=source,
            description=getattr(frame, "error", None),
        )
        log_voice_error(public, getattr(frame, "exception", None), session_id=session.id)
        # A retryable OpenAI error (observed live: a rate-limit rejection of one
        # response) is a provider hiccup, not a reason to end the call. Unlike the
        # cascade there is no "just speak this" frame to apologize with — every
        # response after the first is triggered by OpenAI's own server-side VAD, not
        # by anything we push locally — so recovery here is simply not tearing the
        # session down: the next thing the person says drives the next response
        # attempt normally. Bounded so a provider that keeps failing still ends the
        # call rather than leaving a silently broken one open.
        is_llm_hiccup = public.code.startswith("voice_openai_") and public.retryable
        if is_llm_hiccup and session.recoverable_llm_errors < 2:
            session.recoverable_llm_errors += 1
            await _trace(
                session,
                "llm_error_recovered",
                role="system",
                metadata={"code": public.code, "attempt": session.recoverable_llm_errors},
            )
            return
        await _trace(session, "pipeline_failed", role="system", metadata={"code": public.code})
        session.fail(public)
        await task.cancel()

    await PipelineRunner(handle_sigint=False).run(task)
