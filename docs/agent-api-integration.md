# Agent API Integration

Cliente: `app/clients/agent_api_client.py`

Endpoint configurável:

```env
AGENT_API_URL=http://pmo-ai-agent-api:8010
AGENT_API_ENDPOINT=/v2/agent/events
AGENT_API_TOKEN=secret
```

Headers:

```http
Authorization: Bearer <AGENT_API_TOKEN>
Content-Type: application/json
X-Request-ID: <request_id>
X-Correlation-ID: <correlation_id>
```

Retry técnico:

- Timeout, `408`, `429` e `5xx`: retry com backoff exponencial.
- `400`, `401`, `403`, `404` e `422`: erro permanente.
- `409`: aceito como replay quando o payload respeita o contrato de resposta.

O retry preserva o mesmo `event_id`, `request_id`, `correlation_id` e payload.

Exemplo de request:

```json
{
  "event_id": "telegram:update:123456",
  "request_id": "uuid-estavel",
  "correlation_id": "uuid",
  "thread_id": "default:telegram:123456",
  "tenant_id": "default",
  "channel": "telegram",
  "message_type": "text",
  "user": {"id": "456", "name": "Rogério", "username": "rogeriomind"},
  "content": {"text": "Quero atualizar uma atividade", "callback_data": null},
  "metadata": {
    "chat_id": "123456",
    "message_id": "987",
    "provider_update_id": "123456",
    "project_id": null,
    "timezone": "America/Sao_Paulo",
    "content_type": "text",
    "source_message_ids": ["uuid-local"]
  }
}
```
