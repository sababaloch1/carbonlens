"""ui/pages_private/coach.py - S4 AI Sustainability Coach.

Tabs:
- Insights        FR-4.01, FR-4.02  footprint context + AI explanation
- Recommendations FR-4.03 - FR-4.06 generate (AI or rules), filter, accept / dismiss / complete
- What-if         FR-4.07           simulate a change with the S2 engine, save it as a recommendation
- Ask the coach   FR-4.08           chat grounded in the organisation's data
- Learning        FR-4.09, FR-4.10  AI-written articles with manager approval
"""

import plotly.graph_objects as go
import streamlit as st

from ui.api_client import api_delete, api_get, api_patch, api_post
from ui.auth_state import current_role
from ui.charts import SERIES_PALETTE, apply_plotly_theme, get_scope_color
from ui.theme import apply_theme

apply_theme()

AI_TIMEOUT = 90  # OpenAI calls take longer than the default 5 s
role = current_role()
can_manage = role in ("admin", "manager")


def show_error(res):
    detail = res.get("detail") if isinstance(res, dict) else res
    st.error(f"{detail}")


st.title("🤖 AI Sustainability Coach")
ok_usage, usage = api_get("coach/usage")
if ok_usage:
    mode_txt = f"AI model: {usage['model']}" if usage["ai_enabled"] else "AI is off, so the rule-based coach is used"
    st.caption(f"{mode_txt} · {usage['tokens_in'] + usage['tokens_out']:,} chat tokens used by your organisation")

tab_insights, tab_recs, tab_whatif, tab_chat, tab_learn = st.tabs(
    ["📊 Insights", "✅ Recommendations", "🧪 What-if", "💬 Ask the coach", "📚 Learning"]
)

# ── Insights ─────────────────────────────────────────────────────────────────
with tab_insights:
    with st.spinner("Analysing your footprint..."):
        ok, data = api_get("coach/insights", timeout=AI_TIMEOUT)
    if not ok:
        show_error(data)
    else:
        s = data["summary"]
        if s.get("period_from"):
            st.caption(f"Last 12 months with data: {s['period_from']} to {s['period_to']}")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total", f"{s['total_t_co2e']:,.2f} t CO2e",
                  delta=f"{s['yoy_pct_change']:+.1f}% vs previous 12 months" if s.get("yoy_pct_change") is not None else None,
                  delta_color="inverse")
        c2.metric("Scope 1", f"{s['by_scope']['scope_1']:,.2f} t")
        c3.metric("Scope 2", f"{s['by_scope']['scope_2']:,.2f} t")
        c4.metric("Scope 3", f"{s['by_scope']['scope_3']:,.2f} t")

        st.subheader("What drives your footprint")
        st.caption("Written by AI from your data" if data["source"] == "ai" else "Rule-based summary")
        if data.get("warning"):
            st.info(data["warning"])
        for line in data["insights"]:
            st.markdown(f"- {line}")

        if s["by_category"]:
            left, right = st.columns(2)
            with left:
                cats = list(reversed(s["by_category"]))
                fig = go.Figure(go.Bar(
                    x=[c["t_co2e"] for c in cats],
                    y=[c["category"].replace("_", " ") for c in cats],
                    orientation="h",
                    marker_color=[get_scope_color(c["scope"]) for c in cats],
                    hovertemplate="%{y}: %{x:.2f} t CO2e<extra></extra>",
                ))
                apply_plotly_theme(fig, yaxis_title="", xaxis_title="t CO2e", title="Emissions by category")
                fig.update_layout(height=340)
                st.plotly_chart(fig, use_container_width=True)
            with right:
                if s["by_department"]:
                    deps = s["by_department"]
                    fig = go.Figure(go.Pie(
                        labels=[d["department"] for d in deps], values=[d["t_co2e"] for d in deps],
                        hole=0.55, marker=dict(colors=SERIES_PALETTE),
                    ))
                    apply_plotly_theme(fig, yaxis_title="", title="By department")
                    fig.update_layout(height=340)
                    st.plotly_chart(fig, use_container_width=True)

# ── Recommendations ──────────────────────────────────────────────────────────
STATUS_ACTIONS = {
    "proposed": [("Accept", "accepted"), ("Dismiss", "dismissed")],
    "accepted": [("Mark done", "completed"), ("Dismiss", "dismissed")],
    "dismissed": [("Reopen", "proposed")],
    "completed": [],
}
LEVEL_ICON = {"low": "🟢", "medium": "🟡", "high": "🔴"}

with tab_recs:
    if can_manage:
        c1, c2 = st.columns([2, 3])
        mode_label = c1.selectbox("Generate with", ["AI (falls back to rules)", "AI only", "Rules only"])
        mode = {"AI (falls back to rules)": "auto", "AI only": "ai", "Rules only": "rules"}[mode_label]
        c2.write("")
        if c2.button("✨ Generate recommendations", use_container_width=True):
            with st.spinner("Looking for the biggest reduction opportunities..."):
                ok, g = api_post("coach/recommendations/generate", json_data={"mode": mode}, timeout=AI_TIMEOUT)
            if ok:
                msg = f"{len(g['created'])} new recommendations"
                if g["skipped_duplicates"]:
                    msg += f", {g['skipped_duplicates']} already on your list"
                st.success(msg)
                if g.get("warning"):
                    st.warning(g["warning"])
            else:
                show_error(g)
    else:
        st.info("Managers and admins can generate recommendations and change their status.")

    status_filter = st.radio("Show", ["all", "proposed", "accepted", "completed", "dismissed"], horizontal=True)
    params = {} if status_filter == "all" else {"status": status_filter}
    ok, recs = api_get("coach/recommendations", params=params)
    recs = recs if ok else []
    open_saving = sum(r["est_saving_t_co2e"] or 0 for r in recs if r["status"] in ("proposed", "accepted"))
    st.metric("Open reduction potential", f"{open_saving:,.2f} t CO2e per year")
    if not recs:
        st.info("No recommendations here yet.")
    for rec in recs:
        with st.container(border=True):
            a, b = st.columns([5, 1.5])
            src = "🤖 AI" if rec["source"] == "ai" else "📐 Rules / simulation"
            scope = (rec["scope"] or "").replace("_", " ").title()
            a.markdown(f"**{rec['title']}**  \n{src} · {scope} · status: `{rec['status']}`")
            b.metric("Est. saving", f"{rec['est_saving_t_co2e'] or 0:,.2f} t")
            st.write(rec["description"])
            st.caption(f"Cost {LEVEL_ICON.get(rec['cost_level'], '')} {rec['cost_level']} · "
                       f"Effort {LEVEL_ICON.get(rec['effort'], '')} {rec['effort']}")
            if can_manage:
                cols = st.columns(6)
                for i, (label, new_status) in enumerate(STATUS_ACTIONS.get(rec["status"], [])):
                    if cols[i].button(label, key=f"{rec['id']}-{new_status}"):
                        ok, res = api_patch(f"coach/recommendations/{rec['id']}/status", json_data={"status": new_status})
                        if ok:
                            st.rerun()
                        show_error(res)

# ── What-if ──────────────────────────────────────────────────────────────────
with tab_whatif:
    st.caption("Simulate a change on your last 12 months of data. The emission engine calculates it; nothing is saved.")
    ok, scenarios = api_get("coach/what-if/scenarios")
    if ok and scenarios:
        scenarios = sorted(scenarios, key=lambda x: not x["available"])
        by_id = {s["id"]: s for s in scenarios}
        c1, c2 = st.columns([3, 2])
        sid = c1.selectbox("Scenario", list(by_id), format_func=lambda k: by_id[k]["title"]
                           + ("" if by_id[k]["available"] else " (no data)"))
        pct = c2.slider("How much of it (%)", 5, 100, 50, step=5)
        st.caption(by_id[sid]["description"])
        b1, b2 = st.columns(2)
        run = b1.button("Run simulation", use_container_width=True)
        save = b2.button("Run and save as recommendation", use_container_width=True, disabled=not can_manage)
        if run or save:
            ok, res = api_post("coach/what-if", json_data={"scenario_id": sid, "change_pct": pct, "save": save})
            if not ok:
                show_error(res)
            else:
                r = res["result"]
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Before", f"{r['before_t_co2e']:,.2f} t")
                m2.metric("After", f"{r['after_t_co2e']:,.2f} t")
                m3.metric("Saving", f"{r['saving_t_co2e']:,.2f} t",
                          delta=f"-{r['saving_pct']:.1f}%" if r["saving_pct"] is not None else None,
                          delta_color="inverse")
                cost = r["saving_cost_eur"]
                m4.metric("Cost saving", f"€{cost:,.0f}" if cost is not None else "n/a",
                          help=None if cost is not None else "The engine has no price for some of these items.")
                fig = go.Figure(go.Bar(x=["Before", "After"], y=[r["before_t_co2e"], r["after_t_co2e"]],
                                       marker_color=[SERIES_PALETTE[4], SERIES_PALETTE[2]],
                                       hovertemplate="%{x}: %{y:.2f} t CO2e<extra></extra>"))
                apply_plotly_theme(fig, yaxis_title="t CO2e")
                fig.update_layout(height=280)
                st.plotly_chart(fig, use_container_width=True)
                if r["engine_errors"]:
                    st.warning(f"{r['engine_errors']} items could not be calculated by the engine.")
                if res.get("saved_recommendation"):
                    st.success("Saved to your recommendations.")
    else:
        show_error(scenarios)

# ── Chat ─────────────────────────────────────────────────────────────────────
with tab_chat:
    ok, sessions = api_get("coach/chat/sessions")
    sessions = sessions if ok else []
    c1, c2, c3 = st.columns([4, 1, 1])
    if c2.button("➕ New chat", use_container_width=True) or not sessions:
        ok, new = api_post("coach/chat/sessions", json_data={})
        if ok:
            st.session_state["coach_chat_session"] = new["id"]
            ok, sessions = api_get("coach/chat/sessions")
    options = {s["id"]: s["title"] or "Conversation" for s in sessions}
    if options:
        current = st.session_state.get("coach_chat_session")
        if current not in options:
            current = next(iter(options))
        current = c1.selectbox("Conversation", list(options), index=list(options).index(current),
                               format_func=lambda k: options[k], label_visibility="collapsed")
        st.session_state["coach_chat_session"] = current
        if c3.button("🗑 Delete", use_container_width=True):
            api_delete(f"coach/chat/sessions/{current}")
            st.session_state.pop("coach_chat_session", None)
            st.rerun()

        ok, msgs = api_get(f"coach/chat/sessions/{current}/messages")
        msgs = msgs if ok else []
        if not msgs:
            st.caption("Ask anything about your footprint, e.g. *Where can we cut the most CO2 this year?*")
        for m in msgs:
            with st.chat_message(m["role"]):
                st.markdown(m["content"])
                if m["role"] == "assistant" and m.get("tokens_out") == 0:
                    st.caption("AI unavailable, so this is an automatic summary.")

        prompt = st.chat_input("Ask the coach")
        if prompt:
            with st.spinner("Thinking..."):
                ok, res = api_post(f"coach/chat/sessions/{current}/messages", json_data={"content": prompt},
                                   timeout=AI_TIMEOUT)
            if ok:
                st.rerun()
            show_error(res)

# ── Learning content ─────────────────────────────────────────────────────────
with tab_learn:
    if can_manage:
        with st.expander("✍️ Create learning content"):
            with st.form("coach_learning_form"):
                topic = st.text_input("Topic", placeholder="What Scope 2 emissions are and how we reduce them")
                audience = st.selectbox("For", ["contributor", "manager", "admin"])
                if st.form_submit_button("Generate draft"):
                    with st.spinner("Writing..."):
                        ok, res = api_post("coach/learning/generate", json_data={"topic": topic, "audience": audience},
                                           timeout=AI_TIMEOUT)
                    if ok:
                        st.success("Draft created. Review it below and approve it to publish.")
                    else:
                        show_error(res)

    ok, items = api_get("coach/learning")
    items = items if ok else []
    if not items:
        st.info("No learning content yet.")
    for item in items:
        badge = "✅ approved" if item["status"] == "approved" else "📝 draft"
        with st.expander(f"{item['topic']} · for {item['audience']}s · {badge}"):
            st.markdown(item["body"])
            if can_manage and item["status"] == "draft":
                if st.button("Approve and publish", key=f"approve-{item['id']}"):
                    ok, res = api_post(f"coach/learning/{item['id']}/approve")
                    if ok:
                        st.rerun()
                    show_error(res)
