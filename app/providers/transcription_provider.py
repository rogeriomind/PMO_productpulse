from abc import ABC, abstractmethod


class TranscriptionProvider(ABC):
    @abstractmethod
    def transcribe(self, file_path: str) -> str:
        raise NotImplementedError
