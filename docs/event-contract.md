# Event Contract

Tipos de evento enviados à IA:

- `welcome`
- `text`
- `menu_selection`
- `task_selection`
- `confirmation`
- `cancel`
- `back`
- `reset`

Regras locais permitidas são apenas de protocolo:

```mermaid
flowchart TD
  A[Mensagem normal] --> B[text]
  C[/start] --> D[welcome]
  E[menu:*] --> F[menu_selection]
  G[status:task:* / update:task:* / task:*] --> H[task_selection]
  I[confirmation:*] --> J[confirmation]
  K[global:cancel] --> L[cancel]
  M[global:back] --> N[back]
  O[global:reset] --> P[reset]
```

Textos humanos como `sim`, `confirmo`, `cancelar`, `status` ou `criar atividade` continuam como `text`.

Resposta esperada da IA:

```json
{
  "request_id": "uuid",
  "correlation_id": "uuid",
  "thread_id": "default:telegram:123456",
  "status": "waiting_user_input",
  "flow": "main_menu",
  "step": "waiting_menu_selection",
  "message": "Olá, Rogério! O que você deseja fazer?",
  "ui": {
    "type": "inline_keyboard",
    "options": [
      {"id": "menu_status", "label": "Status", "callback_data": "menu:status", "row": 0}
    ]
  },
  "data": {},
  "requires_confirmation": false,
  "confirmation": null,
  "error": null
}
```

Botão Telegram renderizado:

```json
{
  "inline_keyboard": [
    [{"text": "Status", "callback_data": "menu:status"}]
  ]
}
```
