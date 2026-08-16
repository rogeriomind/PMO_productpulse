import pytest

from app.clients.agent_api_client import AgentApiContractError
from app.contracts.agent_response import AgentResponse
from app.renderers.channel_response_renderer import ChannelResponseRenderer


def _response(ui):
    return AgentResponse(
        request_id="request-1",
        correlation_id="correlation-1",
        thread_id="default:telegram:123",
        status="waiting_user_input",
        message="Escolha",
        ui=ui,
    )


def test_text_without_ui():
    outbound = ChannelResponseRenderer().render(
        "telegram", _response({"type": "none", "options": []})
    )

    assert outbound.text == "Escolha"
    assert outbound.reply_markup is None


def test_inline_keyboard_respects_rows():
    outbound = ChannelResponseRenderer().render(
        "telegram",
        _response(
            {
                "type": "inline_keyboard",
                "options": [
                    {"id": "a", "label": "A", "callback_data": "menu:a", "row": 0},
                    {"id": "b", "label": "B", "callback_data": "menu:b", "row": 0},
                    {"id": "c", "label": "C", "callback_data": "menu:c", "row": 1},
                ],
            }
        ),
    )

    assert outbound.reply_markup == {
        "inline_keyboard": [
            [
                {"text": "A", "callback_data": "menu:a"},
                {"text": "B", "callback_data": "menu:b"},
            ],
            [{"text": "C", "callback_data": "menu:c"}],
        ]
    }


def test_inline_keyboard_without_row_uses_one_button_per_line():
    outbound = ChannelResponseRenderer().render(
        "telegram",
        _response(
            {
                "type": "inline_keyboard",
                "options": [
                    {"id": "a", "label": "A", "callback_data": "menu:a"},
                    {"id": "b", "label": "B", "callback_data": "menu:b"},
                ],
            }
        ),
    )

    assert len(outbound.reply_markup["inline_keyboard"]) == 2


def test_confirmation_uses_api_options():
    outbound = ChannelResponseRenderer().render(
        "telegram",
        _response(
            {
                "type": "confirmation",
                "options": [
                    {
                        "id": "yes",
                        "label": "Aprovar",
                        "callback_data": "confirmation:approve:1",
                    }
                ],
            }
        ),
    )

    assert outbound.reply_markup["inline_keyboard"][0][0]["text"] == "Aprovar"


def test_numbered_list_uses_returned_options():
    outbound = ChannelResponseRenderer().render(
        "telegram",
        _response(
            {
                "type": "numbered_list",
                "options": [
                    {"id": "1", "label": "Primeira", "callback_data": "task:1"},
                    {"id": "2", "label": "Segunda", "callback_data": "task:2"},
                ],
            }
        ),
    )

    assert "1. Primeira" in outbound.text
    assert "2. Segunda" in outbound.text
    assert outbound.reply_markup is None


def test_numbered_list_does_not_duplicate_existing_numbers():
    outbound = ChannelResponseRenderer().render(
        "telegram",
        _response(
            {
                "type": "numbered_list",
                "options": [
                    {"id": "1", "label": "1. Primeira", "callback_data": "task:1"},
                ],
            }
        ),
    )

    assert "1. Primeira" in outbound.text
    assert "1. 1. Primeira" not in outbound.text


def test_callback_data_limit_is_validated():
    with pytest.raises(AgentApiContractError):
        ChannelResponseRenderer().render(
            "telegram",
            _response(
                {
                    "type": "inline_keyboard",
                    "options": [{"id": "x", "label": "X", "callback_data": "x" * 65}],
                }
            ),
        )


def test_whatsapp_falls_back_to_numbered_text():
    outbound = ChannelResponseRenderer().render(
        "whatsapp",
        _response(
            {
                "type": "inline_keyboard",
                "options": [
                    {"id": "a", "label": "Status", "callback_data": "menu:status"}
                ],
            }
        ),
    )

    assert outbound.reply_markup is None
    assert "1. Status" in outbound.text
