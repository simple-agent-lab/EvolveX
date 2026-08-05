const escapeSvg = (value) => String(value ?? '')
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;')
  .replaceAll("'", '&#039;');

function generationKey(value) {
  const text = String(value);
  const [head, suffix = '0'] = text.split('-', 2);
  const leading = head.match(/^\d+/);
  return [leading ? Number(leading[0]) : -1, /^\d+$/.test(suffix) ? Number(suffix) : 0, text];
}

export function compareGenerationIds(left, right) {
  const a = generationKey(left);
  const b = generationKey(right);
  return Math.sign(a[0] - b[0] || a[1] - b[1] || a[2].localeCompare(b[2]));
}

export function generationsThrough(generations, selectedId) {
  return generations.filter((item) => compareGenerationIds(item.genid, selectedId) <= 0);
}

export function artifactPresentation(metadata, text) {
  const kind = String(metadata.kind || '').toLowerCase();
  if (kind === 'diff' || kind === 'patch') return {mode: 'diff', language: 'diff', text};
  if (kind === 'json') {
    try {
      return {mode: 'highlight', language: 'json', text: JSON.stringify(JSON.parse(text), null, 2)};
    } catch {
      return {mode: 'plain', language: 'plaintext', text};
    }
  }
  const language = {
    yaml: 'yaml',
    yml: 'yaml',
    py: 'python',
    sh: 'bash',
    js: 'javascript',
    md: 'markdown',
  }[kind];
  return language
    ? {mode: 'highlight', language, text}
    : {mode: 'plain', language: 'plaintext', text};
}

export function scoreTrend(generations, selectedId = null) {
  const points = generations
    .filter((item) => item.score != null)
    .toSorted((a, b) => compareGenerationIds(a.genid, b.genid));
  if (!points.length) return '<div class="empty">No scored generations yet.</div>';

  const width = Math.max(480, points.length * 52);
  const height = 180;
  const left = 36;
  const right = 16;
  const top = 14;
  const bottom = 30;
  const x = (index) => points.length === 1
    ? (left + width - right) / 2
    : left + index * (width - left - right) / (points.length - 1);
  const y = (score) => top
    + (1 - Math.max(0, Math.min(1, Number(score)))) * (height - top - bottom);
  const ticks = [[1, top], [0.5, y(0.5)], [0, height - bottom]];
  const coordinates = points.map((item, index) => `${x(index)},${y(item.score)}`).join(' ');

  return `<div class="trend-scroll"><svg class="trend" viewBox="0 0 ${width} ${height}" role="img" aria-label="Canonical score by generation">
    ${ticks.map(([tick, cy]) => `<line class="trend-grid" x1="${left}" x2="${width - right}" y1="${cy}" y2="${cy}"/><text class="trend-axis-label" x="${left - 7}" y="${cy + 3}">${tick}</text>`).join('')}
    <polyline class="trend-line" points="${coordinates}"/>
    ${points.map((item, index) => {
      const genid = escapeSvg(item.genid);
      const score = escapeSvg(item.score);
      const selected = String(item.genid) === String(selectedId) ? ' selected' : '';
      return `<g><circle class="trend-dot${selected}" cx="${x(index)}" cy="${y(item.score)}" r="4" aria-label="Generation ${genid}: ${score}"><title>Generation ${genid}: ${score}</title></circle><text class="trend-x-label" x="${x(index)}" y="${height - 9}">G${genid}</text></g>`;
    }).join('')}
  </svg></div>`;
}
