import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  downloadArtifact,
  chatStream,
  fetchConversation,
  fetchConversations,
  fetchRunArtifacts,
  fetchMe,
  type ConversationSummary,
  type Message,
  type RunArtifact,
} from "./api";
import { useRun, type RunProjection, type ToolCall } from "./runStore";
import { env } from "./env";
import spinnerUrl from "./spinner.svg";
import bauhiniaUrl from "./bauhinia.svg";
import spinnerVerbs from "./spinner_verbs.json";

const fmtTime = (ts: number) =>
  new Date(ts).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

type ActiveChat = {
  conversationId: string | null;
  title: string;
  messages: Message[];
  runId?: string;
};

const blankChat = (): ActiveChat => ({
  conversationId: null,
  title: "New chat",
  messages: [],
});

const URL_PARAM = "c";
const ARTIFACT_POLL_INTERVAL_MS = 3000;

function readUrlConvId(): string | null {
  return new URLSearchParams(window.location.search).get(URL_PARAM);
}

function writeUrlConvId(id: string | null) {
  const url = new URL(window.location.href);
  if (id) url.searchParams.set(URL_PARAM, id);
  else url.searchParams.delete(URL_PARAM);
  window.history.pushState({}, "", url.toString());
}

function replaceUrlConvId(id: string) {
  const url = new URL(window.location.href);
  url.searchParams.set(URL_PARAM, id);
  window.history.replaceState({}, "", url.toString());
}

function CityIcon({ size = 18 }: { size?: number }) {
  return <img src={bauhiniaUrl} width={size} height={size} alt="Bauhinia" />;
}

function SendIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
      <path d="M3 12 21 4l-8 18-2-8-8-2z" fill="currentColor" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
      <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function SidebarToggleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
      <rect x="3" y="4" width="18" height="16" rx="2" stroke="currentColor" strokeWidth="2" />
      <path d="M9 4v16" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}

function SpinnerWithVerb() {
  const [verb, setVerb] = useState(
    () => spinnerVerbs[Math.floor(Math.random() * spinnerVerbs.length)]
  );
  useEffect(() => {
    let id: ReturnType<typeof setTimeout>;
    const tick = () => {
      setVerb(spinnerVerbs[Math.floor(Math.random() * spinnerVerbs.length)]);
      id = setTimeout(tick, 800 + Math.random() * 1200);
    };
    id = setTimeout(tick, 800 + Math.random() * 1200);
    return () => clearTimeout(id);
  }, []);
  return (
    <span className="spinner-with-verb">
      <img src={spinnerUrl} alt="Loading" className="spinner" width={24} height={24} />
      <span className="spinner-verb">{verb}…</span>
    </span>
  );
}

function renderInline(text: string): React.ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/);
  return parts.map((p, i) => {
    if (p.startsWith("**") && p.endsWith("**")) return <strong key={i}>{p.slice(2, -2)}</strong>;
    if (p.startsWith("`") && p.endsWith("`")) return <code key={i} className="inline-code">{p.slice(1, -1)}</code>;
    return p;
  });
}

function renderMarkdown(text: string) {
  const lines = text.split("\n");
  const out: React.ReactNode[] = [];
  let listItems: string[] = [];
  let inCodeBlock = false;
  let codeLines: string[] = [];

  const flushList = () => {
    if (listItems.length === 0) return;
    out.push(
      <ul key={`ul-${out.length}`}>
        {listItems.map((li, i) => <li key={i}>{renderInline(li)}</li>)}
      </ul>
    );
    listItems = [];
  };

  const flushCode = () => {
    if (codeLines.length === 0) return;
    out.push(<pre key={`pre-${out.length}`}><code>{codeLines.join("\n")}</code></pre>);
    codeLines = [];
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    if (line.startsWith("```")) {
      if (inCodeBlock) {
        flushCode();
        inCodeBlock = false;
      } else {
        flushList();
        inCodeBlock = true;
      }
      continue;
    }

    if (inCodeBlock) {
      codeLines.push(line);
      continue;
    }

    const h1 = line.match(/^#\s+(.+)/);
    const h2 = line.match(/^##\s+(.+)/);
    const h3 = line.match(/^###\s+(.+)/);
    const li = line.match(/^[-*]\s+(.+)/);
    const ol = line.match(/^\d+\.\s+(.+)/);
    const hr = /^---+$/.test(line.trim());

    if (h1) {
      flushList();
      out.push(<h2 key={i} className="md-h1">{renderInline(h1[1])}</h2>);
    } else if (h2) {
      flushList();
      out.push(<h3 key={i} className="md-h2">{renderInline(h2[1])}</h3>);
    } else if (h3) {
      flushList();
      out.push(<h4 key={i} className="md-h3">{renderInline(h3[1])}</h4>);
    } else if (li || ol) {
      listItems.push((li || ol)![1]);
    } else if (hr) {
      flushList();
      out.push(<hr key={i} className="md-hr" />);
    } else {
      flushList();
      const content = renderInline(line);
      out.push(<div key={i} className={line.trim() ? "" : "md-blank"}>{line.trim() ? content : " "}</div>);
    }
  }

  flushList();
  flushCode();
  return out;
}

function formatArgs(args: unknown): string {
  if (!args || typeof args !== "object") return "";
  return Object.entries(args as Record<string, unknown>)
    .map(([k, v]) => {
      const s = typeof v === "string" ? v : JSON.stringify(v);
      const trimmed = s.length > 80 ? s.slice(0, 80) + "…" : s;
      return `${k}=${trimmed}`;
    })
    .join(", ");
}

const STATE_GLYPH: Record<ToolCall["state"], string> = {
  pending: "⟳",
  ok: "✓",
  error: "✗",
};

function ToolRow({ t }: { t: ToolCall }) {
  const dur = t.finishedAt ? `${t.finishedAt - t.startedAt}ms` : "running…";
  return (
    <div className={`tool tool-${t.state}`}>
      <div className="tool-line">
        <span className="tool-glyph">{STATE_GLYPH[t.state]}</span>
        <span className="tool-name">{t.name}</span>
        <span className="tool-args">{formatArgs(t.args)}</span>
        <span className="tool-dur">{dur}</span>
      </div>
      {t.preview && <div className="tool-preview">{t.preview}</div>}
    </div>
  );
}

function RunPane({ run }: { run: RunProjection }) {
  const [artifacts, setArtifacts] = useState<RunArtifact[]>([]);
  useEffect(() => {
    let done = false;
    let timer: ReturnType<typeof setInterval> | null = null;

    const load = async () => {
      const next = await fetchRunArtifacts(run.runId);
      if (done) return;
      setArtifacts(next);
      if (next.length > 0 && timer) {
        clearInterval(timer);
        timer = null;
      }
    };

    if (run.status === "succeeded") {
      load();
      timer = setInterval(load, ARTIFACT_POLL_INTERVAL_MS);
    }

    return () => {
      done = true;
      if (timer) clearInterval(timer);
    };
  }, [run.runId, run.status]);

  type Item =
    | { kind: "tool"; ts: number; tool: ToolCall }
    | { kind: "message"; ts: number; text: string };
  const timeline: Item[] = useMemo(() => {
    const items: Item[] = [
      ...run.tools.map<Item>((tool) => ({ kind: "tool", ts: tool.startedAt, tool })),
      ...run.messages.map<Item>((m) => ({ kind: "message", ts: m.ts, text: m.text })),
    ];
    items.sort((a, b) => a.ts - b.ts);
    return items;
  }, [run.tools, run.messages]);

  return (
    <aside className="run-pane">
      <div className="run-head">
        <span className="run-title">City intelligence agent</span>
        <span className={`run-status status-${run.status}`}>{run.status}</span>
      </div>
      <div className="run-body">
        {timeline.length === 0 ? (
          <div className="run-empty">waiting for first event…</div>
        ) : (
          timeline.map((item, i) =>
            item.kind === "tool" ? (
              <ToolRow key={`t-${item.tool.id}`} t={item.tool} />
            ) : (
              <div key={`m-${i}-${item.ts}`} className="run-message">
                {renderMarkdown(item.text)}
              </div>
            )
          )
        )}
        {run.error && <div className="run-error">{run.error}</div>}
        {artifacts.length > 0 && (
          <div className="run-artifacts">
            <div className="run-artifacts-title">Outputs</div>
            <div className="run-artifacts-list">
              {artifacts.map((a) => (
                <button
                  key={a.artifact_id}
                  type="button"
                  className="run-artifact-link"
                  onClick={() => {
                    downloadArtifact(run.runId, a.artifact_id, a.filename).catch(
                      (err) => console.error("artifact download failed", err),
                    );
                  }}
                >
                  {a.filename}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}

export default function App() {
  const [active, setActive] = useState<ActiveChat>(() => blankChat());
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const refreshConversations = useCallback(async () => {
    const list = await fetchConversations();
    setConversations(list);
  }, []);

  const pendingRef = useRef<{
    originId: string;
    agentId: string;
    agentText: string;
    agentRunId?: string;
    runId?: string;
  } | null>(null);

  const loadConversation = useCallback(async (id: string) => {
    const detail = await fetchConversation(id);
    if (!detail) {
      setActive(blankChat());
      writeUrlConvId(null);
      return;
    }
    const messages: Message[] = detail.messages.map((m) => ({
      id: m.message_id,
      role: m.role,
      text: m.content,
      ts: new Date(m.created_at).getTime(),
      agentRunId: m.agent_run_id ?? undefined,
    }));
    const pending = pendingRef.current;
    if (pending && pending.originId === detail.conversation_id) {
      messages.push({
        id: pending.agentId,
        role: "agent",
        text: pending.agentText,
        ts: Date.now(),
        agentRunId: pending.agentRunId,
      });
    }
    const lastRun =
      pending && pending.originId === detail.conversation_id
        ? pending.runId ?? [...messages].reverse().find((m) => m.agentRunId)?.agentRunId
        : [...messages].reverse().find((m) => m.agentRunId)?.agentRunId;
    setActive({
      conversationId: detail.conversation_id,
      title: detail.title,
      messages,
      runId: lastRun,
    });
  }, []);

  useEffect(() => {
    (async () => {
      const me = await fetchMe();
      if (me) {
        await refreshConversations();
        const urlId = readUrlConvId();
        if (urlId) await loadConversation(urlId);
      }
    })();
  }, [refreshConversations, loadConversation]);

  useEffect(() => {
    const onPop = () => {
      const id = readUrlConvId();
      if (id) loadConversation(id);
      else setActive(blankChat());
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, [loadConversation]);

  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [active.messages.length]);

  const run = useRun(active.runId);

  const pendingAgentId = pendingRef.current?.agentId;
  const composerBusy =
    busy &&
    !!pendingAgentId &&
    active.messages.some((m) => m.id === pendingAgentId);

  async function send() {
    const text = input.trim();
    if (!text || composerBusy) return;
    setInput("");
    setBusy(true);

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: "user",
      text,
      ts: Date.now(),
    };
    const agentId = crypto.randomUUID();
    const originId = active.conversationId ?? `pending:${crypto.randomUUID()}`;
    const myPending = { originId, agentId, agentText: "" } as {
      originId: string;
      agentId: string;
      agentText: string;
      runId?: string;
      agentRunId?: string;
    };
    pendingRef.current = myPending;

    setActive((c) => ({
      ...c,
      messages: [
        ...c.messages,
        userMsg,
        { id: agentId, role: "agent", text: "", ts: Date.now() },
      ],
    }));

    const applyIfCurrent = (updater: (c: ActiveChat) => ActiveChat) => {
      if (pendingRef.current !== myPending) return;
      setActive((c) => {
        if (c.conversationId && c.conversationId !== myPending.originId) return c;
        return updater(c);
      });
    };

    await chatStream(active.conversationId, text, (ev) => {
      if (ev.type === "conversation") {
        if (ev.created) {
          replaceUrlConvId(ev.conversation_id);
          refreshConversations();
        }
        if (myPending.originId.startsWith("pending:")) {
          myPending.originId = ev.conversation_id;
        }
        applyIfCurrent((c) => ({ ...c, conversationId: ev.conversation_id }));
      } else if (ev.type === "text") {
        myPending.agentText += ev.delta;
        applyIfCurrent((c) => ({
          ...c,
          messages: c.messages.map((m) =>
            m.id === myPending.agentId ? { ...m, text: m.text + ev.delta } : m
          ),
        }));
      } else if (ev.type === "agent_spawned") {
        myPending.runId = ev.agent_run_id;
        myPending.agentRunId = ev.agent_run_id;
        applyIfCurrent((c) => ({
          ...c,
          runId: ev.agent_run_id,
          messages: c.messages.map((m) =>
            m.id === myPending.agentId
              ? { ...m, agentRunId: ev.agent_run_id }
              : m
          ),
        }));
      } else if (ev.type === "done") {
        if (pendingRef.current === myPending) {
          pendingRef.current = null;
          setBusy(false);
        }
        refreshConversations();
      }
    });
  }

  function onKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  function startNewChat() {
    setActive(blankChat());
    writeUrlConvId(null);
  }

  function openConversation(id: string) {
    if (id === active.conversationId) return;
    writeUrlConvId(id);
    loadConversation(id);
  }

  return (
    <div className="app">
      <aside className={`sidebar ${sidebarOpen ? "" : "collapsed"}`}>
        <div className="sidebar-brand">
          <div className="sidebar-brand-mark">
            <CityIcon size={16} />
          </div>
          {sidebarOpen && (
            <div className="sidebar-brand-text">
              <span className="sidebar-brand-title">{env.appTitle}</span>
              <span className="sidebar-brand-sub">{env.appSubtitle}</span>
            </div>
          )}
        </div>
        <div className="sidebar-head">
          {sidebarOpen && (
            <button className="new-chat" onClick={startNewChat}>
              <PlusIcon />
              <span>New chat</span>
            </button>
          )}
          <button
            className="icon-btn"
            onClick={() => setSidebarOpen((s) => !s)}
            aria-label="Toggle sidebar"
            title="Toggle sidebar"
          >
            <SidebarToggleIcon />
          </button>
        </div>
        {sidebarOpen && (
          <div className="chat-list">
            <div className="chat-list-label">History</div>
            {conversations.length === 0 && (
              <div className="chat-item-sub" style={{ padding: "8px 10px" }}>
                No chats yet
              </div>
            )}
            {conversations.map((c) => (
              <button
                key={c.conversation_id}
                className={`chat-item ${
                  c.conversation_id === active.conversationId ? "active" : ""
                }`}
                onClick={() => openConversation(c.conversation_id)}
                title={c.title}
              >
                <div className="chat-item-title">{c.title || "Untitled"}</div>
                <div className="chat-item-sub">
                  {fmtTime(new Date(c.updated_at).getTime())}
                </div>
              </button>
            ))}
          </div>
        )}
      </aside>

      <div className="main">
        <div className={`workspace ${run ? "split" : ""}`}>
          <main className="messages">
            {active.messages.map((m) => (
              <div key={m.id} className={`row ${m.role}`}>
                <div className={`bubble ${m.role}`}>
                  {m.role === "agent" && !m.text ? (
                    <SpinnerWithVerb />
                  ) : (
                    renderMarkdown(m.text)
                  )}
                  <span className="time">{fmtTime(m.ts)}</span>
                </div>
              </div>
            ))}
            <div ref={endRef} />
          </main>

          {run && <RunPane run={run} />}
        </div>

        <div className="composer">
          <div className="composer-inner">
            <div className="composer-icon">
              <CityIcon size={16} />
            </div>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKey}
              placeholder="Ask about city data, districts, demographics, or planning…"
              disabled={composerBusy}
            />
            <button onClick={send} disabled={composerBusy || !input.trim()} aria-label="Send">
              <SendIcon />
              <span>发送</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
