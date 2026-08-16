# Worker Architecture

O `MessageWorker` processa transporte, não negócio.

```mermaid
sequenceDiagram
  participant Q as PostgreSQL Queue
  participant W as MessageWorker
  participant D as AgentDispatches
  participant A as API externa da IA
  participant R as Renderer
  participant C as Canal

  W->>Q: lock_next()
  W->>W: debounce / preprocessamento
  W->>W: AgentEventMapper
  W->>D: get_or_create(event_id)
  alt resposta já persistida
    D-->>W: response_payload
  else chamada nova
    W->>A: POST /v2/agent/events
    A-->>W: AgentResponse
    W->>D: save_response()
  end
  W->>R: render(channel, response)
  W->>C: send()
  W->>D: mark_delivered()
  W->>Q: mark_done_many()
```

O worker não importa serviços de Board, confirmação local, agente mockado ou repositório de ações.

Falha de entrega ao canal depois de resposta da IA não chama a IA novamente. O `response_payload` fica salvo em `agent_dispatches` e o retry repete somente o outbound.
