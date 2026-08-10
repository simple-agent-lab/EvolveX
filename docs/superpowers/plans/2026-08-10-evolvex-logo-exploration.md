# EvolveX Logo Exploration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a structurally verified, visually audited gallery of exactly 50 refined EvolveX logo concepts in the approved 18/16/16 art-direction split without changing the public repository logo.

**Architecture:** Keep the exploration in an internal, force-tracked `docs/superpowers/artifacts/` package. Each concept is a self-contained SVG presentation sheet with reusable vector mark and wordmark symbols plus light, dark, monochrome, and 32-pixel proofs; a JSON manifest is the source of truth, a standard-library validator enforces the structural contract, and a standard-library builder produces one self-contained gallery for browser selection.

**Tech Stack:** SVG 1.1-compatible vector markup, Python 3.12 standard library (`argparse`, `json`, `pathlib`, `xml.etree.ElementTree`), static HTML/CSS/JavaScript, pytest, macOS Quick Look for visual rendering.

## Global Constraints

- Produce exactly 50 distinct concepts: 18 minimal original mascots, 16 playful open-source identities, and 16 technical editorial identities.
- The three collections are genuine art directions, not cosmetic recolors of a shared template.
- Lead with one recognizable silhouette and one visual idea.
- Remain recognizable at 32 pixels and legible at 16 pixels where practical.
- Work in one-color black and white before relying on color.
- Use no more than two main brand colors in the primary version.
- Include an intentional EvolveX wordmark treatment; do not use an unmodified default system font as the final typographic expression.
- Avoid neural-network dots, circuit traces, brains, atoms, glowing orbs, chat bubbles, generic trees, and random gradient X marks.
- Do not copy or closely imitate reference-project marks.
- Keep `README.md`, `docs/evolve-mark.svg`, `docs/evolve-lineage.svg`, and `tools/generate_readme_assets.py` unchanged until the user explicitly approves a winner.
- Store no remote fonts, remote images, JavaScript packages, or runtime CDN dependencies.

## File Structure

| Path | Responsibility |
| --- | --- |
| `docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/README.md` | Local viewing, validation, rendering, and selection instructions. |
| `docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/manifest.json` | Ordered source of truth for collection counts, stable IDs, names, files, palettes, motifs, and wordmark construction. |
| `docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/validate.py` | Standard-library structural validator for the manifest and each SVG sheet. |
| `docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/build_gallery.py` | Deterministically inline manifest metadata and SVG sheets into one self-contained comparison gallery. |
| `docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/gallery.html` | Generated multi-select browser gallery; never hand-edit. |
| `docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/concepts/*.svg` | Fifty self-contained SVG presentation sheets named by stable concept ID and slug. |
| `docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/tests/test_exploration.py` | Focused validator and deterministic-gallery tests. |
| `docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/audit.md` | Final visual audit record and replacement decisions for rejected concepts. |

## SVG Presentation Contract

Every concept file uses `viewBox="0 0 1200 620"`, `role="img"`, and `aria-labelledby`. It contains `<title>` and `<desc>`, then these exact IDs:

- `<symbol id="mark" viewBox="0 0 128 128">` — the standalone mark;
- `<symbol id="wordmark" viewBox="0 0 520 128">` — vector paths only, no `<text>`;
- `<g id="primary-proof">` — full-color horizontal lockup on a light field;
- `<g id="dark-proof">` — full-color or reversed lockup on a dark field;
- `<g id="mono-proof">` — one-color black mark and lockup;
- `<g id="avatar-proof">` — `<use href="#mark" width="32" height="32">` at actual 32-pixel size.

The root also records `data-concept-id`, `data-collection`, `data-primary-color`, `data-secondary-color`, and `data-wordmark`. `data-wordmark` is either `custom-path` or `modified-open-font`; the latter requires a non-empty `font_license` entry in the manifest. External `href`, `<image>`, `<script>`, `<foreignObject>`, animation, filters, masks, and embedded raster data are forbidden.

---

### Task 1: Build the exploration contract, validator, and gallery pipeline

**Files:**
- Create: `docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/README.md`
- Create: `docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/manifest.json`
- Create: `docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/validate.py`
- Create: `docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/build_gallery.py`
- Create: `docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/tests/test_exploration.py`

**Interfaces:**
- Produces: `load_manifest(root: Path) -> dict[str, object]`.
- Produces: `validate_manifest(root: Path, manifest: dict[str, object], *, complete: bool, family: str | None = None) -> list[str]`.
- Produces: `validate_svg(path: Path, concept: dict[str, object]) -> list[str]`.
- Produces: CLI `python validate.py [--complete] [--family mascot|playful|editorial]` with exit code `0` only when no validation errors exist.
- Produces: `render_gallery(root: Path, manifest: dict[str, object]) -> str` and CLI `python build_gallery.py [--check] [--output PATH]`.

- [ ] **Step 1: Write focused tests for the manifest and SVG contract**

Create fixture builders inside `tests/test_exploration.py` and add these exact behaviors:

```python
def test_complete_manifest_requires_exact_18_16_16_split(tmp_path: Path) -> None:
    manifest = fixture_manifest(mascot=18, playful=16, editorial=15)
    errors = validate_manifest(tmp_path, manifest, complete=True)
    assert "expected 16 editorial concepts, found 15" in errors


def test_svg_requires_all_proof_groups_and_vector_wordmark(tmp_path: Path) -> None:
    concept = fixture_concept("M01", "mascot")
    path = tmp_path / concept["file"]
    path.parent.mkdir(parents=True)
    path.write_text(fixture_svg().replace('id="avatar-proof"', 'id="missing-avatar"'))
    errors = validate_svg(path, concept)
    assert "M01: missing id avatar-proof" in errors


def test_svg_rejects_text_and_external_resources(tmp_path: Path) -> None:
    concept = fixture_concept("M01", "mascot")
    path = tmp_path / concept["file"]
    path.parent.mkdir(parents=True)
    path.write_text(fixture_svg().replace("</svg>", '<text>bad</text><image href="https://example.com/a.png"/></svg>'))
    errors = validate_svg(path, concept)
    assert "M01: text elements are forbidden" in errors
    assert "M01: external resources are forbidden" in errors


def test_gallery_render_is_deterministic(tmp_path: Path) -> None:
    manifest = fixture_manifest(mascot=1, playful=0, editorial=0)
    write_fixture_assets(tmp_path, manifest)
    assert render_gallery(tmp_path, manifest) == render_gallery(tmp_path, manifest)
```

- [ ] **Step 2: Run the focused tests and confirm the missing implementation failure**

Run:

```bash
uv run --frozen pytest -q docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/tests/test_exploration.py
```

Expected: collection fails because `validate.py` and `build_gallery.py` do not exist.

- [ ] **Step 3: Implement the validator**

Use these constants and public structure in `validate.py`:

```python
EXPECTED_COUNTS = {"mascot": 18, "playful": 16, "editorial": 16}
REQUIRED_IDS = {"mark", "wordmark", "primary-proof", "dark-proof", "mono-proof", "avatar-proof"}
FORBIDDEN_TAGS = {"text", "image", "script", "foreignObject", "animate", "animateTransform", "filter", "mask"}
FORBIDDEN_MOTIFS = {
    "neural-network", "circuit", "brain", "atom", "glowing-orb",
    "chat-bubble", "generic-tree", "gradient-x",
}
```

Implement the four public signatures listed in **Interfaces** with explicit standard-library logic: normalize XML namespaces before tag comparison, require internal fragment-only `href` values, reject duplicate concept IDs and files, compare manifest collection counts, ensure `colors` has one or two entries, ensure the SVG root metadata matches the manifest, and return every error in stable sorted order. `main()` prints each error on its own line to stderr and returns `1`; when validation passes, it prints the validated family counts to stdout and returns `0`.

- [ ] **Step 4: Implement deterministic gallery generation**

`build_gallery.py` must read the manifest in listed order, validate it with `complete=False`, read each SVG as UTF-8, escape metadata with `html.escape`, inline the SVG inside its card, and emit one HTML document with:

```python
def render_gallery(root: Path, manifest: dict[str, object]) -> str:
    """Return one self-contained HTML gallery ordered by manifest concepts."""


def main(argv: list[str] | None = None) -> int:
    """Write the requested output, or fail under --check when bytes differ."""
```

With no `--output`, target `gallery.html` beside the script. The HTML must have three collection filters, a visible selected-count label, multi-select cards keyed by stable concept ID, localStorage key `evolvex-logo-shortlist-v1`, and no network references.

- [ ] **Step 5: Add the empty manifest and operating instructions**

Create `manifest.json` exactly as:

```json
{
  "version": 1,
  "expected_counts": {"mascot": 18, "playful": 16, "editorial": 16},
  "concepts": []
}
```

Document these commands in `README.md`:

```bash
uv run --frozen python validate.py --family mascot
uv run --frozen python validate.py --family playful
uv run --frozen python validate.py --family editorial
uv run --frozen python validate.py --complete
uv run --frozen python build_gallery.py
uv run --frozen python build_gallery.py --check
```

- [ ] **Step 6: Run focused tests**

Run:

```bash
uv run --frozen pytest -q docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/tests/test_exploration.py
```

Expected: all tests pass.

- [ ] **Step 7: Commit the contract and pipeline**

```bash
git add -f docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration
git commit -m "design: add EvolveX logo exploration pipeline"
```

### Task 2: Author 18 minimal original mascot concepts

**Files:**
- Create: `docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/concepts/M01-tessellated-tern.svg`
- Create: `docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/concepts/M02-split-tail-finch.svg`
- Create: `docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/concepts/M03-nautilus-runner.svg`
- Create: `docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/concepts/M04-axolotl-x.svg`
- Create: `docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/concepts/M05-orbit-moth.svg`
- Create: `docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/concepts/M06-compass-beetle.svg`
- Create: `docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/concepts/M07-paper-crane.svg`
- Create: `docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/concepts/M08-gecko-mark.svg`
- Create: `docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/concepts/M09-kite-ray.svg`
- Create: `docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/concepts/M10-firefly-beacon.svg`
- Create: `docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/concepts/M11-salamander-curve.svg`
- Create: `docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/concepts/M12-pangolin-spiral.svg`
- Create: `docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/concepts/M13-heron-step.svg`
- Create: `docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/concepts/M14-evo-mote.svg`
- Create: `docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/concepts/M15-mosaic-turtle.svg`
- Create: `docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/concepts/M16-swift-arrow.svg`
- Create: `docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/concepts/M17-quiet-fox.svg`
- Create: `docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/concepts/M18-curious-quill.svg`
- Modify: `docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/manifest.json`

**Interfaces:**
- Consumes: the SVG presentation contract and validator from Task 1.
- Produces: complete `mascot` collection with IDs `M01` through `M18`.

- [ ] **Step 1: Add all 18 mascot manifest entries before drawing**

For each entry set `collection` to `mascot`, `wordmark` to `custom-path`, `font_license` to `null`, and `motif` to its exact slug from the filename. Use these palette assignments so the collection is not another green/purple batch:

| IDs | Primary | Secondary |
| --- | --- | --- |
| M01–M03 | `#111111` | `#FF6B4A` |
| M04–M06 | `#14213D` | `#FCA311` |
| M07–M09 | `#172A3A` | `#41C7A5` |
| M10–M12 | `#221E22` | `#E9C46A` |
| M13–M15 | `#102A43` | `#4EA5D9` |
| M16–M18 | `#251F47` | `#F36F9B` |

- [ ] **Step 2: Draw M01–M06 and run the partial validator**

Draw each as a distinct closed silhouette, not the same body with changed ears or wings. At 32 pixels, preserve only eyes or one signature cut when it materially improves recognition. Use vector paths for the EvolveX wordmark and the exact presentation contract.

Run:

```bash
uv run --frozen python docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/validate.py
```

Expected: no errors for files M01–M06; missing-file errors remain for M07–M18.

- [ ] **Step 3: Draw M07–M12 and repeat the partial validator**

Give M07–M12 different construction logic: folded planes, negative-space gecko, broad ray silhouette, point-light firefly, continuous salamander curve, and armored spiral. Do not reuse a shared circular head or symmetrical face.

Run the same partial validator. Expected: no errors for M01–M12; missing-file errors remain only for M13–M18.

- [ ] **Step 4: Draw M13–M18 and validate the family**

Use tall editorial proportion for the heron, a non-animal soft geometric mote, a low turtle silhouette, a fast asymmetric swift, a quiet angular fox, and a quill whose negative space suggests forward motion.

Run:

```bash
uv run --frozen python docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/validate.py --family mascot
```

Expected: `validated 18 mascot concepts` and exit code `0`.

- [ ] **Step 5: Render contact sheets and reject weak silhouettes**

```bash
mkdir -p /tmp/evolvex-logo-mascot-preview
qlmanage -t -s 1200 -o /tmp/evolvex-logo-mascot-preview docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/concepts/M*.svg
```

Inspect both the large lockup and embedded 32-pixel proof. Replace any concept that reads as an emoji, resembles a reference mascot, or needs its name to explain the silhouette.

- [ ] **Step 6: Commit the mascot collection**

```bash
git add -f docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/manifest.json docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/concepts/M*.svg
git commit -m "design: explore EvolveX mascot identities"
```

### Task 3: Author 16 playful open-source concepts

**Files:**
- Create: `docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/concepts/P01-confetti-x.svg` through `P16-joyful-slash.svg`, with every intermediate path specified in the inventory below
- Modify: `docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/manifest.json`

**Interfaces:**
- Consumes: the SVG presentation contract and validator from Task 1.
- Produces: complete `playful` collection with IDs `P01` through `P16`.

- [ ] **Step 1: Add the exact playful concept inventory to the manifest**

Use these IDs, names, filenames, and distinct visual ideas:

| ID | Name | File | Visual idea |
| --- | --- | --- | --- |
| P01 | Confetti X | `P01-confetti-x.svg` | Four irregular paper pieces imply an X without touching. |
| P02 | Sticker Fold | `P02-sticker-fold.svg` | One folded corner becomes the evolutionary accent. |
| P03 | Wobble Mark | `P03-wobble-mark.svg` | Hand-tensioned asymmetric loop with a crisp wordmark. |
| P04 | Friendly Asterisk | `P04-friendly-asterisk.svg` | Five unequal arms with one bright advancing arm. |
| P05 | Soft Domino | `P05-soft-domino.svg` | Two offset rounded tiles create motion through balance. |
| P06 | Patchwork E | `P06-patchwork-e.svg` | Three materially different bands assemble an E. |
| P07 | Chunky Ribbon | `P07-chunky-ribbon.svg` | Broad ribbon folds once into an X-like gesture. |
| P08 | Paper Comet | `P08-paper-comet.svg` | Cut-paper body with a single high-energy tail. |
| P09 | Curious Bracket | `P09-curious-bracket.svg` | Two brackets lean toward a small center spark. |
| P10 | Tilted Badge | `P10-tilted-badge.svg` | Imperfect badge with editorially precise lettering. |
| P11 | Double Take | `P11-double-take.svg` | Two offset silhouettes suggest iteration without arrows. |
| P12 | Color Relay | `P12-color-relay.svg` | One colored baton passes between two black forms. |
| P13 | Pocket Spark | `P13-pocket-spark.svg` | Compact spark nested in a soft pocket silhouette. |
| P14 | Open Loop | `P14-open-loop.svg` | Cheerful loop whose gap creates forward tension. |
| P15 | Building Pebbles | `P15-building-pebbles.svg` | Three non-identical pebbles stack into a stable emblem. |
| P16 | Joyful Slash | `P16-joyful-slash.svg` | A bold slash and restrained dot create a smiling rhythm. |

Assign `#121212` as the primary for P01–P08 and `#1F2544` for P09–P16. Rotate secondary colors by concept through `#FF5C5C`, `#FFB703`, `#22B8A7`, and `#5B7CFA`; each concept receives exactly one secondary color.

- [ ] **Step 2: Draw P01–P08 and run the partial validator**

Use materially different edge language across these eight: torn, folded, rounded, elastic, tiled, woven, ribboned, and cut-paper. The wordmark must counterbalance the playful mark with clean custom vector lettering.

Run the partial validator. Expected: no errors for P01–P08; missing-file errors remain for P09–P16.

- [ ] **Step 3: Draw P09–P16 and validate the family**

Keep P09–P16 bold enough for 32 pixels, but do not add faces, eyes, or mascot anatomy. Each concept must communicate warmth through proportion, rhythm, and color only.

Run:

```bash
uv run --frozen python docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/validate.py --family playful
```

Expected: `validated 16 playful concepts` and exit code `0`.

- [ ] **Step 4: Render and audit the playful collection**

```bash
mkdir -p /tmp/evolvex-logo-playful-preview
qlmanage -t -s 1200 -o /tmp/evolvex-logo-playful-preview docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/concepts/P*.svg
```

Replace marks that look like generic app icons, emoji, children's products, or minor variations of another card.

- [ ] **Step 5: Commit the playful collection**

```bash
git add -f docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/manifest.json docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/concepts/P*.svg
git commit -m "design: explore playful EvolveX identities"
```

### Task 4: Author 16 technical editorial concepts

**Files:**
- Create: `docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/concepts/T01-cut-e-wordmark.svg` through `T16-horizon-wordmark.svg`
- Modify: `docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/manifest.json`

**Interfaces:**
- Consumes: the SVG presentation contract and validator from Task 1.
- Produces: complete `editorial` collection with IDs `T01` through `T16`.

- [ ] **Step 1: Add the exact editorial inventory to the manifest**

| ID | Name | File | Visual idea |
| --- | --- | --- | --- |
| T01 | Cut-E Wordmark | `T01-cut-e-wordmark.svg` | Custom E with one diagonal cut repeated subtly in X. |
| T02 | Extended X | `T02-extended-x.svg` | Restrained wordmark with one long X terminal. |
| T03 | Counterform | `T03-counterform.svg` | Negative E appears inside a solid editorial block. |
| T04 | Baseline Shift | `T04-baseline-shift.svg` | The X rises one measured unit above a stable baseline. |
| T05 | Ligature EX | `T05-ligature-ex.svg` | E and X share one structural stroke. |
| T06 | Split Weight | `T06-split-weight.svg` | Light Evolve contrasts with a heavy custom X. |
| T07 | Narrow Signal | `T07-narrow-signal.svg` | Condensed wordmark with one precise color signal. |
| T08 | Wide Research | `T08-wide-research.svg` | Broad low-contrast lettering for papers and banners. |
| T09 | Editorial Seal | `T09-editorial-seal.svg` | Compact seal derived from custom E/X counters. |
| T10 | Index Mark | `T10-index-mark.svg` | Superscript-like X treated as an experimental index. |
| T11 | Proof Line | `T11-proof-line.svg` | One horizontal rule intersects only the X. |
| T12 | Modular Type | `T12-modular-type.svg` | Letters share a consistent cut-and-join grammar. |
| T13 | Serif Contrast | `T13-serif-contrast.svg` | Custom wedge-serif Evolve paired with sans X. |
| T14 | Mono Stamp | `T14-mono-stamp.svg` | Single-color stamped wordmark with deliberate ink traps. |
| T15 | Open Counter X | `T15-open-counter-x.svg` | X is built from two open counters rather than strokes. |
| T16 | Horizon Wordmark | `T16-horizon-wordmark.svg` | A quiet horizon aligns the entire name and lifts the X. |

Use black and white as the base. Assign exactly one accent to T01, T04, T07, T10, T13, and T16, cycling through `#E4572E`, `#2563EB`, and `#17A673`; all other editorial concepts are monochrome.

- [ ] **Step 2: Draw T01–T08 and run the partial validator**

Treat the wordmark as the primary design, not as a label beside an icon. Construct every letter from SVG paths. Preserve a coherent internal system for stroke terminals, counters, spacing, and optical alignment within each concept, while keeping the eight concepts visibly different.

Run the partial validator. Expected: no errors for T01–T08; missing-file errors remain for T09–T16.

- [ ] **Step 3: Draw T09–T16 and validate the family**

Give T09–T16 different typographic voices: seal, index, ruled proof, modular, serif contrast, stamp, counterform, and horizon. Do not use a downloaded wordmark image or live `<text>` element.

Run:

```bash
uv run --frozen python docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/validate.py --family editorial
```

Expected: `validated 16 editorial concepts` and exit code `0`.

- [ ] **Step 4: Render and audit the editorial collection**

```bash
mkdir -p /tmp/evolvex-logo-editorial-preview
qlmanage -t -s 1200 -o /tmp/evolvex-logo-editorial-preview docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/concepts/T*.svg
```

Reject any concept that looks like an unmodified typeface, a cryptocurrency token, or a generic SaaS monogram.

- [ ] **Step 5: Commit the editorial collection**

```bash
git add -f docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/manifest.json docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/concepts/T*.svg
git commit -m "design: explore editorial EvolveX identities"
```

### Task 5: Build the complete multi-select gallery

**Files:**
- Regenerate: `docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/gallery.html`
- Modify: `docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/README.md`

**Interfaces:**
- Consumes: all 50 manifest entries and SVG sheets from Tasks 2–4.
- Produces: self-contained `gallery.html` with stable multi-selection persisted under `evolvex-logo-shortlist-v1`.

- [ ] **Step 1: Validate the complete source set**

```bash
uv run --frozen python docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/validate.py --complete
```

Expected: `validated 50 concepts: mascot=18 playful=16 editorial=16` and exit code `0`.

- [ ] **Step 2: Generate the gallery**

```bash
uv run --frozen python docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/build_gallery.py
uv run --frozen python docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/build_gallery.py --check
```

Expected: the first command writes `gallery.html`; the second reports `gallery.html is current`.

- [ ] **Step 3: Serve the gallery through the existing brainstorming companion**

Generate a fresh semantic screen filename under the active companion content directory:

```bash
uv run --frozen python docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/build_gallery.py --output .superpowers/brainstorm/83265-1786351892/content/logo-gallery-refined-50.html
```

Confirm the server's `state/server-info` exists and `state/server-stopped` does not before sharing the existing keyed URL.

- [ ] **Step 4: Test browser interaction manually**

In the companion, select one concept from each collection, reload, and confirm all three selections persist. Toggle collection filters and confirm the selected count remains unchanged. Clear selections and confirm localStorage key `evolvex-logo-shortlist-v1` becomes an empty array.

- [ ] **Step 5: Commit the generated gallery and instructions**

```bash
git add -f docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/gallery.html docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/README.md
git commit -m "design: publish EvolveX logo comparison gallery"
```

### Task 6: Perform the quality audit and replace rejected concepts

**Files:**
- Create: `docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/audit.md`
- Modify as required: `docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/concepts/*.svg`
- Modify as required: `docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/manifest.json`
- Regenerate: `docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/gallery.html`

**Interfaces:**
- Consumes: the complete gallery from Task 5.
- Produces: a 50-row audit with an explicit pass or replacement result for each stable ID.

- [ ] **Step 1: Create the audit matrix**

Use exactly these columns in `audit.md`:

```markdown
| ID | 32px silhouette | Monochrome | Wordmark authored | Distinct in collection | No banned motif | Reference-distance | Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
```

Each criterion is `pass` or a concise failure reason. `Result` is `keep` or `replace`.

- [ ] **Step 2: Audit all 50 concepts without preserving weak work**

Compare concepts within their collection and against the reference calibration board. Mark `replace` when a design needs its title to be understood, shares the same construction skeleton with another concept, loses its silhouette at 32 pixels, resembles a reference project's mark, or violates any global constraint.

- [ ] **Step 3: Replace every rejected concept in place**

Keep the stable ID, but change the name, slug, motif, palette if needed, manifest file path, and SVG. Delete the rejected SVG only after the replacement validates. Record `replaced: <old name> -> <new name>` in the audit result.

- [ ] **Step 4: Revalidate and regenerate**

```bash
uv run --frozen python docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/validate.py --complete
uv run --frozen python docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/build_gallery.py
uv run --frozen python docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/build_gallery.py --check
```

Expected: all commands pass after replacements.

- [ ] **Step 5: Commit the audited set**

```bash
git add -f docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration
git commit -m "design: audit EvolveX logo exploration"
```

### Task 7: Run final verification and hand off the shortlist

**Files:**
- Verify only: `docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/`
- Do not modify: `README.md`, `docs/evolve-mark.svg`, `docs/evolve-lineage.svg`, `tools/generate_readme_assets.py`

**Interfaces:**
- Consumes: audited 50-concept gallery from Task 6.
- Produces: verified browser shortlist input for the next refinement cycle.

- [ ] **Step 1: Run focused structural checks**

```bash
uv run --frozen pytest -q docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/tests/test_exploration.py
uv run --frozen python docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/validate.py --complete
uv run --frozen python docs/superpowers/artifacts/2026-08-10-evolvex-logo-exploration/build_gallery.py --check
```

Expected: all tests pass, all 50 concepts validate, and the gallery is current.

- [ ] **Step 2: Prove public assets were not changed**

```bash
git diff 0907f2c -- README.md docs/evolve-mark.svg docs/evolve-lineage.svg tools/generate_readme_assets.py
```

Expected: no diff for these four paths.

- [ ] **Step 3: Run the repository default suite**

```bash
uv run --frozen pytest -q
```

Expected: the default suite passes; slow tests remain skipped by repository policy.

- [ ] **Step 4: Push the final gallery to the active companion**

Run `build_gallery.py --output .superpowers/brainstorm/83265-1786351892/content/logo-gallery-refined-50-final.html`, confirm the server is alive, and share the existing full keyed URL. Ask the user to shortlist concepts by clicking them and to describe any cross-concept combination they want refined.

- [ ] **Step 5: Record final repository state**

```bash
git status --short
git log -6 --oneline
```

Expected: only the user's pre-existing `.codex/` and `arxiv/` entries remain untracked; the exploration commits are visible; no public logo asset changed.
