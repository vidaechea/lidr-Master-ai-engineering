import asyncio

import streamlit as st

from app.services.base_llm_service import LLMServiceError
from app.services.factory import create_llm_service

st.set_page_config(
    page_title="Estimator CAG",
    page_icon="📋",
    layout="wide",
)


def _render_details(meta: dict) -> None:
    """Render the full estimation metadata inside an expander."""
    with st.expander("Details", expanded=False):
        # Tokens
        st.subheader("Tokens")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Input tokens", meta["input_tokens"])
        col2.metric("Output tokens", meta["output_tokens"])
        col3.metric("Reasoning tokens", meta.get("reasoning_tokens") or 0)
        col4.metric("Estimated input tokens", meta["estimated_input_tokens"])

        col5, col6 = st.columns(2)
        col5.metric("Cache creation tokens", meta.get("cache_creation_tokens", 0))
        col6.metric("Cache read tokens", meta.get("cache_read_tokens", 0))

        st.divider()

        # Costs
        st.subheader("Costs (USD)")
        col7, col8, col9 = st.columns(3)
        col7.metric("Turn cost", f"${meta['turn_cost_usd']:.6f}")
        col8.metric("Total cost", f"${meta['total_cost_usd']:.6f}")
        col9.metric(
            "Pre-call cost",
            f"${meta['pre_call_cost_usd']:.6f}" if meta.get("pre_call_cost_usd") is not None else "—",
        )
        st.metric(
            "Estimated pre-call cost",
            f"${meta['estimated_precall_cost_usd']:.6f}",
        )

        st.divider()

        # Model & run info
        st.subheader("Run info")
        col10, col11, col12 = st.columns(3)
        col10.metric("Model", meta["model"])
        col11.metric("Finish reason", meta.get("finish_reason", "—"))
        col12.metric("Truncated", str(meta.get("truncated", False)))
        st.caption(f"Response ID: `{meta.get('response_id', '—')}`")

        # Requirements (pre-call output)
        if meta.get("requirements"):
            st.divider()
            st.subheader("Extracted requirements (pre-call)")
            st.markdown(meta["requirements"])


# ── Session state bootstrap ────────────────────────────────────────────────────

if "messages" not in st.session_state:
    st.session_state.messages = []

if "service" not in st.session_state:
    st.session_state.service = create_llm_service()

# ── Render existing messages ───────────────────────────────────────────────────

st.title("Meeting Estimator")
st.caption("Paste a meeting transcript below to receive a detailed effort estimate.")

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message["role"] == "assistant" and "meta" in message:
            _render_details(message["meta"])

# ── Chat input ─────────────────────────────────────────────────────────────────

transcript = st.chat_input("Paste your meeting transcript here…")

if transcript:
    # Display user message
    st.session_state.messages.append({"role": "user", "content": transcript})
    with st.chat_message("user"):
        st.markdown(transcript)

    # Call estimation service
    with st.chat_message("assistant"):
        with st.spinner("Estimating…"):
            try:
                result = asyncio.run(
                    st.session_state.service.estimate(transcript)
                )
                estimation = result["estimation"]
                st.markdown(estimation)

                meta = {k: v for k, v in result.items() if k != "estimation"}
                _render_details(meta)

                st.session_state.messages.append(
                    {"role": "assistant", "content": estimation, "meta": meta}
                )

            except LLMServiceError as exc:
                error_msg = f"**Error {exc.status_code}:** {exc.message}"
                st.error(error_msg)
                st.session_state.messages.append(
                    {"role": "assistant", "content": error_msg}
                )
