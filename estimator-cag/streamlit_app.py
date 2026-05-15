import asyncio
import queue
import threading
import time
from typing import Generator

import streamlit as st
from streamlit.runtime.scriptrunner import get_script_run_ctx

from app.config import MODEL_REGISTRY, settings
from app.schemas.estimation import (
    DetailLevel,
    EstimationRequest,
    EstimationResponse,
    ExampleFormat,
    OutputFormat,
    ProjectType,
    ReferenceProject,
)
from app.services.cache_service import CachedEstimationService
from app.services.estimation_service import EstimationService
from app.services.helpers.error_mapper import LLMServiceError

# ── Provider / model registry ─────────────────────────────────────────────────

# All model names — used for model and fallback selectors.
_ALL_MODELS = list(MODEL_REGISTRY.keys())

# Models that support reasoning / extended thinking.
_REASONING_MODELS: set[str] = {
    name for name, cfg in MODEL_REGISTRY.items() if cfg.reasoning
}

# display name → litellm_params model string (e.g. "anthropic/claude-haiku-…").
_DISPLAY_TO_LITELLM_MODEL: dict[str, str] = {
    name: cfg.litellm_model for name, cfg in MODEL_REGISTRY.items()
}

# ── Service factory ───────────────────────────────────────────────────────────

def _build_service() -> EstimationService | CachedEstimationService:
    svc = EstimationService()
    if settings.cache_enabled:
        return CachedEstimationService(svc)
    return svc

# ── Helpers ───────────────────────────────────────────────────────────────────

_CHECK_LABELS: dict[str, str] = {
    "has_title": "H2 project title",
    "has_breakdown_table": "Breakdown table",
    "has_totals_section": "Totals section",
    "has_team_section": "Team section",
    "has_duration_section": "Duration section",
    "finish_reason_ok": "Finish reason",
}


def _render_validation_inline(response: EstimationResponse) -> None:
    """Render the output validation card inline, below the estimation text."""
    v = response.validation
    if v is None:
        return

    score_pct = int(v.score * 100)
    if v.score >= 0.8:
        color, icon = "green", "✅"
    elif v.score >= 0.5:
        color, icon = "orange", "⚠️"
    else:
        color, icon = "red", "❌"

    with st.expander(f"{icon} Output validation — score: :{color}[**{score_pct}%**]", expanded=v.score < 0.8):
        check_cols = st.columns(len(_CHECK_LABELS))
        for col, (key, label) in zip(check_cols, _CHECK_LABELS.items()):
            passed = getattr(v, key, False)
            col.metric(label, "✅" if passed else "❌")

        num_col1, num_col2 = st.columns(2)
        num_col1.metric(
            "Hours: declared / rows",
            f"{v.declared_total_hours} / {v.sum_row_hours}" if v.declared_total_hours is not None else "—",
            delta="✅ match" if v.hours_match else ("❌ mismatch" if v.hours_match is False else None),
            delta_color="normal" if v.hours_match else "inverse",
        )
        num_col2.metric(
            "Cost: declared / rows",
            f"{v.declared_total_cost:,.0f} / {v.sum_row_cost:,.0f}" if v.declared_total_cost is not None else "—",
            delta="✅ match" if v.cost_match else ("❌ mismatch" if v.cost_match is False else None),
            delta_color="normal" if v.cost_match else "inverse",
        )

        if v.issues:
            st.warning("**Issues found:**\n" + "\n".join(f"- {i}" for i in v.issues), icon="⚠️")
        else:
            st.success("All checks passed.", icon="✅")


def _render_details(response: EstimationResponse, session_id: str) -> None:
    """Render the full estimation metadata inside the sidebar."""
    with st.sidebar.expander(f"Details — session {session_id}", expanded=False):
        # Tokens
        st.subheader("Tokens")
        token_cols = st.columns(3)
        token_cols[0].metric("Input tokens", response.input_tokens)
        token_cols[1].metric("Output tokens", response.output_tokens)
        token_cols[2].metric("Estimated input tokens", response.estimated_input_tokens)

        st.divider()

        # Costs
        st.subheader("Costs (USD)")
        col7, col8 = st.columns(2)
        col7.metric("Turn cost", f"${response.turn_cost_usd:.6f}")
        col8.metric("Total cost", f"${response.total_cost_usd:.6f}")

        if response.pre_call_cost_usd is not None or response.estimated_precall_cost_usd is not None:
            col9, col10 = st.columns(2)
            col9.metric(
                "Pre-call cost",
                f"${response.pre_call_cost_usd:.6f}" if response.pre_call_cost_usd is not None else "—",
            )
            col10.metric(
                "Estimated pre-call cost",
                f"${response.estimated_precall_cost_usd:.6f}" if response.estimated_precall_cost_usd is not None else "—",
            )

        st.divider()

        # Run info
        st.subheader("Run info")
        cache_hit = getattr(response, "cache_hit", None)
        response_time_s = getattr(response, "response_time_s", None)
        run_items: list[tuple[str, str]] = [("Model", response.model)]
        if cache_hit is not None:
            run_items.append(("Cache", "✅ HIT" if cache_hit else "❌ MISS"))
        if response_time_s is not None:
            run_items.append(("Response time", f"{response_time_s} s"))
        run_cols = st.columns(len(run_items))
        for col, (label, value) in zip(run_cols, run_items):
            col.metric(label, value)
        st.caption(f"Response ID: `{response.response_id}`")

        # Validation
        if response.validation is not None:
            st.divider()
            v = response.validation
            score = v.score
            score_pct = int(score * 100)
            score_color = "green" if score >= 0.8 else ("orange" if score >= 0.5 else "red")
            st.subheader("Validation")
            st.markdown(
                f"**Score:** :{score_color}[{score_pct}%]  "
                f"({sum(1 for k in _CHECK_LABELS if getattr(v, k, False))}/{len(_CHECK_LABELS)} checks passed)"
            )

            check_cols = st.columns(len(_CHECK_LABELS))
            for col, (key, label) in zip(check_cols, _CHECK_LABELS.items()):
                passed = getattr(v, key, False)
                col.metric(label, "✅" if passed else "❌")

            num_col1, num_col2 = st.columns(2)
            hours_match = v.hours_match
            num_col1.metric(
                "Hours: declared vs rows",
                f"{v.declared_total_hours} / {v.sum_row_hours}" if v.declared_total_hours is not None else "—",
                delta="✅ match" if hours_match else ("❌ mismatch" if hours_match is False else None),
                delta_color="normal" if hours_match else "inverse",
            )
            cost_match = v.cost_match
            num_col2.metric(
                "Cost: declared vs rows",
                f"{v.declared_total_cost:,.0f} / {v.sum_row_cost:,.0f}" if v.declared_total_cost is not None else "—",
                delta="✅ match" if cost_match else ("❌ mismatch" if cost_match is False else None),
                delta_color="normal" if cost_match else "inverse",
            )

            issues = v.issues
            if issues:
                st.warning("**Issues found:**\n" + "\n".join(f"- {i}" for i in issues), icon="⚠️")
            else:
                st.success("All checks passed.", icon="✅")

        # Requirements (pre-call output)
        if response.requirements:
            st.divider()
            st.subheader("Extracted requirements (pre-call)")
            st.markdown(response.requirements)

        # Stale reporting — only for cache hits
        cache_key = getattr(response, "cache_key", None)
        if cache_hit and cache_key:
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
                    if isinstance(svc, CachedEstimationService):
                        asyncio.run_coroutine_threadsafe(
                            svc.report_stale(cache_key), _get_event_loop()
                        ).result()
                    st.session_state[stale_flag_key] = True
                    st.rerun()


# ── Page config ───────────────────────────────────────────────────────────────

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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_session_id() -> str:
    ctx = get_script_run_ctx()
    return ctx.session_id if ctx and ctx.session_id else "unknown"


def _get_event_loop() -> asyncio.AbstractEventLoop:
    """Return the persistent background event loop for this Streamlit session."""
    if "_bg_loop" not in st.session_state:
        loop = asyncio.new_event_loop()

        def _run(lp: asyncio.AbstractEventLoop) -> None:
            lp.run_forever()

        t = threading.Thread(target=_run, args=(loop,), daemon=True)
        t.start()
        st.session_state["_bg_loop"] = loop

    return st.session_state["_bg_loop"]


def _sync_stream(
    service: EstimationService | CachedEstimationService,
    request: EstimationRequest,
    prompt_version: str,
    response_out: list | None = None,
) -> Generator[str, None, None]:
    """Bridge the async estimate_stream generator to st.write_stream (sync).

    Runs on the persistent background event loop so TLS connections are reused.
    A sentinel signals stream completion.

    When *response_out* is provided, an :class:`EstimationResponse` built from
    the stream's usage metadata is appended to it after the last delta is
    yielded, so callers can display cost/token details in the sidebar.
    """
    _SENTINEL = object()
    delta_queue: queue.Queue = queue.Queue()
    exc_holder: list[BaseException] = []
    inner_response_out: list = []
    loop = _get_event_loop()

    async def _producer() -> None:
        try:
            inner = service._inner if isinstance(service, CachedEstimationService) else service
            async for delta in inner.estimate_stream(
                request,
                prompt_version=prompt_version,
                response_out=inner_response_out,
            ):
                delta_queue.put(delta)
        except BaseException as exc:  # noqa: BLE001
            exc_holder.append(exc)
        finally:
            delta_queue.put(_SENTINEL)

    asyncio.run_coroutine_threadsafe(_producer(), loop)

    while True:
        item = delta_queue.get()
        if item is _SENTINEL:
            break
        yield item

    if exc_holder:
        raise exc_holder[0]

    if response_out is not None and inner_response_out:
        response_out.extend(inner_response_out)


def _render_cache_metrics_sidebar() -> None:
    """Show aggregate cache statistics in a sidebar expander."""
    if not settings.cache_enabled:
        return
    svc = st.session_state.get("service")
    if not isinstance(svc, CachedEstimationService):
        return
    with st.sidebar.expander("📊 Cache Metrics", expanded=False):
        if st.button("🔄 Refresh", key="cache_metrics_refresh"):
            st.session_state.pop("_cache_metrics", None)
        if "_cache_metrics" not in st.session_state:
            st.session_state["_cache_metrics"] = asyncio.run_coroutine_threadsafe(
                svc.get_metrics(), _get_event_loop()
            ).result()
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


# ── Session state bootstrap ────────────────────────────────────────────────────

if "messages" not in st.session_state:
    st.session_state.messages = []

if "service" not in st.session_state:
    st.session_state.service = _build_service()

if "litellm_primary" not in st.session_state:
    st.session_state.litellm_primary = settings.litellm_primary_model
if "litellm_fallback" not in st.session_state:
    st.session_state.litellm_fallback = settings.litellm_fallback_model

_get_event_loop()

# ── Page header ───────────────────────────────────────────────────────────────

st.title("Software Estimator")
st.caption("Paste a meeting transcript below to receive a detailed effort estimate.")

# ── Collapsible LLM options ───────────────────────────────────────────────────

session_id = _get_session_id()
with st.expander("LLM Options", expanded=False):
    col_a, col_b, col_c, col_d = st.columns(4)

    with col_a:
        st.subheader("Model")

        # ── Primary model ─────────────────────────────────────────────────
        _primary_idx = (
            _ALL_MODELS.index(st.session_state.litellm_primary)
            if st.session_state.litellm_primary in _ALL_MODELS else 0
        )
        model = st.selectbox(
            "Model",
            options=_ALL_MODELS,
            index=_primary_idx,
            help="Primary model tried on every request.",
        )
        model_cfg = MODEL_REGISTRY[model]
        st.caption(f"Provider: **{model_cfg.provider}** | Context: {model_cfg.context_window:,} tokens")

        # ── Fallback model ────────────────────────────────────────────────
        _fallback_options = [m for m in _ALL_MODELS if m != model]
        _default_fallback = (
            st.session_state.litellm_fallback
            if st.session_state.litellm_fallback in _fallback_options
            else _fallback_options[0]
        )
        fallback_model = st.selectbox(
            "Fallback model",
            options=_fallback_options,
            index=_fallback_options.index(_default_fallback),
            help=(
                f"Used automatically after {settings.router_num_retries} failed "
                "retry/ies on the primary. Must differ from the primary model."
            ),
        )
        fallback_cfg = MODEL_REGISTRY[fallback_model]
        st.caption(f"Provider: **{fallback_cfg.provider}** | Context: {fallback_cfg.context_window:,} tokens")

        # Reconfigure router when either model changes
        _changed = (
            st.session_state.litellm_primary != model
            or st.session_state.litellm_fallback != fallback_model
        )
        if _changed:
            st.session_state.litellm_primary = model
            st.session_state.litellm_fallback = fallback_model
            from app.services.litellm_service import create_litellm_router_service
            create_litellm_router_service(
                _DISPLAY_TO_LITELLM_MODEL.get(model, model),
                _DISPLAY_TO_LITELLM_MODEL.get(fallback_model, fallback_model),
            )
            st.session_state.messages = []
            st.rerun()

        model_supports_reasoning = model in _REASONING_MODELS

    with col_b:
        st.subheader("Sampling")
        _is_anthropic = model_cfg.provider == "anthropic"
        _sampling_options = (
            ["temperature", "top_p", "top_k", "none"] if _is_anthropic
            else ["temperature", "top_p", "none"]
        )
        sampling_mode = st.radio(
            "Sampling parameter",
            options=_sampling_options,
            index=0,
            help=(
                "Only one parameter can be active at a time. "
                "'none' uses the model default. Top K is Anthropic-only."
            ),
        )
        temperature: float | None = None
        top_p: float | None = None
        top_k: int | None = None
        if sampling_mode == "temperature":
            temperature = st.slider("Temperature", min_value=0.0, max_value=1.0, value=0.0, step=0.05,
                                    help="Controls randomness. Lower = more deterministic.")
        elif sampling_mode == "top_p":
            top_p = st.slider("Top P", min_value=0.0, max_value=1.0, value=1.0, step=0.05,
                              help="Nucleus sampling. Mutually exclusive with temperature.")
        elif sampling_mode == "top_k":
            top_k = st.number_input("Top K", min_value=1, max_value=500, value=40, step=1,
                                    help="Top-K sampling. Anthropic only.")

        if model_supports_reasoning:
            reasoning_effort: str = st.select_slider(
                "Reasoning effort",
                options=["low", "medium", "high"],
                value="medium",
                help="Budget for extended thinking (o-series / Claude Opus).",
            )
        else:
            reasoning_effort = "medium"
            st.caption("Reasoning: not supported by selected model.")

    with col_c:
        st.subheader("Generation")
        num_examples = st.slider(
            "Number of examples",
            min_value=0, max_value=5, value=3, step=1,
            help="Few-shot examples injected in the system prompt (0 = zero-shot).",
        )
        max_output_tokens = st.number_input(
            "Max output tokens",
            min_value=256, max_value=32_768, value=2_048, step=256,
            help="Hard cap on tokens the model can generate.",
        )
        example_format = st.selectbox(
            "Example format",
            options=list(ExampleFormat),
            format_func=lambda f: f.value.replace("_", " ").title(),
        )
        prompt_version = st.selectbox(
            "Prompt version",
            options=["v1", "v2"],
            index=0,
            help="v1 — standard estimator tone. v2 — senior delivery consultant tone with confidence level.",
        )

    with col_d:
        st.subheader("Session")
        use_stream = st.toggle(
            "Streaming response",
            value=True,
            help=(
                "Tokens are shown as they arrive. "
                "Disable for full token/cost/validation metadata in the sidebar."
            ),
        )
        continue_conversation = st.toggle(
            "Multi-turn (continue conversation)",
            value=False,
            help="Each message continues from the previous one. Increases token usage over time.",
        )
        pre_call = st.toggle(
            "Pre-call (extract requirements first)",
            value=False,
            help=(
                "Runs a cheaper pre-processing call to extract structured requirements "
                "before the main estimation. Improves quality for long or noisy transcripts."
            ),
        )
        st.write("")
        if st.button("Clear conversation", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

_render_cache_metrics_sidebar()

# ── Estimation form ───────────────────────────────────────────────────────────

with st.form("estimation_form"):
    description = st.text_area(
        "Project description",
        placeholder="Describe the project to estimate (20–2000 characters)…",
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

    st.divider()
    st.markdown("**Reference projects** *(optional)*")
    num_ref = st.number_input(
        "Number of reference projects",
        min_value=0, max_value=5, value=0, step=1,
        help="Add past similar projects to help the model calibrate the estimate.",
    )
    _ref_entries: list[dict] = []
    for _i in range(int(num_ref)):
        st.markdown(f"_Project {_i + 1}_")
        _rc1, _rc2, _rc3, _rc4 = st.columns([3, 5, 2, 2])
        _ref_entries.append({
            "name": _rc1.text_input("Name", key=f"ref_name_{_i}", placeholder="e.g. HR Tool v1"),
            "description": _rc2.text_input("Description", key=f"ref_desc_{_i}", placeholder="e.g. Basic HR CRUD app"),
            "total_hours": _rc3.number_input("Hours", min_value=0, value=0, step=10, key=f"ref_hours_{_i}"),
            "total_cost": _rc4.number_input("Cost (EUR)", min_value=0, value=0, step=500, key=f"ref_cost_{_i}"),
        })

    submitted = st.form_submit_button("📊 Estimate", use_container_width=True)

# ── Messages history ──────────────────────────────────────────────────────────

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message["role"] == "assistant" and message.get("response") is not None:
            _render_validation_inline(message["response"])
            _render_details(message["response"], session_id)

# ── Handle form submission ────────────────────────────────────────────────────

if submitted:
    if len(description.strip()) < 20:
        st.error("Project description must be at least 20 characters.", icon="⚠️")
        st.stop()

    _reference_projects = [
        ReferenceProject(
            name=r["name"],
            description=r["description"],
            total_hours=r["total_hours"] or None,
            total_cost=r["total_cost"] or None,
        )
        for r in _ref_entries
        if r["name"].strip() and r["description"].strip()
    ] or None

    _request = EstimationRequest(
        transcription=description.strip(),
        model=model,  # type: ignore[arg-type]
        output_format=output_format,
        detail_level=DetailLevel(detail_level),
        project_type=ProjectType(project_type),
        num_examples=int(num_examples),
        example_format=example_format,
        max_output_tokens=int(max_output_tokens),
        temperature=temperature,
        top_p=top_p,
        top_k=int(top_k) if top_k is not None else None,
        reasoning_effort=reasoning_effort,  # type: ignore[arg-type]
        pre_call=pre_call,
        reference_projects=_reference_projects,
    )

    st.session_state.messages.append({"role": "user", "content": description.strip()})
    with st.chat_message("user"):
        st.markdown(description.strip())

    with st.chat_message("assistant"):
        try:
            _t0 = time.perf_counter()

            if use_stream:
                _captured: list[EstimationResponse] = []
                estimation_text = st.write_stream(
                    _sync_stream(st.session_state.service, _request, prompt_version, _captured)
                )
                response_time_s = round(time.perf_counter() - _t0, 2)
                st.caption(f"Completed in {response_time_s}s")
                if _captured:
                    _stream_meta = _captured[0].model_copy(update={"response_time_s": response_time_s})
                    _render_validation_inline(_stream_meta)
                    _render_details(_stream_meta, session_id)
                    st.session_state.messages.append(
                        {"role": "assistant", "content": str(estimation_text), "response": _stream_meta}
                    )
                else:
                    st.session_state.messages.append(
                        {"role": "assistant", "content": str(estimation_text), "response": None}
                    )

            else:
                with st.spinner("Generating estimation…"):
                    response = asyncio.run_coroutine_threadsafe(
                        st.session_state.service.estimate(_request, prompt_version=prompt_version),
                        _get_event_loop(),
                    ).result()
                response_time_s = round(time.perf_counter() - _t0, 2)
                response = response.model_copy(update={"response_time_s": response_time_s})  # type: ignore[call-arg]

                st.markdown(response.estimation)
                st.caption(f"Completed in {response_time_s}s")
                _render_validation_inline(response)
                _render_details(response, session_id)

                st.session_state.messages.append(
                    {"role": "assistant", "content": response.estimation, "response": response}
                )

        except LLMServiceError as exc:
            st.error(
                f"**{exc.error_type}** (HTTP {exc.status_code})\n\n{exc.message}",
                icon="🚨",
            )
            st.session_state.messages.append(
                {"role": "assistant", "content": f"**Error {exc.status_code} — {exc.error_type}:** {exc.message}", "response": None}
            )
        except Exception as exc:
            st.error(f"**Unexpected error:** {exc}", icon="🚨")
            st.session_state.messages.append(
                {"role": "assistant", "content": f"**Unexpected error:** {exc}", "response": None}
            )
