"""One live cascade. No recorded-message STT and no model-owned money arithmetic."""

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
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

INSTRUCTIONS = """You are Riverline, a calm English-only financial conversation assistant.
This is the live conversation milestone: financial calculation and saved plan tools are
not connected yet. Explain that briefly once. Do not calculate totals, claim to save facts
or generate a completed plan. You can understand the user's goal and clarify their inputs.
Ask what brings them here today, unless they already told you. Ask one concise, relevant
question at a time. Never conduct a fixed questionnaire. Remember facts within this call;
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
            model=settings.llm_model,
            max_completion_tokens=800,
            extra={"reasoning": {"effort": "low"}},
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
    # Universal aggregation retains context and supports interruption/semantic turn handling.
    task = PipelineTask(
        Pipeline([transport.input(), stt, user, llm, tts, transport.output(), assistant]),
        params=PipelineParams(audio_in_sample_rate=16000, audio_out_sample_rate=24000),
        enable_rtvi=False,
        idle_timeout_secs=60,
    )
    session.pipeline = task

    @transport.event_handler("on_first_participant_joined")
    async def joined(_transport, participant):
        session.status = "active"
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_participant_left")
    async def left(_transport, participant, reason):
        await task.cancel()

    @task.event_handler("on_pipeline_error")
    async def failed(_task, frame):
        source = getattr(getattr(frame, "processor", None), "name", None)
        public = classify_voice_error(
            getattr(frame, "exception", None), source=source, description=getattr(frame, "error", None)
        )
        log_voice_error(public, getattr(frame, "exception", None))
        session.fail(public)
        await task.cancel()

    await PipelineRunner(handle_sigint=False).run(task)
