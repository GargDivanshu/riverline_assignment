"""One live cascade. No recorded-message STT and no model-owned money arithmetic."""

from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import TTSSpeakFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.services.elevenlabs.stt import ElevenLabsRealtimeSTTService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.openrouter.llm import OpenRouterLLMService
from pipecat.transcriptions.language import Language
from pipecat.transports.daily.transport import DailyParams, DailyTransport

from app.config import Settings
from app.errors import classify_voice_error, log_voice_error
from app.voice.activity import VoiceActivityProcessor

INSTRUCTIONS = """You are Riverline, a calm English-only financial conversation assistant.
This is the live conversation milestone: financial calculation and saved plan tools are
not connected yet. Explain that briefly once. Do not calculate totals, claim to save facts
or generate a completed plan. You can understand the user's goal and clarify their inputs.
On your first turn, warmly explain in one sentence that you can map what is coming in,
what is due, and what needs attention over the next 30 days. Then invite the person to
start wherever feels easiest: income, a payment, or something urgent. Do not open with
"what brings you here". After that, ask one concise, relevant question at a time. Never
conduct a fixed questionnaire. Remember facts within this call;
do not ask again just to fill a template. Repetition is not a new income or debt.
Let the user hesitate, restart and correct themselves. Acknowledge clear corrections;
clarify ambiguous amounts or which debt they refer to. Never guess missing amounts/dates.
Distinguish cash already available from money owed or expected; ask about timing and
reliability when it changes their immediate concern. Separate debt balance from instalments,
and business revenue from money available personally. Ask about responsibilities and
protected spending when relevant. Age, occupation and city are not mandatory intake fields.
Never shame spending, pressure cuts, recommend new loans, promise approval, invent lender
offers or say a payment was made. Keep replies brief and conversational, without markdown.
Speak only English, even if asked to switch languages. If unsure, say what needs clarification.
"""

OPENING = (
    "Hi, I’ll help you get a clear 30-day view of three things: money coming in, "
    "payments you owe, and everyday spending. I’ll ask a few short questions and make "
    "the plan as we go. Are you ready to start?"
)


async def run_cascade(session, settings: Settings) -> None:
    transport = DailyTransport(
        session.room_url,
        session.bot_token,
        "Riverline",
        DailyParams(audio_in_enabled=True, audio_out_enabled=True, video_out_enabled=False),
    )
    stt = ElevenLabsRealtimeSTTService(
        api_key=settings.elevenlabs_api_key,
        settings=ElevenLabsRealtimeSTTService.Settings(
            model=settings.stt_model, language=Language.EN
        ),
    )
    llm = OpenRouterLLMService(
        api_key=settings.openrouter_api_key,
        settings=OpenRouterLLMService.Settings(
            model=settings.voice_model,
            max_completion_tokens=180,
        ),
    )
    tts = ElevenLabsTTSService(
        api_key=settings.elevenlabs_api_key,
        settings=ElevenLabsTTSService.Settings(
            voice=settings.elevenlabs_voice_id,
            model=settings.tts_model,
        ),
    )
    context = LLMContext([{"role": "system", "content": INSTRUCTIONS}])
    user, assistant = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )
    activity = VoiceActivityProcessor(session)
    # Universal aggregation retains context and supports interruption/semantic turn handling.
    task = PipelineTask(
        Pipeline([transport.input(), stt, user, llm, tts, transport.output(), activity, assistant]),
        params=PipelineParams(audio_in_sample_rate=16000, audio_out_sample_rate=24000),
        enable_rtvi=False,
        idle_timeout_secs=60,
    )
    session.pipeline = task

    @transport.event_handler("on_first_participant_joined")
    async def joined(_transport, participant):
        session.status = "active"
        session.activity = "thinking"
        logger.info("voice_participant_joined session_id={}", session.id)
        await task.queue_frames([TTSSpeakFrame(OPENING, append_to_context=True)])
        logger.info("voice_opening_queued session_id={}", session.id)

    @transport.event_handler("on_participant_left")
    async def left(_transport, participant, reason):
        logger.info("voice_participant_left session_id={}", session.id)
        await task.cancel()

    @task.event_handler("on_pipeline_error")
    async def failed(_task, frame):
        source = getattr(getattr(frame, "processor", None), "name", None)
        public = classify_voice_error(
            getattr(frame, "exception", None), source=source, description=getattr(frame, "error", None)
        )
        log_voice_error(public, getattr(frame, "exception", None), session_id=session.id)
        session.fail(public)
        await task.cancel()

    await PipelineRunner(handle_sigint=False).run(task)
