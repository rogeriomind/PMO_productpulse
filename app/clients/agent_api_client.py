import logging
import random
import time
from typing import Any
from urllib.parse import urljoin

import httpx
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.contracts.agent_event import AgentEvent
from app.contracts.agent_response import AgentResponse

logger = logging.getLogger(__name__)


class AgentApiError(RuntimeError):
    retryable = False

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class AgentApiAuthenticationError(AgentApiError):
    pass


class AgentApiValidationError(AgentApiError):
    pass


class AgentApiTimeoutError(AgentApiError):
    retryable = True


class AgentApiTransientError(AgentApiError):
    retryable = True


class AgentApiContractError(AgentApiError):
    pass


class AgentApiClient:
    TRANSIENT_STATUS_CODES = {408, 429}
    PERMANENT_STATUS_CODES = {400, 401, 403, 404, 422}

    def __init__(
        self, settings: Settings | None = None, client: httpx.Client | None = None
    ):
        self.settings = settings or get_settings()
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(
                connect=5.0,
                read=self.settings.agent_api_timeout_seconds,
                write=10.0,
                pool=5.0,
            ),
            limits=httpx.Limits(
                max_connections=20,
                max_keepalive_connections=10,
                keepalive_expiry=30.0,
            ),
        )

    def send_event(self, event: AgentEvent) -> AgentResponse:
        payload = event.to_payload()
        url = self._url()
        headers = self._headers(event)
        attempts = max(1, self.settings.agent_api_retry_attempts)
        last_error: AgentApiError | None = None

        for attempt in range(1, attempts + 1):
            try:
                response = self.client.post(url, headers=headers, json=payload)
            except httpx.TimeoutException as exc:
                last_error = AgentApiTimeoutError(
                    "A API da IA não respondeu dentro do tempo limite."
                )
                if attempt >= attempts:
                    raise last_error from exc
                self._sleep(attempt)
                continue
            except httpx.HTTPError as exc:
                last_error = AgentApiTransientError(
                    "Falha técnica ao chamar a API da IA."
                )
                if attempt >= attempts:
                    raise last_error from exc
                self._sleep(attempt)
                continue

            if response.status_code == 409:
                return self._parse_response(response)

            if response.status_code in self.PERMANENT_STATUS_CODES:
                self._raise_permanent(response)

            if (
                response.status_code in self.TRANSIENT_STATUS_CODES
                or response.status_code >= 500
            ):
                last_error = AgentApiTransientError(
                    f"A API da IA retornou erro transitório HTTP {response.status_code}.",
                    status_code=response.status_code,
                )
                if attempt >= attempts:
                    raise last_error
                self._sleep(attempt)
                continue

            if response.status_code >= 400:
                raise AgentApiError(
                    f"A API da IA retornou HTTP {response.status_code}.",
                    status_code=response.status_code,
                )

            return self._parse_response(response)

        raise last_error or AgentApiTransientError(
            "Falha técnica ao chamar a API da IA."
        )

    def close(self) -> None:
        self.client.close()

    def _url(self) -> str:
        base = self.settings.agent_api_url.rstrip("/") + "/"
        endpoint = self.settings.agent_api_endpoint.lstrip("/")
        return urljoin(base, endpoint)

    def _headers(self, event: AgentEvent) -> dict[str, str]:
        token = self.settings.agent_api_token.get_secret_value()
        headers = {
            "Content-Type": "application/json",
            "X-Request-ID": event.request_id,
            "X-Correlation-ID": event.correlation_id,
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _parse_response(self, response: httpx.Response) -> AgentResponse:
        try:
            data: Any = response.json()
        except ValueError as exc:
            raise AgentApiContractError(
                "Resposta da API da IA não é JSON válido.",
                status_code=response.status_code,
            ) from exc
        try:
            return AgentResponse.model_validate(data)
        except ValidationError as exc:
            logger.info(
                "agent_contract_invalid",
                extra={"payload": {"status_code": response.status_code}},
            )
            raise AgentApiContractError(
                "Resposta da API da IA não respeita o contrato.",
                status_code=response.status_code,
            ) from exc

    def _raise_permanent(self, response: httpx.Response) -> None:
        if response.status_code in {401, 403}:
            raise AgentApiAuthenticationError(
                "Credenciais da API da IA inválidas.", status_code=response.status_code
            )
        if response.status_code in {400, 422}:
            raise AgentApiValidationError(
                "Payload rejeitado pela API da IA.", status_code=response.status_code
            )
        raise AgentApiError(
            f"A API da IA rejeitou a requisição HTTP {response.status_code}.",
            status_code=response.status_code,
        )

    def _sleep(self, attempt: int) -> None:
        delay = self.settings.agent_api_retry_base_seconds * (2 ** (attempt - 1))
        if delay > 0:
            time.sleep(delay + random.uniform(0, delay * 0.1))
