import test from 'node:test';
import assert from 'node:assert/strict';
import { formatScore } from './score-format.mjs';

test('score display keeps backend precision without rounding up to perfect', () => {
  assert.equal(formatScore(99.99), '99.99');
  assert.equal(formatScore(70.73), '70.73');
  assert.equal(formatScore(100), '100');
  assert.equal(formatScore(0), '0');
});
