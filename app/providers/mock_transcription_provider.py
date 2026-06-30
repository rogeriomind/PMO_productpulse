from app.providers.transcription_provider import TranscriptionProvider


class MockTranscriptionProvider(TranscriptionProvider):
    def transcribe(self, file_path: str) -> str:
        return "Criar atividade para João revisar cronograma até sexta."
