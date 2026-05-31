import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "wouter";
import { ArrowLeft, Sparkles } from "lucide-react";
import { REFERENCE_TABS, type Entry, type EntryKind, type Param } from "@/data/reference";

// ── Kind badge styling ───────────────────────────────────────────────────────
const KIND_STYLE: Record<EntryKind, string> = {
  class: "bg-[#efe9d9] text-[#6b4f2a] border-[#e0d4b8]",
  function: "bg-[#eef1ec] text-[#3f6b4a] border-[#d7e2d4]",
  method: "bg-[#eef1ec] text-[#3f6b4a] border-[#d7e2d4]",
  endpoint: "bg-[#14120e] text-[#f4f0e7] border-[#14120e]",
  event: "bg-[#efe6f1] text-[#7a4f86] border-[#e4d4ea]",
  config: "bg-[#eaeef3] text-[#3f5a7a] border-[#d4dde9]",
  enum: "bg-[#f3ece4] text-[#7a5f3f] border-[#e6dac9]",
};

const KIND_LABEL: Record<EntryKind, string> = {
  class: "class",
  function: "function",
  method: "method",
  endpoint: "endpoint",
  event: "event",
  config: "config",
  enum: "enum",
};

const METHOD_COLOR: Record<string, string> = {
  GET: "text-[#3f6b4a]",
  POST: "text-[#3f5a7a]",
  PUT: "text-[#7a5f3f]",
  PATCH: "text-[#7a5f3f]",
  DELETE: "text-[#b91c1c]",
};

// Render an endpoint signature with HTTP verbs tinted; otherwise plain mono.
function Signature({ entry }: { entry: Entry }) {
  if (!entry.signature) return null;
  if (entry.kind !== "endpoint") {
    return (
      <code className="font-mono text-[13px] text-[#14120e] break-words">
        {entry.signature}
      </code>
    );
  }
  return (
    <code className="font-mono text-[12.5px] text-[#14120e] break-words leading-relaxed">
      {entry.signature.split(/(\s+)/).map((tok, i) => {
        const color = METHOD_COLOR[tok];
        return color ? (
          <span key={i} className={`font-semibold ${color}`}>
            {tok}
          </span>
        ) : (
          <span key={i}>{tok}</span>
        );
      })}
    </code>
  );
}

function ParamRow({ p }: { p: Param }) {
  return (
    <div className="grid grid-cols-[minmax(0,200px)_minmax(0,1fr)] gap-x-4 gap-y-1 py-2.5 border-t border-[#f0eadc] first:border-t-0">
      <div className="min-w-0">
        <div className="flex items-center gap-1.5 flex-wrap">
          <code className="font-mono text-[12.5px] font-medium text-[#14120e] break-words">
            {p.name}
          </code>
          {p.required && (
            <span className="text-[9px] uppercase tracking-wide text-[#b91c1c] font-semibold">
              required
            </span>
          )}
          {p.customizable && (
            <span className="inline-flex items-center gap-0.5 text-[9px] uppercase tracking-wide text-[#7a4f86] font-semibold">
              <Sparkles className="w-2.5 h-2.5" /> tunable
            </span>
          )}
        </div>
        <code className="font-mono text-[11px] text-[#9b9285] break-words">{p.type}</code>
        {p.default !== undefined && (
          <code className="font-mono text-[11px] text-[#9b9285] block">
            default: {p.default}
          </code>
        )}
      </div>
      <p className="text-[12.5px] text-[#5c554b] leading-relaxed min-w-0">{p.desc}</p>
    </div>
  );
}

function EntryCard({ entry }: { entry: Entry }) {
  return (
    <div id={entry.id} className="scroll-mt-6 py-7 border-t border-[#ebe5d6] first:border-t-0 first:pt-1">
      <div className="flex items-center gap-2.5 flex-wrap mb-1.5">
        <h3 className="text-[17px] font-semibold text-[#14120e] tracking-tight">
          {entry.name}
        </h3>
        <span
          className={`text-[10px] font-medium px-1.5 py-0.5 rounded-md border ${KIND_STYLE[entry.kind]}`}
        >
          {KIND_LABEL[entry.kind]}
        </span>
        {entry.module && (
          <code className="font-mono text-[11px] text-[#9b9285] ml-auto">{entry.module}</code>
        )}
      </div>

      {entry.signature && (
        <div className="my-2.5 px-3 py-2 rounded-lg bg-[#faf7f0] border border-[#ebe5d6]">
          <Signature entry={entry} />
        </div>
      )}

      <p className="text-[13.5px] text-[#5c554b] leading-relaxed max-w-[68ch]">{entry.desc}</p>

      {entry.params && entry.params.length > 0 && (
        <div className="mt-4">
          <div className="text-[10px] uppercase tracking-wider text-[#9b9285] font-semibold mb-1">
            {entry.kind === "endpoint" ? "Body / params" : "Fields"}
          </div>
          <div className="px-0.5">
            {entry.params.map((p) => (
              <ParamRow key={p.name} p={p} />
            ))}
          </div>
        </div>
      )}

      {entry.returns && (
        <div className="mt-3 text-[12.5px]">
          <span className="text-[10px] uppercase tracking-wider text-[#9b9285] font-semibold mr-2">
            Returns
          </span>
          <code className="font-mono text-[12px] text-[#3f6b4a]">{entry.returns}</code>
        </div>
      )}

      {entry.customize && (
        <div className="mt-4 flex gap-2.5 px-3.5 py-3 rounded-lg bg-[#f7f2f8] border border-[#e8dcee]">
          <Sparkles className="w-3.5 h-3.5 text-[#7a4f86] shrink-0 mt-0.5" />
          <p className="text-[12.5px] text-[#5c4f5e] leading-relaxed">
            <span className="font-semibold text-[#7a4f86]">Customize · </span>
            {entry.customize}
          </p>
        </div>
      )}
    </div>
  );
}

export default function Reference() {
  const [activeTabId, setActiveTabId] = useState<string>(REFERENCE_TABS[0].id);
  const activeTab = REFERENCE_TABS.find((t) => t.id === activeTabId) ?? REFERENCE_TABS[0];
  const [activeId, setActiveId] = useState<string>(activeTab.sections[0]?.id ?? "");
  const mainRef = useRef<HTMLDivElement>(null);

  // Section ids within the active tab — drives the scroll-spy.
  const sectionIds = useMemo(() => activeTab.sections.map((s) => s.id), [activeTab]);

  useEffect(() => {
    // Reset the active section + scroll position whenever the tab changes.
    setActiveId(activeTab.sections[0]?.id ?? "");
    mainRef.current?.scrollTo({ top: 0 });
  }, [activeTabId, activeTab.sections]);

  useEffect(() => {
    const root = mainRef.current;
    if (!root) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setActiveId(visible[0].target.id);
      },
      { root, rootMargin: "0px 0px -70% 0px", threshold: 0 }
    );
    sectionIds.forEach((id) => {
      const el = document.getElementById(`section-${id}`);
      if (el) observer.observe(el);
    });
    return () => observer.disconnect();
  }, [sectionIds]);

  const scrollTo = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div className="flex flex-col h-[100dvh] w-full p-3 gap-3 text-foreground overflow-hidden font-sans">
      {/* TOP BAR — matches Arena */}
      <header className="shrink-0 tile rounded-2xl px-5 h-[60px] flex items-center justify-between z-10 shadow-sm">
        <div className="flex items-center gap-2.5">
          <Link href="/" className="flex items-center gap-2.5 cursor-pointer" data-testid="brand-home">
            <div className="w-8 h-8 blob-stretch" aria-hidden="true">
              <div className="w-full h-full overflow-hidden pixel-gradient blob" />
            </div>
            <span className="font-serif text-[26px] leading-none text-[#14120e]">AERA</span>
          </Link>
          <span className="text-[13px] font-medium text-[#9b9285] self-center">Reference</span>
          <span className="ml-2 text-[12px] text-[#9b9285] hidden md:inline">
            Developer documentation — the orchestration engine, function by function
          </span>
        </div>
        <Link
          href="/"
          className="flex items-center gap-1.5 h-9 px-4 text-xs font-semibold text-[#14120e] border border-[#ebe5d6] rounded-lg hover:border-[#14120e]/30 hover:bg-[#faf7f0] transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Back to home
        </Link>
      </header>

      {/* BODY — nav + content */}
      <div className="flex-1 flex gap-3 overflow-hidden">
        {/* LEFT NAV */}
        <nav className="tile rounded-2xl w-60 shrink-0 overflow-y-auto py-4 px-3 hidden md:block">
          {/* Tab switcher */}
          <div className="flex bg-[#faf7f0] border border-[#ebe5d6] rounded-lg p-0.5 mb-3">
            {REFERENCE_TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTabId(tab.id)}
                className={`flex-1 text-center px-2 py-1.5 rounded-md text-[11.5px] font-semibold transition-colors ${
                  activeTabId === tab.id
                    ? "bg-[#14120e] text-[#f4f0e7]"
                    : "text-[#5c554b] hover:text-[#14120e]"
                }`}
                data-testid={`reference-tab-${tab.id}`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {activeTab.sections.map((section) => (
            <div key={section.id} className="mb-1">
              <button
                onClick={() => scrollTo(`section-${section.id}`)}
                className={`w-full text-left px-3 py-1.5 rounded-lg text-[13px] font-semibold transition-colors ${
                  activeId === section.id
                    ? "bg-[#14120e] text-[#f4f0e7]"
                    : "text-[#14120e] hover:bg-[#faf7f0]"
                }`}
              >
                {section.title}
              </button>
              {activeId === section.id && (
                <div className="mt-1 mb-2 ml-2 border-l border-[#ebe5d6] pl-2">
                  {section.entries.map((e) => (
                    <button
                      key={e.id}
                      onClick={() => scrollTo(e.id)}
                      className="block w-full text-left px-2 py-1 rounded-md text-[11.5px] text-[#6b6359] hover:text-[#14120e] hover:bg-[#faf7f0] transition-colors truncate"
                    >
                      {e.name}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
        </nav>

        {/* CONTENT */}
        <main ref={mainRef} className="tile rounded-2xl flex-1 overflow-y-auto px-8 py-7">
          <div className="max-w-[820px] mx-auto">
            {/* Intro (per-tab) */}
            <div className="pb-7 mb-2 border-b border-[#ebe5d6]">
              <h1 className="font-serif text-[34px] leading-tight text-[#14120e] mb-2">
                {activeTab.introTitle}
              </h1>
              <p className="text-[14px] text-[#5c554b] leading-relaxed max-w-[68ch]">
                {activeTab.introBody}{" "}
                Items marked{" "}
                <span className="inline-flex items-center gap-0.5 text-[#7a4f86] font-semibold">
                  <Sparkles className="w-3 h-3" /> tunable
                </span>{" "}
                are the highlighted hooks.
              </p>
            </div>

            {activeTab.sections.map((section) => (
              <section key={section.id} id={`section-${section.id}`} className="scroll-mt-6 pt-8 first:pt-2">
                <h2 className="text-[22px] font-semibold text-[#14120e] tracking-tight">
                  {section.title}
                </h2>
                <p className="mt-1 mb-2 text-[13px] text-[#6b6359] leading-relaxed max-w-[70ch]">
                  {section.blurb}
                </p>
                {section.entries.map((entry) => (
                  <EntryCard key={entry.id} entry={entry} />
                ))}
              </section>
            ))}

            <div className="h-24" aria-hidden="true" />
          </div>
        </main>
      </div>
    </div>
  );
}
