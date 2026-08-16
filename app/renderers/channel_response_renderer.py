from app.contracts.agent_response import AgentResponse
from app.models.channel_outbound_message import ChannelOutboundMessage
from app.renderers.telegram_response_renderer import TelegramResponseRenderer
from app.renderers.whatsapp_response_renderer import WhatsAppResponseRenderer


class ChannelResponseRenderer:
    def __init__(self):
        self.renderers = {
            "telegram": TelegramResponseRenderer(),
            "whatsapp": WhatsAppResponseRenderer(),
        }

    def render(
        self, channel: str, agent_response: AgentResponse
    ) -> ChannelOutboundMessage:
        renderer = self.renderers.get(channel)
        if not renderer:
            raise RuntimeError(f"Renderer de canal não configurado: {channel}")
        return renderer.render(agent_response)
