from app.ui.layout import build_readiness_summary


def test_build_readiness_summary_blocks_when_access_is_denied() -> None:
    status, message, next_action = build_readiness_summary(
        access_allowed=False,
        access_message="Upload required before analytics access.",
        outputs_ready=False,
        outputs_message="",
    )
    assert status == "blocked"
    assert "Upload required" in message
    assert "No-Code Upload Center" in next_action


def test_build_readiness_summary_reports_pending_outputs() -> None:
    status, message, next_action = build_readiness_summary(
        access_allowed=True,
        access_message="",
        outputs_ready=False,
        outputs_message="Output build still running.",
    )
    assert status == "pending"
    assert message == "Output build still running."
    assert "run the pipeline" in next_action.lower()


def test_build_readiness_summary_keeps_ready_access_context_message() -> None:
    status, message, next_action = build_readiness_summary(
        access_allowed=True,
        access_message="Using previously uploaded real data.",
        outputs_ready=True,
        outputs_message="",
    )
    assert status == "ready"
    assert message == "Using previously uploaded real data."
    assert next_action == ""


def test_build_readiness_summary_uses_default_ready_message() -> None:
    status, message, next_action = build_readiness_summary(
        access_allowed=True,
        access_message="",
        outputs_ready=True,
        outputs_message="",
    )
    assert status == "ready"
    assert message == "Analytics data is ready."
    assert next_action == ""
