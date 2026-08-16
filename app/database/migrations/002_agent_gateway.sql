ALTER TABLE conversations ADD COLUMN IF NOT EXISTS provider_user_name VARCHAR(255);
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS provider_username VARCHAR(255);

ALTER TABLE messages ADD COLUMN IF NOT EXISTS provider_update_id VARCHAR(255);
ALTER TABLE messages ADD COLUMN IF NOT EXISTS event_id VARCHAR(255);
ALTER TABLE messages ADD COLUMN IF NOT EXISTS content_type VARCHAR(50);
ALTER TABLE messages ADD COLUMN IF NOT EXISTS callback_query_id VARCHAR(255);
ALTER TABLE messages ADD COLUMN IF NOT EXISTS callback_data TEXT;

UPDATE messages SET content_type = message_type WHERE content_type IS NULL;

ALTER TABLE messages ALTER COLUMN content_type SET DEFAULT 'unknown';
ALTER TABLE messages ALTER COLUMN content_type SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_messages_event_id_not_null ON messages(event_id) WHERE event_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_messages_event_id ON messages(event_id);
CREATE INDEX IF NOT EXISTS ix_messages_callback_data ON messages(callback_data);

CREATE TABLE IF NOT EXISTS agent_dispatches (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id VARCHAR(255) NOT NULL,
  conversation_id UUID NOT NULL REFERENCES conversations(id),
  request_id VARCHAR(64) NOT NULL,
  correlation_id VARCHAR(64) NOT NULL,
  thread_id VARCHAR(255) NOT NULL,
  source_message_ids JSONB,
  request_payload JSONB NOT NULL,
  response_payload JSONB,
  status VARCHAR(30) NOT NULL DEFAULT 'pending',
  attempts INT NOT NULL DEFAULT 0,
  last_error TEXT,
  agent_called_at TIMESTAMP,
  delivered_at TIMESTAMP,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_agent_dispatches_event_id UNIQUE(event_id)
);

CREATE INDEX IF NOT EXISTS ix_agent_dispatches_conversation_created_at ON agent_dispatches(conversation_id, created_at);
CREATE INDEX IF NOT EXISTS ix_agent_dispatches_status_created_at ON agent_dispatches(status, created_at);
