from __future__ import annotations

import streamlit as st


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
