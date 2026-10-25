/** Concept-study timeline invariants. Owner: Adetola. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { BEATS, DURATION, sample, smooth } from '../sword-demo-timeline.js';

test('beats cover the sequence continuously with no gaps', () => {
  let end = 0;
  for (const beat of BEATS) {
    assert.equal(beat.start, end);
    assert.ok(beat.duration > 0);
    assert.equal(sample(beat.start).index, BEATS.indexOf(beat));
    end += beat.duration;
  }
  assert.equal(end, DURATION);
});
test('scrubbing clamps to valid beats and progress', () => {
  assert.equal(sample(-4).t, 0);
  assert.equal(sample(DURATION + 10).index, BEATS.length - 1);
  for (let t = -1; t <= DURATION + 1; t += .03) {
    const state = sample(t);
    assert.ok(state.progress >= 0 && state.progress < 1);
  }
});
test('smooth gesture interpolation clamps and has expected midpoint', () => {
  assert.equal(smooth(.2, .8, 0), 0);
  assert.ok(Math.abs(smooth(.2, .8, .5) - .5) < 1e-12);
  assert.equal(smooth(.2, .8, 1), 1);
});
