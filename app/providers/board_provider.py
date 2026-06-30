from abc import ABC, abstractmethod


class BoardProviderError(RuntimeError):
    pass


class BoardProvider(ABC):
    @abstractmethod
    def list_users(self) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    def list_activities(self, filters: dict | None = None) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    def get_activity(self, activity_id: str) -> dict:
        raise NotImplementedError

    @abstractmethod
    def create_activity(self, payload: dict) -> dict:
        raise NotImplementedError

    @abstractmethod
    def update_activity(self, activity_id: str, payload: dict) -> dict:
        raise NotImplementedError

    @abstractmethod
    def move_activity(self, activity_id: str, status: str, reason: str | None = None) -> dict:
        raise NotImplementedError

    @abstractmethod
    def add_comment(self, activity_id: str, message: str) -> dict:
        raise NotImplementedError

    @abstractmethod
    def get_alerts(self) -> dict:
        raise NotImplementedError
