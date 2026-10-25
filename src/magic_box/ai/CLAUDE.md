# ai

**Owner:** Nikhil

Muse Spark text generation: per-match incantations and the Duel Chronicle. Runs on a worker thread in the game process.

## Inputs → Outputs
- In: match context (classes, player names) and the `GameEvent` log; settings from `ai` in `config.yaml`.
- Out: `{slot: {spell_id: incantation}}` for `engine.provide_incantations()`, and a chronicle string for `engine.provide_chronicle()`.

## Hard rules
- Never block the game loop. Calls run on the worker thread with `ai.timeout_s` (8 s); the engine never waits.
- Always have a fallback: fixed incantations from `config.yaml` (`fallback` per spell), and a template chronicle filled from the event log.
- Validate generated incantations for length (3–7 words) and distance from the other player's set.
- Use the OpenAI SDK against `ai.base_url` with `ai.model`. Read the key from the env var named by `ai.api_key_env` (`META_MODEL_API_KEY`). Never hard-code or log it.
- No `pygame`, `pyzed`, `cv2`.

## Files
- `spark_client.py`: Muse Spark chat completion over the OpenAI-compatible API.
- `incantations.py`: generate incantations with Spark, plus the fixed config fallback.
- `chronicle.py`: Spark-written chronicle, plus the template fallback.

## Test without the Jetson
There is no `tests/ai/` yet; create it and test with a fake client (no network). The app runs without the API key because the fallbacks apply:
```
uv run python -m magic_box --fake
```

## Open TODOs
- Confirm Spark `base_url` and model id against current dev.meta.ai documentation.
- Validate generated-incantation quality and the eight-second timeout against the live API.
