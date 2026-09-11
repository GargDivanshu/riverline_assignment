# Voice error contract

The agent normalizes external failures before they cross the Python API boundary. It never returns provider response bodies, tokens, raw exception messages, audio, or transcripts.

| Condition | Public code pattern | HTTP status | User action |
| --- | --- | --- | --- |
| Missing provider configuration | `voice_not_configured` | 503 | Configure the local environment, then retry. |
| Daily/ElevenLabs/OpenRouter authentication failure | `voice_{provider}_authentication_failed` | 503 | Server operator checks credentials; the user does not retry repeatedly. |
| Provider rate limit | `voice_{provider}_rate_limited` | 429 | Wait briefly, then start a new call. |
| Provider timeout | `voice_{provider}_timeout` | 504 | Start a new call. |
| Provider rejects a request | `voice_{provider}_request_rejected` | 502 | Start a new call; inspect the safe server code if it repeats. |
| Network or provider 5xx failure | `voice_{provider}_unavailable` | 503 | Start a new call. |
| Unclassified pipeline failure | `voice_{provider}_failed` | 502 | Start a new call and use the displayed reference code. |
| Existing/ended/unknown session | `voice_already_active`, `voice_ended`, `voice_session_not_found` | 409/404 | Start or resume the appropriate call. |
| Local capacity reached | `voice_capacity_reached` | 429 | Wait briefly. |
| Invalid payload or missing web-to-agent identity | `invalid_request`, `service_unauthorized`, `user_context_required` | 422/401/400 | This is a web/backend integration error, not a provider message. |

`app.errors` is the single classifier for Daily REST, Pipecat pipeline, ElevenLabs and OpenRouter errors. The FastAPI exception handlers use the same JSON envelope:

```json
{
  "error": {
    "code": "voice_elevenlabs_timeout",
    "message": "A voice service took too long. Start a new call.",
    "retryable": true
  }
}
```

The Next.js tRPC boundary maps that envelope to typed client errors. Browser microphone failures and Daily client events have their own safe messages and always release the local audio object. Failed or ended backend sessions also release the UI so that the user can start again.

Server logs retain only the normalized error code, retryability and exception class. They deliberately omit upstream response bodies and conversation content.
