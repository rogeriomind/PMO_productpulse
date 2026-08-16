from abc import ABC, abstractmethod


class MessageProvider(ABC):
    @abstractmethod
    def send_text(
        self, chat_id: str, text: str, reply_markup: dict | None = None
    ) -> dict:
        raise NotImplementedError
