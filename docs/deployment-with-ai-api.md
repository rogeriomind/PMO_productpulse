# Deployment With AI API

Crie a rede compartilhada:

```bash
docker network create pmo_ai_network
```

Configure:

```env
AGENT_API_URL=http://pmo-ai-agent-api:8010
PMO_AI_NETWORK_NAME=pmo_ai_network
AGENT_API_TOKEN=<token>
QUEUE_NOTIFY_ENABLED=false
DEBOUNCE_ADAPTIVE_ENABLED=false
```

Suba o ProductPulse:

```bash
docker compose -f docker-compose.prod.yml up --build -d
```

A API da IA e o worker precisam estar na mesma rede Docker. A API webhook pode permanecer somente em `pmo_agent`.

Readiness:

```bash
curl https://seu-dominio/ready
```

Resposta esperada:

```json
{
  "status": "ok",
  "checks": {
    "database": "ok",
    "queue": "ok",
    "agent_api": "ok"
  }
}
```

Rollback: volte a imagem anterior do ProductPulse e mantenha o banco. As migrations novas são aditivas; `task_actions` não é removida nesta entrega.

## Rollout de latência

Etapa 1: subir o worker persistente com os recursos novos desligados.

```env
QUEUE_NOTIFY_ENABLED=false
DEBOUNCE_ADAPTIVE_ENABLED=false
```

Etapa 2: ativar wake-up PostgreSQL.

```env
QUEUE_NOTIFY_ENABLED=true
QUEUE_NOTIFY_CHANNEL=pmo_productpulse_queue
WORKER_FALLBACK_POLL_SECONDS=10
```

Etapa 3: ativar debounce adaptativo de forma conservadora.

```env
DEBOUNCE_ADAPTIVE_ENABLED=true
DEBOUNCE_MIN_MS=1000
DEBOUNCE_MAX_MS=3000
DEBOUNCE_INCREMENT_MS=400
DEBOUNCE_MAX_MESSAGES=8
```

Depois de validar logs e latência, reduzir para:

```env
DEBOUNCE_MIN_MS=700
DEBOUNCE_MAX_MS=2500
```

Deploy isolado na VPS:

```bash
cd /opt/PMO_productpulse
git pull
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs --tail=200
```

Não executar comandos Docker globais no host da VPS. Outros projetos podem estar rodando no mesmo servidor.
