# PMO Agent Message Pipeline MVP

Backend FastAPI para receber mensagens de canais, normalizar eventos, aplicar rate limit e debounce, persistir tudo em PostgreSQL, processar em worker e integrar com a API do PMO Board. A inteligência é mockada por contrato e pode ser trocada depois por LangGraph, LangChain, OpenAI, Azure OpenAI ou outro motor.

## Arquitetura

Fluxo principal:

1. `POST /webhooks/telegram` ou `POST /webhooks/whatsapp` recebe o payload.
2. `InboundNormalizer` valida e normaliza a mensagem.
3. `InboundService` aplica rate limit, persiste conversa/mensagem e enfileira no PostgreSQL.
4. `MessageWorker` consome `message_queue` com lease, retry e debounce.
5. `PreprocessingService` usa texto direto ou transcrição mockada para áudio.
6. `MockAgentService` retorna JSON estruturado com intenção e `board_action`.
7. `BoardService` consulta o PMO Board para queries ou cria `task_action` pendente para alterações.
8. `ConfirmationService` executa somente após o usuário confirmar.
9. `OutboundService` responde no canal correto e salva mensagens outbound.
10. `AuditService` registra cada etapa em `audit_logs` e logs JSON.

## Como rodar local

Crie o arquivo de ambiente:

```bash
cp .env.example .env
```

Suba a stack:

```bash
docker compose up --build
```

## Deploy na Contabo

O arquivo `docker-compose.prod.yml` sobe `api`, `worker`, PostgreSQL próprio e Caddy em HTTPS para `telegram.productpulse.com.br`.

Na VPS, com o PMO Board já rodando no network Docker `board_pmo_default`:

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

No `.env` da VPS, use:

```env
PMO_API_URL=http://pmo-board-api:3333/api
```

O Caddy publica apenas a porta `443`, mantendo a porta `80` livre para o PMO Board existente.

Teste o healthcheck:

```bash
curl http://localhost:8000/health
```

Resposta esperada:

```json
{"status":"ok"}
```

## Configurar Telegram

Preencha no `.env`:

```env
TELEGRAM_BOT_TOKEN=seu-token
TELEGRAM_WEBHOOK_SECRET=um-segredo-opcional
```

Configure o webhook:

```bash
curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  -d "url=https://seu-dominio/webhooks/telegram" \
  -d "secret_token=${TELEGRAM_WEBHOOK_SECRET}"
```

## Simular mensagem Telegram

```bash
curl -X POST http://localhost:8000/webhooks/telegram \
  -H "Content-Type: application/json" \
  -d '{
    "update_id": 1,
    "message": {
      "message_id": 10,
      "chat": {"id": 123},
      "from": {"id": 456},
      "text": "Cria uma atividade para Maria revisar o cronograma até sexta com prioridade alta."
    }
  }'
```

Depois processe manualmente em ambiente local:

```bash
curl -X POST http://localhost:8000/workers/process-message
```

O worker contínuo também roda no serviço `worker` do Docker Compose.

## Conectar com PMO Board

Configure no `.env`:

```env
PMO_API_URL=http://host.docker.internal:3333/api
PMO_API_EMAIL=rogerio@pmo.local
PMO_API_PASSWORD=123456
```

O `PmoBoardAuthProvider` faz login em `/auth/login`, mantém o JWT em memória e refaz login uma vez se receber `401`.

## Testar criação e confirmação

1. Envie a mensagem de criação pelo webhook.
2. Rode o worker até receber a pergunta de confirmação.
3. Envie uma nova mensagem Telegram com `confirmo`, `sim`, `ok` ou `pode fazer`.
4. Rode o worker de novo.

Antes da confirmação, a alteração fica em `task_actions` com status `pending_confirmation`. Após confirmação, o worker executa `POST /activities`.

## Consultar debug e auditoria

```bash
curl http://localhost:8000/debug/conversations/{conversation_id}
curl http://localhost:8000/debug/actions/{action_id}
```

Os logs de auditoria ficam em `audit_logs`; os logs da aplicação saem em JSON no stdout.

## Rodar testes

```bash
pytest
```

Os testes usam SQLite em memória e mocks HTTP para validar normalização, fila, debounce, agente mockado, provider do board e confirmação.

## Evoluir para IA real

Substitua `MockAgentService` por uma implementação de `AgentService`. O contrato de saída deve continuar retornando:

```json
{
  "intent": "create_task",
  "confidence": 0.85,
  "requires_confirmation": true,
  "response_text": "string",
  "board_action": {"type": "create_activity", "payload": {}},
  "missing_fields": []
}
```

## Evoluir para WhatsApp

Troque `WhatsAppMessageProviderMock` por um provider Meta real e mantenha o contrato `MessageProvider.send_text`. O webhook `/webhooks/whatsapp` e o normalizador já estão preparados para o adapter.

## Trocar PMO Board por Jira, Trello, ClickUp ou Azure DevOps

Implemente a interface `BoardProvider` em `app/providers/board_provider.py` e injete o novo provider no worker. A regra de negócio continua em `BoardService`.
