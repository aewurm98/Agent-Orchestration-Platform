# Agentic Engineering Arena

Real-time evolutionary multi-agent AI orchestration platform for VC demos. Agents evolve across game environments via a Taguchi-seeded evolutionary algorithm, with live Socket.io visualisation of topology, fitness, and agent reasoning.

## Run & Operate

- `pnpm --filter @workspace/arena run dev` — React frontend (port 18277, preview at `/`)
- `cd artifacts/backend && uvicorn main:app_with_socket --host 0.0.0.0 --port 8000 --reload` — FastAPI + Socket.io backend
- `pnpm run typecheck` — full TypeScript typecheck across workspace
- `pnpm run build` — build all packages

Both workflows must be running simultaneously for the app to function.

Required env vars:
- `ANTHROPIC_API_KEY` — for real LLM calls (add via Secrets; simulation runs in scripted mode without it)

## Stack

- **Frontend**: React 18, Vite, Tailwind CSS v4, shadcn/ui, ReactFlow, Recharts, socket.io-client
- **Backend**: Python 3.11, FastAPI, python-socketio (ASGI), LangGraph, langchain-anthropic, SQLAlchemy + aiosqlite (SQLite)
- **Monorepo**: pnpm workspaces, TypeScript 5.9
- **Workflows**: `Python Backend` (port 8000) + `artifacts/arena: web` (port 18277)

## Architecture

- Python FastAPI backend runs as a standalone workflow on port 8000; Vite dev server proxies `/api` and `/socket.io` to it
- Socket.io paths added to `artifact.toml` so the Replit proxy forwards WS connections correctly
- LLM call sites are guarded — deterministic scripted agents drive simulation unless `ANTHROPIC_API_KEY` is set
- SQLite via aiosqlite for persistence (no provisioned DB required); Redis is optional/no-op if unavailable
- `app_with_socket` export in `main.py` wraps FastAPI with the socketio ASGI app — uvicorn must point to this, not `app`

## Simulation Modes

### Boundary Modes
- **INTRA** — single environment, continuous evolution within one scenario
- **INTER** — cross-environment evolution; topology transfers between scenario resets

### Mutation Strategies (engines)
- **MATH** — deterministic genome mutation via `ManufacturingGenome.mutate()`
- **DEAP** — population-based EA (selection + crossover + mutation) via `agents/ea_integration.py`
- **LLM** — LangGraph orchestrator drives mutation reasoning (auto-detects `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`)

See `docs/EA_ENGINE.md` for the end-user reference (how to enable each engine, knob table, resume protocol, cost expectations, troubleshooting).

### Scenarios
- **Supply Chain** — grid-based logistics agents
- **Disaster Relief** — grid-based emergency response agents
- **Peer Agents** — agent-to-agent negotiation
- **Manufacturing v2** — 10×10 factory floor with 6 machine types, 5 agent roles, full economics

## Manufacturing v2 (§12 spec)

The flagship demo environment. Config: `FIRST_FACTORY_CONFIG` — 10×10 grid, $8k budget, 300 tick horizon, seed 42.

**Agents**: management, procurement, operations, engineering, sales (5 roles)  
**Machines**: CNC, laser cutter, assembly bot, quality check, packaging, conveyor (6 types)  
**Fitness**: 7-component vector → scalar via weights `[0.4, 0.3, 0.15, −0.05, −0.05, 0.05, 0.05]`  
- Components (raw, no sign flip in `fitness_vector()`): throughput, quality, utilisation, cost, time, energy, safety  
- Sign convention applied only in `fitness_scalar()`  

**REST endpoints**:
- `POST /api/mfg/start` — initialises env, runs Taguchi L9 baseline, seeds edge scores
- `POST /api/mfg/step` — advances one tick; returns state delta (no grid, includes fitness_vector)
- `GET /api/mfg/state` — full environment state snapshot
- `GET /api/mfg/metrics` — current metrics dict

**Evolutionary loop** (INTRA path):
1. Taguchi L9 samples → picks best genome (`_best_genome`) and env
2. Edge scores seeded from winning topology at 0.5
3. `orch_state` initialised with `accepted_fitness`, `genome_config`, `stagnation_counter`, `fitness_history`
4. `trace_cursor = 0` set before INTER/INTRA loop starts
5. Every `GENERATION_TICKS`: `run_one_generation(orch_state)` → emits `fitness_update` with extended genome/stagnation fields
6. `accepted_fitness` is the all-time elitism best — never decreases; used as `best_fitness` in the plot

## Evolutionary Core (Task #13)

Key fixes merged from the EA core task:
- `_apply_edge_regrowth` in `orchestrator.py` — restores pruned edges to prevent topology collapse
- Duplicate LLM call removed — single `run_one_generation` call per generation boundary
- `apply_policy_override` type-coerces string inputs before applying genome overrides
- `sweep_edge_scores` moved into the evaluate node in `orchestrator.py` — runs every 5 ticks, policy-agnostic
- `trace_cursor` pattern — incremental agent thought emission without re-emitting old traces

## Where Things Live

### Frontend (`artifacts/arena/src/`)
- `context/SocketContext.tsx` — all Socket.io state; handles 6 backend events; `clearSessionState` resets mfg state on scenario switch to prevent scenario bleed
- `pages/Arena.tsx` — root layout; scenario selector; INTRA/INTER boundary mode toggle; MATH/LLM mutation strategy toggle; `interTicks` config
- `components/GameViewport.tsx` — HTML5 Canvas game renderer
- `components/DAGVisualizer.tsx` — ReactFlow agent topology DAG (edge width/colour = payload size / GRPO score)
- `components/EvoDashboard.tsx` — Recharts scatter evolution chart with genome panel
- `components/TracePanel.tsx` — streaming agent thought log with role-colour coding
- `components/HITLModal.tsx` — 30s countdown human-in-the-loop intervention modal
- `components/MetricsBar.tsx` — live cost/latency/fitness gauges
- `components/WorkflowLibrary.tsx` — collapsible saved topology sidebar
- `components/manufacturing/GridCanvas.tsx` — Manufacturing v2 grid renderer
- `components/manufacturing/ManufacturingHUD.tsx` — live factory metrics HUD (starting_budget parameterised)

### Backend (`artifacts/backend/`)
- `main.py` — FastAPI app + socketio ASGI, all REST + WS endpoints, INTER/INTRA simulation loop
- `agents/orchestrator.py` — LangGraph StateGraph (7 nodes); evaluate node runs `sweep_edge_scores`
- `agents/evolutionary_engine.py` — FitnessScore, SemanticMutation, GraphGRPOPrune, TaguchiL9Sample, GenerationLog
- `agents/evaluator.py` — CLEAR framework scorer
- `agents/manufacturing_roles.py` — Manufacturing v2 role policies; `_edge_scores`, `sweep_edge_scores`, `init_edge_scores`
- `game_envs/manufacturing_v2/env.py` — `ManufacturingEnvV2`; `step()` returns state delta (no grid)
- `game_envs/manufacturing_v2/economics.py` — `fitness_vector()` (raw signs), `fitness_scalar()`, `AgentState`
- `game_envs/manufacturing_v2/scenarios.py` — `FIRST_FACTORY_CONFIG` (§12 spec)
- `game_envs/` — supply_chain, disaster_relief, peer_agents (each with GridState, step, to_json)
- `state/db.py` — SQLAlchemy/aiosqlite models: workflows, generations, traces
- `state/redis_client.py` — optional Redis snapshot helpers (no-op if Redis unavailable)

## Gotchas

- Always run both workflows: `Python Backend` AND `artifacts/arena: web`
- After changing Python files, `--reload` picks up changes automatically
- `ANTHROPIC_API_KEY` must be set as a Secret before enabling real LLM calls
- `clearSessionState` in Arena.tsx replaces the old `setIsRunning(false)` pattern — it fully resets mfgState, mfgMetrics, and mfgAlerts to prevent cross-scenario data bleed
- `starting_budget` in ManufacturingHUD is parameterised from SocketContext (not hardcoded)
- `fitness_vector()` returns 7 raw positive components — sign weighting happens only in `fitness_scalar()`
- Starlette 1.0.0 installed (required by FastAPI 0.136.x)
- The branch is currently 2 commits ahead of origin/main — this is expected; Replit syncs on deploy

## User Preferences

_Populate as you build_
