import { useEffect, useState } from "react";
import { Link, useLocation } from "wouter";
import {
  ArrowRight,
  Dna,
  Network,
  Activity,
  ShieldCheck,
  GitBranch,
  LineChart,
  Boxes,
  Factory,
} from "lucide-react";

// ── Marketing content ─────────────────────────────────────────────────────────
// Grounded in what the platform actually does (see /docs for the real engine).

// The hero blob doubles as an interactive "spotlight" — each highlight gives it
// a distinct color identity (hueShift) and a slight tilt, and surfaces a key
// capability and the problem it solves. Clicking the blob drops you into the Arena.
const HIGHLIGHTS = [
  {
    key: "evolve",
    label: "Self-optimizing",
    title: "Systems that tune themselves",
    blurb: "Stop hand-tuning agents. Evolutionary search explores topologies and parameters and keeps whatever wins.",
    hueShift: 0,
    rot: -3,
  },
  {
    key: "derisk",
    label: "De-risked",
    title: "Catch failures before they ship",
    blurb: "Stress-test agentic systems against demand shocks, breakdowns, and adversarial conditions — and find the configurations that hold up before anything ships.",
    hueShift: 120,
    rot: 4,
  },
  {
    key: "control",
    label: "Observable",
    title: "The human is no longer in the loop",
    blurb: "Every run streams full telemetry — reasoning traces, fitness curves, and topology changes — so you can inspect what the system did and why.",
    hueShift: 210,
    rot: -5,
  },
  {
    key: "measure",
    label: "Measurable",
    title: "Reproducible, comparable runs",
    blurb: "Seeded and checkpointed end to end, so every improvement is provable — not anecdotal.",
    hueShift: 300,
    rot: 6,
  },
];

const STATS = [
  { value: "API", label: "Bring your own scenario" },
  { value: "2", label: "Stress-test scenarios" },
  { value: "2", label: "Agent modes — tune to your needs" },
  { value: "Real-time", label: "Telemetry & traces" },
];

const FEATURES = [
  {
    icon: Dna,
    title: "Evolutionary optimization",
    desc: "Each generation proposes new candidate systems — varying parameters, wiring, and policies — runs them against the simulation, and keeps the strongest performers. Every run is fully reproducible.",
  },
  {
    icon: Network,
    title: "Build, prototype, stress-test",
    desc: "Use the simulation as a sandbox to understand agent workflows — push them through demand shocks, breakdowns, and adversarial conditions, and watch where they break.",
  },
  {
    icon: GitBranch,
    title: "Bring your own scenario",
    desc: "Wire AERA into your own system over a clean API — supply the state, the evaluator, and the constraints, and evolution works on your real use case.",
  },
  {
    icon: ShieldCheck,
    title: "Full telemetry trail",
    desc: "Every decision, candidate, and evaluation is recorded — so you can replay any run and audit exactly what the system did and why.",
  },
  {
    icon: Activity,
    title: "Live observability",
    desc: "Stream agent reasoning, fitness curves, and the evolving agent ↔ tool topology over websockets as a run unfolds.",
  },
  {
    icon: LineChart,
    title: "Reproducible & checkpointed",
    desc: "Every run is seeded and checkpointed to a database — warm-start a new run from any prior generation's best genome.",
  },
];

const SCENARIOS = [
  {
    icon: Boxes,
    name: "Supply Chain",
    desc: "Supplier → warehouses → distributor → retail. The system learns to meet customer demand without stockouts, maximizing the Global Logistics Score.",
  },
  {
    icon: Factory,
    name: "Manufacturing",
    desc: "A 3-stage factory flow graph (Molding/Wire → Assembly → Packaging). Evolution tunes machine capacities, conveyor bandwidths, and maintenance for profit.",
  },
];

const STEPS = [
  { n: "01", title: "Pick a scenario", desc: "Choose an environment and the boundary mode that frames each generation." },
  { n: "02", title: "Pick an agent mode", desc: "Run with a fast heuristic agent or an LLM-driven agent — tailor the loop to your speed, cost, and reasoning needs." },
  { n: "03", title: "Watch it evolve", desc: "Fitness, traces, and topology stream live as generations compound." },
  { n: "04", title: "Keep the best", desc: "Save the winning topology to your library and warm-start from it later." },
];

function Logo() {
  return (
    <div className="flex items-center gap-2.5">
      <div className="w-8 h-8 blob-stretch" aria-hidden="true">
        <div className="w-full h-full overflow-hidden pixel-gradient blob" />
      </div>
      <span className="font-serif text-[26px] leading-none text-[#14120e]">AERA</span>
    </div>
  );
}

export default function Landing() {
  const [, navigate] = useLocation();
  const [idx, setIdx] = useState(0);
  const [paused, setPaused] = useState(false);
  const [tilt, setTilt] = useState({ x: 0, y: 0 });
  const active = HIGHLIGHTS[idx];

  // Auto-cycle the spotlight, but hold while the user is interacting with it.
  useEffect(() => {
    if (paused) return;
    const t = setInterval(() => setIdx((i) => (i + 1) % HIGHLIGHTS.length), 3800);
    return () => clearInterval(t);
  }, [paused]);

  // Cursor parallax: nudge the blob toward the pointer, normalized to [-1, 1].
  const onPointerMove = (e: React.MouseEvent) => {
    const r = e.currentTarget.getBoundingClientRect();
    setTilt({
      x: (e.clientX - (r.left + r.width / 2)) / (r.width / 2),
      y: (e.clientY - (r.top + r.height / 2)) / (r.height / 2),
    });
  };

  return (
    <div className="h-[100dvh] w-full overflow-y-auto bg-[#f4f0e7] text-[#14120e] font-sans">
      {/* NAV */}
      <header className="sticky top-0 z-20 bg-[#f4f0e7]/85 backdrop-blur-sm border-b border-[#e6dfce]">
        <div className="max-w-[1140px] mx-auto px-6 h-[68px] flex items-center justify-between">
          <Link href="/" className="cursor-pointer" data-testid="landing-logo">
            <Logo />
          </Link>
          <nav className="flex items-center gap-1 sm:gap-2">
            <a href="#platform" className="hidden sm:inline-flex h-9 items-center px-3.5 text-[13px] font-medium text-[#5c554b] rounded-lg hover:bg-white/70 transition-colors">
              Platform
            </a>
            <a href="#scenarios" className="hidden sm:inline-flex h-9 items-center px-3.5 text-[13px] font-medium text-[#5c554b] rounded-lg hover:bg-white/70 transition-colors">
              Scenarios
            </a>
            <Link
              href="/docs"
              className="hidden sm:inline-flex h-9 items-center px-3.5 text-[13px] font-medium text-[#5c554b] rounded-lg hover:bg-white/70 transition-colors"
            >
              Docs
            </Link>
            <Link
              href="/arena"
              className="ml-1 inline-flex items-center gap-1.5 h-9 px-4 text-[13px] font-semibold bg-[#14120e] text-[#f4f0e7] rounded-lg hover:bg-[#2a2620] transition-colors"
              data-testid="nav-launch"
            >
              Launch the Arena
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </nav>
        </div>
      </header>

      {/* HERO */}
      <section className="max-w-[1140px] mx-auto px-6 pt-16 pb-14 sm:pt-24 sm:pb-20 grid lg:grid-cols-[1.05fr_0.95fr] gap-12 items-center">
        <div>
          <span className="block text-[11px] font-semibold tracking-[0.18em] uppercase text-[#7a4f86]">
            Agentic Engineering Arena
          </span>
          <h1 className="mt-5 font-serif text-[44px] sm:text-[60px] leading-[1.02] tracking-tight text-[#14120e]">
            Evolve agentic systems that hold up under pressure.
          </h1>
          <p className="mt-5 text-[16px] sm:text-[17px] leading-relaxed text-[#5c554b] max-w-[34rem]">
            AERA runs your multi-agent workflows through high-fidelity simulations,
            then evolves their topology, policies, and parameters — generation over
            generation — until they perform in the conditions that matter.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Link
              href="/arena"
              className="inline-flex items-center gap-2 h-11 px-6 text-[14px] font-semibold bg-[#14120e] text-[#f4f0e7] rounded-xl hover:bg-[#2a2620] transition-colors shadow-sm"
              data-testid="hero-launch"
            >
              Launch the Arena
              <ArrowRight className="w-4 h-4" />
            </Link>
            <Link
              href="/docs"
              className="inline-flex items-center gap-2 h-11 px-6 text-[14px] font-semibold text-[#14120e] bg-white border border-[#ebe5d6] rounded-xl hover:border-[#14120e]/30 transition-colors"
            >
              Explore the engine
            </Link>
          </div>
        </div>

        {/* HERO VISUAL — an interactive spotlight built from the signature blob.
            It reacts to the cursor, takes on each highlight's color, and opens
            the Arena on click. */}
        <div
          className="flex flex-col items-center gap-4"
          onMouseEnter={() => setPaused(true)}
          onMouseLeave={() => {
            setPaused(false);
            setTilt({ x: 0, y: 0 });
          }}
        >
          <button
            type="button"
            onClick={() => navigate("/arena")}
            onMouseMove={onPointerMove}
            aria-label="Open the Arena"
            className="group relative w-[300px] h-[300px] sm:w-[360px] sm:h-[360px] flex items-center justify-center cursor-pointer"
          >
            {/* single liquid blob — tilts toward the cursor, recolors per highlight */}
            <div
              className="absolute inset-0 blob-stretch"
              style={{
                transform: `translate(${tilt.x * 14}px, ${tilt.y * 14}px) rotate(${active.rot}deg)`,
                filter: `hue-rotate(${active.hueShift}deg)`,
                transition: "transform .3s ease-out, filter .8s ease",
              }}
              aria-hidden="true"
            >
              <div className="w-full h-full overflow-hidden pixel-gradient blob shadow-xl transition-transform duration-300 group-hover:scale-[1.03]" />
            </div>
            {/* glass card — the readable capability floating on the liquid */}
            <div className="relative z-10 w-[210px] bg-white/75 backdrop-blur-md rounded-2xl border border-white/60 shadow-lg px-5 py-4 text-center pointer-events-none">
              <div className="text-[10px] uppercase tracking-widest text-[#7a4f86] font-semibold">{active.label}</div>
              <div className="mt-1.5 font-serif text-[21px] leading-[1.15] text-[#14120e]">{active.title}</div>
            </div>
            {/* open-in-arena hint on hover */}
            <span className="absolute bottom-3 left-1/2 -translate-x-1/2 inline-flex items-center gap-1 text-[11px] font-semibold text-[#14120e]/70 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
              Open in the Arena <ArrowRight className="w-3 h-3" />
            </span>
          </button>

          {/* one-line context for the active highlight (fixed height = no jump) */}
          <p className="h-10 max-w-[22rem] text-center text-[12.5px] leading-snug text-[#5c554b]">
            {active.blurb}
          </p>

          {/* selectable highlight chips */}
          <div className="flex flex-wrap gap-2 justify-center">
            {HIGHLIGHTS.map((h, i) => (
              <button
                key={h.key}
                onMouseEnter={() => setIdx(i)}
                onFocus={() => setIdx(i)}
                onClick={() => setIdx(i)}
                className={`px-3 h-8 rounded-full text-[12px] font-semibold transition-colors ${
                  i === idx
                    ? "bg-[#14120e] text-[#f4f0e7]"
                    : "bg-white border border-[#ebe5d6] text-[#5c554b] hover:border-[#14120e]/30"
                }`}
                data-testid={`spotlight-${h.key}`}
              >
                {h.label}
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* STATS */}
      <section className="border-y border-[#e6dfce] bg-white/50">
        <div className="max-w-[1140px] mx-auto px-6 py-8 grid grid-cols-2 md:grid-cols-4 gap-6">
          {STATS.map((s) => (
            <div key={s.label}>
              <div className="font-serif text-[30px] leading-none text-[#14120e]">{s.value}</div>
              <div className="mt-1.5 text-[12.5px] text-[#6b6359]">{s.label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* FEATURES */}
      <section id="platform" className="max-w-[1140px] mx-auto px-6 py-20 sm:py-24 scroll-mt-20">
        <div className="max-w-[40rem]">
          <h2 className="font-serif text-[34px] sm:text-[40px] leading-tight tracking-tight">
            A complete loop for engineering agents.
          </h2>
          <p className="mt-3 text-[15px] leading-relaxed text-[#5c554b]">
            Orchestrate, evaluate, evolve, and observe — every part of the
            optimization loop is a real, inspectable surface you can drive from
            the UI or over HTTP.
          </p>
        </div>
        <div className="mt-12 grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {FEATURES.map((f) => (
            <div key={f.title} className="tile rounded-2xl p-6 hover:shadow-md transition-shadow">
              <div className="w-10 h-10 rounded-xl bg-[#efe9d9] border border-[#e6dac9] flex items-center justify-center">
                <f.icon className="w-5 h-5 text-[#6b4f2a]" />
              </div>
              <h3 className="mt-4 text-[16px] font-semibold tracking-tight">{f.title}</h3>
              <p className="mt-2 text-[13.5px] leading-relaxed text-[#5c554b]">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* SCENARIOS */}
      <section id="scenarios" className="bg-white/50 border-y border-[#e6dfce] scroll-mt-20">
        <div className="max-w-[1140px] mx-auto px-6 py-20 sm:py-24">
          <div className="max-w-[40rem]">
            <h2 className="font-serif text-[34px] sm:text-[40px] leading-tight tracking-tight">
              Scenarios to build, prototype, and stress-test against.
            </h2>
            <p className="mt-3 text-[15px] leading-relaxed text-[#5c554b]">
              Two simulation worlds ship with AERA — sandboxes for understanding
              agent workflows, stress-testing them under pressure, and finding
              the configurations that hold up. For your own use case, plug in
              through the API.
            </p>
          </div>
          <div className="mt-12 grid md:grid-cols-2 gap-5">
            {SCENARIOS.map((s) => (
              <div key={s.name} className="tile rounded-2xl p-7 flex gap-5">
                <div className="w-12 h-12 shrink-0 rounded-xl bg-[#14120e] flex items-center justify-center">
                  <s.icon className="w-6 h-6 text-[#f4f0e7]" />
                </div>
                <div>
                  <h3 className="text-[18px] font-semibold tracking-tight">{s.name}</h3>
                  <p className="mt-2 text-[13.5px] leading-relaxed text-[#5c554b]">{s.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* HOW IT WORKS */}
      <section className="max-w-[1140px] mx-auto px-6 py-20 sm:py-24">
        <h2 className="font-serif text-[34px] sm:text-[40px] leading-tight tracking-tight max-w-[40rem]">
          From scenario to evolved system in four steps.
        </h2>
        <div className="mt-12 grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
          {STEPS.map((s) => (
            <div key={s.n} className="relative">
              <div className="font-serif text-[40px] leading-none text-[#d8cdb4]">{s.n}</div>
              <h3 className="mt-3 text-[16px] font-semibold tracking-tight">{s.title}</h3>
              <p className="mt-2 text-[13.5px] leading-relaxed text-[#5c554b]">{s.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* CTA PANEL */}
      <section className="max-w-[1140px] mx-auto px-6 pb-20 sm:pb-24">
        <div className="tile-dark rounded-3xl px-8 sm:px-14 py-14 sm:py-16 text-center relative overflow-hidden">
          <div className="absolute -top-16 -right-10 w-64 h-64 opacity-30 blur-2xl blob-stretch" aria-hidden="true">
            <div className="w-full h-full pixel-gradient blob" />
          </div>
          <h2 className="relative font-serif text-[34px] sm:text-[44px] leading-tight tracking-tight text-[#f4f0e7]">
            See a system evolve in real time.
          </h2>
          <p className="relative mt-4 text-[15px] leading-relaxed text-[#f4f0e7]/70 max-w-[34rem] mx-auto">
            Open the Arena, pick a scenario, and watch generations of agent
            systems compete, evolve, and improve — live.
          </p>
          <div className="relative mt-8 flex flex-wrap items-center justify-center gap-3">
            <Link
              href="/arena"
              className="inline-flex items-center gap-2 h-11 px-7 text-[14px] font-semibold bg-[#f4f0e7] text-[#14120e] rounded-xl hover:bg-white transition-colors"
              data-testid="cta-launch"
            >
              Launch the Arena
              <ArrowRight className="w-4 h-4" />
            </Link>
            <Link
              href="/docs"
              className="inline-flex items-center gap-2 h-11 px-7 text-[14px] font-semibold text-[#f4f0e7] border border-[#f4f0e7]/25 rounded-xl hover:bg-[#f4f0e7]/10 transition-colors"
            >
              Read the docs
            </Link>
          </div>
        </div>
      </section>

      {/* FOOTER */}
      <footer className="border-t border-[#e6dfce]">
        <div className="max-w-[1140px] mx-auto px-6 py-10 flex flex-col sm:flex-row items-center justify-between gap-4">
          <Logo />
          <p className="text-[12.5px] text-[#9b9285]">
            AERA — Agentic Engineering Arena · © 2026
          </p>
          <div className="flex items-center gap-5 text-[13px] font-medium text-[#5c554b]">
            <Link href="/arena" className="hover:text-[#14120e] transition-colors">Arena</Link>
            <Link href="/docs" className="hover:text-[#14120e] transition-colors">Docs</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
