#!/usr/bin/env bash
# Demo launcher: runs the game, records every run, restarts it if it crashes.
#
# Usage: scripts/run_demo.sh [--fake] [--windowed] [--no-record] [--dry-run] [-- GAME_ARGS...]
#   --fake       keyboard players and a synthetic camera (laptop test); passed to the game
#   --windowed   do not force fullscreen (fullscreen is the default on the Jetson)
#   --no-record  skip --record
#   --dry-run    print the command that would run, then exit 0
#   -- ...       everything after is passed to `python -m magic_box` unchanged
#
# On the Jetson (aarch64): fullscreen and `--env-file .env` (if .env exists).
# Output: recordings/<timestamp>/ holds the session files and game.log. A restart records
# to recordings/<timestamp>/restart-N. Esc (exit 0) ends the loop; a crash restarts the game,
# at most 5 times per 60 s, then the launcher gives up with the game's last exit code.
# A game exit of 130 or 143 (Ctrl-C, SIGTERM) stops the launcher with that code.
# Env: MAX_RESTARTS (5), RESTART_WINDOW_S (60), RESTART_DELAY_S (1), GAME_CMD (default: uv run).
# Owner: Daniel
set -euo pipefail

# Ctrl-C or SIGTERM stops the launcher; it must never look like a game crash.
trap 'exit 130' INT TERM

cd "$(dirname "$0")/.."

fake=0
windowed=0
record=1
dry=0
extra=()
while [ $# -gt 0 ]; do
  case "$1" in
    --fake) fake=1 ;;
    --windowed) windowed=1 ;;
    --no-record) record=0 ;;
    --dry-run) dry=1 ;;
    -h | --help)
      sed -n '2,16p' "$0"
      exit 0
      ;;
    --)
      shift
      extra=("$@")
      break
      ;;
    *)
      echo "run_demo: unknown argument: $1 (see --help)" >&2
      exit 2
      ;;
  esac
  shift
done

max_restarts="${MAX_RESTARTS:-5}"
window_s="${RESTART_WINDOW_S:-60}"
delay_s="${RESTART_DELAY_S:-1}"
stamp="$(date +%Y%m%d-%H%M%S)"
run_dir="recordings/${stamp}"

# build_cmd <record dir>: fills the global array `cmd`
build_cmd() {
  cmd=()
  if [ -n "${GAME_CMD:-}" ]; then
    # shellcheck disable=SC2206 # intentional word splitting of the override
    cmd=(${GAME_CMD})
  else
    cmd=(uv run)
    if [ "$fake" -eq 0 ] && [ -f .env ]; then
      cmd+=(--env-file .env)
    fi
    cmd+=(python -m magic_box)
  fi
  if [ "$fake" -eq 1 ]; then
    cmd+=(--fake)
  fi
  if [ "$windowed" -eq 0 ] && { [ "$(uname -m)" = "aarch64" ] || [ -f /etc/nv_tegra_release ]; }; then
    cmd+=(--fullscreen)
  fi
  if [ "$record" -eq 1 ]; then
    cmd+=(--record "$1")
  fi
  if [ "${#extra[@]}" -gt 0 ]; then
    cmd+=("${extra[@]}")
  fi
}

if [ "$dry" -eq 1 ]; then
  build_cmd "$run_dir"
  echo "${cmd[*]}"
  exit 0
fi

mkdir -p "$run_dir"
log="${run_dir}/game.log"
echo "run_demo: logging to ${log}" >&2

starts=() # epoch seconds of recent launches
attempt=0
while true; do
  now="$(date +%s)"
  recent=()
  for t in "${starts[@]+"${starts[@]}"}"; do
    if [ $((now - t)) -lt "$window_s" ]; then
      recent+=("$t")
    fi
  done
  starts=("${recent[@]+"${recent[@]}"}")
  if [ "${#starts[@]}" -gt "$max_restarts" ]; then
    echo "run_demo: more than ${max_restarts} restarts in ${window_s}s, giving up" | tee -a "$log" >&2
    exit "${code:-1}"
  fi
  starts+=("$now")

  if [ "$attempt" -eq 0 ]; then
    rec="$run_dir"
  else
    rec="${run_dir}/restart-${attempt}"
  fi
  build_cmd "$rec"
  echo "run_demo: [$(date +%T)] start ${attempt}: ${cmd[*]}" | tee -a "$log" >&2
  set +e
  "${cmd[@]}" 2>&1 | tee -a "$log"
  code="${PIPESTATUS[0]}"
  set -e
  if [ "$code" -eq 130 ] || [ "$code" -eq 143 ]; then
    echo "run_demo: game interrupted (${code}), stopping" | tee -a "$log" >&2
    exit "$code"
  fi
  if [ "$code" -eq 0 ]; then
    echo "run_demo: game exited cleanly" | tee -a "$log" >&2
    exit 0
  fi
  echo "run_demo: [$(date +%T)] game exited with ${code}, restarting" | tee -a "$log" >&2
  attempt=$((attempt + 1))
  sleep "$delay_s"
done
