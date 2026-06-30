from app.services.mock_agent_service import MockAgentService


def test_create_task_intent():
    result = MockAgentService().process("c1", "u1", "Cria uma atividade para Maria")
    assert result.intent == "create_task"
    assert result.board_action.type == "create_activity"
    assert result.requires_confirmation is True


def test_update_task_intent():
    result = MockAgentService().process("c1", "u1", "Atualiza a atividade de integração")
    assert result.intent == "update_task"
    assert result.board_action.type == "update_activity"


def test_move_activity_intent():
    result = MockAgentService().process("c1", "u1", "Muda a atividade de integração para concluída")
    assert result.intent == "move_activity"
    assert result.board_action.payload["status"] == "DONE"


def test_query_alerts_intent():
    result = MockAgentService().process("c1", "u1", "Quais atividades estão atrasadas?")
    assert result.intent == "query_alerts"
    assert result.board_action.type == "query_alerts"


def test_unknown_intent():
    result = MockAgentService().process("c1", "u1", "Oi, tudo bem?")
    assert result.intent == "unknown"
    assert result.confidence == 0.2
