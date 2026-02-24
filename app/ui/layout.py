from __future__ import annotations

import streamlit as st
from typing import Any, Literal


def render_global_context_bar(
    workspace_name: str,
    plan_name: str,
    active_section: str,
    active_page: str,
    advanced_mode_enabled: bool,
) -> None:
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.caption("Workspace")
    c1.write(f"**{workspace_name or 'Default Workspace'}**")
    c2.caption("Plan")
    c2.write(f"**{plan_name}**")
    c3.caption("Section")
    c3.write(f"**{active_section}**")
    c4.caption("Page")
    c4.write(f"**{active_page}**")
    c5.caption("Advanced")
    c5.write("**On**" if advanced_mode_enabled else "**Off**")


def render_page_scaffold(page_name: str, section_name: str) -> None:
    st.caption(f"{section_name} / {page_name}")


def render_section_header(title: str, helper_text: str = "") -> None:
    st.subheader(title)
    if helper_text.strip():
        st.caption(helper_text.strip())


def render_metric_strip(metrics: list[tuple[str, str]]) -> None:
    if not metrics:
        return
    columns = st.columns(len(metrics))
    for idx, (label, value) in enumerate(metrics):
        columns[idx].metric(str(label), str(value))


def render_empty_state(message: str, next_action: str = "", level: Literal["info", "warning", "error"] = "info") -> None:
    msg = str(message).strip() or "No data available."
    if level == "error":
        st.error(msg)
    elif level == "warning":
        st.warning(msg)
    else:
        st.info(msg)
    if str(next_action).strip():
        st.caption(next_action.strip())


def render_compact_dataframe(
    frame: Any,
    *,
    max_rows: int = 50,
    hide_index: bool = True,
    use_container_width: bool = True,
) -> None:
    if frame is None:
        st.info("No records available.")
        return
    try:
        if bool(getattr(frame, "empty", False)):
            st.info("No records available.")
            return
        safe_limit = max(int(max_rows), 1)
        subset = frame.head(safe_limit) if hasattr(frame, "head") else frame
        st.dataframe(
            subset,
            use_container_width=use_container_width,
            hide_index=hide_index,
        )
    except Exception:
        st.dataframe(frame, use_container_width=use_container_width, hide_index=hide_index)


def build_readiness_summary(
    *,
    access_allowed: bool,
    access_message: str,
    outputs_ready: bool,
    outputs_message: str,
) -> tuple[str, str, str]:
    if not access_allowed:
        return (
            "blocked",
            access_message.strip() or "Analytics pages are not ready yet.",
            "Go to `No-Code Upload Center` and complete: Upload → Validate (Strict) → Run Pipeline.",
        )
    if not outputs_ready:
        return (
            "pending",
            outputs_message.strip() or "Processed outputs are still being prepared.",
            "Use `No-Code Upload Center` to run the pipeline and generate fresh outputs.",
        )
    if access_message.strip():
        return ("ready", access_message.strip(), "")
    return ("ready", "Analytics data is ready.", "")


def render_readiness_panel(status: str, message: str, next_action: str = "") -> None:
    normalized = str(status).strip().lower()
    if normalized == "blocked":
        st.warning(message)
    elif normalized == "pending":
        st.info(message)
    else:
        st.success(message)
    if next_action.strip():
        st.caption(next_action.strip())
