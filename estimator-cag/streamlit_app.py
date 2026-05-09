import asyncio
import queue
import threading
from typing import Generator

import streamlit as st
from streamlit.runtime.scriptrunner import get_script_run_ctx

from app.config import settings
from app.schemas.estimation import DetailLevel, OutputFormat, ProjectType
from app.services.base_llm_service import LLMServiceError
from app.services.cache_service import CachedLLMService
from app.services.evaluation import evaluate_estimation_structure
from app.services.factory import create_llm_service

# ── Provider / model registry (mirrors service registries) ───────────────────

_OPENAI_MODELS = [
    "gpt-4o-mini",
    "gpt-5.4-mini",
    "gpt-5.4",
    "gpt-4-turbo",
    "gpt-3.5-turbo",
    "o3-mini",
    "o3",
    "o4-mini",
    "o4-mini-2025-04-16",
]
_ANTHROPIC_MODELS = [
    "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001",
    "claude-opus-4-7",
]
_LITELLM_MODELS = [
    "gpt-4o-mini → claude-haiku (auto-failover)",
]
_MODELS_BY_PROVIDER: dict[str, list[str]] = {
    "openai": _OPENAI_MODELS,
    "anthropic": _ANTHROPIC_MODELS,
    "litellm": _LITELLM_MODELS,
}

# Models that support reasoning / extended thinking
_REASONING_MODELS: set[str] = {
    "o3-mini", "o3", "o4-mini", "o4-mini-2025-04-16",  # OpenAI
    "claude-opus-4-7",                                   # Anthropic
}

st.set_page_config(
    page_title="Estimator CAG",
    page_icon="📋",
    layout="wide",
)

st.markdown(
    """
    <style>
        :root {
            --app-font: "Source Sans 3", "Source Sans Pro", sans-serif;
        }
        html, body, [class*="css"] {
            font-family: var(--app-font);
            font-size: 16px;
        }
        [data-testid="stMetric"] {
            font-size: 0.85rem;
        }
        [data-testid="stMetricLabel"] {
            font-size: 0.8rem;
        }
        [data-testid="stMetricValue"] {
            font-size: 1.05rem;
        }
        [data-testid="stMetricDelta"] {
            font-size: 0.75rem;
        }
        h1 {
            font-size: 2.2rem;
            letter-spacing: -0.02em;
        }
        h2 {
            font-size: 1.35rem;
        }
        h3 {
            font-size: 1.1rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


_CHECK_LABELS: dict[str, str] = {
    "has_title": "H2 project title",
    "has_breakdown_table": "Breakdown table",
    "has_totals_section": "Totals section",
    "has_team_section": "Team section",
    "has_duration_section": "Duration section",
    "finish_reason_ok": "Finish reason",
}


def _render_details(meta: dict, session_id: str) -> None:
    """Render the full estimation metadata inside the sidebar."""
    with st.sidebar.expander(f"Details — session {session_id}", expanded=False):
        if meta.get("system_prompt"):
            with st.expander("System prompt", expanded=False):
                st.code(meta["system_prompt"], language="text")

        if meta.get("pre_call_prompt"):
            with st.expander("Pre-call prompt", expanded=False):
                st.code(meta["pre_call_prompt"], language="text")

        # Tokens
        st.subheader("Tokens")
        reasoning_tokens = meta.get("reasoning_tokens")
        token_cols = st.columns(4 if reasoning_tokens is not None else 3)
        token_cols[0].metric("Input tokens", meta["input_tokens"])
        token_cols[1].metric("Output tokens", meta["output_tokens"])
        if reasoning_tokens is not None:
            token_cols[2].metric("Reasoning tokens", reasoning_tokens)
            token_cols[3].metric("Estimated input tokens", meta["estimated_input_tokens"])
        else:
            token_cols[2].metric("Estimated input tokens", meta["estimated_input_tokens"])

        cache_creation_tokens = meta.get("cache_creation_tokens", 0)
        cache_read_tokens = meta.get("cache_read_tokens", 0)
        if cache_creation_tokens or cache_read_tokens:
            col5, col6 = st.columns(2)
            col5.metric("Cache creation tokens", cache_creation_tokens)
            col6.metric("Cache read tokens", cache_read_tokens)

        st.divider()

        # Costs
        st.subheader("Costs (USD)")
        col7, col8 = st.columns(2)
        col7.metric("Turn cost", f"${meta['turn_cost_usd']:.6f}")
        col8.metric("Total cost", f"${meta['total_cost_usd']:.6f}")

        show_precall_costs = (
            meta.get("pre_call_cost_usd") is not None
            or meta.get("estimated_precall_cost_usd") is not None
        )
        if show_precall_costs:
            col9, col10 = st.columns(2)
            _precall_cost = meta.get("pre_call_cost_usd")
            _est_precall_cost = meta.get("estimated_precall_cost_usd")
            col9.metric(
                "Pre-call cost",
                f"${_precall_cost:.6f}" if _precall_cost is not None else "—",
            )
            col10.metric(
                "Estimated pre-call cost",
                f"${_est_precall_cost:.6f}" if _est_precall_cost is not None else "—",
            )

        st.divider()

        # Model & run info
        st.subheader("Run info")
        run_items: list[tuple[str, str]] = [("Model", meta["model"])]
        if meta.get("finish_reason"):
            run_items.append(("Finish reason", meta["finish_reason"]))
        if "truncated" in meta:
            run_items.append(("Truncated", str(meta.get("truncated"))))
        if "cache_hit" in meta:
            run_items.append(("Cache", "✅ HIT" if meta["cache_hit"] else "❌ MISS"))
        if "response_time_s" in meta:
            run_items.append(("Response time", f"{meta['response_time_s']} s"))
        run_cols = st.columns(len(run_items))
        for col, (label, value) in zip(run_cols, run_items):
            col.metric(label, value)
        if meta.get("response_id"):
            st.caption(f"Response ID: `{meta['response_id']}`")

        # Validation
        if meta.get("validation"):
            st.divider()
            v = meta["validation"]
            score = v.get("score", 0)
            score_pct = int(score * 100)
            score_color = "green" if score >= 0.8 else ("orange" if score >= 0.5 else "red")
            st.subheader("Validation")
            st.markdown(
                f"**Score:** :{score_color}[{score_pct}%]  "
                f"({sum(1 for k in _CHECK_LABELS if v.get(k, False))}/{len(_CHECK_LABELS)} checks passed)"
            )

            # Boolean structure checks
            check_cols = st.columns(len(_CHECK_LABELS))
            for col, (key, label) in zip(check_cols, _CHECK_LABELS.items()):
                passed = v.get(key, False)
                col.metric(label, "✅" if passed else "❌")

            # Numeric consistency
            num_col1, num_col2 = st.columns(2)
            declared_h = v.get("declared_total_hours")
            sum_h = v.get("sum_row_hours")
            hours_match = v.get("hours_match")
            num_col1.metric(
                "Hours: declared vs rows",
                f"{declared_h} / {sum_h}" if declared_h is not None else "—",
                delta="✅ match" if hours_match else ("❌ mismatch" if hours_match is False else None),
                delta_color="normal" if hours_match else "inverse",
            )
            declared_c = v.get("declared_total_cost")
            sum_c = v.get("sum_row_cost")
            cost_match = v.get("cost_match")
            num_col2.metric(
                "Cost: declared vs rows",
                f"{declared_c:,.0f} / {sum_c:,.0f}" if declared_c is not None else "—",
                delta="✅ match" if cost_match else ("❌ mismatch" if cost_match is False else None),
                delta_color="normal" if cost_match else "inverse",
            )

            # Issues list
            issues = v.get("issues", [])
            if issues:
                st.warning(
                    "**Issues found:**\n" + "\n".join(f"- {i}" for i in issues),
                    icon="⚠️",
                )
            else:
                st.success("All checks passed.", icon="✅")

        # Requirements (pre-call output)
        if meta.get("requirements"):
            st.divider()
            st.subheader("Extracted requirements (pre-call)")
            st.markdown(meta["requirements"])

        # Stale report — only for cache hits
        cache_key = meta.get("cache_key")
        if meta.get("cache_hit") and cache_key:
            st.divider()
            stale_flag_key = f"stale_done_{cache_key}"
            if st.session_state.get(stale_flag_key):
                st.info("Marcado como obsoleto. Se eliminó de la caché.", icon="🗑️")
            else:
                if st.button(
                    "👎 Marcar como obsoleto",
                    key=f"stale_btn_{cache_key}",
                    help="Elimina esta respuesta de la caché y registra un informe de respuesta obsoleta.",
                ):
                    svc = st.session_state.get("service")
                    if isinstance(svc, CachedLLMService):
                        loop = asyncio.new_event_loop()
                        loop.run_until_complete(svc.report_stale(cache_key))
                        loop.close()
                    st.session_state[stale_flag_key] = True
                    st.rerun()


def _get_session_id() -> str:
    ctx = get_script_run_ctx()
    return ctx.session_id if ctx and ctx.session_id else "unknown"


def _render_cache_metrics_sidebar() -> None:
    """Show aggregate cache statistics in a sidebar expander."""
    if not settings.cache_enabled:
        return
    svc = st.session_state.get("service")
    if not isinstance(svc, CachedLLMService):
        return
    with st.sidebar.expander("📊 Cache Metrics", expanded=False):
        if st.button("🔄 Refresh", key="cache_metrics_refresh"):
            st.session_state.pop("_cache_metrics", None)
        if "_cache_metrics" not in st.session_state:
            loop = asyncio.new_event_loop()
            st.session_state["_cache_metrics"] = loop.run_until_complete(svc.get_metrics())
            loop.close()
        m = st.session_state["_cache_metrics"]
        if not m:
            st.caption("Redis no disponible.")
            return
        c1, c2 = st.columns(2)
        c1.metric("Hit rate", f"{m['hit_rate_pct']} %")
        c2.metric("Total requests", m["total"])
        c3, c4 = st.columns(2)
        c3.metric("Hits", m["hits"])
        c4.metric("Misses", m["misses"])
        st.metric("Cost avoided", f"${m['cost_avoided_usd']:.6f}")
        c5, c6 = st.columns(2)
        c5.metric("Avg latency HIT", f"{m['avg_latency_hit_ms']} ms" if m["avg_latency_hit_ms"] is not None else "—")
        c6.metric("Avg latency MISS", f"{m['avg_latency_miss_ms']} ms" if m["avg_latency_miss_ms"] is not None else "—")
        if m["speedup_x"] is not None:
            st.metric("Speedup (MISS / HIT)", f"{int(m['speedup_x'])}x")
        c7, c8 = st.columns(2)
        c7.metric("Stale reports", m["stale_reports"])
        c8.metric("Stale rate", f"{m['stale_rate_pct']} %")


def _sync_stream(service, transcript: str, kwargs: dict) -> Generator[str, None, None]:
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
            async for delta in service.estimate_stream(transcript, **kwargs):
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
    st.session_state.active_provider = settings.llm_provider

# ── Page header ───────────────────────────────────────────────────────────────

st.title("Software Estimator")
st.caption("Paste a meeting transcript below to receive a detailed effort estimate.")

# ── Collapsible LLM options ───────────────────────────────────────────────────

session_id = _get_session_id()
with st.expander("LLM Options", expanded=False):
    col_a, col_b, col_c, col_d = st.columns(4)

    with col_a:
        st.subheader("Model")
        provider = st.selectbox(
            "Provider",
            options=["openai", "anthropic", "litellm"],
            index=["openai", "anthropic", "litellm"].index(st.session_state.active_provider),
            help="LLM provider. 'litellm' usa un Router con failover automático entre proveedores.",

        )
        if provider != st.session_state.active_provider:
            settings.llm_provider = provider  # type: ignore[assignment]
            st.session_state.service = create_llm_service()
            st.session_state.active_provider = provider
            st.session_state.messages = []
            st.rerun()

        available_models = _MODELS_BY_PROVIDER[provider]
        model = st.selectbox(
            "Model",
            options=available_models,
            help="Specific model to use. Models prefixed with 'o' (OpenAI) or 'opus' (Anthropic) support extended reasoning.",
        )

    with col_b:
        st.subheader("Sampling")
        _sampling_options = (
            ["temperature", "top_p", "top_k", "none"]
            if provider == "anthropic"
            else ["temperature", "top_p", "none"]
        )
        sampling_mode = st.radio(
            "Sampling parameter",
            options=_sampling_options,
            index=0,
            help=(
                "Only one sampling parameter can be active at a time. 'none' uses the model default. "
                "Top K is only supported by Anthropic."
            ),
        )
        temperature: float | None = None
        top_p: float | None = None
        top_k: int | None = None
        if sampling_mode == "temperature":
            temperature = st.slider(
                "Temperature",
                min_value=0.0, max_value=2.0, value=1.0, step=0.05,
                help="Controls randomness. Lower = more deterministic, higher = more creative. Typical range: 0.5–1.2.",
            )
        elif sampling_mode == "top_p":
            top_p = st.slider(
                "Top P",
                min_value=0.0, max_value=1.0, value=1.0, step=0.05,
                help="Nucleus sampling: considers only the top tokens whose cumulative probability reaches this value. Mutually exclusive with temperature.",
            )
        elif sampling_mode == "top_k":
            top_k = st.number_input(
                "Top K",
                min_value=1, max_value=500, value=40, step=1,
                help="Limits the token selection to the K most likely tokens at each step. Only supported by Anthropic models.",
            )

    with col_c:
        st.subheader("Generation")
        num_examples = st.slider(
            "Number of examples",
            min_value=0, max_value=5, value=3, step=1,
            help="How many few-shot examples to include in the system prompt (0 = zero-shot). More examples improve consistency but use more tokens.",
        )
        max_output_tokens = st.number_input(
            "Max output tokens",
            min_value=256, max_value=32_768, value=2_048, step=256,
            help="Hard cap on the number of tokens the model can generate. Higher values allow longer responses but increase cost and latency.",
        )
        model_supports_reasoning = model in _REASONING_MODELS
        reasoning_effort = st.select_slider(
            "Reasoning effort",
            options=["low", "medium", "high"],
            value="medium",
            disabled=not model_supports_reasoning,
            help=None if model_supports_reasoning else "Not supported by the selected model.",
        )

    with col_d:
        st.subheader("Session")
        use_stream = st.toggle(
            "Streaming response",
            value=True,
            help="When enabled, tokens are shown as they arrive (streaming). Disable for a single synchronous response.",
        )
        continue_conversation = st.toggle(
            "Multi-turn (continue conversation)",
            value=False,
            help="When enabled, each message continues from the previous one, keeping context across turns. Increases token usage over time.",
        )
        pre_call = st.toggle(
            "Pre-call (extract requirements first)",
            value=False,
            help="Runs a cheaper pre-processing step to extract structured requirements from the transcript before sending it to the estimator. Improves quality for long or noisy transcripts.",
        )
        st.write("")
        if st.button("Clear conversation", use_container_width=True):
            st.session_state.messages = []
            st.session_state.service.reset()
            st.rerun()

_render_cache_metrics_sidebar()

# ── Build call kwargs ─────────────────────────────────────────────────────────

_call_kwargs: dict = {
    "model": model,
    "reasoning_effort": reasoning_effort,
    "max_output_tokens": int(max_output_tokens),
    "continue_conversation": continue_conversation,
    "pre_call": pre_call,
    "num_examples": int(num_examples),
}
if temperature is not None:
    _call_kwargs["temperature"] = temperature
if top_p is not None:
    _call_kwargs["top_p"] = top_p
if top_k is not None:
    _call_kwargs["top_k"] = int(top_k)

# ── Estimation form ───────────────────────────────────────────────────────────

with st.form("estimation_form"):
    description = st.text_area(
        "Project description",
        placeholder="Describe the project to estimate (20\u20132000 characters)\u2026",
        max_chars=2000,
        height=160,
    )
    _col_pt, _col_dl, _col_of = st.columns(3)
    with _col_pt:
        project_type = st.selectbox(
            "Project type",
            options=[pt.value for pt in ProjectType],
            format_func=lambda v: v.replace("_", " ").title(),
        )
    with _col_dl:
        detail_level = st.selectbox(
            "Detail level",
            options=[dl.value for dl in DetailLevel],
            format_func=lambda v: v.title(),
        )
    with _col_of:
        output_format = st.selectbox(
            "Output format",
            options=list(OutputFormat),
            format_func=lambda f: f.value.replace("_", " ").title(),
        )
    submitted = st.form_submit_button("\U0001f4ca Estimate", use_container_width=True)

# ── Messages history ──────────────────────────────────────────────────────────

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message["role"] == "assistant" and "meta" in message:
            _render_details(message["meta"], session_id)

# ── Handle form submission ────────────────────────────────────────────────────

if submitted:
    if len(description.strip()) < 20:
        st.error("Project description must be at least 20 characters.", icon="\u26a0\ufe0f")
        st.stop()

    _context_parts = [
        f"**Project type:** {project_type.replace('_', ' ').title()}",
        f"**Detail level:** {detail_level.title()}",
        f"**Output format:** {output_format.value.replace('_', ' ').title()}",
        "",
        description.strip(),
    ]
    transcript = "\n".join(_context_parts)
    _call_kwargs["example_format"] = output_format.to_example_format()
    st.session_state.messages.append({"role": "user", "content": transcript})
    with st.chat_message("user"):
        st.markdown(transcript)

    with st.chat_message("assistant"):
        try:
            system_prompt = st.session_state.service._build_system_prompt(
                fmt=output_format.to_example_format(),
                num_examples=int(num_examples),
            )
            pre_call_prompt = (
                st.session_state.service._build_pre_call_system_prompt() if pre_call else None
            )

            import time
            _t0 = time.perf_counter()
            if use_stream:
                estimation = st.write_stream(
                    _sync_stream(st.session_state.service, transcript, _call_kwargs)
                )
                meta = {
                    k: v
                    for k, v in st.session_state.service._last_stream_result.items()
                    if k != "estimation"
                }
            else:
                with st.spinner("Generating estimation…"):
                    loop = asyncio.new_event_loop()
                    result = loop.run_until_complete(
                        st.session_state.service.estimate(transcript, **_call_kwargs)
                    )
                    loop.close()
                estimation = result["estimation"]
                st.markdown(estimation)
                meta = {k: v for k, v in result.items() if k != "estimation"}
            meta["response_time_s"] = round(time.perf_counter() - _t0, 2)

            finish_reason = meta.get("finish_reason", "unknown")
            validation = evaluate_estimation_structure(str(estimation), finish_reason)
            meta["validation"] = validation.model_dump()
            meta["system_prompt"] = system_prompt
            meta["pre_call_prompt"] = pre_call_prompt
            _render_details(meta, session_id)

            st.session_state.messages.append(
                {"role": "assistant", "content": estimation, "meta": meta}
            )

        except LLMServiceError as exc:
            st.error(
                f"**{exc.error_type}** (HTTP {exc.status_code})\n\n{exc.message}",
                icon="🚨",
            )
            st.session_state.messages.append(
                {"role": "assistant", "content": f"**Error {exc.status_code} — {exc.error_type}:** {exc.message}"}
            )
        except Exception as exc:
            st.error(f"**Unexpected error:** {exc}", icon="🚨")
            st.session_state.messages.append(
                {"role": "assistant", "content": f"**Unexpected error:** {exc}"}
            )
