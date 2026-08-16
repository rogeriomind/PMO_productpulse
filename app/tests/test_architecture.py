from pathlib import Path

import pytest

from app.config import Settings


ROOT = Path(__file__).resolve().parents[2]


def test_message_worker_does_not_import_local_business_services():
    worker = (ROOT / "app" / "workers" / "message_worker.py").read_text(
        encoding="utf-8"
    )
    forbidden = [
        "board_" + "service",
        "board_" + "context_service",
        "confirmation_" + "service",
        "mock_" + "agent_service",
        "pmo_" + "board_provider",
        "pmo_" + "board_auth_provider",
        "task_" + "action_repository",
        "TELEGRAM_MENU_TEXT",
        "TELEGRAM_MENU_REPLY_MARKUP",
        "_telegram_menu_flow",
        "_process_agent_input",
    ]

    for token in forbidden:
        assert token not in worker


def test_active_project_does_not_use_old_board_settings():
    forbidden = [
        "PMO_" + "API_URL",
        "PMO_" + "API_EMAIL",
        "PMO_" + "API_PASSWORD",
        "BOARD_" + "PROVIDER",
    ]
    active_files = [
        path
        for path in (ROOT / "app").rglob("*.py")
        if "tests" not in path.parts and "__pycache__" not in path.parts
    ]

    for path in active_files:
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"{token} found in {path}"


def test_production_requires_agent_token():
    with pytest.raises(ValueError):
        Settings(
            app_env="production", agent_api_url="http://agent.local", agent_api_token=""
        )


def test_production_requires_explicit_agent_url():
    with pytest.raises(ValueError):
        Settings(app_env="production", agent_api_token="token")


def test_performance_defaults_are_low_latency():
    settings = Settings(app_env="test", agent_api_token="token")

    assert settings.debounce_seconds == 1
    assert settings.debounce_max_seconds == 2
    assert settings.worker_sleep_seconds == 0.2
    assert settings.worker_backoff_max_seconds == 1
    assert settings.worker_wakeup_mode == "polling"
    assert settings.queue_notify_enabled is False
    assert settings.debounce_adaptive_enabled is False
    assert settings.worker_fallback_poll_seconds == 10
    assert settings.worker_max_drain_batch == 100
