import { env } from "./env";

export type Message = {
  id: string;
  role: "user" | "agent";
  text: string;
  ts: number;
  agentRunId?: string;
};

export const apiUrl = (path: string) => {
  if (!env.apiBase) return path;
  return new URL(path, `${env.apiBase}/`).toString();
};

export type SessionInfo = {
  session_id: string;
};

export async function fetchMe(): Promise<SessionInfo | null> {
  try {
    const res = await fetch(apiUrl("/api/me"), { credentials: "include" });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export type ConversationSummary = {
  conversation_id: string;
  title: string;
  created_at: string;
  updated_at: string;
};

export type ConversationDetail = ConversationSummary & {
  messages: {
    message_id: string;
    role: "user" | "agent";
    content: string;
    agent_run_id: string | null;
    created_at: string;
  }[];
};

export async function fetchConversations(): Promise<ConversationSummary[]> {
  try {
    const res = await fetch(apiUrl("/api/conversations"), { credentials: "include" });
    if (!res.ok) return [];
    return await res.json();
  } catch {
    return [];
  }
}

export async function fetchConversation(id: string): Promise<ConversationDetail | null> {
  try {
    const res = await fetch(apiUrl(`/api/conversations/${id}`), {
      credentials: "include",
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export type ChatEvent =
  | { type: "conversation"; conversation_id: string; created: boolean }
  | { type: "text"; delta: string }
  | { type: "agent_spawned"; agent_run_id: string; prompt: string }
  | { type: "done" };

export type RunArtifact = {
  artifact_id: string;
  agent_run_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
};

export async function chatStream(
  conversation_id: string | null,
  content: string,
  onEvent: (ev: ChatEvent) => void
): Promise<void> {
  const res = await fetch(apiUrl("/api/chat"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ conversation_id, content }),
  });
  if (!res.ok || !res.body) {
    onEvent({ type: "done" });
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) !== -1) {
      const frame = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      for (const line of frame.split("\n")) {
        if (!line.startsWith("data: ")) continue;
        try {
          onEvent(JSON.parse(line.slice(6)) as ChatEvent);
        } catch {
          /* ignore */
        }
      }
    }
  }
  onEvent({ type: "done" });
}

export async function fetchRunArtifacts(runId: string): Promise<RunArtifact[]> {
  try {
    const res = await fetch(apiUrl(`/api/runs/${runId}/artifacts`), {
      credentials: "include",
    });
    if (!res.ok) return [];
    return await res.json();
  } catch {
    return [];
  }
}

export function artifactDownloadUrl(runId: string, artifactId: string): string {
  return apiUrl(`/api/runs/${runId}/artifacts/${artifactId}`);
}

export async function downloadArtifact(
  runId: string,
  artifactId: string,
  filename: string,
): Promise<void> {
  const res = await fetch(artifactDownloadUrl(runId, artifactId), {
    credentials: "include",
  });
  if (!res.ok) {
    throw new Error(`download failed: ${res.status}`);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  try {
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
  } finally {
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }
}
