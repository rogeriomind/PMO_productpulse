# Como conectar outra app na API do PMO Board

Este guia mostra como uma aplicação externa pode autenticar e consumir a API REST do PMO Board.

## URL base

Ambiente local:

```text
http://localhost:3333/api
```

No frontend ou em outra app, guarde essa URL em variável de ambiente:

```env
VITE_PMO_API_URL="http://localhost:3333/api"
```

Para apps Node, mobile ou backend:

```env
PMO_API_URL="http://localhost:3333/api"
```

## Autenticação

A API usa JWT. Primeiro faça login:

```http
POST /auth/login
Content-Type: application/json

{
  "email": "rogerio@pmo.local",
  "password": "123456"
}
```

Resposta:

```json
{
  "token": "jwt",
  "user": {
    "id": "uuid",
    "name": "Rogerio",
    "email": "rogerio@pmo.local",
    "avatarUrl": "https://..."
  }
}
```

Depois envie o token em todas as chamadas protegidas:

```http
Authorization: Bearer <token>
```

## Exemplo com fetch

```ts
const API_URL = import.meta.env.VITE_PMO_API_URL ?? "http://localhost:3333/api";

async function login() {
  const response = await fetch(`${API_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email: "rogerio@pmo.local",
      password: "123456"
    })
  });

  if (!response.ok) {
    throw new Error("Falha ao autenticar");
  }

  return response.json();
}

async function getActivities(token: string) {
  const response = await fetch(`${API_URL}/activities`, {
    headers: {
      Authorization: `Bearer ${token}`
    }
  });

  if (!response.ok) {
    throw new Error("Falha ao buscar atividades");
  }

  return response.json();
}
```

## Exemplo com Axios

```ts
import axios from "axios";

export const pmoApi = axios.create({
  baseURL: import.meta.env.VITE_PMO_API_URL ?? "http://localhost:3333/api"
});

pmoApi.interceptors.request.use((config) => {
  const token = localStorage.getItem("pmo-token");

  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  return config;
});

export async function login(email: string, password: string) {
  const { data } = await pmoApi.post("/auth/login", { email, password });
  localStorage.setItem("pmo-token", data.token);
  return data.user;
}

export async function listActivities() {
  const { data } = await pmoApi.get("/activities");
  return data;
}
```

## Endpoints principais

### Health check

```http
GET /health
```

### Usuários

```http
GET /users
Authorization: Bearer <token>
```

### Listar atividades

```http
GET /activities
Authorization: Bearer <token>
```

Filtros opcionais:

```http
GET /activities?status=TODO&priority=HIGH&search=lembrete
```

Parâmetros aceitos:

```text
status: BACKLOG | TODO | IN_PROGRESS | BLOCKED | IN_REVIEW | DONE | CANCELED
priority: LOW | MEDIUM | HIGH | CRITICAL
assigneeId: uuid
search: texto
dueDateFrom: YYYY-MM-DD
dueDateTo: YYYY-MM-DD
```

### Criar atividade

```http
POST /activities
Authorization: Bearer <token>
Content-Type: application/json

{
  "title": "Configurar lembrete automatico",
  "description": "Configurar lembrete automatico de atualizacao de atividades.",
  "status": "TODO",
  "priority": "HIGH",
  "assigneeId": "uuid-do-usuario",
  "dueDate": "2026-07-10",
  "tags": ["Automacao", "WhatsApp"],
  "checklist": ["Definir regras", "Configurar templates"]
}
```

### Detalhar atividade

```http
GET /activities/:id
Authorization: Bearer <token>
```

### Atualizar atividade

```http
PATCH /activities/:id
Authorization: Bearer <token>
Content-Type: application/json

{
  "title": "Novo titulo",
  "description": "Nova descricao",
  "priority": "MEDIUM",
  "assigneeId": "uuid-do-usuario",
  "dueDate": "2026-07-15",
  "tags": ["Produto", "PMO"]
}
```

### Mover atividade

```http
PATCH /activities/:id/status
Authorization: Bearer <token>
Content-Type: application/json

{
  "status": "IN_PROGRESS"
}
```

Para mover para `BLOCKED` ou `CANCELED`, envie `reason`:

```json
{
  "status": "BLOCKED",
  "reason": "Dependencia externa"
}
```

### Checklist

```http
POST /activities/:id/checklist
PATCH /checklist/:itemId
DELETE /checklist/:itemId
```

Exemplo:

```http
PATCH /checklist/:itemId
Authorization: Bearer <token>
Content-Type: application/json

{
  "isDone": true
}
```

### Comentários

```http
POST /activities/:id/comments
GET /activities/:id/comments
```

Exemplo:

```http
POST /activities/:id/comments
Authorization: Bearer <token>
Content-Type: application/json

{
  "message": "Comentario sobre a atividade"
}
```

### Histórico

```http
GET /activities/:id/history
Authorization: Bearer <token>
```

### Alertas

```http
GET /alerts
Authorization: Bearer <token>
```

Resposta:

```json
{
  "overdue": [],
  "atRisk": [],
  "blocked": [],
  "withoutAssignee": [],
  "nearDueDate": []
}
```

## Tratamento de erro

Erros retornam JSON com `message`:

```json
{
  "message": "Complete todos os itens do checklist antes de concluir."
}
```

Exemplo de helper:

```ts
async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, options);
  const data = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(data?.message ?? "Erro ao chamar API");
  }

  return data;
}
```

## CORS

Se a outra app rodar em outra porta ou domínio, atualize `CORS_ORIGIN` no `.env` da API:

```env
CORS_ORIGIN="http://localhost:3000"
```

Depois reinicie a API.

## Modo de dados

Por padrão, esta entrega pode rodar sem PostgreSQL usando:

```env
DATA_DRIVER="json"
```

Para usar PostgreSQL/Prisma:

```env
DATA_DRIVER="prisma"
DATABASE_URL="postgresql://pmo:pmo@localhost:5432/pmo_board?schema=public"
```

Depois rode:

```bash
npm run db:push
npm run db:seed
```
