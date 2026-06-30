CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS conversations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  provider VARCHAR(50) NOT NULL,
  provider_chat_id VARCHAR(255) NOT NULL,
  provider_user_id VARCHAR(255),
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
  UNIQUE(provider, provider_chat_id)
);

CREATE TABLE IF NOT EXISTS messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID NOT NULL REFERENCES conversations(id),
  provider VARCHAR(50) NOT NULL,
  provider_message_id VARCHAR(255),
  direction VARCHAR(20) NOT NULL,
  message_type VARCHAR(50) NOT NULL,
  raw_payload JSONB,
  normalized_text TEXT,
  media_file_id VARCHAR(255),
  media_url TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  UNIQUE(provider, provider_message_id)
);

CREATE TABLE IF NOT EXISTS message_queue (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  message_id UUID NOT NULL REFERENCES messages(id),
  conversation_id UUID NOT NULL REFERENCES conversations(id),
  status VARCHAR(30) NOT NULL DEFAULT 'pending',
  attempts INT NOT NULL DEFAULT 0,
  locked_until TIMESTAMP,
  error_message TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS debounce_buffers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID NOT NULL REFERENCES conversations(id),
  status VARCHAR(30) NOT NULL DEFAULT 'open',
  combined_text TEXT,
  last_message_at TIMESTAMP NOT NULL DEFAULT NOW(),
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS task_actions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID NOT NULL REFERENCES conversations(id),
  user_id VARCHAR(255),
  intent VARCHAR(100) NOT NULL,
  action_payload JSONB NOT NULL,
  status VARCHAR(30) NOT NULL DEFAULT 'pending_confirmation',
  confirmation_token VARCHAR(100),
  confirmed_at TIMESTAMP,
  executed_at TIMESTAMP,
  result_payload JSONB,
  error_message TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID,
  message_id UUID,
  event_type VARCHAR(100) NOT NULL,
  status VARCHAR(30) NOT NULL,
  payload JSONB,
  error_message TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_messages_conversation_created_at ON messages(conversation_id, created_at);
CREATE INDEX IF NOT EXISTS ix_message_queue_status_locked ON message_queue(status, locked_until, created_at);
CREATE INDEX IF NOT EXISTS ix_task_actions_conversation_status ON task_actions(conversation_id, status, created_at);
CREATE INDEX IF NOT EXISTS ix_audit_logs_conversation_created_at ON audit_logs(conversation_id, created_at);
