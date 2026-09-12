"""Signal that user audio is arriving as soon as STT produces any result.

This used to also decide when a user's turn ended, reimplementing that logic by
hand. It turned out the pipeline was configured with `ExternalUserTurnStrategies`,
which requires an external component to emit UserStartedSpeakingFrame /
UserStoppedSpeakingFrame — frames this processor never sent. The context
aggregator was therefore never told a turn had ended, so it could hold a
transcribed answer out of the LLM's context for an entire extra turn. Turn
detection now uses pipecat's own TranscriptionUserTurnStartStrategy and
SpeechTimeoutUserTurnStopStrategy (see pipeline.py), which speak that protocol
correctly. This processor keeps only the one thing that still needs a session
reference: telling the no-input watchdog that audio has arrived.
"""

from __future__ import annotations

from collections.abc import Callable

from pipecat.frames.frames import Frame, InterimTranscriptionFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


class AudioReceivedSignal(FrameProcessor):
    """Fire a callback on the first interim transcript, then pass every frame through."""

    def __init__(self, *, on_interim: Callable[[], None]):
        super().__init__(name="AudioReceivedSignal")
        self._on_interim = on_interim

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, InterimTranscriptionFrame) and frame.text.strip():
            self._on_interim()
        await self.push_frame(frame, direction)
