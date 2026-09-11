"""Convert final STT segments into a bounded, deterministic model turn."""

from __future__ import annotations

import asyncio

from pipecat.frames.frames import Frame, LLMRunFrame, TranscriptionFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


class TranscriptTurnGate(FrameProcessor):
    """Run the LLM after a short gap between final transcription segments.

    STT is the reliable endpointing source in this cascade. Browser microphone
    VAD can remain open indefinitely, which must not leave a user waiting for a
    model response after a completed transcription.
    """

    def __init__(self, *, silence_secs: float = 0.75):
        super().__init__(name="TranscriptTurnGate")
        self._silence_secs = silence_secs
        self._task: asyncio.Task[None] | None = None

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, TranscriptionFrame) and frame.text.strip():
            if self._task:
                self._task.cancel()
            self._task = asyncio.create_task(self._run_after_silence())
        await self.push_frame(frame, direction)

    async def cleanup(self):
        if self._task:
            self._task.cancel()
            self._task = None
        await super().cleanup()

    async def _run_after_silence(self) -> None:
        try:
            await asyncio.sleep(self._silence_secs)
        except asyncio.CancelledError:
            return
        await self.push_frame(LLMRunFrame(), FrameDirection.DOWNSTREAM)
