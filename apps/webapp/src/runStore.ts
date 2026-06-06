import { useEffect, useState } from "react";
import { apiUrl } from "./api";

export type ToolCall = {
  id: string;
  name: string;
  args?: unknown;
  state: "pending" | "ok" | "error";
  preview?: string;
  startedAt: number;
  finishedAt?: number;
};

export type RunMessage = { ts: number; text: string };

export type RunProjection = {
  runId: string;
  status: "queued" | "running" | "succeeded" | "failed";
  connection: "connecting" | "open" | "closed";
  error?: string;
  prompt?: string;
  tools: ToolCall[];
  messages: RunMessage[];
};

type ServerEvent =
  | { type: "run.started"; ts: number; prompt?: string }
  | {
      type: "model.message";
      ts: number;
      text: string;
      tool_calls: { id?: string; name?: string; args?: unknown }[];
    }
  | {
      type: "tool.result";
      ts: number;
      call_id: string;
      name?: string;
      ok: boolean;
      preview: string;
    }
  | { type: "run.finished"; ts: number; status: "succeeded" | "failed"; error?: string };

function empty(runId: string): RunProjection {
  return {
    runId,
    status: "queued",
    connection: "connecting",
    tools: [],
    messages: [],
  };
}

function reduce(p: RunProjection, e: ServerEvent): RunProjection {
  switch (e.type) {
    case "run.started":
      return { ...p, status: "running", prompt: e.prompt };
    case "model.message": {
      const messages = e.text ? [...p.messages, { ts: e.ts, text: e.text }] : p.messages;
      const tools = [...p.tools];
      for (const tc of e.tool_calls) {
        if (!tc.id || !tc.name) continue;
        if (tools.some((t) => t.id === tc.id)) continue;
        tools.push({
          id: tc.id,
          name: tc.name,
          args: tc.args,
          state: "pending",
          startedAt: e.ts,
        });
      }
      return { ...p, messages, tools };
    }
    case "tool.result": {
      const tools = p.tools.map((t) =>
        t.id === e.call_id
          ? {
              ...t,
              name: t.name || e.name || t.name,
              state: e.ok ? "ok" : "error",
              preview: e.preview,
              finishedAt: e.ts,
            }
          : t
      ) as ToolCall[];
      return { ...p, tools };
    }
    case "run.finished":
      return { ...p, status: e.status, error: e.error };
  }
}

type Listener = (p: RunProjection) => void;

class Run {
  projection: RunProjection;
  private listeners = new Set<Listener>();
  private es: EventSource | null = null;
  private closed = false;

  constructor(runId: string) {
    this.projection = empty(runId);
    this.open();
  }

  private open() {
    if (this.closed) return;
    const url = apiUrl(`/api/runs/${this.projection.runId}/events`);
    const es = new EventSource(url, { withCredentials: true });
    this.es = es;
    es.onopen = () => this.update({ ...this.projection, connection: "open" });
    es.onerror = () => {
      if (this.closed) return;
      this.update({ ...this.projection, connection: "connecting" });
    };
    const handle = (raw: MessageEvent) => {
      try {
        this.update(reduce(this.projection, JSON.parse(raw.data) as ServerEvent));
      } catch {
        /* ignore malformed frame */
      }
      if (this.projection.status === "succeeded" || this.projection.status === "failed") {
        this.close();
      }
    };
    for (const t of ["run.started", "model.message", "tool.result", "run.finished"]) {
      es.addEventListener(t, handle as EventListener);
    }
  }

  private update(next: RunProjection) {
    this.projection = next;
    for (const l of this.listeners) l(next);
  }

  subscribe(l: Listener): () => void {
    this.listeners.add(l);
    l(this.projection);
    return () => {
      this.listeners.delete(l);
    };
  }

  private close() {
    if (this.closed) return;
    this.closed = true;
    this.es?.close();
    this.es = null;
    this.update({ ...this.projection, connection: "closed" });
  }
}

const runs = new Map<string, Run>();

export function getRun(runId: string): Run {
  let r = runs.get(runId);
  if (!r) {
    r = new Run(runId);
    runs.set(runId, r);
  }
  return r;
}

export function useRun(runId: string | null | undefined): RunProjection | null {
  const [p, setP] = useState<RunProjection | null>(null);
  useEffect(() => {
    if (!runId) {
      setP(null);
      return;
    }
    return getRun(runId).subscribe(setP);
  }, [runId]);
  return p;
}
