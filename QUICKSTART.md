# Quick Start

Run one of the supported recipes against the shared, content-pinned
Terminal-Bench 2.0 subset. The launcher requires Bash, Python 3.12+,
[`uv`](https://docs.astral.sh/uv/), Git 2.25+, and a running Docker daemon.

```bash
git clone https://github.com/simple-agent-lab/EvolveX.git
cd EvolveX

# API authentication is the default. Keep credentials out of recipe YAML.
cat > .env <<'EOF'
OPENAI_API_KEY=replace-me
# OPENAI_BASE_URL=https://your-openai-compatible-endpoint/v1
EOF

docker info
```

Choose a recipe, download and verify the pinned dataset, build that recipe's
pinned meta-agent image, and launch one generation:

```bash
RECIPE=ahe
./scripts/setup_terminal_bench.sh "$RECIPE"
./scripts/run_recipe_demo.sh "$RECIPE"
```

Supported values are `aevolve`, `ahe`, `ahe_codex`, `gepa`, `hill_climb`,
`hill_climb_codex`, `hyperagents`, and `hyperagents_codex`. Codex-capable
profiles may use `CODEX_AUTH_JSON_PATH=/absolute/path/to/auth.json` instead of
an API key. Use `WORKSPACE`, `TASKS`, `GENERATIONS`, `ENV_FILE`, or
`EVOLVE_ASSET_DIR` to override launcher defaults. See the
[recipe guide](recipes/README.md) and
[operations guide](docs/guides/operations.md) for the full configuration and
recovery workflow.

## Benchmark results

Scores are shown as **seed → best**, with the absolute change underneath. All
runs use a GPT-5.4-high target model and a GPT-5.4-xhigh Codex meta-agent.

### Terminal Bench 2

Split: **50 train / 19 gate / 20 sealed**.

<table width="100%">
  <thead>
    <tr>
      <th width="14%">Target agent</th>
      <th width="14%">Method</th>
      <th width="18%">Train</th>
      <th width="18%">Gate</th>
      <th width="18%">Sealed</th>
      <th width="18%">Overall</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td rowspan="4">MiniSWE Agent</td>
      <td>AHE</td>
      <td>58.0% → 74.0%<br><strong>(+16.0%)</strong></td>
      <td>57.9% → 68.4%<br><strong>(+10.5%)</strong></td>
      <td>70.0% → 70.0%<br><strong>(+0.0%)</strong></td>
      <td>60.7% → 71.9%<br><strong>(+11.2%)</strong></td>
    </tr>
    <tr>
      <td>Hyperagents</td>
      <td>58.0% → 68.0%<br><strong>(+10.0%)</strong></td>
      <td>57.9% → 73.7%<br><strong>(+15.8%)</strong></td>
      <td>70.0% → 70.0%<br><strong>(+0.0%)</strong></td>
      <td>60.7% → 69.7%<br><strong>(+9.0%)</strong></td>
    </tr>
    <tr>
      <td>A Evolve</td>
      <td>58.0% → 68.0%<br><strong>(+10.0%)</strong></td>
      <td>57.9% → 78.9%<br><strong>(+21.0%)</strong></td>
      <td>70.0% → 65.0%<br><strong>(−5.0%)</strong></td>
      <td>60.7% → 69.7%<br><strong>(+9.0%)</strong></td>
    </tr>
    <tr>
      <td>GEPA</td>
      <td>58.0% → 68.0%<br><strong>(+10.0%)</strong></td>
      <td>57.9% → 68.4%<br><strong>(+10.5%)</strong></td>
      <td>70.0% → 75.0%<br><strong>(+5.0%)</strong></td>
      <td>60.7% → 69.7%<br><strong>(+9.0%)</strong></td>
    </tr>
    <tr>
      <td rowspan="4">Codex</td>
      <td>AHE</td>
      <td>58.0% → 74.0%<br><strong>(+16.0%)</strong></td>
      <td>52.6% → 47.4%<br><strong>(−5.2%)</strong></td>
      <td>65.0% → 70.0%<br><strong>(+5.0%)</strong></td>
      <td>58.4% → 67.4%<br><strong>(+9.0%)</strong></td>
    </tr>
    <tr>
      <td>Hyperagents</td>
      <td>58.0% → 72.0%<br><strong>(+14.0%)</strong></td>
      <td>52.6% → 57.9%<br><strong>(+5.3%)</strong></td>
      <td>65.0% → 75.0%<br><strong>(+10.0%)</strong></td>
      <td>58.4% → 69.7%<br><strong>(+11.3%)</strong></td>
    </tr>
    <tr>
      <td>A Evolve</td>
      <td>58.0% → 58.0%<br><strong>(+0.0%)</strong></td>
      <td>52.6% → 52.6%<br><strong>(+0.0%)</strong></td>
      <td>65.0% → 65.0%<br><strong>(+0.0%)</strong></td>
      <td>58.4% → 58.4%<br><strong>(+0.0%)</strong></td>
    </tr>
    <tr>
      <td>GEPA</td>
      <td>58.0% → 58.0%<br><strong>(+0.0%)</strong></td>
      <td>52.6% → 52.6%<br><strong>(+0.0%)</strong></td>
      <td>65.0% → 65.0%<br><strong>(+0.0%)</strong></td>
      <td>58.4% → 58.4%<br><strong>(+0.0%)</strong></td>
    </tr>
  </tbody>
</table>

### Tau³ Banking

Split: **50 train / 20 gate / 27 sealed**.

<table width="100%">
  <thead>
    <tr>
      <th width="14%">Target agent</th>
      <th width="14%">Method</th>
      <th width="18%">Train</th>
      <th width="18%">Gate</th>
      <th width="18%">Sealed</th>
      <th width="18%">Overall</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td rowspan="4">MiniSWE Agent</td>
      <td>AHE</td>
      <td>30.0% → 36.0%<br><strong>(+6.0%)</strong></td>
      <td>35.0% → 35.0%<br><strong>(+0.0%)</strong></td>
      <td>18.5% → 25.9%<br><strong>(+7.4%)</strong></td>
      <td>27.8% → 33.0%<br><strong>(+5.2%)</strong></td>
    </tr>
    <tr>
      <td>Hyperagents</td>
      <td>30.0% → 38.0%<br><strong>(+8.0%)</strong></td>
      <td>35.0% → 45.0%<br><strong>(+10.0%)</strong></td>
      <td>18.5% → 37.0%<br><strong>(+18.5%)</strong></td>
      <td>27.8% → 39.2%<br><strong>(+11.4%)</strong></td>
    </tr>
    <tr>
      <td>A Evolve</td>
      <td>30.0% → 34.0%<br><strong>(+4.0%)</strong></td>
      <td>35.0% → 45.0%<br><strong>(+10.0%)</strong></td>
      <td>18.5% → 29.6%<br><strong>(+11.1%)</strong></td>
      <td>27.8% → 35.1%<br><strong>(+7.3%)</strong></td>
    </tr>
    <tr>
      <td>GEPA</td>
      <td>30.0% → 32.0%<br><strong>(+2.0%)</strong></td>
      <td>35.0% → 45.0%<br><strong>(+10.0%)</strong></td>
      <td>18.5% → 25.9%<br><strong>(+7.4%)</strong></td>
      <td>27.8% → 33.0%<br><strong>(+5.2%)</strong></td>
    </tr>
    <tr>
      <td rowspan="4">Codex</td>
      <td>AHE</td>
      <td>30.0% → 36.0%<br><strong>(+6.0%)</strong></td>
      <td>30.0% → 45.0%<br><strong>(+15.0%)</strong></td>
      <td>7.4% → 14.8%<br><strong>(+7.4%)</strong></td>
      <td>23.7% → 32.0%<br><strong>(+8.3%)</strong></td>
    </tr>
    <tr>
      <td>Hyperagents</td>
      <td>30.0% → 36.0%<br><strong>(+6.0%)</strong></td>
      <td>30.0% → 50.0%<br><strong>(+20.0%)</strong></td>
      <td>7.4% → 48.1%<br><strong>(+40.7%)</strong></td>
      <td>23.7% → 42.3%<br><strong>(+18.6%)</strong></td>
    </tr>
    <tr>
      <td>A Evolve</td>
      <td>30.0% → 38.0%<br><strong>(+8.0%)</strong></td>
      <td>30.0% → 45.0%<br><strong>(+15.0%)</strong></td>
      <td>7.4% → 18.5%<br><strong>(+11.1%)</strong></td>
      <td>23.7% → 34.0%<br><strong>(+10.3%)</strong></td>
    </tr>
    <tr>
      <td>GEPA</td>
      <td>30.0% → 36.0%<br><strong>(+6.0%)</strong></td>
      <td>30.0% → 35.0%<br><strong>(+5.0%)</strong></td>
      <td>7.4% → 14.8%<br><strong>(+7.4%)</strong></td>
      <td>23.7% → 29.9%<br><strong>(+6.2%)</strong></td>
    </tr>
  </tbody>
</table>
