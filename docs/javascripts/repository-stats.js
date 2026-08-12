(() => {
  const selector = "[data-rsihub-repository-stats]"
  const cacheLifetimeMs = 10 * 60 * 1000
  let currentStats
  let pendingStats

  function normalize(payload) {
    const stars = Number(payload.stars ?? payload.stargazers_count)
    const forks = Number(payload.forks ?? payload.forks_count)
    if (!Number.isSafeInteger(stars) || stars < 0 || !Number.isSafeInteger(forks) || forks < 0) {
      throw new Error("Invalid repository statistics")
    }
    return { stars, forks }
  }

  function formatCount(value) {
    if (value < 1000) return String(value)
    const units = [
      [1_000_000_000, "b"],
      [1_000_000, "m"],
      [1_000, "k"],
    ]
    const [divisor, suffix] = units.find(([threshold]) => value >= threshold)
    const scaled = value / divisor
    return `${scaled >= 10 ? scaled.toFixed(0) : scaled.toFixed(1).replace(/\.0$/, "")}${suffix}`
  }

  function repositoryApiUrl(source) {
    const repository = new URL(source.href)
    const [owner, name] = repository.pathname.split("/").filter(Boolean)
    if (repository.hostname !== "github.com" || !owner || !name) {
      throw new Error("Unsupported repository URL")
    }
    return `https://api.github.com/repos/${encodeURIComponent(owner)}/${encodeURIComponent(name)}`
  }

  function cacheKey(source) {
    return `rsihub-repository-stats:v1:${source.href}`
  }

  function readCache(source) {
    try {
      const cached = JSON.parse(sessionStorage.getItem(cacheKey(source)))
      if (Date.now() - cached.stored_at > cacheLifetimeMs) return undefined
      return normalize(cached)
    } catch {
      return undefined
    }
  }

  function writeCache(source, stats) {
    try {
      sessionStorage.setItem(cacheKey(source), JSON.stringify({ ...stats, stored_at: Date.now() }))
    } catch {
      // Storage can be disabled without affecting either network fallback.
    }
  }

  async function fetchLiveStats(source) {
    const controller = new AbortController()
    const timeout = window.setTimeout(() => controller.abort(), 4000)
    try {
      const response = await fetch(repositoryApiUrl(source), {
        cache: "no-store",
        headers: { Accept: "application/vnd.github+json" },
        signal: controller.signal,
      })
      if (!response.ok) throw new Error(`GitHub API returned ${response.status}`)
      return normalize(await response.json())
    } finally {
      window.clearTimeout(timeout)
    }
  }

  async function fetchFallbackStats(source) {
    const response = await fetch(source.dataset.rsihubRepositoryStats, { cache: "no-cache" })
    if (!response.ok) throw new Error(`Repository statistics fallback returned ${response.status}`)
    return normalize(await response.json())
  }

  async function loadStats(source) {
    const cached = readCache(source)
    if (cached) return cached
    let stats
    try {
      stats = await fetchLiveStats(source)
    } catch {
      stats = await fetchFallbackStats(source)
    }
    writeCache(source, stats)
    return stats
  }

  function renderFact(kind, value) {
    const fact = document.createElement("li")
    fact.className = `md-source__fact md-source__fact--${kind}`
    fact.textContent = formatCount(value)
    return fact
  }

  function render(stats) {
    for (const source of document.querySelectorAll(selector)) {
      const repository = source.querySelector(":scope > .md-source__repository")
      if (!repository) continue
      let facts = repository.querySelector(":scope > .md-source__facts")
      if (!facts) {
        facts = document.createElement("ul")
        facts.className = "md-source__facts"
        repository.append(facts)
      }
      repository.classList.add("md-source__repository--active")
      facts.replaceChildren(renderFact("stars", stats.stars), renderFact("forks", stats.forks))
    }
  }

  function hydrate() {
    const source = document.querySelector(selector)
    if (!source) return
    if (currentStats) {
      render(currentStats)
      return
    }
    pendingStats ??= loadStats(source)
    pendingStats.then((stats) => {
      currentStats = stats
      render(stats)
    }).catch(() => {
      // Keep the repository link usable when both the live API and fallback fail.
    })
  }

  hydrate()
  if (typeof document$ !== "undefined") document$.subscribe(hydrate)
})()
