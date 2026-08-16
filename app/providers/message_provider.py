from abc import ABC, abstractmethod


class MessageProvider(ABC):
    @abstractmethod
    def send_text(
        self, chat_id: str, text: str, reply_markup: dict | None = None
    ) -> dict:
        raise NotImplementedError

    def send_chat_action(self, chat_id: str, action: str = "typing") -> dict:
        return {"ok": True, "unsupported": True, "chat_id": chat_id, "action": action}
