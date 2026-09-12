"""Expose Pipecat's output-speech lifecycle to the owner-scoped session."""

import time
from collections.abc import Callable

from pipecat.frames.frames import BotStartedSpeakingFrame, BotStoppedSpeakingFrame, Frame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


class VoiceActivityProcessor(FrameProcessor):
    def __init__(self, session, *, on_bot_started_speaking: Callable[[], None] | None = None):
        super().__init__(name="VoiceActivityProcessor")
        self.session = session
        self._on_bot_started_speaking = on_bot_started_speaking

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, BotStartedSpeakingFrame):
            self.session.activity = "speaking"
            await self._trace("bot_started_speaking")
            # The transcript-finalized event this used to rely on lags actual speech
            # by several seconds (it can't finalize until the utterance is done), which
            # made a stall watchdog tied to it fire falsely while the bot was already
            # talking. This frame is the real, immediate signal that a response arrived.
            if self._on_bot_started_speaking:
                self._on_bot_started_speaking()
        elif isinstance(frame, BotStoppedSpeakingFrame):
            self.session.activity = "listening"
            await self._trace("bot_stopped_speaking")
            if self.session.opening_is_playing:
                self.session.opening_is_playing = False
                self.session.opening_playback_finished.set()
        await self.push_frame(frame, direction)

    async def _trace(self, event_type: str) -> None:
        store = getattr(self.session, "finance_store", None)
        if not store:
            return
        try:
            await store.record_conversation_event(
                self.session.id,
                event_type,
                role="system",
                elapsed_ms=int((time.monotonic() - self.session.created_monotonic) * 1000),
            )
        except Exception:  # noqa: BLE001 - tracing must not interrupt speech
            return
