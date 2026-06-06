-- Fully idempotent schema. Safe to re-run on every startup.
-- Tables are created with only their PK; every other column is added via
-- ALTER TABLE ... ADD COLUMN IF NOT EXISTS so that columns introduced after
-- the table was first created are always applied.

-- ── sessions ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY
);
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS last_seen  TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE sessions DROP COLUMN IF EXISTS user_id;

-- ── conversations ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS conversations (
    conversation_id TEXT PRIMARY KEY
);
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS session_id  TEXT REFERENCES sessions(session_id) ON DELETE CASCADE;
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS title       TEXT NOT NULL DEFAULT 'New chat';
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS created_at  TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS updated_at  TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE conversations DROP COLUMN IF EXISTS user_id;

-- ── conversation_messages ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS conversation_messages (
    message_id TEXT PRIMARY KEY
);
ALTER TABLE conversation_messages ADD COLUMN IF NOT EXISTS conversation_id TEXT REFERENCES conversations(conversation_id) ON DELETE CASCADE;
ALTER TABLE conversation_messages ADD COLUMN IF NOT EXISTS role            TEXT NOT NULL DEFAULT '';
ALTER TABLE conversation_messages ADD COLUMN IF NOT EXISTS content        TEXT NOT NULL DEFAULT '';
ALTER TABLE conversation_messages ADD COLUMN IF NOT EXISTS agent_run_id   TEXT;
ALTER TABLE conversation_messages ADD COLUMN IF NOT EXISTS created_at     TIMESTAMPTZ NOT NULL DEFAULT now();

-- ── agent_runs ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agent_runs (
    agent_run_id TEXT PRIMARY KEY
);
ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS session_id      TEXT REFERENCES sessions(session_id) ON DELETE CASCADE;
ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS conversation_id TEXT REFERENCES conversations(conversation_id) ON DELETE SET NULL;
ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS prompt          TEXT NOT NULL DEFAULT '';
ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS status          TEXT NOT NULL DEFAULT 'queued';
ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS created_at      TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE agent_runs DROP COLUMN IF EXISTS user_id;
ALTER TABLE agent_runs DROP COLUMN IF EXISTS company_id;
ALTER TABLE agent_runs DROP COLUMN IF EXISTS role;

-- ── artifacts ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id TEXT PRIMARY KEY
);
ALTER TABLE artifacts ADD COLUMN IF NOT EXISTS agent_run_id  TEXT REFERENCES agent_runs(agent_run_id) ON DELETE CASCADE;
ALTER TABLE artifacts ADD COLUMN IF NOT EXISTS filename      TEXT NOT NULL DEFAULT '';
ALTER TABLE artifacts ADD COLUMN IF NOT EXISTS content_type  TEXT NOT NULL DEFAULT 'application/octet-stream';
ALTER TABLE artifacts ADD COLUMN IF NOT EXISTS size_bytes    BIGINT NOT NULL DEFAULT 0;
ALTER TABLE artifacts ADD COLUMN IF NOT EXISTS object_key    TEXT NOT NULL DEFAULT '';
ALTER TABLE artifacts ADD COLUMN IF NOT EXISTS created_at    TIMESTAMPTZ NOT NULL DEFAULT now();
