# Migration: Remove Local Business Logic

Foram removidos do runtime:

- agente mockado local;
- serviços de Board;
- provider/autenticação do Board;
- confirmação local;
- repositório de ações locais;
- endpoint `/debug/actions/{action_id}`;
- menus e respostas hardcoded no worker.

`task_actions` permanece no banco como histórico legado. Ela não deve receber novos registros. A remoção futura deve ser feita em uma migration própria depois de validar retenção, auditoria e backup.

Para consultar despachos técnicos:

```sql
SELECT event_id, status, attempts, last_error, created_at
FROM agent_dispatches
ORDER BY created_at DESC;
```

Para identificar falha na IA, procure status `retry` ou `failed` em `agent_dispatches` e eventos `agent_api_call_failed` em `audit_logs`.
