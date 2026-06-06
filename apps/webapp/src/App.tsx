import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  downloadArtifact,
  chatStream,
  fetchConversation,
  fetchConversations,
  fetchRunArtifacts,
  fetchUsers,
  fetchMe,
  login,
  type ConversationSummary,
  type Message,
  type RunArtifact,
  type UserOption,
} from "./api";
import { useRun, type RunProjection, type ToolCall } from "./runStore";
import { env } from "./env";
import spinnerUrl from "./spinner.svg";
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

function BoltIcon({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <path d="M13 2 4 14h7l-1 8 9-12h-7l1-8z" fill="currentColor" />
    </svg>
  );
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

function renderBubbleText(text: string) {
  return text.split("\n").map((line, i) => {
    const m = line.match(/^\*\*([^*]+):\*\*\s*(.*)$/);
    if (m) {
      return (
        <div key={i}>
          <strong>{m[1]}:</strong> {m[2]}
        </div>
      );
    }
    return <div key={i}>{line || " "}</div>;
  });
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
        <span className="run-title">Research agent</span>
        <span className={`run-status status-${run.status}`}>{run.status}</span>
      </div>
      <div className="run-sub">
        run {run.runId} · <span className={`run-conn conn-${run.connection}`}>{run.connection}</span>
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
                {renderBubbleText(item.text)}
              </div>
            )
          )
        )}
        {run.error && <div className="run-error">{run.error}</div>}
        {artifacts.length > 0 && (
          <div className="run-artifacts">
            <div className="run-artifacts-title">Artifacts</div>
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
  const [users, setUsers] = useState<UserOption[]>([]);
  const [currentUserId, setCurrentUserId] = useState<string>("");

  const refreshConversations = useCallback(async () => {
    const list = await fetchConversations();
    setConversations(list);
  }, []);

  // Holds the in-flight assistant turn so we can re-attach it after the user
  // navigates away and back. The backend only persists the assistant message
  // once the stream completes (apps/backend/services/chat.py), so without this
  // a mid-stream `loadConversation` would show only the user message.
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
      // Not found / not owned — fall back to blank chat and clear URL
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
    // If a stream is still in flight for this conversation, the assistant
    // turn isn't in the DB yet — splice the local in-flight copy in so the
    // user sees what's accumulated so far.
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
      const list = await fetchUsers();
      setUsers(list);
      const me = await fetchMe();
      let userId = me?.user_id;
      if (!userId && list[0]) {
        const sess = await login(list[0].user_id);
        userId = sess?.user_id;
      }
      if (userId) {
        setCurrentUserId(userId);
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

  async function switchUser(user_id: string) {
    const sess = await login(user_id);
    if (sess) {
      // The in-flight stream belonged to the previous user's session; drop
      // its local state so it can't re-attach to a chat the new user owns.
      pendingRef.current = null;
      setBusy(false);
      setCurrentUserId(sess.user_id);
      setActive(blankChat());
      writeUrlConvId(null);
      await refreshConversations();
    }
  }

  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [active.messages.length]);

  const run = useRun(active.runId);
  // Composer is busy only for the chat the in-flight send originated in.
  // We detect "this chat owns the pending send" by the agent placeholder's id
  // being present in this chat's message list — survives navigation away/back
  // because loadConversation re-splices it from pendingRef.
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
    // Closure-captured so concurrent sends (if any) can't corrupt each other.
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

    // Apply to the active view only if it's still the originating chat AND
    // this pending hasn't been superseded by a newer send.
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
        <header className="header">
          <div />
          <div className="user-switcher">
            <label htmlFor="user-select">Acting as</label>
            <select
              id="user-select"
              value={currentUserId}
              onChange={(e) => switchUser(e.target.value)}
            >
              {users.length === 0 && <option value="">(no users)</option>}
              {users.map((u) => (
                <option key={u.user_id} value={u.user_id}>
                  {u.company_name} — {u.role} ({u.user_id})
                </option>
              ))}
            </select>
          </div>
          <div className="brand">
            <div className="brand-text right">
              <span className="brand-title">{env.appTitle}</span>
              <span className="brand-sub">{env.appSubtitle}</span>
            </div>
            <div className="brand-mark">
              <BoltIcon />
            </div>
          </div>
        </header>

        <div className={`workspace ${run ? "split" : ""}`}>
          <main className="messages">
            {active.messages.map((m) => (
              <div key={m.id} className={`row ${m.role}`}>
                <div className={`bubble ${m.role}`}>
                  {m.role === "agent" && !m.text ? (
                    <SpinnerWithVerb />
                  ) : (
                    renderBubbleText(m.text)
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
              <BoltIcon size={16} />
            </div>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKey}
              placeholder="Ask about plant performance, maintenance, or safety…"
              disabled={composerBusy}
            />
            <button onClick={send} disabled={composerBusy || !input.trim()} aria-label="Send">
              <SendIcon />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
