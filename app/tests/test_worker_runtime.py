from app.config import Settings
from app.workers.runtime import WorkerRuntime


def _settings(**overrides):
    values = {
        "app_env": "test",
        "telegram_bot_token": "",
        "agent_api_token": "token",
        "agent_api_retry_base_seconds": 0,
    }
    values.update(overrides)
    return Settings(**values)


def test_worker_runtime_reuses_process_dependencies(db):
    runtime = WorkerRuntime(_settings())

    try:
        first = runtime.create_worker(db)
        second = runtime.create_worker(db)

        assert first.agent_api_client is runtime.agent_api_client
        assert second.agent_api_client is runtime.agent_api_client
        assert first.agent_event_mapper is runtime.agent_event_mapper
        assert second.response_renderer is runtime.response_renderer
        assert first.outbound_service.providers["telegram"] is runtime.telegram_provider
        assert first.preprocessing_service.transcription_provider is (
            runtime.transcription_provider
        )
    finally:
        runtime.close()

    assert runtime.agent_http_client.is_closed
    assert runtime.telegram_http_client.is_closed
