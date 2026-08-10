import test from 'node:test';
import assert from 'node:assert/strict';

import {
  artifactHref,
  artifactPresentation,
  compareGenerationIds,
  finalResultGeneration,
  generationsThrough,
  scoreTrend,
  snapshotRevision,
  trainScoreChange,
} from '../../src/evolve/viewer/static/viewer-ui.js';

test('generation ordering treats 10 as newer than 2', () => {
  assert.equal(compareGenerationIds('2', '10'), -1);
  assert.deepEqual(
    generationsThrough([{genid: '0'}, {genid: '2'}, {genid: '10'}], '2').map((item) => item.genid),
    ['0', '2'],
  );
});

test('overview final result uses the best eligible canonical generation, not the latest attempt', () => {
  const result = finalResultGeneration([
    {genid: '0', score: 0.58, selection_eligible: true},
    {genid: '4', score: 0.68, selection_eligible: true},
    {genid: '9', score: 0.63, selection_eligible: true},
    {genid: '10', score: null, selection_eligible: false},
  ]);

  assert.equal(result.genid, '4');
});

test('score chart has fixed score ticks and generation labels', () => {
  const html = scoreTrend([
    {genid: '0', score: 0.32},
    {genid: '1', score: 0.28},
    {genid: '10', score: 0.36},
  ], '10');

  assert.match(html, /Canonical score by generation/);
  assert.match(html, /viewBox="0 0 480 180"/);
  assert.match(html, />1<.*>0\.5<.*>0</s);
  assert.match(html, />G0<.*>G1<.*>G10</s);
  assert.match(html, /Generation 10: 0\.36/);
  assert.match(html, /x1="78\.8" x2="78\.8"/);
  assert.match(html, /trend-dot selected/);
  assert.match(html, /class="trend-point" tabindex="0" role="img"/);
  assert.match(html, /<rect class="trend-hit"[^>]+height="136"/);
  assert.match(html, /<line class="trend-guide"/);
  assert.match(html, /class="trend-tooltip"/);
  assert.match(html, />G10: 0\.36</);
});

test('artifact presentation prettifies JSON and selects mature diff rendering', () => {
  assert.deepEqual(
    artifactPresentation({kind: 'json', label: 'result.json'}, '{"score":0.3}'),
    {mode: 'highlight', language: 'json', text: '{\n  "score": 0.3\n}'},
  );
  assert.equal(
    artifactPresentation({kind: 'diff', label: 'model_patch.diff'}, 'diff --git a/a b/a\n').mode,
    'diff',
  );
});

test('malformed JSON falls back to plain text mode', () => {
  assert.deepEqual(
    artifactPresentation({kind: 'json', label: 'broken.json'}, '{oops'),
    {mode: 'plain', language: 'plaintext', text: '{oops'},
  );
});

test('artifact links stay inside the evolve preview', () => {
  assert.equal(artifactHref('abc def'), '/artifacts/abc%20def');
});

test('snapshot revision ignores refresh timestamps but detects experiment changes', () => {
  const first = {experiment: {id: 'run', updated_at: 'first'}, generations: [{genid: '0', score: 0.3}]};
  const refreshed = {experiment: {id: 'run', updated_at: 'second'}, generations: [{genid: '0', score: 0.3}]};
  const changed = {experiment: {id: 'run', updated_at: 'third'}, generations: [{genid: '0', score: 0.4}]};

  assert.equal(snapshotRevision(first), snapshotRevision(refreshed));
  assert.notEqual(snapshotRevision(first), snapshotRevision(changed));
});

test('GEPA train score comparison remains distinct from canonical performance', () => {
  const html = trainScoreChange(29, 34, 5);

  assert.match(html, /Before<\/span><strong>29/);
  assert.match(html, /After<\/span><strong>34/);
  assert.match(html, /\+5/);
  assert.match(html, /GEPA train score changed from 29 to 34/);
});
