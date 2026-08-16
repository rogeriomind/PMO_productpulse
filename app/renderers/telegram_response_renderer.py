from collections import defaultdict

from app.clients.agent_api_client import AgentApiContractError
from app.contracts.agent_response import AgentResponse, AgentUiOption
from app.models.channel_outbound_message import ChannelOutboundMessage


class TelegramResponseRenderer:
    def render(self, response: AgentResponse) -> ChannelOutboundMessage:
        if response.ui.type == "none":
            return ChannelOutboundMessage(text=response.message)

        if response.ui.type in {"inline_keyboard", "confirmation"}:
            return ChannelOutboundMessage(
                text=response.message,
                reply_markup={
                    "inline_keyboard": self._inline_keyboard(response.ui.options)
                },
            )

        if response.ui.type == "numbered_list":
            return ChannelOutboundMessage(text=self._numbered_text(response))

        return ChannelOutboundMessage(text=response.message)

    def _inline_keyboard(
        self, options: list[AgentUiOption]
    ) -> list[list[dict[str, str]]]:
        rows: defaultdict[int, list[dict[str, str]]] = defaultdict(list)
        next_row = 0
        for option in options:
            callback_data = option.callback_data or option.id
            if len(callback_data.encode("utf-8")) > 64:
                raise AgentApiContractError(
                    "callback_data do Telegram excede 64 bytes."
                )
            row = option.row if option.row is not None else next_row
            rows[row].append({"text": option.label, "callback_data": callback_data})
            if option.row is None:
                next_row += 1
        return [rows[row] for row in sorted(rows)]

    def _numbered_text(self, response: AgentResponse) -> str:
        if not response.ui.options:
            return response.message
        options = "\n".join(
            f"{index}. {option.label}"
            for index, option in enumerate(response.ui.options, start=1)
        )
        return f"{response.message}\n\n{options}"
