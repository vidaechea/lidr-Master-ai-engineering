import asyncio
import queue
import threading
from typing import Generator

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


def _sync_stream(service, transcript: str) -> Generator[str, None, None]:
    """Bridge between the async estimate_stream generator and st.write_stream.

    Runs the async generator in a background thread so that Streamlit's
    synchronous main thread can consume deltas via a queue.
    A sentinel ``None`` value signals that the stream is finished.
    """
    _SENTINEL = object()
    delta_queue: queue.Queue = queue.Queue()
    exc_holder: list[BaseException] = []

    async def _producer() -> None:
        try:
            async for delta in service.estimate_stream(transcript):
                delta_queue.put(delta)
        except BaseException as exc:  # noqa: BLE001
            exc_holder.append(exc)
        finally:
            delta_queue.put(_SENTINEL)

    def _run_loop() -> None:
        asyncio.run(_producer())

    thread = threading.Thread(target=_run_loop, daemon=True)
    thread.start()

    while True:
        item = delta_queue.get()
        if item is _SENTINEL:
            break
        yield item

    thread.join()

    if exc_holder:
        raise exc_holder[0]


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

    # Call estimation service and stream the response
    with st.chat_message("assistant"):
        try:
            estimation = st.write_stream(
                _sync_stream(st.session_state.service, transcript)
            )
            meta = {
                k: v
                for k, v in st.session_state.service._last_stream_result.items()
                if k != "estimation"
            }
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
