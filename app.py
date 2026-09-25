from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

st.set_page_config(
    page_title="RAG Data Observatory",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');
    :root { --ink: #10252b; --muted: #627277; --mint: #b9e7d8; --coral: #f26b5e; --cream: #f7f4ed; --line: #dbe5e1; }
    html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; color: var(--ink); }
    .stApp { background: var(--cream); }
    h1, h2, h3 { font-family: 'Space Grotesk', sans-serif; letter-spacing: 0; }
    [data-testid="stSidebar"] { background: #10252b; }
    [data-testid="stSidebar"] * { color: #eaf7f1; }
    [data-testid="stSidebar"] .stRadio label { color: #d4e7e0; }
    .hero { background: #10252b; color: #f4fbf7; padding: 2rem 2.2rem; border-radius: 6px; margin-bottom: 1.4rem; border-left: 7px solid var(--coral); }
    .hero h1 { color: #f4fbf7; margin: 0 0 .35rem; font-size: 2.25rem; }
    .hero p { color: #b9d0c8; margin: 0; max-width: 780px; }
    .eyebrow { color: var(--mint); text-transform: uppercase; font-size: .72rem; font-weight: 700; letter-spacing: .12em; }
    .section-label { color: var(--coral); text-transform: uppercase; font-weight: 700; font-size: .72rem; letter-spacing: .1em; margin-top: 1rem; }
    .status { display: inline-block; padding: .3rem .55rem; border-radius: 3px; font-weight: 700; font-size: .78rem; }
    .pass { background: #d7f1e7; color: #176047; }
    .fail { background: #ffe0dc; color: #9d2e26; }
    .warn { background: #fff0c9; color: #755513; }
    div[data-testid="stMetric"] { background: #fffdf8; border: 1px solid var(--line); border-radius: 5px; padding: .8rem 1rem; }
    div[data-testid="stMetricLabel"] { color: var(--muted); }
    .caption { color: var(--muted); font-size: .85rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def load_metrics(name: str) -> dict[str, Any]:
    return load_json(DATA / "results" / f"{name}_metrics.json", {})


def load_quality(name: str) -> dict[str, Any]:
    return load_json(DATA / "quality" / f"{name}_quality_report.json", {})


@st.cache_data

def load_table(kind: str) -> pd.DataFrame:
    path = DATA / "clean" / f"papers_clean{kind}.csv"
    try:
        return pd.read_csv(path)
    except FileNotFoundError:
        return pd.DataFrame()


@st.cache_resource

def load_index():
    from core.config import load_settings
    from retrieval.index import LocalEmbeddingIndex

    return LocalEmbeddingIndex.load(load_settings())


baseline = load_metrics("baseline")
corrupted = load_metrics("corrupted")
repaired = load_metrics("repaired")
quality_baseline = load_quality("baseline")
quality_corrupted = load_quality("corrupted")
quality_repaired = load_quality("repaired")
freshness = load_json(DATA / "quality" / "freshness_report.json", {})
corrupted_freshness = load_json(DATA / "quality" / "corrupted_freshness_report.json", {})
repaired_freshness = load_json(DATA / "quality" / "repaired_freshness_report.json", {})

with st.sidebar:
    st.markdown("<div class='eyebrow'>DATA OBSERVATORY</div>", unsafe_allow_html=True)
    st.markdown("## RAG pipeline")
    st.caption("Crossref → clean → quality gate → ChromaDB")
    view = st.radio("View", ["Command center", "Dataset explorer", "Corruption log", "Retrieval demo"], label_visibility="collapsed")
    st.divider()
    st.caption("Evidence loaded from local pipeline artifacts")
    st.caption("Baseline · Corrupted · Repaired")

st.markdown(
    "<div class='hero'><div class='eyebrow'>CHECKPOINT 4 / LIVE EVIDENCE</div><h1>RAG Data Observatory</h1><p>See exactly how data quality changes retrieval behavior, then verify that rebuilding from Raw restores the baseline.</p></div>",
    unsafe_allow_html=True,
)


def status_badge(label: str, ok: bool | None, warning: bool = False) -> str:
    if warning:
        return f"<span class='status warn'>{label}</span>"
    return f"<span class='status {'pass' if ok else 'fail'}'>{label}</span>"


if view == "Command center":
    st.markdown("<div class='section-label'>At a glance</div>", unsafe_allow_html=True)
    cols = st.columns(4)
    cols[0].metric("Corpus records", len(load_table("")))
    cols[1].metric("Baseline hit rate", f"{baseline.get('retrieval_hit_rate', 0):.2f}")
    cols[2].metric("Corrupted hit rate", f"{corrupted.get('retrieval_hit_rate', 0):.2f}", delta=f"{corrupted.get('retrieval_hit_rate', 0) - baseline.get('retrieval_hit_rate', 0):.2f}")
    cols[3].metric("Repaired hit rate", f"{repaired.get('retrieval_hit_rate', 0):.2f}", delta=f"{repaired.get('retrieval_hit_rate', 0) - corrupted.get('retrieval_hit_rate', 0):.2f}")

    left, right = st.columns([1.5, 1])
    with left:
        st.markdown("<div class='section-label'>Retrieval impact</div>", unsafe_allow_html=True)
        metric_df = pd.DataFrame(
            {
                "Baseline": [baseline.get("retrieval_hit_rate", 0), baseline.get("mean_token_f1", 0), baseline.get("mean_judge_score", 0) / 5],
                "Corrupted": [corrupted.get("retrieval_hit_rate", 0), corrupted.get("mean_token_f1", 0), corrupted.get("mean_judge_score", 0) / 5],
                "Repaired": [repaired.get("retrieval_hit_rate", 0), repaired.get("mean_token_f1", 0), repaired.get("mean_judge_score", 0) / 5],
            },
            index=["Retrieval hit rate", "Token F1", "Judge score / 5"],
        )
        st.bar_chart(metric_df, height=310, color=["#10252b", "#f26b5e", "#55a98b"])
    with right:
        st.markdown("<div class='section-label'>Quality gate</div>", unsafe_allow_html=True)
        for label, quality in [("Baseline", quality_baseline), ("Corrupted", quality_corrupted), ("Repaired", quality_repaired)]:
            ok = quality.get("success")
            st.markdown(f"**{label}** &nbsp; {status_badge('PASS' if ok else 'FAIL', ok)}", unsafe_allow_html=True)
        st.markdown("<div class='section-label'>Freshness SLA</div>", unsafe_allow_html=True)
        freshness_df = pd.DataFrame(
            {
                "Stale rows": [freshness.get("stale_rows", 0), corrupted_freshness.get("stale_rows", 0), repaired_freshness.get("stale_rows", 0)],
                "Total rows": [freshness.get("total_rows", 0), corrupted_freshness.get("total_rows", 0), repaired_freshness.get("total_rows", 0)],
            },
            index=["Baseline", "Corrupted", "Repaired"],
        )
        st.dataframe(freshness_df, use_container_width=True, height=145)

    st.markdown("<div class='section-label'>Experiment readout</div>", unsafe_allow_html=True)
    st.info("The combined corruption experiment drops retrieval hit rate from 1.00 to 0.20. Rebuilding from the Raw snapshot restores both quality-gate status and retrieval metrics to baseline.")

elif view == "Dataset explorer":
    st.markdown("<div class='section-label'>Inspect records</div>", unsafe_allow_html=True)
    dataset_choice = st.selectbox("Dataset", ["Clean baseline", "Corrupted", "Repaired"])
    suffix = {"Clean baseline": "", "Corrupted": "_corrupted", "Repaired": "_repaired"}[dataset_choice]
    table = load_table(suffix)
    query = st.text_input("Filter by title, DOI, author or category", placeholder="e.g. retrieval")
    if query and not table.empty:
        haystack = table.astype(str).agg(" ".join, axis=1).str.lower()
        table = table[haystack.str.contains(query.lower(), regex=False)]
    st.caption(f"{len(table)} records shown")
    columns = [column for column in ["paper_id", "title", "published", "age_days", "authors_joined", "categories_joined", "summary_chars"] if column in table.columns]
    st.dataframe(table[columns], use_container_width=True, height=500, hide_index=True)

elif view == "Corruption log":
    st.markdown("<div class='section-label'>Controlled experiment</div>", unsafe_allow_html=True)
    log = load_json(DATA / "results" / "corruption_log.json", {"scenarios": []})
    st.caption(f"{log.get('total_scenarios', 0)} scenarios · {log.get('original_rows', 0)} original rows · {log.get('corrupted_rows', 0)} corrupted rows")
    for scenario in log.get("scenarios", []):
        with st.expander(scenario.get("scenario", "Unknown scenario").replace("_", " ").title()):
            st.write(scenario.get("action", ""))
            st.dataframe(pd.DataFrame({"paper_id": scenario.get("paper_ids", [])}), use_container_width=True, hide_index=True)

elif view == "Retrieval demo":
    st.markdown("<div class='section-label'>Ask the indexed corpus</div>", unsafe_allow_html=True)
    st.caption("This query uses the persisted baseline ChromaDB collection and MiniLM embeddings.")
    question = st.text_input("Query", placeholder="Which papers discuss freshness SLAs?")
    top_k = st.slider("Results", min_value=1, max_value=5, value=3)
    if st.button("Search corpus", type="primary", disabled=not question):
        with st.spinner("Embedding query and searching ChromaDB..."):
            try:
                results = load_index().semantic_search(question, top_k=top_k)
                if not results:
                    st.warning("No matching documents found.")
                for rank, result in enumerate(results, start=1):
                    with st.container(border=True):
                        st.markdown(f"**{rank}. {result.title}**")
                        st.caption(f"DOI {result.paper_id} · similarity {result.score:.3f}")
                        st.write(result.metadata.get("summary", result.content))
            except Exception as exc:
                st.error(f"Retrieval demo failed: {exc}")

st.divider()
st.caption("Local evidence dashboard · artifacts under data/ · no secrets displayed")
