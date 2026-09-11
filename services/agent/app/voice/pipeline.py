"""One live cascade with constrained tools for persisted financial facts."""

import time
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from loguru import logger
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.frames.frames import TTSSpeakFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.transcript_processor import TranscriptProcessor
from pipecat.services.elevenlabs.stt import ElevenLabsRealtimeSTTService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.services.openrouter.llm import OpenRouterLLMService
from pipecat.transcriptions.language import Language
from pipecat.transports.daily.transport import DailyParams, DailyTransport
from pipecat.turns.user_start import TranscriptionUserTurnStartStrategy
from pipecat.turns.user_stop import SpeechTimeoutUserTurnStopStrategy
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from pydantic import ValidationError

from app.config import Settings
from app.errors import classify_voice_error, log_voice_error
from app.finance import FinancialFactInput
from app.voice.activity import VoiceActivityProcessor

INSTRUCTIONS = """You are Riverline, a calm English-only financial conversation assistant.
You keep a 30-day money view in the workspace while speaking. The record_financial_fact
tool is the only way to add or correct a fact. Call it before acknowledging any clear money
fact. Never invent a number, date, lender, category, or certainty. If an amount, timing, or
which payment the person means is unclear, ask one short clarification instead of using a tool.
Use opening_cash only for money available now; income for money expected to arrive; commitment
for loan EMIs, card bills, BNPL, and money owed to people; expense for usual spending. A debt
balance and its monthly payment are different facts. Expected or owed money is not cash already
available. Mark irregular or not-guaranteed income as estimated or uncertain. Use an ISO date
only when the person gives a clear date or an unambiguous relative date. If no date is known,
leave it out. Call get_financial_snapshot before explaining a plan or resolving a correction.
The tools calculate; do not do arithmetic yourself and only describe numbers returned by them.

The opening greeting already explained the purpose. Once the person agrees, ask the smallest
next question that changes the 30-day plan. Usually learn their immediate goal, then one known
income or payment, its amount and timing. Do not run a fixed questionnaire. Keep one question
per turn and acknowledge corrections naturally. Age, occupation, city and family details are
only useful when the person offers them or they affect their question. Never shame spending,
pressure cuts, recommend new loans, promise approval, invent lender offers, or say a payment was
made. Keep replies brief, conversational and without markdown. Speak only English. For spoken
amounts, use words such as "fifty thousand rupees", never currency symbols or numeric shorthand.
"""

NEW_OPENING = (
    "Hi, I’m Riverline. I can help you understand money coming in, payments due, "
    "and everyday spending. I’ll keep this simple. Are you ready to begin?"
)
RETURNING_OPENING = (
    "Welcome back. We can update your current plan or look at one payment. "
    "What would you like to work on?"
)


def conversation_instruction(mode: str) -> str:
    if mode == "new":
        return """This is an explicit first-time onboarding. The fixed opening has already played.
After the person agrees, do not ask why they came here. Ask exactly: "What do you do for work,
or how does money usually come in for you?" Then learn only the next missing fact that makes the
plan useful: reliable income, irregular income, cash available, a due payment, or a necessary
expense. Explain purpose before asking a question, and never mention a form or survey."""
    return """This is a returning-user conversation. The fixed opening has already played.
Do not repeat onboarding or ask what brought them here. Ask one focused question about the payment,
income, expense, or plan change they want to discuss. Existing financial facts remain their context."""


TOOLS = ToolsSchema(
    standard_tools=[
        FunctionSchema(
            "record_financial_fact",
            "Persist one clearly stated financial fact and recalculate the 30-day view.",
            {
                "category": {
                    "type": "string",
                    "enum": ["opening_cash", "income", "commitment", "expense"],
                },
                "label": {"type": "string", "description": "Short neutral label."},
                "amount_rupees": {"type": "integer", "minimum": 0},
                "due_date": {
                    "type": "string",
                    "description": "ISO date YYYY-MM-DD only when known.",
                },
                "certainty": {
                    "type": "string",
                    "enum": ["confirmed", "estimated", "uncertain", "unknown"],
                },
                "fact_id": {
                    "type": "string",
                    "description": "Existing id only when correcting a fact.",
                },
            },
            ["category", "label", "amount_rupees", "certainty"],
        ),
        FunctionSchema(
            "get_financial_snapshot",
            "Read the persisted facts and deterministic 30-day projection before explaining it.",
            {},
            [],
        ),
    ]
)


def _tool_snapshot(snapshot) -> dict:
    return {
        "revision": snapshot.revision,
        "plan_status": snapshot.plan_status,
        "facts": {
            "income": len(snapshot.income),
            "commitments": len(snapshot.commitments),
            "expenses": len(snapshot.expenses),
            "opening_cash_paise": snapshot.opening_cash_paise,
        },
        "summary": snapshot.summary.model_dump(mode="json"),
        "timeline": [event.model_dump(mode="json") for event in snapshot.timeline],
    }


async def _trace(
    session,
    event_type: str,
    *,
    role: str | None = None,
    content: str | None = None,
    metadata: dict | None = None,
) -> None:
    if not session.finance_store:
        return
    try:
        await session.finance_store.record_conversation_event(
            session.id,
            event_type,
            role=role,
            content=content,
            elapsed_ms=int((time.monotonic() - session.created_monotonic) * 1000),
            metadata=metadata,
        )
    except Exception as error:  # noqa: BLE001 - trace collection must never interrupt audio
        logger.warning(
            "conversation_trace_failed session_id={} error_type={}",
            session.id,
            type(error).__name__,
        )


async def _record_fact(params: FunctionCallParams, session) -> None:
    try:
        arguments = dict(params.arguments)
        arguments["operation_id"] = uuid4()
        snapshot = await session.finance_store.record(
            session.owner, FinancialFactInput.model_validate(arguments)
        )
        logger.info(
            "voice_tool_succeeded session_id={} tool=record_financial_fact revision={}",
            session.id,
            snapshot.revision,
        )
        await _trace(
            session,
            "tool_completed",
            role="tool",
            metadata={"tool": "record_financial_fact", "revision": snapshot.revision},
        )
        await params.result_callback({"ok": True, "workspace": _tool_snapshot(snapshot)})
    except (ValidationError, ValueError) as error:
        fields = (
            [".".join(str(part) for part in item["loc"]) for item in error.errors()]
            if isinstance(error, ValidationError)
            else ["unknown"]
        )
        logger.warning(
            "voice_tool_rejected session_id={} tool=record_financial_fact error_type={} fields={}",
            session.id,
            type(error).__name__,
            fields,
        )
        await _trace(
            session,
            "tool_rejected",
            role="tool",
            metadata={"tool": "record_financial_fact", "fields": fields},
        )
        await params.result_callback(
            {
                "ok": False,
                "error": "The fact was not saved. Ask one short clarification for the missing field; do not retry the same call.",
                "invalid_fields": fields,
            }
        )
    except Exception as error:  # noqa: BLE001 - tool boundary returns a safe result
        logger.error(
            "voice_tool_failed session_id={} tool=record_financial_fact error_type={}",
            session.id,
            type(error).__name__,
        )
        await _trace(
            session, "tool_failed", role="tool", metadata={"tool": "record_financial_fact"}
        )
        await params.result_callback(
            {
                "ok": False,
                "error": "The workspace could not save that fact. Ask the person to try again.",
            }
        )


async def _get_snapshot(params: FunctionCallParams, session) -> None:
    try:
        snapshot = await session.finance_store.workspace(session.owner)
        logger.info(
            "voice_tool_succeeded session_id={} tool=get_financial_snapshot revision={}",
            session.id,
            snapshot.revision,
        )
        await _trace(
            session,
            "tool_completed",
            role="tool",
            metadata={"tool": "get_financial_snapshot", "revision": snapshot.revision},
        )
        await params.result_callback({"ok": True, "workspace": _tool_snapshot(snapshot)})
    except Exception as error:  # noqa: BLE001 - tool boundary returns a safe result
        logger.error(
            "voice_tool_failed session_id={} tool=get_financial_snapshot error_type={}",
            session.id,
            type(error).__name__,
        )
        await _trace(
            session, "tool_failed", role="tool", metadata={"tool": "get_financial_snapshot"}
        )
        await params.result_callback(
            {"ok": False, "error": "The workspace is temporarily unavailable."}
        )


async def run_cascade(session, settings: Settings) -> None:
    logger.info("voice_pipeline_stage session_id={} stage=creating_transport", session.id)
    transport = DailyTransport(
        session.room_url,
        session.bot_token,
        "Riverline",
        DailyParams(audio_in_enabled=True, audio_out_enabled=True, video_out_enabled=False),
    )
    logger.info("voice_pipeline_stage session_id={} stage=creating_stt", session.id)
    stt = ElevenLabsRealtimeSTTService(
        api_key=settings.elevenlabs_api_key,
        settings=ElevenLabsRealtimeSTTService.Settings(
            model=settings.stt_model, language=Language.EN
        ),
    )
    logger.info("voice_pipeline_stage session_id={} stage=creating_llm", session.id)
    llm = OpenRouterLLMService(
        api_key=settings.openrouter_api_key,
        settings=OpenRouterLLMService.Settings(
            model=settings.voice_model,
            max_completion_tokens=180,
        ),
    )
    llm.register_function(
        "record_financial_fact", lambda params: _record_fact(params, session), timeout_secs=8
    )
    llm.register_function(
        "get_financial_snapshot", lambda params: _get_snapshot(params, session), timeout_secs=8
    )
    logger.info("voice_pipeline_stage session_id={} stage=creating_tts", session.id)
    tts = ElevenLabsTTSService(
        api_key=settings.elevenlabs_api_key,
        settings=ElevenLabsTTSService.Settings(
            voice=settings.elevenlabs_voice_id,
            model=settings.tts_model,
        ),
    )
    logger.info("voice_pipeline_stage session_id={} stage=creating_task", session.id)
    context = LLMContext(
        [
            {
                "role": "system",
                "content": f"Today is {datetime.now(ZoneInfo('Asia/Kolkata')).date().isoformat()}.\n{conversation_instruction(session.conversation_mode)}\n{INSTRUCTIONS}",
            }
        ],
        tools=TOOLS,
    )
    user, assistant = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            # ElevenLabs emits final transcript segments reliably in this room,
            # while browser/VAD stop events can remain open on a noisy mic. Make
            # those final segments the source of truth for a complete turn.
            user_turn_strategies=UserTurnStrategies(
                start=[TranscriptionUserTurnStartStrategy(use_interim=False)],
                stop=[SpeechTimeoutUserTurnStopStrategy(user_speech_timeout=0.75)],
            ),
            user_turn_stop_timeout=1.25,
        ),
    )
    transcript = TranscriptProcessor()

    @transcript.event_handler("on_transcript_update")
    async def transcript_update(_processor, frame):
        for message in frame.messages:
            if message.role in {"user", "assistant"} and message.content.strip():
                await _trace(
                    session, "transcript", role=message.role, content=message.content.strip()
                )

    activity = VoiceActivityProcessor(session)
    # Universal aggregation retains context and supports interruption/semantic turn handling.
    task = PipelineTask(
        Pipeline(
            [
                transport.input(),
                stt,
                transcript.user(),
                user,
                llm,
                tts,
                transport.output(),
                activity,
                transcript.assistant(),
                assistant,
            ]
        ),
        params=PipelineParams(audio_in_sample_rate=16000, audio_out_sample_rate=24000),
        enable_rtvi=False,
        # A silent participant is not an error. The session endpoint enforces its
        # own maximum duration, while this keeps an unfinished spoken turn from
        # being terminated after one minute.
        idle_timeout_secs=0,
    )
    session.pipeline = task
    logger.info("voice_pipeline_stage session_id={} stage=running", session.id)

    @transport.event_handler("on_joined")
    async def transport_joined(_transport, _data):
        logger.info("voice_bot_joined session_id={}", session.id)
        await _trace(session, "bot_joined", role="system")

    @transport.event_handler("on_error")
    async def transport_error(_transport, error):
        # The Daily message can contain transport internals; log only its safe classification.
        public = classify_voice_error(source="daily", description=error)
        log_voice_error(public, session_id=session.id)
        await _trace(session, "transport_failed", role="system", metadata={"code": public.code})
        session.fail(public)
        await task.cancel()

    @transport.event_handler("on_transcription_error")
    async def transcription_error(_transport, error):
        # The room remains usable for output, but the event is visible in the same session trace.
        public = classify_voice_error(source="elevenlabs", description=error)
        log_voice_error(public, session_id=session.id)
        await _trace(session, "transcription_failed", role="system", metadata={"code": public.code})

    @transport.event_handler("on_first_participant_joined")
    async def joined(_transport, participant):
        session.status = "active"
        session.activity = "thinking"
        logger.info("voice_participant_joined session_id={}", session.id)
        await _trace(session, "participant_joined", role="system")
        opening = NEW_OPENING if session.conversation_mode == "new" else RETURNING_OPENING
        await task.queue_frames([TTSSpeakFrame(opening, append_to_context=True)])
        logger.info("voice_opening_queued session_id={}", session.id)
        await _trace(session, "opening_queued", role="assistant", content=opening)

    @transport.event_handler("on_participant_left")
    async def left(_transport, participant, reason):
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
        await _trace(session, "pipeline_failed", role="system", metadata={"code": public.code})
        session.fail(public)
        await task.cancel()

    await PipelineRunner(handle_sigint=False).run(task)
