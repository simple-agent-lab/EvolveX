import {
  artifactHref,
  artifactPresentation,
  finalResultGeneration,
  generationsThrough,
  scoreTrend,
  snapshotRevision,
  trainScoreChange,
} from './viewer-ui.js';

const state = { snapshot: null, revision: '', timer: null, refreshing: false, artifactCache: new Map() };
const content = document.querySelector('#viewer-content');
const experimentName = document.querySelector('#experiment-name');
const healthPill = document.querySelector('#health-pill');
const refreshStatus = document.querySelector('#refresh-status');

const escapeHtml = (value) => String(value ?? '')
  .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;').replaceAll("'", '&#039;');
const label = (value) => String(value ?? 'unknown').replaceAll('_', ' ');
const number = (value, digits = 3) => value == null ? '—' : Number(value).toFixed(digits).replace(/\.?0+$/, '');
const time = (value) => value ? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : 'No activity recorded';
const compactTime = (value) => value ? new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' }).format(
  Math.round((new Date(value).getTime() - Date.now()) / 60000), 'minute'
) : 'unknown';
const badge = (value) => `<span class="badge ${escapeHtml(value || 'unknown')}">${escapeHtml(label(value))}</span>`;

async function getJson(url) {
  const response = await fetch(url, { cache: 'no-store' });
  if (!response.ok) throw new Error(`${url} returned ${response.status}`);
  return response.json();
}

async function refresh() {
  if (state.refreshing) return;
  state.refreshing = true;
  refreshStatus.textContent = 'Refreshing…';
  try {
    const nextSnapshot = await getJson('/api/evolve/snapshot');
    const nextRevision = snapshotRevision(nextSnapshot);
    const shouldRender = state.snapshot == null || nextRevision !== state.revision;
    const viewState = shouldRender && state.snapshot != null ? captureViewState() : null;
    state.snapshot = nextSnapshot;
    state.revision = nextRevision;
    updateChrome();
    if (shouldRender) {
      await renderRoute(window.location.pathname, new URLSearchParams(window.location.search));
      restoreViewState(viewState);
    }
    refreshStatus.textContent = `Updated ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`;
  } catch (error) {
    refreshStatus.textContent = 'Refresh failed';
    if (!state.snapshot) {
      content.innerHTML = `<div class="error-card"><strong>Could not read this experiment.</strong><p>${escapeHtml(error.message)}</p></div>`;
    }
  } finally {
    state.refreshing = false;
  }
}

function captureViewState() {
  const controls = [...content.querySelectorAll('input[id], select[id], textarea[id]')].map((control) => ({
    id: control.id,
    value: control.value,
    checked: 'checked' in control ? control.checked : null,
  }));
  const scrollers = [...content.querySelectorAll('.trend-scroll, .table-wrap, .artifact-preview')].map((element) => ({
    left: element.scrollLeft,
    top: element.scrollTop,
  }));
  return {
    route: `${window.location.pathname}${window.location.search}`,
    controls,
    scrollers,
    windowX: window.scrollX,
    windowY: window.scrollY,
    focusedId: content.contains(document.activeElement) ? document.activeElement.id : null,
    artifactWrap: document.querySelector('#artifact-preview')?.classList.contains('wrap') || false,
    performancePages: [...content.querySelectorAll('[data-performance-card]')].map((card) => Number(card.dataset.page) || 1),
  };
}

function restoreViewState(saved) {
  if (!saved || saved.route !== `${window.location.pathname}${window.location.search}`) return;
  for (const item of saved.controls) {
    const control = document.getElementById(item.id);
    if (!control) continue;
    control.value = item.value;
    if (item.checked != null && 'checked' in control) control.checked = item.checked;
  }
  [...content.querySelectorAll('.trend-scroll, .table-wrap, .artifact-preview')].forEach((element, index) => {
    const position = saved.scrollers[index];
    if (!position) return;
    element.scrollLeft = position.left;
    element.scrollTop = position.top;
  });
  if (saved.artifactWrap) {
    const preview = document.querySelector('#artifact-preview');
    const button = document.querySelector('#artifact-wrap');
    preview?.classList.add('wrap');
    preview?.classList.remove('no-wrap');
    button?.setAttribute('aria-pressed', 'true');
    if (button) button.textContent = 'Do not wrap';
  }
  content.querySelectorAll('[data-performance-card]').forEach((card, index) => {
    setPerformancePage(card, saved.performancePages[index] || 1);
  });
  document.getElementById(saved.focusedId)?.focus({preventScroll: true});
  window.scrollTo(saved.windowX, saved.windowY);
}

function updateChrome() {
  const experiment = state.snapshot.experiment;
  experimentName.textContent = experiment.id;
  experimentName.title = experiment.workspace;
  healthPill.className = `status-pill ${experiment.health}`;
  healthPill.textContent = label(experiment.health);
  document.title = `${experiment.id} · Evolve`;
}

function activateNavigation(name) {
  document.querySelectorAll('[data-nav]').forEach((link) => {
    link.classList.toggle('active', link.dataset.nav === name);
    if (link.dataset.nav === name) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });
}

async function renderRoute(pathname, params) {
  if (!state.snapshot) return;
  if (pathname.startsWith('/artifacts/')) {
    activateNavigation(null);
    await renderArtifact(decodeURIComponent(pathname.slice('/artifacts/'.length)));
  } else if (pathname === '/trials') {
    activateNavigation('trials');
    await renderTrials(params);
  } else if (pathname === '/generations') {
    activateNavigation('generations');
    renderGenerations();
  } else if (pathname.startsWith('/generations/')) {
    activateNavigation('generations');
    await renderGeneration(decodeURIComponent(pathname.slice('/generations/'.length)));
  } else {
    activateNavigation('overview');
    await renderOverview();
  }
}

async function renderOverview() {
  const snapshot = state.snapshot;
  const experiment = snapshot.experiment;
  const finalResult = finalResultGeneration(snapshot.generations);
  const finalResultId = finalResult?.genid || null;
  const finalDetail = finalResultId
    ? await getJson(`/api/evolve/generations/${encodeURIComponent(finalResultId)}`)
    : null;
  const recent = snapshot.generations.slice(-6).reverse();
  content.innerHTML = `
    <div class="page-heading">
      <div><h2>Experiment overview</h2><p>Global final result, experiment health, and generation history.</p></div>
      ${finalResultId ? `<a class="button" data-evolve-link href="/generations/${encodeURIComponent(finalResultId)}">Open champion agent · G${escapeHtml(finalResultId)}</a>` : ''}
    </div>
    <div class="stack">
      ${healthCard(experiment, finalDetail, true)}
      <div class="grid-two">
        ${overviewPlaceholderCard()}
        ${performanceCard(finalDetail, snapshot.generations, true)}
      </div>
      ${generationTable(recent, 'Recent generations')}
    </div>`;
  bindPerformancePagers();
}

function overviewPlaceholderCard() {
  return '<section class="card overview-placeholder" aria-label="Reserved overview panel"></section>';
}

function healthCard(experiment, detail, globalResult = false) {
  const stages = detail?.stages || [];
  const warnings = experiment.warnings || [];
  const displayGeneration = globalResult ? detail?.summary?.genid : experiment.focus_generation;
  const displayHealth = globalResult ? detail?.summary?.status || 'unknown' : experiment.health;
  const description = globalResult
    ? 'Global champion from canonical evaluation'
    : experiment.current_stage ? `Current stage: ${label(experiment.current_stage)}` : time(experiment.last_activity_at);
  return `<section class="card health-card">
    <div class="health-banner">
      <div>
        <span class="status-pill ${escapeHtml(displayHealth)}">${escapeHtml(label(displayHealth))}</span>
        <h2>${displayGeneration ? `${globalResult ? 'Champion agent · ' : ''}Generation ${escapeHtml(displayGeneration)}` : 'Waiting for the first generation'}</h2>
        <p>${escapeHtml(description)}</p>
      </div>
      <div class="metric-big"><strong>${number(experiment.best_score)}</strong><span>Best canonical score</span></div>
    </div>
    ${stages.length ? `<div class="stage-strip" aria-label="Generation stages">${stages.map(stageItem).join('')}</div>` : ''}
    ${warnings.length ? `<ul class="warning-list">${warnings.map((warning) => `<li><strong>${escapeHtml(label(warning.code))}:</strong> ${escapeHtml(warning.message)}</li>`).join('')}</ul>` : ''}
  </section>`;
}

function stageItem(stage) {
  const progress = stage.progress_completed != null
    ? `${stage.progress_completed}${stage.progress_total != null ? ` / ${stage.progress_total}` : ''}` : label(stage.state);
  return `<div class="stage ${escapeHtml(stage.state)}"><strong>${escapeHtml(label(stage.name))}</strong>${escapeHtml(progress)}</div>`;
}

function changeCard(detail) {
  const change = detail?.change;
  if (!change || (!change.rationale && !change.changed_paths.length)) {
    return `<section class="card"><div class="card-header"><div><h3>Latest modification</h3><p>Why the candidate changed</p></div></div><div class="empty"><strong>No modification evidence</strong>Artifacts will appear after the modify stage.</div></section>`;
  }
  return `<section class="card">
    <div class="card-header"><div><h3>Latest modification</h3><p>Generation ${escapeHtml(detail.summary.genid)} from parent ${escapeHtml(detail.summary.parent || '—')}</p></div><div class="diff-stat"><span class="plus">+${change.insertions}</span><span class="minus">−${change.deletions}</span></div></div>
    <p class="change-rationale">${escapeHtml(change.rationale || 'No rationale was recorded.')}</p>
    <ul class="file-list">${change.changed_paths.slice(0, 8).map((path) => `<li><span>${escapeHtml(path)}</span></li>`).join('')}</ul>
    ${change.patch_artifact_id ? `<p><a class="button" data-evolve-link href="${artifactHref(change.patch_artifact_id)}">View formatted diff</a></p>` : ''}
  </section>`;
}

function performanceCard(detail, generations, globalResult = false) {
  const performance = detail?.performance || {};
  const delta = performance.delta;
  const hasTrainScore = performance.train_score_before != null && performance.train_score_after != null;
  const canonicalSubtitle = globalResult
    ? `Global champion · Generation ${escapeHtml(detail?.summary?.genid || '—')}`
    : 'Canonical evaluation only';
  return `<section class="card performance-card" data-performance-card data-page="1">
    <div class="card-header"><div><h3>${globalResult ? 'Final performance' : 'Performance'}</h3><p data-performance-subtitle data-canonical-label="${canonicalSubtitle}">${canonicalSubtitle}</p></div><div class="performance-header-actions">${performance.contract_certified == null ? '' : badge(performance.contract_certified ? 'certified' : 'uncertified')}${hasTrainScore ? '<div class="performance-pager" aria-label="Performance pages"><button class="performance-page-button" type="button" data-performance-previous aria-label="Previous performance page" disabled>‹</button><span><strong data-performance-page-number>1</strong> / 2</span><button class="performance-page-button" type="button" data-performance-next aria-label="Next performance page">›</button></div>' : ''}</div></div>
    <div data-performance-page="1">
      <div class="score-value">${number(performance.score)}${delta == null ? '' : `<span class="score-delta ${delta >= 0 ? 'plus' : 'minus'}">${delta >= 0 ? '+' : ''}${number(delta)}</span>`}</div>
      ${scoreTrend(generations, detail?.summary?.genid)}
      <div class="legend"><span><strong>${performance.observed_trials ?? '—'}</strong> observed trials</span><span><strong>${performance.expected_trials ?? '—'}</strong> expected</span><span>${performance.comparable ? 'Parent delta comparable' : 'Parent delta not comparable'}</span></div>
    </div>
    ${hasTrainScore ? `<div data-performance-page="2" hidden>
      ${trainScoreChange(performance.train_score_before, performance.train_score_after, performance.train_delta)}
      <div class="train-score-note"><strong>GEPA validation minibatch</strong><span>This train comparison decides whether the proposal proceeds to canonical evaluation.</span></div>
    </div>` : ''}
  </section>`;
}

function setPerformancePage(card, page) {
  const selected = Math.max(1, Math.min(2, Number(page) || 1));
  card.dataset.page = String(selected);
  card.querySelectorAll('[data-performance-page]').forEach((panel) => {
    panel.hidden = Number(panel.dataset.performancePage) !== selected;
  });
  const numberLabel = card.querySelector('[data-performance-page-number]');
  const subtitle = card.querySelector('[data-performance-subtitle]');
  if (numberLabel) numberLabel.textContent = String(selected);
  if (subtitle) subtitle.textContent = selected === 1 ? subtitle.dataset.canonicalLabel : 'GEPA train score change';
  const previous = card.querySelector('[data-performance-previous]');
  const next = card.querySelector('[data-performance-next]');
  if (previous) previous.disabled = selected === 1;
  if (next) next.disabled = selected === 2;
}

function bindPerformancePagers() {
  document.querySelectorAll('[data-performance-card]').forEach((card) => {
    card.querySelector('[data-performance-previous]')?.addEventListener('click', () => setPerformancePage(card, 1));
    card.querySelector('[data-performance-next]')?.addEventListener('click', () => setPerformancePage(card, 2));
  });
}

function renderGenerations() {
  const generations = [...state.snapshot.generations].reverse();
  content.innerHTML = `<div class="page-heading"><div><h2>Generations</h2><p>${generations.length} recorded candidates and baselines.</p></div><div class="page-actions"><a class="button" href="/" data-evolve-link>← Overview</a></div></div>${generationTable(generations, null)}`;
}

function generationTable(generations, title) {
  return `<section class="card">
    ${title ? `<div class="card-header"><div><h3>${escapeHtml(title)}</h3><p>Newest first</p></div><a class="button" href="/generations" data-evolve-link>View all</a></div>` : ''}
    ${generations.length ? `<div class="table-wrap"><table><thead><tr><th>Generation</th><th>Status</th><th>Current stage</th><th class="numeric">Score</th><th class="numeric">Files</th><th class="numeric">Diff</th></tr></thead><tbody>${generations.map((generation) => `<tr>
      <td><a class="row-link" data-evolve-link href="/generations/${encodeURIComponent(generation.genid)}">Generation ${escapeHtml(generation.genid)}</a><div class="subtle">Parent ${escapeHtml(generation.parent || '—')}</div></td>
      <td>${badge(generation.status)}</td><td>${escapeHtml(label(generation.current_stage || 'finished'))}</td><td class="numeric">${number(generation.score)}</td><td class="numeric">${generation.change_files}</td><td class="numeric"><span class="plus">+${generation.insertions}</span> <span class="minus">−${generation.deletions}</span></td>
    </tr>`).join('')}</tbody></table></div>` : '<div class="empty"><strong>No generations yet</strong>The viewer will update when archive rows appear.</div>'}
  </section>`;
}

async function renderGeneration(genid) {
  let detail;
  try { detail = await getJson(`/api/evolve/generations/${encodeURIComponent(genid)}`); }
  catch (error) { content.innerHTML = `<div class="error-card"><strong>Generation not found.</strong><p>${escapeHtml(error.message)}</p><p><a class="button" data-evolve-link href="/generations">← Generations</a></p></div>`; return; }
  const summary = detail.summary;
  content.innerHTML = `
    <div class="page-heading"><div><p class="eyebrow">Generation detail</p><h2>Generation ${escapeHtml(summary.genid)}</h2><div class="detail-meta"><span>Status ${badge(summary.status)}</span><span>Parent <strong>${escapeHtml(summary.parent || '—')}</strong></span><span>Score <strong>${number(summary.score)}</strong></span></div></div><div class="page-actions"><a class="button" data-evolve-link href="/generations">← Generations</a><a class="button" data-evolve-link href="/trials?generation=${encodeURIComponent(summary.genid)}">View trials</a></div></div>
    <div class="stack">
      <section class="card"><div class="card-header"><div><h3>Stage progress</h3><p>Evidence inferred from this generation's artifacts</p></div></div><div class="stage-strip">${detail.stages.map(stageItem).join('')}</div></section>
      <div class="grid-two">${changeCard(detail)}${performanceCard(detail, generationsThrough(state.snapshot.generations, summary.genid))}</div>
      ${artifactCard(detail.artifacts)}
    </div>`;
  bindPerformancePagers();
}

function artifactCard(artifacts) {
  return `<section class="card"><div class="card-header"><div><h3>Artifacts</h3><p>Registered stage and evaluation evidence</p></div><span class="muted">${artifacts.length} files</span></div>
    ${artifacts.length ? `<ul class="artifact-list">${artifacts.map((artifact) => `<li><a ${artifact.previewable ? `href="${artifactHref(artifact.id)}" data-evolve-link` : ''}><span>${escapeHtml(artifact.relative_path)}</span><span class="subtle">${formatBytes(artifact.size)}</span></a></li>`).join('')}</ul>` : '<div class="empty">No registered artifacts for this generation.</div>'}
  </section>`;
}

async function loadArtifact(artifactId) {
  const cached = state.artifactCache.get(artifactId);
  if (cached) return cached;
  const metadata = await getJson(`/api/evolve/artifacts/${encodeURIComponent(artifactId)}/metadata`);
  const response = await fetch(metadata.content_url, {cache: 'no-store'});
  if (!response.ok) throw new Error(`${metadata.content_url} returned ${response.status}`);
  const loaded = {metadata, text: await response.text()};
  state.artifactCache.set(artifactId, loaded);
  return loaded;
}

async function renderArtifact(artifactId) {
  content.innerHTML = '<section class="loading-card" aria-busy="true"><span class="spinner" aria-hidden="true"></span><div><strong>Loading artifact</strong><p>Reading the bounded preview.</p></div></section>';
  let loaded;
  try {
    loaded = await loadArtifact(artifactId);
  } catch (error) {
    content.innerHTML = `<div class="error-card"><strong>Could not read this artifact.</strong><p>${escapeHtml(error.message)}</p><p><a class="button" data-evolve-link href="/">← Overview</a></p></div>`;
    return;
  }
  const {metadata, text} = loaded;
  const generationMatch = metadata.relative_path.match(/^runs\/gen-([^/]+)\//);
  const backHref = generationMatch ? `/generations/${encodeURIComponent(generationMatch[1])}` : '/';
  content.innerHTML = `
    <div class="page-heading artifact-heading">
      <div><p class="eyebrow">Artifact preview</p><h2>${escapeHtml(metadata.label)}</h2><p class="artifact-path">${escapeHtml(metadata.relative_path)}</p></div>
      <div class="page-actions"><a class="button" data-evolve-link href="${backHref}">← ${generationMatch ? 'Generation' : 'Overview'}</a><a class="button" target="_blank" href="${escapeHtml(metadata.content_url)}">Raw</a><button class="button" id="artifact-wrap" type="button" aria-pressed="false">Wrap lines</button></div>
    </div>
    ${metadata.truncated ? '<div class="artifact-notice">Preview limited to the first 1 MiB of this artifact.</div>' : ''}
    <section class="card artifact-card"><div class="artifact-meta"><span>${escapeHtml(metadata.kind || 'text')}</span><span>${formatBytes(metadata.size)}</span></div><div id="artifact-preview" class="artifact-preview no-wrap"></div></section>`;

  const preview = document.querySelector('#artifact-preview');
  const wrapButton = document.querySelector('#artifact-wrap');
  wrapButton.addEventListener('click', () => {
    const wrapping = preview.classList.toggle('wrap');
    preview.classList.toggle('no-wrap', !wrapping);
    wrapButton.setAttribute('aria-pressed', String(wrapping));
    wrapButton.textContent = wrapping ? 'Do not wrap' : 'Wrap lines';
  });
  renderArtifactPresentation(preview, artifactPresentation(metadata, text));
}

function renderArtifactPresentation(container, presentation) {
  try {
    if (presentation.mode === 'diff') {
      if (!globalThis.Diff2Html) throw new Error('Diff renderer is unavailable');
      container.classList.add('diff-preview');
      container.innerHTML = globalThis.Diff2Html.html(presentation.text, {
        drawFileList: true,
        matching: 'none',
        outputFormat: 'line-by-line',
        diffMaxChanges: 5000,
      });
      return;
    }
    const pre = document.createElement('pre');
    const code = document.createElement('code');
    if (presentation.mode === 'highlight') {
      if (!globalThis.hljs) throw new Error('Syntax highlighter is unavailable');
      code.className = `language-${presentation.language}`;
      code.innerHTML = globalThis.hljs.highlight(presentation.text, {language: presentation.language}).value;
    } else {
      code.textContent = presentation.text;
    }
    pre.append(code);
    container.append(pre);
  } catch (error) {
    container.classList.remove('diff-preview');
    const warning = document.createElement('div');
    warning.className = 'artifact-render-warning';
    warning.textContent = `${error.message}; showing plain text.`;
    const pre = document.createElement('pre');
    const code = document.createElement('code');
    code.textContent = presentation.text;
    pre.append(code);
    container.replaceChildren(warning, pre);
  }
}

async function renderTrials(params) {
  const apiParams = new URLSearchParams(params);
  if (!apiParams.has('page')) apiParams.set('page', '1');
  if (!apiParams.has('page_size')) apiParams.set('page_size', '50');
  const data = await getJson(`/api/evolve/trials?${apiParams}`);
  const generations = [...state.snapshot.generations].reverse();
  const selectedGeneration = params.get('generation');
  const backHref = selectedGeneration ? `/generations/${encodeURIComponent(selectedGeneration)}` : '/';
  const backLabel = selectedGeneration ? `Generation ${escapeHtml(selectedGeneration)}` : 'Overview';
  content.innerHTML = `
    <div class="page-heading"><div><h2>Trials</h2><p>Canonical outcomes with direct access to full Harbor inspection.</p></div><div class="page-actions"><a class="button" data-evolve-link href="${backHref}">← ${backLabel}</a></div></div>
    <section class="card">
      <form id="trial-filters" class="filters">
        <div class="field"><label for="filter-generation">Generation</label><select id="filter-generation" name="generation"><option value="">All generations</option>${generations.map((generation) => `<option value="${escapeHtml(generation.genid)}" ${params.get('generation') === generation.genid ? 'selected' : ''}>${escapeHtml(generation.genid)}</option>`).join('')}</select></div>
        <div class="field"><label for="filter-purpose">Purpose</label><select id="filter-purpose" name="purpose"><option value="">All purposes</option>${['candidate', 'genesis', 'rollout', 'anchor'].map((purpose) => `<option ${params.get('purpose') === purpose ? 'selected' : ''}>${purpose}</option>`).join('')}</select></div>
        <div class="field"><label for="filter-status">Status</label><select id="filter-status" name="status"><option value="">All statuses</option>${['complete', 'benchmark_complete', 'error', 'unknown'].map((status) => `<option ${params.get('status') === status ? 'selected' : ''}>${status}</option>`).join('')}</select></div>
        <div class="field"><label for="filter-task">Exact task</label><input id="filter-task" name="task" value="${escapeHtml(params.get('task') || '')}" placeholder="Task name"></div>
        <div class="filter-action"><button class="button primary" type="submit">Apply</button></div>
      </form>
      ${trialTable(data.items)}
      ${pagination(data, params)}
    </section>`;
  document.querySelector('#trial-filters').addEventListener('submit', applyTrialFilters);
  document.querySelectorAll('[data-page]').forEach((button) => button.addEventListener('click', () => {
    const next = new URLSearchParams(window.location.search); next.set('page', button.dataset.page); navigate(`/trials?${next}`);
  }));
}

function trialTable(trials) {
  if (!trials.length) return '<div class="empty"><strong>No trials match these filters</strong>Clear one or more filters to widen the result.</div>';
  return `<div class="table-wrap"><table><thead><tr><th>Task</th><th>Generation</th><th>Purpose</th><th>Status</th><th class="numeric">Reward</th><th class="numeric">Duration</th><th>Inspection</th></tr></thead><tbody>${trials.map((trial) => `<tr>
    <td><span class="mono">${escapeHtml(trial.task)}</span><div class="subtle">Repetition ${trial.repetition}</div></td><td><a class="row-link" data-evolve-link href="/generations/${encodeURIComponent(trial.generation)}">${escapeHtml(trial.generation)}</a></td><td>${escapeHtml(label(trial.purpose))}</td><td>${badge(trial.status)}</td><td class="numeric">${number(trial.reward)}</td><td class="numeric">${trial.duration_ms == null ? '—' : `${number(trial.duration_ms / 1000, 2)}s`}</td><td>${trial.harbor_url ? `<a class="button" href="${escapeHtml(trial.harbor_url)}">Full Harbor inspection</a>` : '<span class="subtle">Not linked</span>'}</td>
  </tr>`).join('')}</tbody></table></div>`;
}

function pagination(data, params) {
  const first = data.total ? (data.page - 1) * data.page_size + 1 : 0;
  const last = Math.min(data.page * data.page_size, data.total);
  return `<div class="pagination"><span>Showing ${first}–${last} of ${data.total}</span><div><button class="button" data-page="${data.page - 1}" ${data.page <= 1 ? 'disabled' : ''}>Previous</button><button class="button" data-page="${data.page + 1}" ${data.page >= data.total_pages ? 'disabled' : ''}>Next</button></div></div>`;
}

function applyTrialFilters(event) {
  event.preventDefault();
  const values = new FormData(event.currentTarget);
  const params = new URLSearchParams();
  for (const [key, value] of values) if (value) params.set(key, value);
  navigate(`/trials${params.size ? `?${params}` : ''}`);
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function navigate(url) {
  history.pushState({}, '', url);
  renderRoute(window.location.pathname, new URLSearchParams(window.location.search));
  content.focus({ preventScroll: true });
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

document.addEventListener('click', (event) => {
  const link = event.target.closest('a[data-evolve-link]');
  if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || link.origin !== location.origin) return;
  event.preventDefault(); navigate(`${link.pathname}${link.search}`);
});
window.addEventListener('popstate', () => renderRoute(window.location.pathname, new URLSearchParams(window.location.search)));

await refresh();
state.timer = window.setInterval(refresh, 3000);
