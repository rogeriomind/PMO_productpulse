ALTER TABLE conversations ADD COLUMN IF NOT EXISTS last_delivered_ui_context_id VARCHAR(80);

ALTER TABLE agent_dispatches ADD COLUMN IF NOT EXISTS superseded_at TIMESTAMP;

CREATE INDEX IF NOT EXISTS ix_conversations_last_delivered_ui_context_id
  ON conversations(last_delivered_ui_context_id);

CREATE INDEX IF NOT EXISTS ix_agent_dispatches_status_updated_at
  ON agent_dispatches(status, updated_at);
