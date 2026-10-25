// Deterministic voice-command grammar. Transcription never directly names arbitrary game actions.

export const ABILITIES = Object.freeze(['bolt', 'ward', 'gather', 'ultimate']);

export const VOICE_KEYWORDS = Object.freeze([
  ...ABILITIES,
  'cast bolt',
  'cast ward',
  'cast gather',
  'cast ultimate',
  'player one',
  'player two',
]);

const PLAYER_SLOT = Object.freeze({ one: 0, '1': 0, two: 1, '2': 1 });

export function normalizeTranscript(transcript) {
  return transcript
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

// Accepted forms: "cast bolt" or "player one cast bolt". Local duels require the
// player prefix at the integration boundary; solo mode can safely default to P1.
export function parseVoiceCommand(transcript) {
  const normalized = normalizeTranscript(transcript);
  const match = /^(?:(?:player|p)\s*(one|two|1|2)\s+)?(?:cast\s+)?(bolt|ward|gather|ultimate)$/.exec(normalized);
  if (!match) return null;
  return {
    slot: match[1] === undefined ? null : PLAYER_SLOT[match[1]],
    ability: match[2],
    transcript: normalized,
  };
}
