"""One live cascade with constrained tools for persisted financial facts."""

import asyncio
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
from pipecat.services.elevenlabs.stt import CommitStrategy, ElevenLabsRealtimeSTTService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.services.openrouter.llm import OpenRouterLLMService
from pipecat.transcriptions.language import Language
from pipecat.transports.daily.transport import DailyParams, DailyTransport
from pipecat.turns.user_start.transcription_user_turn_start_strategy import (
    TranscriptionUserTurnStartStrategy,
)
from pipecat.turns.user_stop.speech_timeout_user_turn_stop_strategy import (
    SpeechTimeoutUserTurnStopStrategy,
)
from pipecat.turns.user_turn_strategies import UserTurnStrategies
from pydantic import ValidationError

from app.config import Settings
from app.errors import classify_voice_error, log_voice_error
from app.finance import (
    FactNotFoundError,
    FinancialFactInput,
    format_existing_facts,
    shape_validation_errors,
    tool_snapshot,
)
from app.voice.activity import VoiceActivityProcessor
from app.voice.audio_received_signal import AudioReceivedSignal

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
leave it out. If instead they describe something that repeats every month on the same day
(salary on the first, rent on the fifth, an EMI on the tenth), that is not a due_date at all —
use recurring_day_of_month with just the day number, and never ask which month or which year;
"every month" already answers that. Call get_financial_snapshot before explaining a plan or
resolving a correction.
The tools calculate; do not do arithmetic yourself and only describe numbers returned by them.
Every amount the tools return is already in whole rupees. Never mention a projected balance,
shortfall, or any summary figure unless the person asked for the plan or you are explaining it
after they have given you the facts that matter to their immediate question — it is not
something to volunteer while you are still gathering their first one or two facts.

If the person gives a range instead of one number (variable income like "sixty to seventy
thousand"), record it as min_amount_rupees and max_amount_rupees, not a single guessed figure —
never collapse a range to one number on your own. If they say only part of an amount can be
used for this plan (a savings cap they set themselves, like "I have sixty thousand saved but
don't want to use more than fifteen"), record the full amount and set usable_amount_rupees to
their cap. If they say money cannot be used for this plan at all (business cash that is not
personal money), record it with restricted set true — it stays visible but is never treated as
spendable. Never relax a restriction or a usable cap the person stated; only they can change it.
Before calling record_financial_fact, always check the current snapshot for a fact that already
describes the same real-world thing (same label or category and similar amount) — a mobile EMI,
a specific card repayment, a specific fee. If one exists, correct it with its fact_id; only create
a new fact when nothing already represents that same thing. A usable cap or a restriction is a
new detail about money you already recorded, never a new fact: correct the existing fact with
its fact_id, adding min/max, usable_amount_rupees, or restricted onto it. Getting this wrong
creates duplicates of the same obligation, which silently doubles or triples it the moment either
copy gets a due date — this has actually happened and produced a wrong, inflated total. When the
person says something is paid, settled, or no longer applies, correct that exact fact with its
fact_id and set resolved true — never record a new fact with a label like "(paid)" to represent
that; resolved is what removes it from the plan, a new fact does not.
Only call record_financial_fact when the person has stated something new or changed — a plain
question, including one asking you to repeat or clarify what you already have, is answered from
the snapshot you already hold and is never itself a reason to call the tool.
When correcting an existing fact with fact_id, send only the fields that changed; everything
else about it is preserved automatically, so never resupply its amount, category, or date just
to add one new detail like a recurring day or a restriction.

If record_financial_fact comes back rejected, that is a system or technical problem, never a
sign the person's own information was unclear — they already told you correctly. Read the
message in the errors you get back and act only on that specific problem. Never respond to a
rejection by asking the person to repeat an amount, a date, a recurring day, or whether
something repeats monthly — you already have all of that from what they said; asking again
about information already given, especially a second time, is always wrong. "Every month"
already means indefinitely — never ask which month, which year, or how many months for a
recurring fact. If a save still cannot succeed after you have addressed the actual error,
say briefly that it could not be saved this time and move on without repeating the question.
A confirmed monthly total does not mean money is available before every payment date — the
snapshot separates confirmed, dated cash flow from what changes if uncertain money arrives, and
you must keep describing them as separate: never call uncertain money available, and never call
a shortfall solved just because uncertain money might cover it.

The person's own stated question is the goal, not a reason to keep gathering more. The moment
you have enough dated facts to actually answer what they asked you (can I afford this, will I be
short, what should I pay first), call get_financial_snapshot and answer it directly, in one
sentence — do not keep asking for further detail once their real question is answerable. Optional
refinements (a savings buffer, tracking preferences, further categorization) come only after that
answer, and only if the person wants them.

If the person declines, says "I don't know", or clearly wants to move on from something you
asked twice, drop that exact topic entirely — do not rephrase and ask again a third way. Move to
whatever is still needed to answer their actual question, or to explaining the plan.

If the person says they are done, have nothing else to add, or asks you to wrap up, close the
call warmly on that same turn — do not offer "one more thing to double-check" or any other
further question first. A second such signal in the same call is confirmation, not an opening for
another question.

A turn that is a single interjection, a stray sound, or otherwise does not read as a real
statement is likely a mistranscribed noise, not something to act on. Do not record a fact, do not
change the topic, and do not acknowledge it at all — no "no worries" or "no problem" either;
simply continue exactly what you were already doing, as if it had not been transcribed.

The opening greeting already explained the purpose. Once the person agrees, ask the smallest
next question that changes the 30-day plan. Usually learn their immediate goal, then one known
income or payment, its amount and timing. Do not run a fixed questionnaire. Keep one question
per turn and acknowledge corrections naturally. Age, occupation, city and family details are
only useful when the person offers them or they affect their question. Never shame spending,
pressure cuts, recommend new loans, promise approval, invent lender offers, or say a payment was
made. Keep replies brief, conversational and without markdown. Speak only English.

Say every reply in one short sentence, two only when truly necessary. Ask exactly one thing
and stop — do not add unsolicited advice, reassurance, or extra observations after answering.
Use Indian numbering in speech: hundred, thousand, lakh, crore. Never say "million" or
"billion", and for spoken amounts use words such as "fifty thousand rupees", never currency
symbols or numeric shorthand.
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
income, expense, or plan change they want to discuss. Everything already saved is listed below in
this same message — that list is your own memory of them, not something you need to ask the tools
for again or admit you cannot see. Never say you cannot see earlier sessions or an earlier
conversation; you can, it is right here."""


async def existing_facts_context(session) -> str:
    """A deterministic summary of already-saved facts, embedded directly into the
    system prompt for a returning conversation.

    Telling the model "existing facts remain their context" as a bare instruction
    was not enough: confirmed live, it has no visibility into saved data unless it
    independently decides to call get_financial_snapshot first, and it did not —
    it told the person "I can't see earlier chats unless they're part of this
    session" even though the facts were sitting in the same workspace it already
    had tool access to. This removes the model's discretion by putting the actual
    data in front of it before the conversation starts.
    """
    if session.conversation_mode != "returning" or not session.finance_store:
        return ""
    try:
        snapshot = await session.finance_store.workspace(session.owner)
    except Exception:  # noqa: BLE001 - a fetch failure here must not block the call starting
        return ""
    return format_existing_facts(tool_snapshot(snapshot))


TOOLS = ToolsSchema(
    standard_tools=[
        FunctionSchema(
            "record_financial_fact",
            "Persist one clearly stated financial fact and recalculate the 30-day view.",
            {
                "category": {
                    "type": "string",
                    "enum": ["opening_cash", "income", "commitment", "expense"],
                    "description": "Required when creating a new fact. Omit when correcting "
                    "an existing fact via fact_id and the category itself is not changing.",
                },
                "label": {
                    "type": "string",
                    "description": "Short neutral label. Required when creating a new fact. "
                    "Omit when correcting an existing fact via fact_id and the label itself "
                    "is not changing.",
                },
                "amount_rupees": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "The amount, when the person gave one number. Required for "
                    "a brand new fact (omit only if giving min_amount_rupees and "
                    "max_amount_rupees instead). When correcting an existing fact with "
                    "fact_id and only some other detail changed (a recurring day, a "
                    "restriction, marking it paid), omit this entirely — the existing "
                    "amount is kept automatically, you never need to resupply it.",
                },
                "min_amount_rupees": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "Only when the person gave a range (for example 'sixty to "
                    "seventy thousand'). Must be given together with max_amount_rupees.",
                },
                "max_amount_rupees": {"type": "integer", "minimum": 0},
                "usable_amount_rupees": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "Only when the person said only part of this amount can be "
                    "used for this plan (for example savings capped at a limit they set). "
                    "Omit when the full amount is usable.",
                },
                "restricted": {
                    "type": "boolean",
                    "description": "True only when the person said this money cannot be used "
                    "for this plan at all (for example business cash that is not personal "
                    "money). Restricted money is still recorded and shown, never spent in the "
                    "plan. Omit or leave false otherwise.",
                },
                "resolved": {
                    "type": "boolean",
                    "description": "True only when the person said this exact fact is now "
                    "paid, settled, or no longer applies. Requires fact_id — this always "
                    "corrects an existing fact, never creates a new one. A resolved fact is "
                    "excluded from every future snapshot and calculation but stays in "
                    "history. Omit or leave false otherwise.",
                },
                "due_date": {
                    "type": "string",
                    "description": "ISO date YYYY-MM-DD only when this is a single, one-time "
                    "date. Never use this for something that repeats every month (salary, "
                    "rent, an EMI on the same day each month) — use recurring_day_of_month "
                    "for that instead, and omit due_date entirely.",
                },
                "recurring_day_of_month": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 31,
                    "description": "Only when the person describes money that repeats on the "
                    "same calendar day every month (salary on the 1st, rent on the 5th, an "
                    "EMI due the 10th of every month) — the day number only, for example 1 for "
                    "'first of every month'. Never ask which month or year for this: it repeats "
                    "every month by definition. Omit due_date when using this.",
                },
                "certainty": {
                    "type": "string",
                    "enum": ["confirmed", "estimated", "uncertain", "unknown"],
                    "description": "Required when creating a new fact — never guess it, ask if "
                    "unclear. 'uncertain' for money that may or may not arrive (a receivable "
                    "with no confirmed date) — it is tracked but never counted as available "
                    "until confirmed. Use 'estimated' for a real, expected amount that is "
                    "simply approximate or a range, such as variable monthly income. Omit "
                    "when correcting an existing fact via fact_id and certainty itself is not "
                    "changing — it is kept exactly as it was.",
                },
                "fact_id": {
                    "type": "string",
                    "description": "Existing id only when correcting a fact. This makes the "
                    "call a patch: only send the fields that are actually changing, "
                    "everything else about the fact is kept exactly as it was.",
                },
                "timing_note": {
                    "type": "string",
                    "description": "Optional short caveat on top of a date or recurring day "
                    "that is not itself a date, for example 'may arrive as late as the "
                    "2nd'. Never invent one; only record what the person actually said.",
                },
            },
            # Nothing is unconditionally required here: a brand-new fact needs
            # category, label, an amount (or range), and certainty, but a
            # correction (fact_id given) needs only fact_id plus whatever is
            # actually changing — a static schema can't express "required
            # unless correcting", so that split is enforced with a clear,
            # actionable rejection message at the validation layer instead.
            [],
        ),
        FunctionSchema(
            "get_financial_snapshot",
            "Read the persisted facts and deterministic 30-day projection before explaining it.",
            {},
            [],
        ),
    ]
)


# Re-exported for the realtime pipeline and any other caller; the implementation
# lives in app.finance since it is pure data shaping, unrelated to any voice engine.
_tool_snapshot = tool_snapshot


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


async def _warn_if_no_input(session, task: PipelineTask) -> None:
    """Make microphone delivery failure audible rather than leaving a silent call."""
    await session.opening_playback_finished.wait()
    try:
        await asyncio.wait_for(session.user_transcript_received.wait(), timeout=5)
        return
    except TimeoutError:
        logger.warning("voice_no_user_audio_after_opening session_id={}", session.id)
        await _trace(session, "no_user_audio_after_opening", role="system")
        await task.queue_frames(
            [
                TTSSpeakFrame(
                    "I cannot hear your microphone yet. Please check that you are unmuted, then try speaking again.",
                    append_to_context=False,
                )
            ]
        )


class ResponseStallWatchdog:
    """Speak an honest acknowledgement if the model goes quiet for too long.

    A user turn can involve several internal round-trips (record a fact, then
    fetch the snapshot, then finally speak) before anything is heard. Observed
    calls show that chain normally finishes in well under this bound; when the
    model or provider stalls, prior behavior was total silence with no error
    and no indication anything was happening at all.
    """

    def __init__(self, session, task: PipelineTask, *, timeout_secs: float = 15.0):
        self._session = session
        self._task = task
        self._timeout_secs = timeout_secs
        self._pending: asyncio.Task[None] | None = None

    def on_user_turn(self) -> None:
        self._cancel()
        self._pending = asyncio.create_task(self._warn_after_timeout())

    def on_assistant_turn(self) -> None:
        self._cancel()

    def _cancel(self) -> None:
        if self._pending:
            self._pending.cancel()
            self._pending = None

    async def _warn_after_timeout(self) -> None:
        try:
            await asyncio.sleep(self._timeout_secs)
        except asyncio.CancelledError:
            return
        # The call may have ended normally while this was pending; a fallback
        # frame queued into a torn-down pipeline would be a spurious failure.
        if self._session.status not in ("starting", "active"):
            return
        logger.warning("voice_llm_stall session_id={}", self._session.id)
        await _trace(self._session, "llm_stall", role="system")
        try:
            await self._task.queue_frames(
                [
                    TTSSpeakFrame(
                        "Sorry, that is taking longer than it should. I'm still working on it.",
                        append_to_context=False,
                    )
                ]
            )
        except Exception as error:  # noqa: BLE001 - a stale watchdog must never crash the pipeline
            logger.debug(
                "voice_llm_stall_notice_failed session_id={} error_type={}",
                self._session.id,
                type(error).__name__,
            )


async def _record_fact(params: FunctionCallParams, session) -> None:
    try:
        arguments = dict(params.arguments)
        arguments["operation_id"] = uuid4()
        snapshot, fact = await session.finance_store.record(
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
        await params.result_callback(
            {
                "status": "success",
                "revision": snapshot.revision,
                "fact": fact,
                "workspace": _tool_snapshot(snapshot),
            }
        )
    except FactNotFoundError:
        # A named, unambiguous reason distinct from every other rejection: the
        # person and the model both said something coherent, there is simply no
        # such fact_id to correct (stale id, already resolved). Never something
        # for the model to re-ask the person's own information about.
        logger.warning(
            "voice_tool_rejected session_id={} tool=record_financial_fact error_code=fact_not_found",
            session.id,
        )
        await _trace(
            session,
            "tool_rejected",
            role="tool",
            metadata={"tool": "record_financial_fact", "error_code": "fact_not_found"},
        )
        await params.result_callback(
            {
                "status": "rejected",
                "error_code": "fact_not_found",
                "errors": [
                    {
                        "field": "fact_id",
                        "message": "No active financial fact exists with this id. Do not "
                        "ask the person to repeat information they already gave; either "
                        "call get_financial_snapshot to find the right id, or record it "
                        "as a new fact if none of the existing ones match.",
                    }
                ],
            }
        )
    except (ValidationError, ValueError) as error:
        # Every entry always carries a real message; `field` is None only when
        # the problem is not about any single field (a whole-object rule, such
        # as "amount is required for a new fact"). This is the actual fix for
        # the live failure: the model used to receive `invalid_fields: [""]` for
        # exactly this case — no field name and no message — and, with nothing
        # to go on, invented unrelated theories (a year, a three-month window)
        # instead of the real, simple problem.
        errors = shape_validation_errors(error)
        logger.warning(
            "voice_tool_rejected session_id={} tool=record_financial_fact error_type={} errors={}",
            session.id,
            type(error).__name__,
            errors,
        )
        await _trace(
            session,
            "tool_rejected",
            role="tool",
            metadata={
                "tool": "record_financial_fact",
                "fields": [e["field"] for e in errors if e["field"]],
                "messages": [e["message"] for e in errors],
            },
        )
        await params.result_callback(
            {
                "status": "rejected",
                "error_code": "financial_fact_validation_failed",
                "errors": errors,
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
                "status": "rejected",
                "error_code": "internal_error",
                "errors": [
                    {
                        "field": None,
                        "message": "The workspace could not save that fact right now. This "
                        "is a system problem, not missing information — do not ask the "
                        "person to repeat anything; briefly say it could not be saved and "
                        "continue.",
                    }
                ],
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
        await params.result_callback(
            {"status": "success", "revision": snapshot.revision, "workspace": _tool_snapshot(snapshot)}
        )
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
            {
                "status": "rejected",
                "error_code": "internal_error",
                "errors": [{"field": None, "message": "The workspace is temporarily unavailable."}],
            }
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
        # Default commit_strategy is MANUAL: ElevenLabs only finalizes a segment when
        # Pipecat's own VAD sends a stop-speaking frame. This transport has no VAD
        # analyzer configured (a Daily/Pipecat VAD proved unreliable for turn-taking
        # earlier in this project), so nothing ever triggered a commit — every prior
        # call was silently falling back to ElevenLabs' own ~30s safety-net commit.
        # Using ElevenLabs' own server-side VAD instead needs no Pipecat VAD analyzer.
        commit_strategy=CommitStrategy.VAD,
        settings=ElevenLabsRealtimeSTTService.Settings(
            model=settings.stt_model,
            language=Language.EN,
            vad_silence_threshold_secs=0.6,
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
    facts_context = await existing_facts_context(session)
    context = LLMContext(
        [
            {
                "role": "system",
                "content": f"Today is {datetime.now(ZoneInfo('Asia/Kolkata')).date().isoformat()}.\n{conversation_instruction(session.conversation_mode)}\n{INSTRUCTIONS}{facts_context}",
            }
        ],
        tools=TOOLS,
    )
    user, assistant = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            # No VAD analyzer is attached to this transport (unreliable for turn-taking
            # earlier in this project), so turn boundaries come from transcripts alone:
            # a turn starts on the first transcript and ends after a short quiet gap.
            # These are pipecat's own maintained strategies for exactly that case —
            # not reimplemented here — so the context aggregator gets the
            # UserStartedSpeakingFrame/UserStoppedSpeakingFrame it actually expects.
            user_turn_strategies=UserTurnStrategies(
                start=[TranscriptionUserTurnStartStrategy()],
                stop=[SpeechTimeoutUserTurnStopStrategy(user_speech_timeout=0.6)],
            ),
        ),
    )
    transcript = TranscriptProcessor()
    audio_received = AudioReceivedSignal(on_interim=session.user_transcript_received.set)
    # stall_watchdog is assigned below, once `task` exists; the callback only calls it
    # once real speech starts, well after that assignment has happened.
    stall_watchdog: ResponseStallWatchdog | None = None
    activity = VoiceActivityProcessor(
        session, on_bot_started_speaking=lambda: stall_watchdog and stall_watchdog.on_assistant_turn()
    )
    # Universal aggregation retains context and supports interruption/semantic turn handling.
    task = PipelineTask(
        Pipeline(
            [
                transport.input(),
                stt,
                transcript.user(),
                audio_received,
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

    stall_watchdog = ResponseStallWatchdog(session, task)

    @transcript.event_handler("on_transcript_update")
    async def transcript_update(_processor, frame):
        for message in frame.messages:
            if message.role in {"user", "assistant"} and message.content.strip():
                if message.role == "user":
                    session.user_transcript_received.set()
                    stall_watchdog.on_user_turn()
                await _trace(
                    session, "transcript", role=message.role, content=message.content.strip()
                )

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
        session.opening_is_playing = True
        await task.queue_frames([TTSSpeakFrame(opening, append_to_context=True)])
        logger.info("voice_opening_queued session_id={}", session.id)
        await _trace(session, "opening_queued", role="assistant", content=opening)
        asyncio.create_task(_warn_if_no_input(session, task))

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
        # A malformed or truncated LLM stream chunk is a provider hiccup, not a reason
        # to end a financial-planning conversation over one bad response. Recover a
        # bounded number of times; a provider that keeps failing still ends the call.
        is_llm_hiccup = public.code.startswith("voice_openrouter_") and public.retryable
        if is_llm_hiccup and session.recoverable_llm_errors < 2:
            session.recoverable_llm_errors += 1
            await _trace(
                session,
                "llm_error_recovered",
                role="system",
                metadata={"code": public.code, "attempt": session.recoverable_llm_errors},
            )
            await task.queue_frames(
                [
                    TTSSpeakFrame(
                        "Sorry, I lost my train of thought there. Could you say that again?",
                        append_to_context=False,
                    )
                ]
            )
            return
        await _trace(session, "pipeline_failed", role="system", metadata={"code": public.code})
        session.fail(public)
        await task.cancel()

    await PipelineRunner(handle_sigint=False).run(task)
