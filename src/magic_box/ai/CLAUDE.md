# ai

**Owner:** Nikhil

Spec: `docs/superpowers/specs/2026-10-24-nikhil-pipeline-design.md` section 10. Muse Spark text generation: per-match incantations and the Duel Chronicle. Runs on a worker thread in the game process.

**Status:** implemented against Meta's documented OpenAI-compatible API and tested only with fakes. Not verified live.

## Inputs → Outputs
- In: match context (classes, player names) and the `GameEvent` log; settings from `ai` in `config.yaml`.
- Out: `{slot: {spell_id: incantation}}` for `engine.provide_incantations()`, and a chronicle string for `engine.provide_chronicle()`. The loop submits the jobs when the scene becomes `loading` or `victory` and polls `AiWorker.poll(now)` every tick.

## Hard rules
- Never block the game loop. Calls run on the worker thread; each job has a deadline of `ai.timeout_s` (8 s) and falls back on timeout. `poll` never waits. The engine never waits.
- With `ai.enabled: false` or no key, return the fallbacks immediately (no call).
- Always have a fallback: fixed incantations from `config.yaml` (`fallback` per spell, used per spell when a generated one is rejected), and a template chronicle filled from the event log (2-4 sentences, never raises).
- Incantation validation: 3-7 words (`ai.min_words`/`max_words`), ASCII letters, spaces and apostrophes only, unique within the player's own set. Slot 1 is checked against slot 0's final set with rapidfuzz `ratio` below `ai.max_cross_similarity`.
- Use the OpenAI SDK against `ai.base_url` with `ai.model` (`muse-spark-1.3`). Read the key from the env var named by `ai.api_key_env` (`META_MODEL_API_KEY`). Never hard-code or log it.
- No `pygame`, `pyzed`, `cv2`.

## Files
- `spark_client.py`: `SparkClient`, Muse Spark chat completion over the OpenAI-compatible API; raises `SparkUnavailable`.
- `incantations.py`: `generate_incantations`, `validate_incantations` and `fallback_incantations`.
- `chronicle.py`: `write_chronicle` (Spark) and `template_chronicle` (fallback).
- `worker.py`: `AiWorker` runs jobs on a thread with deadlines (`start_incantations`, `start_chronicle`, `poll`).

## Test without the Jetson
Tests are in `tests/ai/` and use `FakeOpenAI` / `FakeClient` from `tests/ai/fakes.py` (no network). The app runs without the API key because the fallbacks apply:
```
uv run pytest tests/ai
uv run python -m magic_box --fake
```

## Open TODOs
- `TODO(Nikhil)`: verify Spark live on the Jetson (key, `base_url`, model id, latency, that the loading card shows Spark-written incantations and not the config fallback).
- Tune `ai.temperature` and `ai.max_cross_similarity` (both guesses) against real output.
