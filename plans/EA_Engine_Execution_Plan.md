# Evolutionary Agentic Engine — Execution Plan

**Branch:** `ea-engine-v1` (off `ui-upgrade-v2`)
**Date opened:** 2026-05-26
**Audit basis:** `attached_assets/Executive_Summary_1779818461672.pdf` + ground-truth code scan

---

## 0. TL;DR

The PDF executive summary was written against a much more skeletal codebase than what actually exists. **~80% of the agent simulation harness is built.** The real gaps are not "missing files" — they are **architectural**:

1. The evolutionary loop is **(1+1)-EA only** — no population, no crossover, no selection pressure.
2. Two LLM-driven hooks (`SemanticMutation`, `evaluator.py`) are still stub random perturbations.
3. The `checkpoint()` orchestrator node is a **no-op** — DB schema exists, writes do not. No `/api/scenario/resume`.
4. **Disaster Relief** and **Peer Agents** simulations are scaffolds without genomes, policies, or fitness loops.
5. **Supply Chain** has fitness (GLS) but no `apply_genome()` method — meta-optimizer mutations don't propagate to the live env.
6. Multi-objective fitness vector exists but is collapsed to a scalar — Pareto front never tracked.

This plan addresses each gap **non-destructively**: every change is gated behind a config flag, the existing (1+1)-EA stays as fallback, and the Socket.IO contract to the React frontend is preserved.

---

## 1. Reconciled Gap Analysis — PDF vs Reality

| PDF claim ("missing") | Reality on disk | Status |
|---|---|---|
| `agents/manufacturing_policies.py` | EXISTS, 463 LoC, fully wired (ScriptedGreedyPolicy) | ✅ False alarm |
| `agents/manufacturing_roles.py` | EXISTS, 649 LoC | ✅ False alarm |
| `agents/meta_optimizer.py` | EXISTS, 382 LoC, LLM-integrated | ✅ False alarm |
| `agents/peer_agents.py` | `game_envs/peer_agents.py` (89 LoC, stub) | ⚠️ Stub only |
| `game_envs/supply_chain.py` | EXISTS, 746 LoC, full GLS engine | ✅ False alarm |
| `game_envs/disaster_relief.py` | EXISTS, 82 LoC, stub | ⚠️ Stub only |
| `game_envs/manufacturing_v2/*` | EXISTS, ~2000 LoC, spec-compliant | ✅ False alarm |
| `state/db.py` | EXISTS, SQLAlchemy schema, save_trace functional | ✅ False alarm |
| `api/mfg_router.py` | EXISTS, 152 LoC | ✅ False alarm |
| `requirements.txt` | Need to verify; PDF assumed missing | ⚠️ Verify |

| Real gap | Severity | Files affected |
|---|---|---|
| (1+1)-EA only — no population, no crossover, no selection | **HIGH** | `orchestrator.py`, `evolutionary_engine.py` |
| `checkpoint()` node is no-op — no DB write | **HIGH** | `orchestrator.py:683`, `state/db.py` |
| No `/api/scenario/resume` endpoint | **MED** | `main.py`, `state/db.py` |
| Supply Chain `apply_genome()` missing — mutations don't reach live env | **HIGH** | `game_envs/supply_chain.py` |
| Disaster Relief: no genome, no fitness, no policy | **MED** | `game_envs/disaster_relief.py`, new `evolution/disaster_genome.py` |
| Peer Agents: env + genome + policy all stubs | **MED** | `game_envs/peer_agents.py`, new `evolution/peer_genome.py` |
| `SemanticMutation` is hardcoded random (`evolutionary_engine.py:28` "STUB") | **LOW** (LLM fallback works) | `evolutionary_engine.py` |
| `evaluator.py` stub (`agents/evaluator.py:45` "STUB") | **LOW** | `agents/evaluator.py` |
| Multi-objective fitness vector collapsed to scalar | **MED** | `manufacturing_v2/economics.py`, `orchestrator.py` |
| No real EA library (DEAP / PyGAD) — all custom | **HIGH** (this is the headline ask) | new `agents/ea_integration.py` |
| No automated tests for EA path | **MED** | new `artifacts/backend/tests/` |

---

## 2. Library Selection: DEAP

After reviewing the EA framework comparison table in the PDF:

| Framework | Verdict |
|---|---|
| **DEAP** ✅ | Pure Python + NumPy. Pip-installable. Supports population, crossover, NSGA-II/SPEA2 multi-objective, hall-of-fame, checkpointing, parallel eval via `multiprocessing`. LGPLv3 (acceptable for SaaS). Battle-tested. |
| PyGAD | Lighter but less feature-rich — missing NSGA-II depth. OK as backup. |
| OpenEvolve | LLM-driven; expensive on Replit credits. Reserve for v2. |
| genetic-js | Node-only; backend is Python. Skip. |
| ECJ | Java; skip. |

**Decision: DEAP as the primary EA engine, with the existing (1+1) MATH path retained as a deterministic fallback for demo mode and CI.**

Rationale: DEAP gives us all the features the PDF gap analysis called for (population, crossover, multi-objective, checkpoints) in a single import. Its pure-Python nature plays well with Replit's CPU budget when population size is small (≤20).

---

## 3. Architecture: Where DEAP Plugs In

```
┌────────────────────────────────────────────────────────────────┐
│  main.py (FastAPI + Socket.IO)                                 │
│  simulation_loop() → run_one_generation(state)                 │
└──────────────────────────┬─────────────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────────────┐
│  orchestrator.py (LangGraph)                                   │
│  goal_intake → topology_init → agent_step → evaluate →         │
│  hitl_gate → mutate ──► checkpoint                             │
│                  │                                              │
│                  │  ┌─────────────────────────────┐            │
│                  └─►│  NEW: ea_integration.py     │            │
│                     │  - encode_genome(state) ────┼─► DEAP     │
│                     │  - decode_genome(ind) ◄─────┤  Individual │
│                     │  - run_one_generation()     │  + Toolbox  │
│                     │    (population, select,     │             │
│                     │     crossover, mutate)      │             │
│                     │  - fitness_fn = real env    │             │
│                     │  - hall_of_fame (elitism)   │             │
│                     │  - checkpoint to DB         │             │
│                     └─────────────────────────────┘            │
└────────────────────────────────────────────────────────────────┘

  Strategy registry (per scenario):
    manufacturing_v2 → ManufacturingGenomeStrategy (uses existing ManufacturingGenome)
    supply_chain     → SupplyChainGenomeStrategy   (uses new SupplyChainEnv.apply_genome)
    disaster_relief  → DisasterReliefStrategy      (new, stub → full)
    peer_agents      → PeerAgentsStrategy          (new, stub → full)
```

**Non-destructive contract:**
- `orchestrator.py:mutate()` reads `state["ea_engine"]` config flag (`"deap"` | `"math"` | `"llm"`).
- When `"deap"`: delegate to `ea_integration.run_one_generation(state)`.
- When `"math"` or `"llm"`: existing code path runs untouched.
- Default = `"math"` until DEAP is proven on each scenario.
- Socket.IO events (`fitness_update`, `dag_update`, etc.) emit the same shape regardless of engine.

---

## 4. Per-Simulation Pipelines

### 4.1 Manufacturing v2 (highest priority — most mature spec)
- **Genome:** existing `ManufacturingGenome` dataclass (`evolution/manufacturing_genome.py`) — 5 agent counts, 6 machine speeds, 1 order rate. Already has `mutate()`, `to_dict()`, `from_dict()`.
- **Encoding to DEAP `Individual`:** flatten dict → list of mixed int/categorical → DEAP `creator.Individual`. Categorical fields ("low"/"normal"/"high") use index mapping.
- **Fitness:** existing minibatch evaluator (`evolution/minibatch.py:evaluate_genome_minibatch`) — 3 seeds × 1000 ticks → averaged `fitness_scalar`. Return as `(weighted_fitness,)` tuple.
- **Operators:**
  - Selection: `tools.selTournament(tournsize=3)`
  - Crossover: `tools.cxTwoPoint` on integer slice, custom for categoricals (uniform crossover)
  - Mutation: existing `ManufacturingGenome.mutate()` (reuse its bounds-aware logic)
- **Population:** 8 (Replit-friendly), with elitism (`tools.HallOfFame(2)`)
- **Multi-objective option:** NSGA-II with weights `(profit, throughput, -missed_rate, -idle_ratio, machine_util)` — gated behind `state["ea_mode"] == "moo"`.

### 4.2 Supply Chain (high priority — has fitness, needs apply_genome)
- **Genome:** `supply_rate`, `transfer_amount`, `warehouse_restock_threshold`, plus from spec v2: `meta_intervention_interval`, `fleet_size`, `default_persona_risk`, `default_persona_greed`. Define a new `SupplyChainGenome` dataclass mirroring the manufacturing one.
- **NEW: `SupplyChainEnv.apply_genome(genome)`** method — currently missing. Patches `supply_rate` into supplier nodes, `fleet_size` into spawn loop, etc.
- **Fitness:** `env.gls` after T_max=500 ticks (per spec). Single seed for INTRA mode (live), minibatch (3 seeds) for INTER mode.
- **Operators:** Same DEAP toolbox as manufacturing.

### 4.3 Disaster Relief (med priority — full stub → MVP)
- **Genome (new):** `rescue_team_size`, `medical_team_size`, `logistics_agents`, `evacuation_priority_weight`, `risk_tolerance`.
- **Env logic:** Currently 82 LoC of skeleton. Need: an episode loop that ticks teams toward casualties, awards points for rescues, deducts for unattended casualties / agent loss. Treat as a simplified multi-agent A* problem.
- **Fitness:** `lives_saved / (response_time × resources_used)`.
- **Out of scope this phase:** complex pathfinding — use Manhattan distance as a stand-in.

### 4.4 Peer Agents (med priority — full stub → MVP)
- **Genome (new):** `cooperation_weight`, `defection_payoff`, `communication_budget`, `memory_depth`.
- **Env logic:** Iterated Prisoner's Dilemma / public-goods game across N peers, scaling with `memory_depth` (Tit-for-Tat with memory N).
- **Fitness:** total cooperative payoff after K rounds.
- **Out of scope this phase:** complex LLM personas — programmatic strategy table.

---

## 5. Persistence & Resume

- **Schema extension** in `state/db.py`: add `EAGeneration` table with `(run_id, gen_id, scenario, genome_json, fitness_scalar, fitness_vector_json, mutation_type, parent_gen_id, timestamp)`.
- **`checkpoint()` node** in `orchestrator.py`: actually write the row. Currently no-op.
- **`/api/scenario/resume?run_id=…`**: new endpoint in `main.py`. Loads the latest checkpoint for a run, rehydrates `orch_state`, resumes the loop.
- **Filesystem fallback:** if DB unavailable, write `state/checkpoints/{run_id}.jsonl` (append-only). Already-existing Replit DB binding is left untouched.

---

## 6. Credit-Efficient Defaults (Replit Constraints)

| Lever | Default | Reasoning |
|---|---|---|
| Population size | 8 | DEAP overhead linear in pop; 8 gives variance without burning CPU. |
| Generations per cycle | 1 per orchestrator tick | Existing pacing; DEAP runs internally per call. |
| Minibatch seeds | 3 (existing) | Spec-compliant; cheap. |
| LLM calls per generation | ≤ 1 (only meta-optimizer; Edge Agents stay programmatic in v1) | Costliest knob. |
| LLM model | `gpt-4o-mini` (existing) | Cheap. Switch to `claude-haiku-4-5` is also viable. |
| Cache fitness | Hash genome → memoize 1 generation | Identical genomes can recur in (μ+λ); avoid re-eval. |
| Deterministic seed | `random.seed(42)` toggleable via `DETERMINISTIC=1` env var | Demo mode + CI tests. |
| Fallback when LLM fails | MATH mutation (existing) | Already implemented. |

**Estimated Replit budget per 20-generation manufacturing run:**
- CPU: ~2 minutes (pop 8 × 3 seeds × 1000 ticks × 20 generations, with C-level numpy where applicable)
- LLM tokens: ≤ 20 calls × ~2k tokens in / 500 out × gpt-4o-mini = **≤ ~$0.04**

---

## 7. Phased Execution Order

| Phase | Tasks | Effort | Output |
|---|---|---|---|
| **0** | ✅ Audit + branch (done) | — | This document |
| **1** | EA core wrapper: `agents/ea_integration.py` with DEAP toolbox, encode/decode for manufacturing, strategy registry pattern | M | New module + manufacturing pipeline working under `ea_engine="deap"` |
| **2** | Persistence: wire `checkpoint()`, add `EAGeneration` table, add `/api/scenario/resume` | S | Resumeable runs |
| **3** | Supply Chain pipeline: write `SupplyChainEnv.apply_genome()`, add `SupplyChainGenomeStrategy`, register | S–M | Supply Chain runs under DEAP |
| **4** | Disaster Relief MVP: env loop + genome + strategy | M | Disaster Relief runs under DEAP |
| **5** | Peer Agents MVP: IPD env + genome + strategy | S–M | Peer Agents runs under DEAP |
| **6** | Tests: unit (encode/decode/mutate determinism), smoke (2-gen runs per scenario, assert fitness ≥ 0 and non-crashing) | M | `tests/` directory |
| **7** | Frontend hooks (optional this branch): expose engine choice in EvoDashboard, render hall-of-fame, surface Pareto front for MOO mode | M | UI control |
| **8** | Docs + deploy: requirements.txt pinning, `.env.example`, deployment notes | S | Ready-to-merge state |

---

## 8. Action Items For the Team

| # | Item | Owner | Notes |
|---|---|---|---|
| A1 | Confirm `OPENAI_API_KEY` (or `ANTHROPIC_API_KEY`) is in Replit Secrets | Backend lead | Used by `meta_optimizer.py` and `supply_chain_llm.py`. If neither set, LLM path silently falls back to MATH (already coded). |
| A2 | If switching to Claude for meta-optimizer (cheaper): set `META_OPTIMIZER_PROVIDER=anthropic` and `META_OPTIMIZER_MODEL=claude-haiku-4-5` env vars | Backend lead | Code change required in `meta_optimizer.py` (currently OpenAI-only). |
| A3 | Add `deap>=1.4`, `numpy>=1.26` to `pyproject.toml` / `requirements.txt` in `artifacts/backend` | Implementer (Claude) | Step 1 of Phase 1. |
| A4 | Decide retention policy for `EAGeneration` table (rolling 30 days? per-run cap?) | PM | Default: cap 500 rows per run_id; oldest evicted. |
| A5 | (Optional) Set up GitHub Action to run `pytest` on PR | DevOps | Replit CI not native; use Actions. |
| A6 | Confirm Disaster Relief & Peer Agents are in-scope for this milestone (PDF treats them as stubs, current frontend ignores them) | PM | If de-scoped, save effort & defer to v2. |
| A7 | Review the signature gradient + node color mapping for new "Generation N / population" UI affordances if added | Design lead | Tied to Phase 7 (optional). |

---

## 9. Non-Destructive Guarantees

- **No file deletions.** New code lives in new modules; existing code is wrapped, not replaced.
- **Feature flag everywhere.** `state["ea_engine"]` (default `"math"`) routes to old or new path. Toggle per-run, not globally.
- **Socket.IO shape preserved.** All emitted events keep their existing keys; new keys (e.g., `population_stats`) are additive.
- **Branch isolation.** All work lives on `ea-engine-v1`. `main` and `ui-upgrade-v2` are untouched.
- **Tests gate behavior.** Smoke tests assert each existing scenario still produces valid (≥ 0) fitness under both engines before phase closes.

---

## 10. Open Questions (deferred — surfaced for PM)

1. Should Pareto-front (multi-objective) results surface in the existing EvoDashboard, or in a new "Compare" panel?
2. Is there appetite for **island-model parallelism** (separate Replit container running a 2nd DEAP island)? Cheap with current architecture, costly with Replit CPU plan.
3. Do we want to enable LLM-driven **crossover** (a more expressive operator than MATH crossover) for v2? Cost is significant.

---

*Plan owner: Claude. Updates to `plans/EA_Engine_Progress.md` after each completed phase.*
