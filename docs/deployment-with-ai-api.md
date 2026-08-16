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

Rollback: volte a imagem anterior do ProductPulse e mantenha o banco. A migration nova é aditiva; `task_actions` não é removida nesta entrega.
