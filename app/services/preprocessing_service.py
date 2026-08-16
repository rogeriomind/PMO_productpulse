from app.database.connection import MessageRecord
from app.providers.transcription_provider import TranscriptionProvider
from app.services.audit_service import AuditService


class PreprocessingService:
    def __init__(
        self, transcription_provider: TranscriptionProvider, audit_service: AuditService
    ):
        self.transcription_provider = transcription_provider
        self.audit_service = audit_service

    def process(self, message: MessageRecord, override_text: str | None = None) -> str:
        if override_text is not None:
            return override_text.strip()

        if message.message_type == "text":
            return (message.normalized_text or "").strip()

        if message.message_type == "audio":
            self.audit_service.record(
                "audio_download_started",
                "started",
                conversation_id=message.conversation_id,
                message_id=message.id,
                payload={
                    "media_file_id": message.media_file_id,
                    "media_url": message.media_url,
                },
            )
            file_path = message.media_url or message.media_file_id or "telegram-audio"
            self.audit_service.record(
                "audio_downloaded",
                "success",
                conversation_id=message.conversation_id,
                message_id=message.id,
                payload={"file_path": file_path, "mock": True},
            )
            text = self.transcription_provider.transcribe(file_path)
            self.audit_service.record(
                "audio_transcribed",
                "success",
                conversation_id=message.conversation_id,
                message_id=message.id,
                payload={"text": text},
            )
            return text

        return ""
