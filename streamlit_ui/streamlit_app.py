"""
Streamlit reviewer UI for Stage 1 hackathon evaluation (document-only).

Evaluators can load a CSV, run AI scoring, review ranked results, apply manual
overrides (persisted in session for re-apply after re-runs), and export results.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TypeVar

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv()

from src.exporter import (  # noqa: E402
    build_results_dataframe,
    export_dataframe_to_excel,
    export_dataframe_to_excel_bytes,
)
from src.models import EvaluationBreakdown, RankedEvaluation, Submission  # noqa: E402
from src.pipeline import load_session_results, run_pipeline, save_final_shortlist  # noqa: E402
from src.load_data import load_submissions  # noqa: E402
from src.validate_data import validate_columns  # noqa: E402
from src.utils import setup_logging  # noqa: E402

logger = logging.getLogger(__name__)
setup_logging()

T = TypeVar("T")

DEFAULT_CSV = ROOT / "data" / "submissions.csv"
UPLOADED_CSV = ROOT / "output" / "_uploaded_submissions.csv"
OUTPUT_DIR = ROOT / "output"

SESSION_RANKED = "ranked"
SESSION_PREVIEW = "preview_df"
SESSION_OVERRIDES = "manual_overrides"
SESSION_CSV_PATH = "active_csv_path"
SESSION_SELECTED = "selected_submission_id"

_CRITERION_ROWS: list[
    tuple[str, str, int, Callable[[EvaluationBreakdown], int], Callable[[EvaluationBreakdown], str]]
] = [
    ("Business Impact", "business_impact", 40, lambda b: b.business_impact.score, lambda b: b.business_impact.reason),
    ("Feasibility & Scalability", "feasibility_scalability", 30, lambda b: b.feasibility_scalability.score, lambda b: b.feasibility_scalability.reason),
    ("AI Depth & Creativity", "ai_depth_creativity", 30, lambda b: b.ai_depth_creativity.score, lambda b: b.ai_depth_creativity.reason),
]


def _inject_global_styles() -> None:
    """Add a subtle, professional UI skin (CSS only; keeps Streamlit simple)."""
    st.markdown(
        """
<style>
/* Page background */
[data-testid="stAppViewContainer"]{
  background: radial-gradient(1200px 600px at 20% -10%, rgba(79,141,247,0.22), rgba(0,0,0,0) 55%),
              radial-gradient(900px 450px at 95% 5%, rgba(16,185,129,0.14), rgba(0,0,0,0) 55%),
              linear-gradient(180deg, #0B1220 0%, #070B14 100%) !important;
}

/* Header spacing */
.block-container{ padding-top: 2.2rem; }

/* Cards */
.he-card{
  background: rgba(17, 27, 46, 0.88);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 14px;
  padding: 14px 16px;
  box-shadow: 0 10px 30px rgba(0,0,0,0.20);
}
.he-kicker{ font-size: 0.82rem; opacity: 0.75; margin-bottom: 2px; }
.he-title{ font-size: 1.6rem; font-weight: 650; line-height: 1.15; margin: 0; }
.he-subtitle{ margin-top: 6px; opacity: 0.78; }

/* Sidebar polish */
[data-testid="stSidebar"]{
  background: linear-gradient(180deg, rgba(17,27,46,0.95) 0%, rgba(9,14,25,0.95) 100%) !important;
  border-right: 1px solid rgba(255,255,255,0.07);
}

/* Dataframe */
div[data-testid="stDataFrame"]{
  border: 1px solid rgba(255,255,255,0.07);
  border-radius: 12px;
  overflow: hidden;
}

/* Expander */
div[data-testid="stExpander"]{
  border: 1px solid rgba(255,255,255,0.07);
  border-radius: 12px;
}
</style>
        """,
        unsafe_allow_html=True,
    )


def _bootstrap_session_state() -> None:
    """Initialize Streamlit session keys once per browser session."""
    defaults: dict[str, Any] = {
        SESSION_CSV_PATH: DEFAULT_CSV,
        "using_uploaded_csv": False,
        SESSION_PREVIEW: None,
        SESSION_RANKED: [],
        SESSION_SELECTED: None,
        SESSION_OVERRIDES: {},
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _get_override_store() -> dict[str, dict[str, Any]]:
    """Mutable map of submission_id -> saved manual edits (survives re-evaluation)."""
    store = st.session_state.get(SESSION_OVERRIDES)
    if not isinstance(store, dict):
        store = {}
        st.session_state[SESSION_OVERRIDES] = store
    return store


def _apply_stored_overrides(ranked: list[RankedEvaluation]) -> None:
    """Apply ``SESSION_OVERRIDES`` onto fresh evaluation results."""
    store = _get_override_store()
    for r in ranked:
        entry = store.get(r.submission.submission_id)
        if not entry:
            continue
        if "manual_total_score" in entry:
            r.manual_total_score = entry["manual_total_score"]
        if "evaluator_notes" in entry:
            r.evaluator_notes = entry["evaluator_notes"]
        if "manual_shortlisted" in entry:
            r.manual_shortlisted = entry["manual_shortlisted"]


def _sync_record_to_store(record: RankedEvaluation) -> None:
    """Persist one record's manual fields into the override store."""
    store = _get_override_store()
    store[record.submission.submission_id] = {
        "manual_total_score": record.manual_total_score,
        "evaluator_notes": record.evaluator_notes,
        "manual_shortlisted": record.manual_shortlisted,
    }


def _try_default_preview() -> None:
    """Silently load the default CSV preview when possible (no UI errors)."""
    if st.session_state.get(SESSION_PREVIEW) is not None:
        return
    if not DEFAULT_CSV.exists():
        return
    try:
        df = load_submissions(DEFAULT_CSV)
        validate_columns(df)
        st.session_state[SESSION_PREVIEW] = df
    except Exception as exc:  # noqa: BLE001
        logger.info("Default CSV preview not loaded: %s", exc)


def _active_csv_path() -> Path:
    """Return the CSV path currently selected for evaluation."""
    path = st.session_state.get(SESSION_CSV_PATH, DEFAULT_CSV)
    return Path(path)


def _preview_frame() -> pd.DataFrame | None:
    """Return a validated preview DataFrame, or ``None`` if missing/corrupt."""
    df = st.session_state.get(SESSION_PREVIEW)
    return df if isinstance(df, pd.DataFrame) else None


def _safe_text(value: object, *, empty: str = "—") -> str:
    """Normalize optional text for UI display."""
    if value is None:
        return empty
    text = str(value).replace("\r\n", "\n").strip()
    return text if text else empty


def _notify_exception(channel: Callable[..., None], title: str, exc: BaseException) -> None:
    """Log and show a user-friendly error."""
    logger.exception("%s", title)
    channel(f"{title}: {exc}")


def _run_with_spinner(label: str, fn: Callable[[], T]) -> T | None:
    """Run a callable inside a spinner; return ``None`` on failure."""
    try:
        with st.spinner(label):
            return fn()
    except FileNotFoundError as exc:
        _notify_exception(st.error, "File not found", exc)
    except ValueError as exc:
        _notify_exception(st.error, "Invalid input", exc)
    except RuntimeError as exc:
        _notify_exception(st.error, "Evaluation failed", exc)
    except OSError as exc:
        _notify_exception(st.error, "I/O error", exc)
    except Exception as exc:  # noqa: BLE001
        _notify_exception(st.error, "Unexpected error", exc)
    return None


def _safe_load_preview(path: Path) -> pd.DataFrame | None:
    """Load and validate a CSV for preview; show sidebar errors on failure."""
    try:
        df = load_submissions(path)
        validate_columns(df)
        return df
    except (FileNotFoundError, ValueError, pd.errors.ParserError, OSError) as exc:
        logger.warning("Preview load failed for %s: %s", path, exc)
        st.sidebar.error(f"Could not load CSV: {exc}")
        return None


def _ranked_results() -> list[RankedEvaluation]:
    """Return evaluated results from session state."""
    ranked = st.session_state.get(SESSION_RANKED, [])
    return ranked if isinstance(ranked, list) else []


def _set_ranked(ranked: list[RankedEvaluation]) -> None:
    """Persist evaluated results, re-apply manual overrides, and fix selection."""
    _apply_stored_overrides(ranked)
    st.session_state[SESSION_RANKED] = ranked
    if ranked:
        ids = [r.submission.submission_id for r in ranked]
        current = st.session_state.get(SESSION_SELECTED)
        if current not in ids:
            st.session_state[SESSION_SELECTED] = ids[0]
    else:
        st.session_state[SESSION_SELECTED] = None


def _display_team_or_id(submission: Submission) -> str:
    """Prefer team name when present; otherwise fall back to submission id."""
    team = (submission.team_name or "").strip()
    return team if team else str(submission.submission_id)


def build_ranked_summary_dataframe(ranked: list[RankedEvaluation]) -> pd.DataFrame:
    """Build a compact evaluator-facing table for the Overview tab."""
    rows: list[dict[str, Any]] = []
    for r in ranked:
        b = r.evaluation.breakdown
        total = (
            r.manual_total_score
            if r.manual_total_score is not None
            else r.evaluation.total_score
        )
        rows.append(
            {
                "Rank": int(r.rank),
                "Team / ID": _display_team_or_id(r.submission),
                "Submission ID": _safe_text(r.submission.submission_id, empty=""),
                "Category": _safe_text(r.submission.category_selection, empty="—"),
                "Total": int(total),
                "BI (40)": int(b.business_impact.score),
                "FS (30)": int(b.feasibility_scalability.score),
                "AD (30)": int(b.ai_depth_creativity.score),
            }
        )
    return pd.DataFrame(rows)


def compute_summary_metrics(
    ranked: list[RankedEvaluation],
    preview_df: pd.DataFrame | None,
) -> dict[str, float | int]:
    """Compute headline metrics for the Overview tab."""
    evaluated = len(ranked)
    preview_rows = len(preview_df) if preview_df is not None else 0

    if evaluated:
        totals = [
            int(
                r.manual_total_score
                if r.manual_total_score is not None
                else r.evaluation.total_score
            )
            for r in ranked
        ]
        avg = float(sum(totals) / len(totals)) if totals else 0.0
        top = int(max(totals)) if totals else 0
        shortlist = int(sum(1 for r in ranked if r.effective_shortlisted()))
        total_rows = preview_rows or evaluated
    else:
        avg = 0.0
        top = 0
        shortlist = 0
        total_rows = preview_rows

    return {
        "total_rows": int(total_rows),
        "evaluated": int(evaluated),
        "average_score": round(avg, 2),
        "top_score": int(top),
        "shortlist": int(shortlist),
    }


def _apply_filters(summary: pd.DataFrame, category: str) -> pd.DataFrame:
    """Filter the summary table for sidebar controls."""
    view = summary.copy()
    if category != "All" and "Category" in view.columns:
        view = view[view["Category"] == category]
    return view


def _get_selected_record(
    ranked: list[RankedEvaluation], submission_id: str | None
) -> RankedEvaluation | None:
    """Return the currently selected ranked record, if any."""
    if not ranked or not submission_id:
        return None
    for r in ranked:
        if r.submission.submission_id == submission_id:
            return r
    return None


def _export_stamp() -> str:
    """UTC timestamp suitable for filenames."""
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")


def render_sidebar() -> str:
    """Render sidebar controls; return Overview category filter."""
    st.sidebar.markdown("### Hackathon Evaluator")
    st.sidebar.caption("Stage 1 · document-only review")

    uploaded = st.sidebar.file_uploader("Upload submissions CSV", type=["csv"])
    if uploaded is not None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        UPLOADED_CSV.write_bytes(uploaded.getvalue())
        st.session_state[SESSION_CSV_PATH] = UPLOADED_CSV
        st.session_state["using_uploaded_csv"] = True
        preview = _safe_load_preview(UPLOADED_CSV)
        if preview is not None:
            st.session_state[SESSION_PREVIEW] = preview
            st.sidebar.success(f"Uploaded CSV ready ({len(preview)} rows).")

    if st.sidebar.button("Load default CSV", use_container_width=True):
        st.session_state[SESSION_CSV_PATH] = DEFAULT_CSV
        st.session_state["using_uploaded_csv"] = False
        preview = _safe_load_preview(DEFAULT_CSV)
        if preview is not None:
            st.session_state[SESSION_PREVIEW] = preview
            st.sidebar.success(f"Default CSV ready ({len(preview)} rows).")

    st.sidebar.divider()
    st.sidebar.markdown("**Evaluation**")
    mock = st.sidebar.toggle("Mock mode (no API calls)", value=True)
    model = st.sidebar.text_input("OpenAI model override (optional)", value="")

    if st.sidebar.button("Run evaluation", type="primary", use_container_width=True):
        path = _active_csv_path()
        if not path.exists():
            st.sidebar.error(f"CSV not found at: {path}")
        else:

            def _run() -> list[RankedEvaluation]:
                return run_pipeline(path, mock=mock, model=model.strip() or None)

            ranked = _run_with_spinner("Running AI evaluation — this may take a few minutes…", _run)
            if ranked is not None:
                _set_ranked(ranked)
                st.sidebar.success(f"Evaluated {len(ranked)} submissions.")

    if st.sidebar.button("Load last session results", use_container_width=True):

        def _load() -> list[RankedEvaluation]:
            return load_session_results()

        ranked = _run_with_spinner("Loading saved results…", _load)
        if ranked is not None:
            _set_ranked(ranked)
            if ranked:
                st.sidebar.success(f"Loaded {len(ranked)} evaluated rows.")
            else:
                st.sidebar.warning("No saved session results found yet.")

    st.sidebar.divider()
    st.sidebar.markdown("**Table filters**")
    ranked = _ranked_results()
    categories = sorted({_safe_text(r.submission.category_selection, empty="") for r in ranked if r.submission.category_selection})
    categories = [c for c in categories if c != "—"]
    category = st.sidebar.selectbox("Category", options=["All"] + categories, index=0)

    st.sidebar.divider()
    st.sidebar.markdown("**Export**")
    st.sidebar.caption("Use the Export tab for downloads.")
    st.sidebar.caption(f"Active CSV: `{_active_csv_path().name}`")

    return category


def _render_metrics_row(metrics: dict[str, float | int], *, has_evaluated: bool) -> None:
    """Render summary metrics with consistent empty handling."""
    c1, c2, c3, c4, c5 = st.columns(5)
    total_rows = metrics["total_rows"]
    c1.metric("Total rows (CSV)", total_rows if total_rows else "—")
    c2.metric("Evaluated", metrics["evaluated"])
    if has_evaluated:
        c3.metric("Average score", f"{metrics['average_score']:.2f}")
        c4.metric("Top score", metrics["top_score"])
        c5.metric("Shortlisted", metrics["shortlist"])
    else:
        c3.metric("Average score", "—")
        c4.metric("Top score", "—")
        c5.metric("Shortlisted", "—")


def render_overview_tab(
    ranked: list[RankedEvaluation],
    preview_df: pd.DataFrame | None,
    category: str,
) -> None:
    """Overview metrics + ranked table."""
    metrics = compute_summary_metrics(ranked, preview_df)
    _render_metrics_row(metrics, has_evaluated=bool(ranked))

    if not ranked:
        st.info(
            "No evaluation results yet. Use the sidebar to load a CSV, then run **Run evaluation** "
            "or **Load last session results**."
        )
        pf = _preview_frame()
        if pf is not None and not pf.empty:
            with st.expander("Preview loaded CSV (first 10 rows)", expanded=False):
                st.dataframe(
                    pf.head(10).fillna(""),
                    use_container_width=True,
                    hide_index=True,
                    height=min(420, 36 * (len(pf.head(10)) + 1)),
                )
        return

    summary = build_ranked_summary_dataframe(ranked)
    view = _apply_filters(summary, category)
    st.subheader("Ranked submissions")
    st.caption("Columns: BI=Business Impact, FS=Feasibility & Scalability, AD=AI Depth & Creativity.")

    if view.empty:
        st.warning("No rows match the current filters.")
        return

    show_opt = st.selectbox(
        "Show",
        options=["Top 10", "Top 25", "Top 50", "All"],
        index=0,
        key="overview_show_count",
        help="Choose how many teams to display in the ranked table.",
    )
    limit_map = {"Top 10": 10, "Top 25": 25, "Top 50": 50, "All": None}
    limit = limit_map.get(show_opt)
    if limit is not None:
        view = view.sort_values("Rank").head(int(limit)).copy()

    column_config: dict[str, Any] = {
        "Rank": st.column_config.NumberColumn("Rank", format="%d"),
        "Team / ID": st.column_config.TextColumn("Team / ID", width="medium"),
        "Submission ID": st.column_config.TextColumn("Submission ID", width="medium"),
        "Category": st.column_config.TextColumn("Category", width="medium"),
        "Total": st.column_config.ProgressColumn(
            "Total (0–100)",
            format="%d",
            min_value=0,
            max_value=100,
        ),
        "BI (40)": st.column_config.NumberColumn("BI (40)", format="%d"),
        "FS (30)": st.column_config.NumberColumn("FS (30)", format="%d"),
        "AD (30)": st.column_config.NumberColumn("AD (30)", format="%d"),
    }

    st.dataframe(
        view,
        column_config=column_config,
        use_container_width=True,
        hide_index=True,
        height=min(520, 38 * (len(view) + 1)),
    )


def _render_scrollable_text(label: str, text: str, *, key_suffix: str) -> None:
    """Render long submission fields in a fixed-height, scrollable box."""
    safe_key = f"txt::{key_suffix}::{label}".replace(" ", "_")
    with st.expander(label, expanded=False):
        st.text_area(
            label,
            value=text,
            height=280,
            disabled=True,
            label_visibility="collapsed",
            key=safe_key,
        )


def _render_score_breakdown(breakdown_obj: EvaluationBreakdown) -> None:
    """Show scores as progress bars plus reasons in expanders."""
    st.markdown("##### Criterion scores")
    for title, _key, cap, score_fn, reason_fn in _CRITERION_ROWS:
        score = int(score_fn(breakdown_obj))
        ratio = 0.0 if cap <= 0 else max(0.0, min(1.0, score / float(cap)))
        st.caption(f"{title} — {score} / {cap}")
        st.progress(ratio)
        reason = _safe_text(reason_fn(breakdown_obj), empty="No reason provided.")
        with st.expander(f"Why: {title}", expanded=False):
            st.write(reason)


def render_detail_tab(ranked: list[RankedEvaluation]) -> None:
    """Detailed review + manual overrides."""
    if not ranked:
        st.info("Run an evaluation to review submissions in detail.")
        return

    ids = [r.submission.submission_id for r in ranked]
    previous = st.session_state.get(SESSION_SELECTED)
    index = ids.index(previous) if previous in ids else 0

    top = st.columns([2, 1])
    with top[0]:
        st.markdown("##### Review a submission")
        st.caption("Pick a team below, then scroll to overrides at the bottom of this tab.")
    with top[1]:
        selected = st.selectbox("Submission", options=ids, index=index, label_visibility="collapsed")
    st.session_state[SESSION_SELECTED] = selected

    current = _get_selected_record(ranked, selected)
    if current is None:
        st.error("Could not find the selected submission.")
        return

    sub = current.submission
    ev = current.evaluation
    b = ev.breakdown

    meta_cols = st.columns([2, 1, 1, 1])
    with meta_cols[0]:
        st.markdown(f"### {_safe_text(_display_team_or_id(sub))}")
        st.caption(f"Submission ID: `{_safe_text(sub.submission_id)}`")
    with meta_cols[1]:
        st.metric("Rank", int(current.rank))
    with meta_cols[2]:
        st.metric("Total (displayed)", int(current.manual_total_score or ev.total_score))
    with meta_cols[3]:
        st.metric("Shortlist (final)", "Yes" if current.effective_shortlisted() else "No")

    if sub.category_warning:
        st.warning(_safe_text(sub.category_warning))

    st.divider()
    st.markdown("##### Submission text (read-only)")
    txt_cols = st.columns(2)
    with txt_cols[0]:
        _render_scrollable_text(
            "Key Submission Impact",
            _safe_text(sub.key_submission_impact, empty=""),
            key_suffix=selected,
        )
        _render_scrollable_text(
            "Business Use Case and Impact",
            _safe_text(sub.business_use_case_and_impact, empty=""),
            key_suffix=selected,
        )
    with txt_cols[1]:
        _render_scrollable_text(
            "Solution / Approach Overview",
            _safe_text(sub.solution_approach_overview, empty=""),
            key_suffix=selected,
        )
        _render_scrollable_text(
            "Tools and Technology Used",
            _safe_text(sub.tools_and_technology_used, empty=""),
            key_suffix=selected,
        )

    st.divider()
    _render_score_breakdown(b)

    st.divider()
    st.markdown("##### Model narrative")
    c1, c2 = st.columns(2)
    with c1:
        st.metric("Model total (recomputed)", int(ev.total_score))
    with c2:
        st.metric("Model shortlist recommendation", _safe_text(ev.shortlist_recommendation, empty="—"))

    with st.expander("Final summary (model)", expanded=True):
        st.write(_safe_text(ev.final_summary, empty="No summary returned."))

    st.divider()
    st.markdown("##### Manual overrides")
    st.caption("Overrides persist for this browser session and are re-applied after you re-run evaluation.")

    if current.has_manual_edits():
        st.success("This submission has saved evaluator edits.")

    use_manual_score = st.checkbox(
        "Override total score",
        value=current.manual_total_score is not None,
        key=f"use_manual_score::{selected}",
    )
    default_score = int(current.manual_total_score if current.manual_total_score is not None else ev.total_score)
    manual_score = st.number_input(
        "Manual total score (0–100)",
        min_value=0,
        max_value=100,
        value=default_score,
        step=1,
        disabled=not use_manual_score,
        key=f"manual_score::{selected}",
    )

    override_shortlist = st.checkbox(
        "Manually set shortlist status",
        value=current.manual_shortlisted is not None,
        key=f"use_manual_sl::{selected}",
    )
    default_sl = (
        bool(current.manual_shortlisted)
        if current.manual_shortlisted is not None
        else bool(current.effective_shortlisted())
    )
    manual_sl = st.toggle(
        "Include in final shortlist",
        value=default_sl,
        disabled=not override_shortlist,
        key=f"manual_sl::{selected}",
    )

    notes = st.text_area(
        "Evaluator notes",
        value=current.evaluator_notes or "",
        height=140,
        key=f"notes::{selected}",
    )

    if st.button("Save changes", type="primary", key=f"save::{selected}"):
        current.manual_total_score = int(manual_score) if use_manual_score else None
        current.evaluator_notes = notes.strip() or None
        current.manual_shortlisted = bool(manual_sl) if override_shortlist else None
        _sync_record_to_store(current)
        _set_ranked(ranked)
        st.success("Saved. Overrides will persist if you re-run evaluation.")


def render_export_tab(ranked: list[RankedEvaluation]) -> None:
    """Downloads + on-disk exports."""
    if not ranked:
        st.info("Run an evaluation before exporting results.")
        return

    full_df = build_results_dataframe(ranked)
    if "final_shortlisted" in full_df.columns:
        mask = full_df["final_shortlisted"].fillna(False).astype(bool)
        top_df = full_df.loc[mask].copy()
    else:
        top_df = full_df.head(10).copy()

    full_csv_df = full_df.fillna("")
    top_csv_df = top_df.fillna("")

    stamp = _export_stamp()
    st.markdown("##### Download")
    st.caption("Filenames include a UTC timestamp to avoid accidental overwrites.")

    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            label="Full results (CSV)",
            data=full_csv_df.to_csv(index=False).encode("utf-8"),
            file_name=f"full_results_{stamp}.csv",
            mime="text/csv",
            use_container_width=True,
        )
        st.download_button(
            label="Shortlist (CSV)",
            data=top_csv_df.to_csv(index=False).encode("utf-8"),
            file_name=f"shortlist_{stamp}.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with c2:
        try:
            full_xlsx = export_dataframe_to_excel_bytes(full_df)
            st.download_button(
                label="Full results (Excel)",
                data=full_xlsx,
                file_name=f"full_results_{stamp}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        except Exception as exc:  # noqa: BLE001
            st.error(f"Could not build Excel export: {exc}")

        try:
            top_xlsx = export_dataframe_to_excel_bytes(top_df)
            st.download_button(
                label="Shortlist (Excel)",
                data=top_xlsx,
                file_name=f"shortlist_{stamp}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        except Exception as exc:  # noqa: BLE001
            st.error(f"Could not build Excel shortlist export: {exc}")

    st.divider()
    st.markdown("##### Write to disk")
    st.caption(f"Writes under `{OUTPUT_DIR}`.")

    c3, c4, c5 = st.columns(3)
    with c3:
        if st.button("Write ui_full_results.xlsx", use_container_width=True):

            def _write_full() -> bool:
                export_dataframe_to_excel(full_df, OUTPUT_DIR / "ui_full_results.xlsx")
                return True

            if _run_with_spinner("Writing Excel…", _write_full) is True:
                st.success("Wrote output/ui_full_results.xlsx")
    with c4:
        if st.button("Write ui_top_shortlist.xlsx", use_container_width=True):

            def _write_top() -> bool:
                export_dataframe_to_excel(top_df, OUTPUT_DIR / "ui_top_shortlist.xlsx")
                return True

            if _run_with_spinner("Writing Excel…", _write_top) is True:
                st.success("Wrote output/ui_top_shortlist.xlsx")
    with c5:
        if st.button("Write final_shortlist.csv", use_container_width=True):

            def _save() -> Path:
                return save_final_shortlist(ranked)

            path = _run_with_spinner("Writing CSV…", _save)
            if path is not None:
                st.success(f"Wrote {path}")


def main() -> None:
    """Streamlit entrypoint."""
    st.set_page_config(
        page_title="Hackathon Stage 1 Evaluator",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    _bootstrap_session_state()
    _try_default_preview()
    _inject_global_styles()

    st.markdown(
        """
<div class="he-card">
  <div class="he-kicker">Stage 1 Evaluation</div>
  <div class="he-title">Hackathon Stage 1 Evaluator</div>
</div>
        """,
        unsafe_allow_html=True,
    )
    st.write("")

    category = render_sidebar()

    ranked = _ranked_results()
    preview_df = _preview_frame()

    tabs = st.tabs(["Overview", "Detailed Review", "Export"])
    with tabs[0]:
        render_overview_tab(ranked, preview_df, category)
    with tabs[1]:
        render_detail_tab(ranked)
    with tabs[2]:
        render_export_tab(ranked)


if __name__ == "__main__":
    main()
