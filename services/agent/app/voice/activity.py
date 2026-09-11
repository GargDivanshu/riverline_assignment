"""Expose Pipecat's real output-speech lifecycle to the owner-scoped session."""

from pipecat.frames.frames import BotStartedSpeakingFrame, BotStoppedSpeakingFrame, Frame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


class VoiceActivityProcessor(FrameProcessor):
    def __init__(self, session):
        super().__init__(name="VoiceActivityProcessor")
        self.session = session

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, BotStartedSpeakingFrame):
            self.session.activity = "speaking"
        elif isinstance(frame, BotStoppedSpeakingFrame):
            self.session.activity = "listening"
        await self.push_frame(frame, direction)
