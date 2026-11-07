import assert from 'node:assert/strict';
import { test } from 'node:test';
import { Player } from '../../app/player.js';

test('master gain tracks cumulative modulation below the per-frame deadband', () => {
  const targets = [];
  const gain = { value: 1, setTargetAtTime(target) { targets.push(target); } };
  const player = Object.create(Player.prototype);
  player.audio = { ctx: { currentTime: 0 }, master: { gain }, lastLimiter: 'off' };
  player.panels = [];
  player.eff = { 'audio.master': 0 };
  player._audioPass();
  assert.equal(gain.value, 0);

  for (const value of [0.00005, 0.00009, 0.00014]) {
    player.eff['audio.master'] = value;
    player._audioPass();
  }
  assert.deepEqual(targets, [0.00014]);
});
