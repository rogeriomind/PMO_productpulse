ALTER TABLE message_queue ADD COLUMN IF NOT EXISTS queue_locked_at TIMESTAMP;
ALTER TABLE message_queue ADD COLUMN IF NOT EXISTS debounce_started_at TIMESTAMP;
ALTER TABLE message_queue ADD COLUMN IF NOT EXISTS debounce_finished_at TIMESTAMP;
ALTER TABLE message_queue ADD COLUMN IF NOT EXISTS ia_request_started_at TIMESTAMP;
ALTER TABLE message_queue ADD COLUMN IF NOT EXISTS ia_response_received_at TIMESTAMP;
ALTER TABLE message_queue ADD COLUMN IF NOT EXISTS response_sent_at TIMESTAMP;

CREATE INDEX IF NOT EXISTS ix_message_queue_created_at ON message_queue(created_at);
CREATE INDEX IF NOT EXISTS ix_message_queue_queue_locked_at ON message_queue(queue_locked_at);
