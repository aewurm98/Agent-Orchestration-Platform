# EA Engine — Progress Log

Living document. Each completed phase appends a section below. Phase 0 = audit + branch + planning (this entry). Subsequent phases will follow `## Phase N — <Title>` format.

---

## Phase 0 — Audit, Branch, Plan  ✅ Complete

**Branch created:** `ea-engine-v1` (off `ui-upgrade-v2`, carrying uncommitted EA work forward non-destructively).

**Files read for audit (no modifications):**
- `attached_assets/Executive_Summary_1779818461672.pdf` (15 pages)
- `artifacts/screenshots/jadelynn/Manufacturing v2 Spec.md`
- `artifacts/screenshots/jadelynn/Supply Chain v2 Spec.md`
- `plans/Project_Architecture_Plan.md`, `plans/Project_Design_Plan.md`
- `artifacts/backend/agents/evolutionary_engine.py`
- (via Explore agent, terse refs) `main.py`, `orchestrator.py`, `meta_optimizer.py`, `manufacturing_roles.py`, `manufacturing_policies.py`, `supply_chain_llm.py`, `manufacturing_genome.py`, `minibatch.py`, `supply_chain.py`, `manufacturing_v2/*`, `disaster_relief.py`, `state/db.py`, `api/mfg_router.py`

**Key findings (full detail in `EA_Engine_Execution_Plan.md`):**
- ~80% of the agent simulation harness already exists; PDF "missing files" list is stale.
- True gap is **architectural**: only a (1+1)-EA, no population/crossover/selection.
- 3 sims are stubs (Disaster Relief, Peer Agents env, `apply_genome` for Supply Chain).
- Checkpoint node is a no-op; no `/resume` endpoint.

**Library choice:** **DEAP** (pure Python, pip-installable, NSGA-II support, Replit-friendly).

**Deliverables created this phase:**
- `plans/EA_Engine_Execution_Plan.md` (this is the playbook)
- `plans/EA_Engine_Progress.md` (this file)

**No code changes yet.** Implementation begins Phase 1.

### Action items raised this phase
- **A1 (Backend lead):** Verify `OPENAI_API_KEY` (or `ANTHROPIC_API_KEY`) is in Replit Secrets — required by existing meta-optimizer; absence falls back to MATH mutation silently.
- **A2 (Backend lead, optional):** Consider switching meta-optimizer to Claude Haiku 4.5 (cheaper). Code change required.
- **A3 (Claude, Phase 1):** Add `deap>=1.4`, `numpy>=1.26` to Python deps.
- **A6 (PM):** Confirm whether Disaster Relief and Peer Agents stubs are in-scope for this branch, or defer to v2.

### Replit credit baseline (pre-DEAP)
- Currently running: (1+1)-EA, manufacturing minibatch (3 seeds × 1000 ticks), 1 LLM call per generation.
- Per 20-generation run: ~30 sec CPU, ≤ ~$0.01 LLM (gpt-4o-mini).
- Target after DEAP: ~2 min CPU, ≤ ~$0.04 LLM. Trade: ~6× CPU for population diversity + crossover.

---

---

## Phase 0.5 — Conflict verification with teammate branches  ✅ Complete

User raised concern: confirm no conflicts with uncommitted teammate work before implementing.

**Branch audit:**
| Branch | Ahead/Behind | Status |
|---|---|---|
| `subrepl-o8bccxe1` | 15/15 | **Superseded** — all 9 "Fix evolutionary core" commits' concepts present in current tree under renamed identifiers (`hitl_confidence`→`confidence`/`kappa`, `edge_credit`→`edge_scores`/`GraphGRPOPrune`, `rollback`→`saved_agent_configs`/`saved_topology`). Working tree is strictly larger (+63/-4 in orchestrator.py, +200/-25 in main.py, +75/-9 in meta_optimizer.py). |
| `subrepl-yaiy69zd` | 29/9 | **Stale pre-v2 fork** — net −8332 lines, deletes `manufacturing_v2/` modules. Do NOT merge. |
| `replit-agent` | 3/29 | Tangential — "Published your App" + small commits. Ignore for EA work. |

**Working-tree changes (13 modified + 7 untracked files):** all authored by `alexwurm` himself (commits e4a7358, e14da7c, dc28c7e, 70e9bbb). Safe — your own WIP carrying forward on `ea-engine-v1`.

**Decision:** proceed with Phase 1 implementation. No cherry-picks required.

### Action items raised this phase
- **A8 (PM, when convenient):** Decide whether to archive/delete `subrepl-o8bccxe1` and `subrepl-yaiy69zd` to declutter the branch list. Not blocking.

---

*Next: Phase 3 — Supply Chain pipeline (`SupplyChainEnv.apply_genome()` + DEAP strategy).*

---

## Phase 2 — Persistence, resume lookup, engine selection  ✅ Complete

**Files added:**
- `scripts/install_python_deps.sh` (executable) — Replit-specific `uv pip install --target=…` wrapper. Run with no args to install everything in `requirements.txt`, or pass package names to install/upgrade specific deps. (Action A9.)

**Files modified:**
- `artifacts/backend/state/db.py` — added `EAGenerationModel` (new table `ea_generations`), `EAGenerationIn` dataclass, and three persistence functions: `save_ea_generation()`, `get_latest_ea_generation(run_id)`, `get_ea_generations(run_id, limit=500)`. The new table is intentionally separate from the legacy `GenerationModel` so existing `arena.db` files do not require a schema migration.
- `artifacts/backend/agents/orchestrator.py` — `checkpoint()` converted to `async def` and now writes a real `EAGeneration` row on every generation, with best-effort error handling so DB problems never stall the simulation. Captures: `run_id`, `scenario`, `gen_id`, `boundary_mode`, `mutation_strategy`, parent/child/accepted fitness, stagnation, genome JSON, fitness vector, population stats, topology diff.
- `artifacts/backend/main.py`:
  - **A10 — engine selection**: new `_resolve_engine(payload)` helper. Precedence: `payload.engine` → `payload.mutation_strategy` (legacy) → `ARENA_DEFAULT_ENGINE` env var → `"MATH"`. Allowed values `{MATH, DEAP, LLM}`. Unknown values silently fall back. `/api/scenario/start` returns the resolved `engine` in its response so the frontend can confirm.
  - **New endpoint `GET /api/scenario/resume/{run_id}`** — returns the latest checkpoint as a `resume_payload` dict. Two-step design (lookup + restart) keeps `simulation_loop` decoupled from resume logic; the frontend POSTs the payload back to `/api/scenario/start` with `resume_run_id` and `resume_payload` set.
  - **New endpoint `GET /api/ea/generations/{run_id}?limit=500`** — full generation history for charts/analytics.

**Verified:**
- `python3 -c "from state.db import EAGenerationModel, ..."` — imports clean.
- `python3 -c "from agents import orchestrator"` — clean (LangGraph deprecation warning is unrelated, pre-existing).
- `python3 -c "import main"` — clean.

**Tunable knobs added:**
| Key | Default | Meaning |
|---|---|---|
| `ARENA_DEFAULT_ENGINE` env var | `"MATH"` | Engine used when `/api/scenario/start` is called without explicit override |

**Known follow-on (Phase 2.5 — small, can ship later):**
Full warm-start wiring inside `simulation_loop`: when `active_run["resume_payload"]` is set, the orch_state init must seed `genome_config`, `generation`, `accepted_fitness`, and `parent_fitness` from the payload instead of from scratch. Currently `/api/scenario/start` accepts and stores the payload but `simulation_loop` does not yet read it back. Endpoint and DB write are live and useful right now (analytics, "view last checkpoint"); true resume needs ~20 lines added to `simulation_loop`. Tracked as A12.

### Action items closed this phase
- **A3:** ✅ deap+numpy in requirements.txt.
- **A9:** ✅ `scripts/install_python_deps.sh` ready.
- **A10:** ✅ Engine selection exposed via env var + API param (lowest-cost intuitive option per direction).

### Action items raised this phase
- **A11 (Backend lead):** `meta_optimizer.py` is OpenAI-only (uses `from openai import AsyncOpenAI`). User confirmed Anthropic key is set, but no OpenAI key. So today the `LLM` engine silently falls back to MATH. Two cheap fixes: (a) add an Anthropic backend in `meta_optimizer.py` (~30 lines, project already imports `langchain-anthropic`), or (b) set `OPENAI_API_KEY` in Replit Secrets. Recommend (a) — uses claude-haiku-4-5 which is cheaper anyway. Not blocking — MATH and DEAP both work without any LLM key.
- **A12 (Implementer, follow-on):** Wire `simulation_loop` to honor `active_run["resume_payload"]` on warm start. Needed for true resume semantics; lookup endpoint + DB writes are already live.

### Credit-efficiency note
The checkpoint write is a single SQLite INSERT per generation, ~50 µs typical. With a 20-generation manufacturing run that is 20 rows / ~1 ms total — negligible cost added.

### Bug fix (post-staging)
`ea_integration._mfg_evaluate` was calling `evaluate_genome_minibatch(g, seeds=…, ticks_per_episode=…)` but the actual signature is `(genome_dict, ticks=1000, seeds=DEFAULT_SEEDS)` and the return key is `fitness`, not `fitness_scalar`. Caught by re-reading `minibatch.py` before commit. Fixed inline. Pre-commit lesson: rely on the function signature, not on what the surrounding docs suggested.

### Staged commit summary
9 files staged (+1228 / -13 LoC) — `ea_integration.py`, `orchestrator.py`, `main.py`, `state/db.py`, `requirements.txt`, `minibatch.py` (untracked dep capture), `install_python_deps.sh`, both plan docs. Pre-existing WIP (UI components, manufacturing_v2 edits, etc.) intentionally NOT staged so the EA commit stays focused.

---

## Phase 3 — Supply Chain pipeline (apply_genome + DEAP strategy)  ✅ Complete

**Audit correction:** my Phase 0 audit said `SupplyChainEnv.apply_genome()` was missing. It actually existed but only handled `fleet_size`. The real gap was that the orchestrator's MATH mutation operated on `supply_rate`, `transfer_amount`, `warehouse_restock_threshold` — three fields the env did not read. Phase 3 makes those fields actually take effect.

**Files modified:**
- `artifacts/backend/game_envs/supply_chain.py`:
  - `GENOME_DEFAULTS` expanded from `{fleet_size}` to all 4 fields with sensible defaults.
  - `__init__` now sets `self._supply_gen_units`, `self._supply_gen_period`, `self._truck_capacity` as instance-level overrides for the module constants. Defaults preserve existing behavior.
  - `apply_genome()` extended to apply all 4 genome fields (fleet_size, supply_rate, transfer_amount, warehouse_restock_threshold). Field-level checks so partial genomes leave unset fields alone.
  - `tick_logic()` reads `self._supply_gen_period` / `self._supply_gen_units` (was: module constants).
  - Pickup logic reads `self._truck_capacity` (was: module constant).
- `artifacts/backend/agents/ea_integration.py`:
  - New `supply_chain` strategy registered: encode/decode/mutate/crossover/random_individual/evaluate. Bounded mutation per field; uniform crossover; spawn a fresh `SupplyChainEnv` for fitness eval (single-seed, 500-tick episode = spec §1.2).
  - Fitness vector returned for each evaluation: `[revenue, -capex, -opex, -penalties]` — larger-is-better in every component. Sets up cleanly for future NSGA-II without extra work.

**Verified:**
- `python3 -m agents.ea_integration` — both strategies (`manufacturing`, `supply_chain`) listed and functional.
- Encode → decode roundtrip preserves all 4 fields exactly.
- Random / mutate / crossover all produce in-bounds values (verified via `_sc_clip`).
- `warehouse_restock_threshold` is plumbed through but currently ignored by env logic (reserved for future warehouse-buying behavior).

**Genome bounds (encoded in `_SC_BOUNDS`):**
| Field | Min | Max | Notes |
|---|---|---|---|
| `fleet_size` | 1 | 10 | trucks |
| `supply_rate` | 5 | 80 | cargo units per supplier generation event |
| `transfer_amount` | 10 | 80 | max load per truck pickup |
| `warehouse_restock_threshold` | 0.2 | 0.8 | reserved; no env effect today |

**Non-destructive guarantees:**
- Defaults to existing module constants → behavior unchanged when no genome is applied.
- Existing supply chain UI, Socket.IO events, and tick loop untouched.
- Old `apply_genome(fleet_size=N)` calls still work.

### Action items raised this phase
- **A13 (Backend lead, future):** If warehouses become a build-cost decision, wire `warehouse_restock_threshold` into a `tick_logic` "if warehouse stock < threshold, dispatch a buy" rule. Currently dead.

### What's possible right now end-to-end
With `mutation_strategy=DEAP` and `scenario=supply_chain`, a /api/scenario/start call will:
1. Construct SupplyChainEnv with default genome.
2. Each orchestrator tick: DEAP runs one (μ+λ) generation — selects from pop of 8, crosses over, mutates, evaluates each child by spinning up a 500-tick episode, returns the best genome as the new `genome_config`.
3. Existing orchestrator elitism wraps this — child accepted only if it beats parent fitness.
4. Checkpoint node writes the row to `ea_generations` table.
5. Socket.IO emits `fitness_update` / `dag_update` with shape unchanged.
6. `/api/scenario/resume/{run_id}` returns the last checkpoint.

*Both prioritized scenarios (manufacturing + supply chain) now have full DEAP support.*


---

## Phase 1 — DEAP wrapper + manufacturing strategy + orchestrator dispatch  ✅ Complete

**Files added:**
- `artifacts/backend/agents/ea_integration.py` (264 LoC) — strategy registry, manufacturing strategy (encode/decode/mutate/crossover/random/evaluate), population storage with sha1 fitness cache, `run_one_generation()` entry point. Module imports cleanly with or without `deap` installed (`available()` predicate).

**Files modified (surgical):**
- `artifacts/backend/agents/orchestrator.py` — added `DEAP` branch to `mutate()` ahead of the existing `LLM` / `MATH` branches (lines ~587). Falls back to MATH on any error or unknown scenario. Existing (1+1) elitism wraps the new branch unchanged.
- `artifacts/backend/requirements.txt` — added `deap>=1.4.1`, `numpy>=1.26.0`.

**Verified:**
- Smoke test (`python3 -m agents.ea_integration`) — strategy registered, random/mutate/crossover work without throwing.
- `ea_integration.available() == True` after install.
- No file deletions. Existing MATH and LLM paths untouched.
- Socket.IO contract preserved — `genome_config`, `current_fitness`, `traces` keep their shape; new keys (`ea_population`, `ea_fitness_cache`, `population_stats`, `ea_best_vector`) are additive.

**Installation note for the team:**
Replit's PEP-668 sandbox blocked plain `pip install`. Working command for this project:
```bash
uv pip install --target=.pythonlibs/lib/python3.11/site-packages 'deap>=1.4.1' 'numpy>=1.26.0'
```
This writes into the Replit project's persistent Python site-packages already on `sys.path`. Auto-installed transitively: `cffi`, `moocore`, `platformdirs`, `pycparser`.

**Activation:** the new engine is off by default — set `state["mutation_strategy"] = "DEAP"` (e.g., via a future POST `/api/scenario/start?mutation_strategy=DEAP`, or directly in the orchestrator state init) to enable it. Default remains `"MATH"`.

### Tunable knobs (all default-safe)
| Key | Default | Meaning |
|---|---|---|
| `ea_population_size` | 8 | Individuals per generation |
| `ea_elite_keep` | 2 | μ for (μ+λ) elitism inside DEAP |
| `ea_crossover_prob` | 0.6 | Per-mating crossover rate |
| `ea_mutation_prob` | 0.4 | Per-child mutation rate |
| `ea_seed` | random | Deterministic seed (or set `ARENA_EA_SEED` env var) |
| `ea_minibatch_seeds` | `[42, 101, 777]` | Seeds for fitness evaluation |
| `ea_ticks_per_episode` | 1000 | Spec §3.1 default |

### Action items raised this phase
- **A3 (Implementer — done):** ✅ `deap>=1.4.1`, `numpy>=1.26.0` added to requirements.txt.
- **A9 (DevOps / Backend lead):** The Replit Nix env requires `uv pip install --target=.pythonlibs/...` rather than plain `pip install`. Consider committing a small `scripts/install_python_deps.sh` so onboarding is one command. (Not blocking — current install persists across sessions.)
- **A10 (Backend lead):** Decide where `mutation_strategy` should be exposed in the API. Three options: (a) `/api/scenario/start?engine=deap` query param, (b) UI toggle in EvoDashboard, (c) env var `ARENA_DEFAULT_ENGINE`. Default `MATH` until DEAP is proven across all scenarios.

### Deferred to later phases
- Multi-objective (NSGA-II) mode (`state["ea_mode"]="moo"`) — wiring exists in strategy (`evaluate` returns vector), but selection still uses scalar tournament. Will enable in Phase 3+ once Pareto-front UI is in scope.
- DEAP `Toolbox`/`creator.Individual` types not yet used — current implementation rolls its own population loop because (a) the genome is a heterogeneous dict, not a flat list of floats, and (b) it lets us reuse the existing `ManufacturingGenome.mutate()` bounds-aware logic. If we move to NSGA-II we will wrap DEAP's `tools.selNSGA2` explicitly.
- Supply-chain / disaster-relief / peer-agents strategies (Phase 3–5).


