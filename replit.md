# Agentic Engineering Arena

A real-time evolutionary multi-agent AI orchestration platform for VC demos. Runs multi-agent simulations across game environments (supply chain, disaster relief, peer agents), evolves agent topologies via a fitness function, and visualises everything live via Socket.io.

## Run & Operate

- `pnpm --filter @workspace/arena run dev` — start React frontend (port 18277, preview at `/`)
- `cd artifacts/backend && uvicorn main:app_with_socket --host 0.0.0.0 --port 8000 --reload` — start Python FastAPI + Socket.io backend
- `pnpm run typecheck` — full TypeScript typecheck across workspace
- `pnpm run build` — build all packages

Required env vars:
- `ANTHROPIC_API_KEY` — for real LLM calls (stubbed currently, add via Secrets)

## Stack

- **Frontend**: React 18, Vite, Tailwind CSS v4, shadcn/ui, ReactFlow, Recharts, socket.io-client
- **Backend**: Python 3.11, FastAPI, python-socketio (ASGI), LangGraph, langchain-anthropic, SQLAlchemy + aiosqlite (SQLite)
- **Monorepo**: pnpm workspaces, TypeScript 5.9
- **Workflows**: `Python Backend` (port 8000) + `artifacts/arena: web` (port 18277)

## Where things live

- `artifacts/arena/src/` — React frontend
  - `context/SocketContext.tsx` — Socket.io state management (all 6 backend events)
  - `pages/Arena.tsx` — root layout: 55/45 split, top bar, tabbed right panel
  - `components/GameViewport.tsx` — HTML5 Canvas game renderer
  - `components/DAGVisualizer.tsx` — ReactFlow agent DAG
  - `components/EvoDashboard.tsx` — Recharts scatter evolution chart
  - `components/TracePanel.tsx` — streaming agent thought log
  - `components/HITLModal.tsx` — 30s countdown human-in-the-loop modal
  - `components/MetricsBar.tsx` — live cost/latency/fitness gauges
  - `components/WorkflowLibrary.tsx` — collapsible saved topology sidebar
- `artifacts/backend/` — Python FastAPI backend
  - `main.py` — FastAPI app + socketio ASGI mount, all REST + WS endpoints
  - `agents/orchestrator.py` — LangGraph StateGraph (7 nodes)
  - `agents/evolutionary_engine.py` — FitnessScore, SemanticMutation, GraphGRPOPrune, TaguchiL9Sample, GenerationLog
  - `agents/evaluator.py` — CLEAR framework scorer
  - `game_envs/` — supply_chain, disaster_relief, peer_agents (each with GridState, step, to_json)
  - `state/db.py` — SQLAlchemy/aiosqlite models: workflows, generations, traces
  - `state/redis_client.py` — optional Redis snapshot helpers

## Architecture decisions

- Python FastAPI backend runs as a standalone workflow on port 8000; Vite dev server proxies `/api` and `/socket.io` to it
- Socket.io paths added to `artifact.toml` so the Replit proxy forwards WS connections correctly
- LLM call sites are all stubbed with `# STUB: replace with LLM call` — deterministic random agents drive the simulation until Anthropic key is provided
- SQLite via aiosqlite for persistence (no provisioned DB required); Redis is optional/no-op if unavailable
- ReactFlow uses a custom circular node layout computed from angle; edge width/color encodes payload size and GRPO scores

## Product

- Start/Stop simulation with scenario selector (Supply Chain, Disaster Relief, Peer Agents)
- Live game canvas showing agents moving on a grid per tick
- Real-time DAG of agent topology with status colours (idle/active/evolved/failed) and pulse animations
- Evolution scatter chart appending each generation's fitness score
- Streaming agent thought log with role-colour coding and filtering
- HITL modal with 30-second countdown triggered by backend confidence threshold
- Workflow library sidebar for saving and reapplying topologies

## Gotchas

- Always run both workflows: Python Backend AND artifacts/arena: web
- After changing Python files, the `--reload` flag picks up changes automatically
- `ANTHROPIC_API_KEY` must be set as a Secret before enabling real LLM calls
- The `app_with_socket` export in `main.py` wraps FastAPI with the socketio ASGI app — uvicorn must point to this, not `app`
- Starlette 1.0.0 installed (required by FastAPI 0.136.x)

## User preferences

_Populate as you build_
