# EA Engine — User Guide

Audience: anyone running the Arena who wants to use the population-based
evolutionary algorithm (DEAP) or the LLM-driven meta-optimizer, rather than
the default deterministic MATH mutation.

## What it is

The Arena evolves agent configurations (genomes) generation by generation.
At each generation boundary the orchestrator runs one of three mutation
"engines" to propose the next genome:

| Engine | Description | Cost | When to use |
|---|---|---|---|
| **MATH** | Deterministic bounds-aware mutation via `ManufacturingGenome.mutate()`. (1+1) elitism. | Free, ~30 s / 20 generations | Fast iteration, reproducible runs, no API key needed |
| **DEAP** | Population-based (μ+λ) evolutionary algorithm — selection + crossover + mutation, evaluated via minibatch. | ~6× CPU vs MATH | Better exploration, no API key needed |
| **LLM** | A language model proposes the next genome from a digest of episode metrics. | ~$0.01–0.04 LLM tokens per 20-gen run | Reasoning-driven mutation; INTER mode recommended |

Built on top of all three: a (1+1) elitism wrapper that rejects child genomes
whose fitness is worse than the accepted parent, so accepted fitness never
regresses regardless of engine.

## How to enable a non-default engine

Three ways, in increasing order of permanence:

### 1. UI toggle (per run)
In the top bar of the Arena, the **Engine** dropdown (next to Boundary Mode)
exposes MATH / DEAP / LLM. Selection takes effect on the next `Run Evolution`
click. LLM is INTRA-disabled because it needs full episodes to score.

### 2. API parameter (per run, programmatic)
```bash
curl -X POST http://localhost:8000/api/scenario/start \
  -H 'Content-Type: application/json' \
  -d '{"scenario":"manufacturing","boundary_mode":"INTER","engine":"DEAP","inter_ticks":1000}'
```
Both `engine` and the legacy `mutation_strategy` field are honoured;
`engine` takes precedence.

### 3. Environment variable (default for all runs)
```bash
export ARENA_DEFAULT_ENGINE=DEAP
```
Used when neither the API nor the UI specifies an engine. Defaults to `MATH`.

## DEAP knob reference

All knobs live on the orchestrator state dict. Override via the start
payload's `ea_*` fields (e.g. `{"engine":"DEAP","ea_population_size":16}`)
or by setting the corresponding env var where shown.

| Key | Default | Env var | Meaning |
|---|---|---|---|
| `ea_population_size` | 8 | — | Individuals per generation |
| `ea_elite_keep` | 2 | — | μ for (μ+λ) elitism inside DEAP |
| `ea_crossover_prob` | 0.6 | — | Per-mating crossover rate |
| `ea_mutation_prob` | 0.4 | — | Per-child mutation rate |
| `ea_seed` | random | `ARENA_EA_SEED` | Deterministic seed |
| `ea_minibatch_seeds` | `[42, 101, 777]` | — | Seeds for fitness evaluation |
| `ea_ticks_per_episode` | 1000 | — | Spec §3.1 default |

DEAP is registered for scenarios `manufacturing` and `supply_chain`.
Other scenarios silently fall back to MATH.

## LLM provider configuration

`meta_optimizer.py` auto-detects the provider:

| Setting | Default | Notes |
|---|---|---|
| `META_OPTIMIZER_PROVIDER` | unset | Force `"openai"` or `"anthropic"`. Bypasses auto-detect. |
| `META_OPTIMIZER_MODEL` | `claude-haiku-4-5` (Anthropic) / `gpt-4o-mini` (OpenAI) | Override the default model name |
| `ANTHROPIC_API_KEY` | — | Picked up by anthropic SDK |
| `OPENAI_API_KEY` | — | Picked up by openai SDK |

Provider resolution order: `META_OPTIMIZER_PROVIDER` → `OPENAI_API_KEY` →
`ANTHROPIC_API_KEY`. Any failure falls back to a no-op delta, which the
orchestrator treats as "no change this generation".

## Reading the generation log

Every generation writes a row to the `ea_generations` SQLite table. Read
the full history for a run:

```bash
curl http://localhost:8000/api/ea/generations/<run_id>?limit=500
```

Returned shape (per row):
```json
{
  "id": 123,
  "run_id": "run_1700000000",
  "scenario": "manufacturing",
  "gen_id": 7,
  "boundary_mode": "INTER",
  "mutation_strategy": "DEAP",
  "parent_fitness": 1000.0,
  "child_fitness": 1050.5,
  "accepted_fitness": 1050.5,
  "stagnation": 0,
  "genome_json": {"agent_counts": {...}, "order_arrival_rate": 11.5, ...},
  "fitness_vector_json": [1050.5, 200.0, -50.0, -25.0],
  "population_stats_json": {"size": 8, "best": 1050.5, "mean": 980.0, "worst": 900.0},
  "topology_diff": "+2/0 edges",
  "timestamp": 1700000123.45
}
```

`population_stats_json` is `null` for MATH/LLM rows (those engines don't have
a population). `fitness_vector_json` is `[revenue, -capex, -opex, -penalties]`
for supply chain runs; for manufacturing it's whatever
`evolution.minibatch` returns.

## Resuming a run

Two-step protocol:

```bash
# 1. Look up the latest checkpoint
curl http://localhost:8000/api/scenario/resume/<old_run_id>
# → { "run_id": ..., "scenario": ..., "resume_payload": {<EA row>} }

# 2. Start a new run that warm-starts from it
curl -X POST http://localhost:8000/api/scenario/start \
  -H 'Content-Type: application/json' \
  -d '{
    "scenario": "manufacturing",
    "boundary_mode": "INTER",
    "engine": "DEAP",
    "resume_run_id": "<old_run_id>",
    "resume_payload": <copy the resume_payload from step 1>
  }'
```

The new run overlays `genome_config`, `generation`, `accepted_fitness`,
`parent_fitness`, and `mutation_strategy` from the payload onto the freshly
constructed orch_state. For non-manufacturing scenarios it also re-applies
the saved genome to the new env. Malformed payloads are caught and the run
cold-starts, never crashes.

## Cost expectations

20-generation manufacturing INTER run, default knobs:

| Engine | CPU | LLM cost | Notes |
|---|---|---|---|
| MATH | ~30 s | $0 | Baseline |
| DEAP | ~2 min | $0 | Population eval × seeds |
| LLM (Haiku) | ~30 s | ~$0.01 | One Haiku call per generation |
| LLM (gpt-4o-mini) | ~30 s | ~$0.04 | One mini call per generation |

DEAP fitness cache (hashed by genome dict) avoids re-evaluating identical
individuals across generations.

## Troubleshooting

### "DEAP available: False" in logs
The `deap` package is missing. Install it:
```bash
scripts/install_python_deps.sh
```
Replit's PEP-668 sandbox blocks plain `pip install`; the script uses
`uv pip install --target=…` to write into the persistent `.pythonlibs/`
site-packages directory.

### LLM strategy silently produces MATH-like results
The LLM call failed (any exception → no-op delta). Common causes:
1. Neither `OPENAI_API_KEY` nor `ANTHROPIC_API_KEY` is set.
2. `META_OPTIMIZER_PROVIDER=openai` but only `ANTHROPIC_API_KEY` is set.
3. Rate limit or transient API error. Check backend stdout — the failure
   reason is logged at `WARNING` level by `meta_optimizer.query_meta_optimizer`.

### Resume returns 404
`/api/scenario/resume/{run_id}` returns 404 if no row in `ea_generations`
has that run_id. Check with:
```bash
sqlite3 artifacts/backend/arena.db "select distinct run_id from ea_generations;"
```

### Tests
```bash
cd artifacts/backend && python3 -m pytest tests/ -v
```
26 unit tests cover encode/decode, bounds, elitism, persistence, and
supply-chain `apply_genome`. The test suite is independent of any LLM
provider — no API key needed.

## File index

| File | Role |
|---|---|
| `artifacts/backend/agents/ea_integration.py` | DEAP wrapper + per-scenario strategies |
| `artifacts/backend/agents/meta_optimizer.py` | LLM meta-optimizer (auto-detects OpenAI/Anthropic) |
| `artifacts/backend/agents/orchestrator.py` | Dispatches MATH/DEAP/LLM in `mutate()` |
| `artifacts/backend/state/db.py` | `EAGenerationModel` + save/load helpers |
| `artifacts/backend/main.py` | `/api/scenario/start`, `/api/scenario/resume/{id}`, `/api/ea/generations/{id}` |
| `artifacts/backend/game_envs/supply_chain.py` | Supply chain env + `apply_genome` + warehouse restock routing |
| `artifacts/backend/evolution/manufacturing_genome.py` | Manufacturing genome schema + bounds |
| `artifacts/backend/tests/` | Pytest suite |
| `plans/EA_Engine_Execution_Plan.md` | Dev-internal: per-phase implementation plan |
| `plans/EA_Engine_Progress.md` | Dev-internal: completed phases + open action items |
