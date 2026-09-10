# Voice boundary

The foundation exposes an honest unavailable state. It does not create Daily rooms, simulate conversation, or call paid providers.

The next slice will instantiate Pipecat's DailyTransport inside a managed session task:

`Daily input → streaming STT → conversation context + LLM → validated financial tools → TTS → Daily output`

Install the `voice` extra in a Linux environment when implementing this slice. Keep provider choice explicit. Authenticate and authorise session creation through the web application; never expose the Daily API key to the browser. Use short-lived room-scoped participant tokens.

The finance engine and state will remain separate Python modules called by tools. Small RTVI state-change notifications will invalidate the browser's typed workspace query. Pipecat is orchestration, Daily is transport, and neither substitutes for financial calculation or user ownership checks.
