from app.contracts.agent_response import AgentResponse
from app.models.channel_outbound_message import ChannelOutboundMessage


class WhatsAppResponseRenderer:
    def render(self, response: AgentResponse) -> ChannelOutboundMessage:
        if response.ui.type == "none" or not response.ui.options:
            return ChannelOutboundMessage(text=response.message)

        options = "\n".join(
            f"{index}. {option.label}"
            for index, option in enumerate(response.ui.options, start=1)
        )
        return ChannelOutboundMessage(text=f"{response.message}\n\n{options}")
