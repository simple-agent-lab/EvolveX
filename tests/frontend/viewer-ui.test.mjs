import test from 'node:test';
import assert from 'node:assert/strict';

import {
  compareGenerationIds,
  generationsThrough,
  scoreTrend,
} from '../../src/evolve/viewer/static/viewer-ui.js';

test('generation ordering treats 10 as newer than 2', () => {
  assert.equal(compareGenerationIds('2', '10'), -1);
  assert.deepEqual(
    generationsThrough([{genid: '0'}, {genid: '2'}, {genid: '10'}], '2').map((item) => item.genid),
    ['0', '2'],
  );
});

test('score chart has fixed score ticks and generation labels', () => {
  const html = scoreTrend([
    {genid: '0', score: 0.32},
    {genid: '1', score: 0.28},
    {genid: '10', score: 0.36},
  ], '10');

  assert.match(html, /Canonical score by generation/);
  assert.match(html, />1<.*>0\.5<.*>0</s);
  assert.match(html, />G0<.*>G1<.*>G10</s);
  assert.match(html, /Generation 10: 0\.36/);
  assert.match(html, /trend-dot selected/);
});
