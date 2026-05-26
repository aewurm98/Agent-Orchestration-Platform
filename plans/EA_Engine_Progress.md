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

## Phase 3.5 — Commits + final smoke test  ✅ Complete

Three commits landed on `ea-engine-v1` (newest first):

| SHA | Subject | Files | Lines |
|---|---|---|---|
| `a78cabc` | Gitignore Claude Code session artifacts | `.gitignore` | +4 |
| `eca7824` | EA engine v1: DEAP wrapper + persistence + manufacturing & supply_chain pipelines | 9 | +2024 / −358 |
| `844df14` | Capture pre-EA WIP from prior session | 17 | +2638 / −733 |

Branch is now ahead of `ui-upgrade-v2` by 3 commits. Working tree clean.

**End-to-end smoke test (post-commit):** all green.
- DEAP available, both strategies registered.
- `SupplyChainEnv.apply_genome()` propagates `supply_rate=25, transfer_amount=30` to instance overrides correctly (verified by reading back `env._supply_gen_units == 25`, `env._truck_capacity == 30`).
- `save_ea_generation` writes to `ea_generations` table cleanly.

### Action items raised this phase
- **A14 (DevOps / Backend lead):** Branch `ea-engine-v1` has 3 commits ahead of `ui-upgrade-v2`. When ready to merge: PR or fast-forward into `ui-upgrade-v2`, then merge that into `main` per existing flow. No conflicts expected with `ui-upgrade-v2` because the pre-EA WIP commit captured everything that was in the working tree.

### What's still open (deferred / non-blocking)
*Last revised 2026-05-26 — see Phase 4 below for the items now closed.*

- **A14 push:** Local fast-forward of `ea-engine-v1` → `ui-upgrade-v2` is done (both at the same SHA). Neither branch is pushed to `origin`. When ready: `git push origin ui-upgrade-v2` then merge into `main` via the existing flow.

---

## Phase 4 — A11/A12/A14 + Phase 6/7/8 + A13 MVP  ✅ Complete

Single session 2026-05-26: closed all four high-leverage items from the
next-session pickup doc, plus A13 MVP, Phase 7 (UI toggle), and Phase 8 (user docs).

### A11 — Anthropic backend in meta_optimizer  ✅
- `artifacts/backend/agents/meta_optimizer.py`:
  - Added `_resolve_provider()` precedence: `META_OPTIMIZER_PROVIDER` env var → `OPENAI_API_KEY` → `ANTHROPIC_API_KEY`.
  - Split `_get_client()` into `_get_openai_client()` + `_get_anthropic_client()` factories. Back-compat shim retained.
  - New `_chat_openai()` / `_chat_anthropic()` adapters; `query_meta_optimizer` dispatches by provider.
  - Anthropic default model: `claude-haiku-4-5`. OpenAI default: `gpt-4o-mini`. Override via `META_OPTIMIZER_MODEL`.
- **Verified:** live Anthropic call with a manufacturing digest returned a parseable genome delta (`reasoning`, `agent_counts`, `order_arrival_rate`).

### A12 — Warm-start wiring in simulation_loop  ✅
- `artifacts/backend/main.py`:
  - New `_apply_resume_payload(orch_state, run_id)` helper. Reads `active_run["resume_payload"]`, copies `gen_id`, `accepted_fitness`, `child_fitness`, `stagnation`, `mutation_strategy`, `genome_json` into orch_state. Appends a `system` trace event. Wrapped in try/except so a malformed payload never crashes the loop.
  - Called at the manufacturing orch_state init site and at the non-manufacturing orch_state init site. For non-mfg scenarios, the saved genome is also re-applied to the freshly built env via `env.apply_genome(...)`.
- **Verified:** unit-checked the cold (no payload), warm (full payload), and malformed-payload paths.

### A13 MVP — Warehouse restock threshold wired  ✅
- `artifacts/backend/game_envs/supply_chain.py`:
  - Default warehouse at (10, 10), capacity 60, **starts full** — so the restock rule is dormant by default. No GLS regression for existing demand-only sims.
  - `apply_genome()` now stores `_warehouse_restock_threshold` (clamped to [0, 1]).
  - `_assign_mission_target()` calls new `_pick_restock_warehouse(t)` — when a cargo-carrying truck would head to a demand zone, it first checks for any warehouse below threshold AND with available space. If found, diverts there. Threshold of 0.0 disables the divert.
- Full scope (spec §4.1 Director infrastructure tools — `build_infrastructure`, `mutate_persona`, `spawn_fleet`, `adjust_incentives`) deferred — out of MVP scope.

### A14 — Local fast-forward merge  ✅
- `git checkout ui-upgrade-v2 && git merge --ff-only ea-engine-v1` succeeded cleanly. Both branches at the same SHA. **Not pushed to `origin`** — see "A14 push" above.
- The earlier `git fetch --all` fatal was a stale `subrepl-o8bccxe1` SSH endpoint (the same one Phase 0.5 audit flagged). `origin` (GitHub) and `gitsafe-backup` both fetch cleanly.

### Phase 6 — Pytest suite  ✅
- `artifacts/backend/tests/` with `conftest.py`, `__init__.py`, and four test modules:
  - `test_ea_integration.py` (13 tests) — encode/decode roundtrip, bounds preservation under random/mutate/crossover (parametrized over manufacturing + supply_chain), genome hash determinism, unknown-scenario error.
  - `test_orchestrator_ea_dispatch.py` (3 tests) — `run_one_generation` returns expected keys, population stats are well-ordered, elitism guarantees best fitness non-decreasing across two generations with a deterministic evaluator (patched in place to avoid env spin-up).
  - `test_persistence.py` (4 tests) — `save_ea_generation` ↔ `get_latest_ea_generation` roundtrip, latest=highest-gen_id, None for unknown run, `get_ea_generations` ascending order.
  - `test_supply_chain_apply_genome.py` (11 tests post-A13) — fleet/supply_rate/transfer_amount propagation, partial genomes leave unset fields alone, threshold clamping, default warehouse spawn, restock divert routing, full-warehouse skip, threshold=0 disables divert.
- **Coverage:** 82% on `agents/ea_integration.py` (uncovered lines are real evaluator bodies which tests intentionally mock, and the `__main__` smoke block).
- Side change: `state/db.py` now reads `ARENA_DB_URL` env var (default unchanged) so test fixtures can isolate to a temp SQLite file. **Production behavior identical** when env var is unset.

### Phase 7 — UI engine toggle  ✅
- `artifacts/arena/src/pages/Arena.tsx`:
  - `MUTATION_STRATEGIES` now includes DEAP. New `MutationStrategy` type covers MATH | DEAP | LLM.
  - Start payload includes both `engine` (canonical) and `mutation_strategy` (legacy) fields.
  - INTRA-mode auto-reset only kicks in when LLM is selected (DEAP works in both modes).
  - Running-indicator badge gives DEAP a distinct green color (`#10b981`).
- `artifacts/arena/src/components/EvoDashboard.tsx` — `MUTATION_COLORS` extended with MATH/DEAP/LLM (both cases) so the per-generation badge isn't always gray.
- **Typecheck:** clean for the touched files. (One pre-existing TS7030 error in `GridCanvas.tsx` is unrelated.)

### Phase 8 — User-facing docs  ✅
- New `docs/EA_ENGINE.md` (~140 lines): what the EA is, how to enable each engine (UI / API / env), DEAP knob reference, LLM provider configuration, generation-log endpoint shape, resume protocol, cost expectations, troubleshooting, file index.
- `replit.md` Mutation Strategies section updated: added DEAP, mentioned auto-detect for LLM, pointer to `docs/EA_ENGINE.md`.

### Commits this phase
| SHA (tentative) | Subject |
|---|---|
| `8c4a737` | EA engine: Anthropic backend for meta_optimizer + warm-start in simulation_loop (A11+A12) |
| `063eda8` | EA engine Phase 6: pytest suite + test-isolatable DB URL |
| _next_ | A13 MVP + Phase 7 UI toggle + Phase 8 docs + progress-doc update |

### Action items raised this phase
- **A14-push (DevOps / PM):** `ea-engine-v1` and `ui-upgrade-v2` are 8 commits ahead of `origin/main`. When merging is approved: `git push origin ui-upgrade-v2`, then merge → `main` per existing flow.
- **A13 Full scope (Backend lead, future):** Director infrastructure-building tools per spec §4.1 — out of MVP scope; the MVP only handles routing.

### Test summary
```
artifacts/backend/tests/        31 passed in 1.04s
```

### Verified end-to-end
- Live Anthropic call returns a parseable manufacturing genome delta.
- Warm-start helper passes cold, warm, and malformed-payload paths.
- Default warehouse starts full → existing sims unchanged.
- Restock divert kicks in when warehouse drained below threshold.
- UI engine selector compiles cleanly (Arena.tsx + EvoDashboard.tsx).

---

## Next-session pickup — concrete handoff

> **NOTE — 2026-05-26:** All items previously listed in this section
> (A11, A12, A13, A14, Phase 6, Phase 7, Phase 8) were completed in Phase 4
> above. The detailed entries below are kept for archival reference and
> for the acceptance criteria language — useful if a future session wants
> to re-validate one of them. The only truly-open item is `A14 push`
> (see Phase 3.5 "What's still open").

Each open item below is self-contained and can be done in any order. File paths and acceptance criteria are explicit so the next session can start without re-reading 8000 lines of code.

### A11 — Add Anthropic backend to meta_optimizer  (~30 LoC, ~30 min)
**Why:** LLM mutation strategy silently falls back to MATH today because the project has only `ANTHROPIC_API_KEY` in Secrets, but `meta_optimizer.py` is OpenAI-only.

**Where:** `artifacts/backend/agents/meta_optimizer.py`
- Lines 15–35: `_get_client()` constructs an `AsyncOpenAI` — needs a fallback path.
- Lines 278–313: `query_meta_optimizer()` calls `client.chat.completions.create(...)` — needs a parallel path for Anthropic.

**Approach:**
1. Add a second factory `_get_anthropic_client()` using `anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])` (the `anthropic` package is already in requirements.txt).
2. Pick provider in `query_meta_optimizer` by env var `META_OPTIMIZER_PROVIDER` (default `"openai"`, fallback `"anthropic"` if OpenAI key missing).
3. Adapter function `_chat(messages, schema)` that returns the same shape regardless of provider — Anthropic side uses `tools=[{"input_schema": …}]` and parses `response.content[0].input`.
4. Recommend `claude-haiku-4-5` (cheap, fast) as the Anthropic default.

**Acceptance:** Setting `engine=LLM` on `/api/scenario/start` produces a valid genome delta (visible in `traces`) even when `OPENAI_API_KEY` is unset.

**Risk:** Low — falls back to MATH on any LLM error, existing behavior.

---

### A12 — True warm-start wiring  (~20 LoC, ~30 min)
**Why:** `GET /api/scenario/resume/{run_id}` returns a checkpoint and `POST /api/scenario/start` accepts `resume_payload` in the body — but `simulation_loop` never reads it.

**Where:** `artifacts/backend/main.py`
- Find the function `simulation_loop(scenario, mode, run_id)` (probably ~lines 600–800; grep for `async def simulation_loop`).
- Find where `orch_state` is first initialized inside that function (likely a dict literal or call to a helper).

**Approach:**
1. After `orch_state` is built, check `active_run.get("resume_payload")`:
   ```python
   rp = active_run.get("resume_payload")
   if rp:
       orch_state["genome_config"] = rp.get("genome_json") or orch_state["genome_config"]
       orch_state["generation"] = int(rp.get("gen_id", 0))
       orch_state["accepted_fitness"] = float(rp.get("accepted_fitness", 0.0))
       orch_state["parent_fitness"] = float(rp.get("child_fitness", 0.0))
       orch_state["mutation_strategy"] = rp.get("mutation_strategy", orch_state.get("mutation_strategy", "MATH"))
   ```
2. Emit a `system` trace event so the UI shows "resumed from generation N".

**Acceptance:** `/api/scenario/start` with `resume_payload` and `resume_run_id` set in the body produces a sim where `generation` starts at the saved gen_id (not 0), and the first `dag_update` socket event reflects the saved genome.

**Risk:** Low — wrap reading in a try/except so a malformed payload doesn't crash the loop.

---

### A13 — Wire `warehouse_restock_threshold`  (variable, design-dependent)
**Why:** The genome field is in `GENOME_DEFAULTS` and `apply_genome()` but the env has no consumer.

**Where:** `artifacts/backend/game_envs/supply_chain.py`
- `_build_initial_network()` (line 246) creates only suppliers + demand zones. No warehouses.
- The Supply Chain v2 Spec §4.1 has a `build_infrastructure` Director tool that builds warehouses dynamically.

**Two scopes to choose between:**
- **MVP (small):** Spawn a default warehouse in `_build_initial_network()` at a midpoint position. In `tick_logic`, when `warehouse.inventory / warehouse.capacity < self._warehouse_restock_threshold`, mark it as "needs restock" and prioritize truck routing to it.
- **Full (large):** Implement the full Director infrastructure-building action space from spec §4.1 (`build_infrastructure`, `mutate_persona`, `spawn_fleet`, `adjust_incentives`). This is a major env extension and probably its own milestone.

**Acceptance (MVP):** With `warehouse_restock_threshold=0.3`, trucks route to the warehouse only when its inventory drops below 30% capacity.

**Risk:** Medium — changes truck routing logic, could regress GLS scores on existing runs.

---

### A14 — Merge plan  (5 min)
**Why:** `ea-engine-v1` is 4 commits ahead of `ui-upgrade-v2`. Branch should be merged when ready.

**Approach:**
1. From `ui-upgrade-v2`: `git merge ea-engine-v1` (fast-forward — no conflicts expected because the pre-EA WIP commit captured the working tree fully).
2. Or open a PR for review: `gh pr create --base ui-upgrade-v2 --head ea-engine-v1`.
3. Eventually merge `ui-upgrade-v2` → `main` per existing flow.

**Pre-merge checklist:**
- [ ] Run `scripts/install_python_deps.sh` on the target environment.
- [ ] Sanity check: `python3 -c "from agents.ea_integration import available; print(available())"` returns `True`.
- [ ] Optional: run Phase 6 tests before merging (if delivered).

---

### Phase 6 — Tests  (~1 hr)
**Why:** No automated coverage for the EA path. Smoke tests verified the happy paths but no regression guard.

**Where to start:** Create `artifacts/backend/tests/` directory.

**Suggested files:**
1. **`test_ea_integration.py`** — pure-Python unit tests, no env spin-up:
   - `test_encode_decode_roundtrip(scenario)` — parametrized over `["manufacturing", "supply_chain"]`.
   - `test_random_individual_in_bounds(scenario)` — assert each field within bounds.
   - `test_mutate_in_bounds(scenario)` — 100 random mutations, all in bounds.
   - `test_crossover_preserves_bounds(scenario)`.
   - `test_genome_hash_stable()` — same dict → same hash.
   - `test_strategy_registry_unknown_scenario_raises()`.
2. **`test_orchestrator_ea_dispatch.py`** — integration with mocked env:
   - Mock `_mfg_evaluate` to return `(0.5, [1,2,3])` instantly.
   - Call `orchestrator.mutate(state)` with `state["mutation_strategy"]="DEAP"` — assert `state["genome_config"]` mutates, `state["population_stats"]` populated.
   - Repeat with `"MATH"` — assert no DEAP keys present.
3. **`test_persistence.py`** — DB roundtrip:
   - `init_db()` + `save_ea_generation()` + `get_latest_ea_generation()`.
4. **`test_supply_chain_apply_genome.py`** — env-level:
   - Construct env, apply genome `{fleet_size: 5, supply_rate: 25}`, assert `len(env.trucks)==5`, `env._supply_gen_units==25`.
   - Run 50 ticks, assert no exceptions.

**Acceptance:** `pytest artifacts/backend/tests/` exits 0, ≥ 80% coverage on `ea_integration.py`.

**Risk:** Low — pure additive.

---

### Phase 7 — Frontend UI toggle  (~30 min)
**Why:** Today engine choice is API-param only; users must POST to start manually.

**Where:** `artifacts/arena/src/components/EvoDashboard.tsx` (probably; grep for `mutation_strategy` to confirm).

**Approach:**
1. Add a `<select>` for engine: `MATH | DEAP | LLM`, default from current `active_run.mutation_strategy` (fetch via existing API).
2. Include the chosen value in the start payload (`{ engine: value }`).
3. Display the active engine in the dashboard header so users know which one is running.

**Acceptance:** Selecting `DEAP` then clicking Start produces a run that uses DEAP. Visible in `/api/healthz` or new `/api/scenario/status` endpoint.

**Risk:** Low — pure additive frontend.

---

### Phase 8 — User-facing docs  (~30 min)
**Why:** `plans/EA_Engine_*.md` are dev-internal. End users need a short "how to use the EA" doc.

**Where:** Either new file `docs/EA_ENGINE.md` or expand `replit.md`.

**Content outline:**
1. What is the EA — one paragraph.
2. How to enable DEAP: API param, env var, eventually UI toggle.
3. How to read `/api/ea/generations/{run_id}` for analytics.
4. Knob reference table (population size, crossover rate, etc.).
5. How to resume: GET `/api/scenario/resume/{run_id}` → POST `/api/scenario/start` with the payload.
6. Cost expectations: ~$0.04 LLM tokens per 20-gen run, ~2 min CPU.
7. Troubleshooting: deap not installed → run `scripts/install_python_deps.sh`. LLM strategy silently MATH → see A11.

**Acceptance:** A new team member can enable DEAP and read its output without reading any of the source files.

**Risk:** Zero.


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


