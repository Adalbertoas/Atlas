from __future__ import annotations

from app.security.permissions import PermissionManager, RiskLevel


def test_read_only_auto_approves():
    pm = PermissionManager()
    decision = pm.evaluate(
        tool_name="get_current_time",
        risk_level=RiskLevel.READ_ONLY,
        parameters={},
        human_description="Consultar hora",
    )
    assert decision.allowed
    assert not decision.requires_confirmation


def test_medium_risk_requires_confirmation():
    pm = PermissionManager()
    decision = pm.evaluate(
        tool_name="open_application",
        risk_level=RiskLevel.MEDIUM_RISK,
        parameters={"application_name": "notepad"},
        human_description="Abrir notepad",
    )
    assert not decision.allowed
    assert decision.requires_confirmation
    assert decision.pending is not None

    # La confirmación queda pendiente y se puede resolver una sola vez.
    pending = pm.get_pending(decision.pending.id)
    assert pending is not None
    resolved = pm.resolve(decision.pending.id)
    assert resolved is not None
    assert pm.get_pending(decision.pending.id) is None


def test_critical_never_auto_approves():
    pm = PermissionManager()
    decision = pm.evaluate(
        tool_name="unlock_door",
        risk_level=RiskLevel.CRITICAL,
        parameters={},
        human_description="Abrir la puerta principal",
    )
    assert not decision.allowed
    assert decision.requires_confirmation
