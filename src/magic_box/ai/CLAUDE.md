# ai

**Owner:** Nikhil

Spec: `docs/superpowers/specs/2026-10-24-nikhil-pipeline-design.md` section 10. Muse Spark text generation: per-match incantations and the Duel Chronicle. Runs on daemon worker threads in the game process.

**Status:** verified live on 2026-10-25 from a laptop (`scripts/check_spark.py`): chat completions at `https://api.meta.ai/v1`, model `muse-spark-1.3` (the reply reports the same id), `Authorization: Bearer` from the OpenAI SDK. Not yet run on the Jetson's Wi-Fi.

## Inputs → Outputs
- In: match context (classes, player names) and the `GameEvent` log; settings from `ai` in `config.yaml`.
- Out: `{slot: {spell_id: incantation}}` for `engine.provide_incantations()`, and a chronicle string for `engine.provide_chronicle()`. The loop submits the jobs when the scene becomes `loading` or `victory` and polls `AiWorker.poll(now)` every tick.

## AiWorker API (for the loop and `main.py`)
- `start_incantations(classes, names, now)`, `start_chronicle(events, names, now)`: start a job on its own daemon thread (`spark-<kind>`). A new job replaces the pending one of the same kind; the old result is dropped. The two kinds run at once, so a stuck chronicle never delays incantations.
- `poll(now) -> [(kind, result)]`: finished results, or the fallback once `now` passes the job's `ai.timeout_s` deadline. Never waits.
- `close()`: drops every job and returns at once; never waits for a call in flight. Idempotent; afterwards `start_*` do nothing and `poll` returns `[]`. `closed` tells whether it ran.
- **Quit safety:** threads are daemon threads, so the interpreter exits at once even with a Spark call in flight (test: 0.3 s with a 30 s call stuck). The old `ThreadPoolExecutor` worker was joined at exit and held the quit for the whole call (up to 8 s). Calling `close()` is optional for exit; call it anyway on quit.

## Hard rules
- Never block the game loop. Calls run on worker threads; each job has a deadline of `ai.timeout_s` (8 s) and falls back on timeout. `poll` never waits. The engine never waits.
- With `ai.enabled: false` or no key, return the fallbacks immediately (no call).
- Always have a fallback: fixed incantations from `config.yaml` (`fallback` per spell, used per spell when a generated one is rejected), and a template chronicle filled from the event log (2-4 sentences, never raises).
- Incantation validation: 3-7 words (`ai.min_words`/`max_words`), ASCII letters, spaces and apostrophes only, unique within the player's own set. Slot 1 is checked against slot 0's final set with rapidfuzz `ratio` below `ai.max_cross_similarity`. The prompt also asks for common words a speech recognizer spells reliably (no acronyms such as "HackTX") and a different first word per spell.
- **`ai.reasoning_effort: minimal`.** Spark reasons before answering. With the model's default effort the incantation call timed out at 8 s (every match would use the config fallback); `low` took 6.2 s, `minimal` 3.1-3.2 s. `null` omits the field. `none` is rejected (HTTP 400).
- Use the OpenAI SDK against `ai.base_url` with `ai.model` (`muse-spark-1.3`). Read the key from the env var named by `ai.api_key_env` (`META_MODEL_API_KEY`). Never hard-code or log it. Errors are logged as type and HTTP status only (`describe_error`).
- No `pygame`, `pyzed`, `cv2`.

## Live measurements (2026-10-25, laptop Wi-Fi)
| Call | `reasoning_effort` | Latency |
|---|---|---|
| Incantations, 2 players × 3 spells | model default | timed out at 8 s (`APITimeoutError`) |
| Incantations | `low` | 6.2 s (6/6 passed validation) |
| Incantations | `minimal` | 3.1-3.2 s (6/6 passed validation, 3 runs) |
| Chronicle (88 words) | `minimal` | 1.7 s |
| Bad key | - | `AuthenticationError 401` in 0.3 s |

## Files
- `spark_client.py`: `SparkClient`, Muse Spark chat completion over the OpenAI-compatible API (`last_model` is the reply's model id); raises `SparkUnavailable`; `describe_error`.
- `incantations.py`: `generate_incantations`, `validate_incantations` and `fallback_incantations`.
- `chronicle.py`: `write_chronicle` (Spark) and `template_chronicle` (fallback).
- `worker.py`: `AiWorker`, daemon-thread jobs with deadlines.
- `scripts/check_spark.py`: live check. Calls Spark through `generate_incantations` like the game, prints latency, model id and each incantation as `[spark]` or `[fallback]`; `--chronicle`, `--reasoning-effort`, `--classes`, `--names`. Exit 1 on a failed call (type and HTTP status only), 2 with no key.

## Test without the Jetson
Tests are in `tests/ai/` and use `FakeOpenAI` / `FakeClient` from `tests/ai/fakes.py` (no network). The app runs without the API key because the fallbacks apply:
```
uv run pytest tests/ai
uv run python -m magic_box --fake
uv run --env-file .env python scripts/check_spark.py --chronicle     # live
```

## Open TODOs
- `TODO(Nikhil)`: on the Jetson, run `check_spark.py` over the venue Wi-Fi and confirm the loading card shows `[spark]` incantations, not the config fallback (`loading_max_s` is 10 s, the deadline 8 s).
- Tune `ai.temperature` and `ai.max_cross_similarity` (both guesses) against real output. Meta's docs say Spark is tuned for the default temperature (1.0).
