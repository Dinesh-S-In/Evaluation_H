"use client";

import { useCallback, useMemo, useState } from "react";
import type { ApiError, EvaluateResponse, RankedRow, SortKey } from "@/lib/types";

function uint8ToBase64(bytes: Uint8Array): string {
  let binary = "";
  const chunk = 0x8000;

  for (let i = 0; i < bytes.length; i += chunk) {
    const subArray = bytes.subarray(i, i + chunk);
    binary += String.fromCharCode.apply(null, Array.from(subArray));
  }

  return btoa(binary);
}

async function readErrorMessage(res: Response): Promise<string> {
  const text = await res.text();
  try {
    const j = JSON.parse(text) as ApiError;
    return j.error + (j.detail ? `: ${j.detail}` : "");
  } catch {
    return text || res.statusText;
  }
}

type TabId = "overview" | "detail" | "export";

function formatNum(n: number | undefined, digits = 1): string {
  if (n === undefined || Number.isNaN(n)) return "—";
  return n.toFixed(digits);
}

export default function HomePage() {
  const [file, setFile] = useState<File | null>(null);
  const [mock, setMock] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rows, setRows] = useState<RankedRow[] | null>(null);
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  const [filterSearch, setFilterSearch] = useState("");
  const [filterCategory, setFilterCategory] = useState<string>("all");
  const [filterShortlistOnly, setFilterShortlistOnly] = useState(false);
  const [filterMinScore, setFilterMinScore] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("rank");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const topCount = useMemo(() => rows?.filter((r) => r.shortlisted).length ?? 0, [rows]);

  const categories = useMemo(() => {
    if (!rows?.length) return [] as string[];
    const s = new Set(rows.map((r) => r.submission.category_selection).filter(Boolean));
    return Array.from(s).sort((a, b) => a.localeCompare(b));
  }, [rows]);

  const filteredSortedRows = useMemo(() => {
    if (!rows?.length) return [];
    const q = filterSearch.trim().toLowerCase();
    let out = [...rows];

    if (q) {
      out = out.filter((r) => {
        const s = r.submission;
        const hay = [
          s.team_name,
          s.submission_id,
          s.category_selection,
          s.solution_approach_overview,
          s.key_submission_impact,
          s.business_use_case_and_impact,
          s.tools_and_technology_used,
        ]
          .map((x) => (x || "").toLowerCase())
          .join(" ");
        return hay.includes(q);
      });
    }

    if (filterCategory !== "all") {
      out = out.filter((r) => r.submission.category_selection === filterCategory);
    }

    if (filterShortlistOnly) {
      out = out.filter((r) => r.shortlisted);
    }

    const minRaw = filterMinScore.trim();
    if (minRaw !== "" && Number.isFinite(Number(minRaw))) {
      const m = Number(minRaw);
      out = out.filter((r) => r.evaluation.total_score >= m);
    }

    out.sort((a, b) => {
      switch (sortKey) {
        case "score":
          return b.evaluation.total_score - a.evaluation.total_score || a.rank - b.rank;
        case "team": {
          const ta = (a.submission.team_name || a.submission.submission_id).toLowerCase();
          const tb = (b.submission.team_name || b.submission.submission_id).toLowerCase();
          return ta.localeCompare(tb) || a.rank - b.rank;
        }
        case "category": {
          const ca = a.submission.category_selection.toLowerCase();
          const cb = b.submission.category_selection.toLowerCase();
          return ca.localeCompare(cb) || a.rank - b.rank;
        }
        case "rank":
        default:
          return a.rank - b.rank;
      }
    });

    return out;
  }, [rows, filterSearch, filterCategory, filterShortlistOnly, filterMinScore, sortKey]);

  const stats = useMemo(() => {
    if (!rows?.length) {
      return {
        total: null as number | null,
        evaluated: null as number | null,
        avg: null as number | null,
        top: null as number | null,
        shortlisted: null as number | null,
      };
    }
    const scores = rows.map((r) => r.evaluation.total_score);
    const sum = scores.reduce((a, b) => a + b, 0);
    return {
      total: rows.length,
      evaluated: rows.length,
      avg: sum / scores.length,
      top: Math.max(...scores),
      shortlisted: rows.filter((r) => r.shortlisted).length,
    };
  }, [rows]);

  const selectedRow = useMemo(() => {
    if (!filteredSortedRows.length) return null;
    if (selectedId) {
      const hit = filteredSortedRows.find((r) => r.submission.submission_id === selectedId);
      if (hit) return hit;
    }
    return filteredSortedRows[0];
  }, [filteredSortedRows, selectedId]);

  const runEvaluate = useCallback(async () => {
    setError(null);
    setRows(null);
    setSelectedId(null);
    setActiveTab("overview");
    if (!file) {
      setError("Choose a submissions CSV file first.");
      return;
    }
    setLoading(true);
    try {
      const buf = new Uint8Array(await file.arrayBuffer());
      const body = JSON.stringify({
        csv_base64: uint8ToBase64(buf),
        mock,
      });
      const res = await fetch("/api/evaluate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
      });
      if (!res.ok) {
        throw new Error(await readErrorMessage(res));
      }
      const data = (await res.json()) as EvaluateResponse;
      setRows(data.results);
      if (data.results[0]) {
        setSelectedId(data.results[0].submission.submission_id);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }, [file, mock]);

  const downloadExport = useCallback(
    async (scope: "full" | "top10", format: "csv" | "xlsx") => {
      if (!rows?.length) return;
      setError(null);
      try {
        const res = await fetch("/api/export", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ results: rows, scope, format }),
        });
        if (!res.ok) {
          throw new Error(await readErrorMessage(res));
        }
        const blob = await res.blob();
        const ext = format === "xlsx" ? "xlsx" : "csv";
        const name = scope === "top10" ? `top10_shortlist.${ext}` : `full_results.${ext}`;
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = name;
        a.click();
        URL.revokeObjectURL(url);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Export failed");
      }
    },
    [rows],
  );

  const onRowActivate = useCallback((id: string) => {
    setSelectedId(id);
    setActiveTab("detail");
  }, []);

  const showDevHint = process.env.NODE_ENV === "development";

  return (
    <main>
      <header className="app-header">
        <p className="eyebrow">Stage 1 Evaluation</p>
        <h1>Hackathon Stage 1 Evaluator</h1>
        <p className="tagline">
          Upload submissions, score against Business Impact (40), Feasibility &amp; Scalability
          (30), and AI Depth &amp; Creativity (30). Filter by category, review full narratives, and
          export ranked results for Vercel or offline use.
        </p>
      </header>

      <div className="card compact">
        <h2 className="card-title">Data source</h2>
        {showDevHint ? (
          <div className="banner info" style={{ marginBottom: "0.85rem" }}>
            Local tip: run <code>vercel dev</code> so <code>/api/evaluate</code> and{" "}
            <code>/api/export</code> work with this UI. Plain <code>npm run dev</code> is UI-only.
          </div>
        ) : null}
        {error ? <div className="banner error">{error}</div> : null}
        <div className="row">
          <label className="field">
            Submissions CSV
            <input
              type="file"
              accept=".csv,text/csv"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </label>
          {file ? (
            <span className="muted">
              Selected: <strong>{file.name}</strong>
            </span>
          ) : null}
          <label className="toggle">
            <input type="checkbox" checked={mock} onChange={(e) => setMock(e.target.checked)} />
            Mock scoring (no API key)
          </label>
          <button type="button" className="primary" disabled={loading} onClick={runEvaluate}>
            {loading ? "Evaluating…" : "Run evaluation"}
          </button>
        </div>
      </div>

      <div className="card">
        <div className="stats-grid">
          <div className="stat">
            <div className="label">Total rows (CSV)</div>
            <div className="value">{stats.total ?? "—"}</div>
          </div>
          <div className="stat">
            <div className="label">Evaluated</div>
            <div className="value">{stats.evaluated ?? "—"}</div>
          </div>
          <div className="stat">
            <div className="label">Average score</div>
            <div className="value">{stats.avg != null ? formatNum(stats.avg, 1) : "—"}</div>
          </div>
          <div className="stat">
            <div className="label">Top score</div>
            <div className="value">{stats.top ?? "—"}</div>
          </div>
          <div className="stat">
            <div className="label">Shortlisted</div>
            <div className="value">{stats.shortlisted ?? "—"}</div>
          </div>
        </div>

        {!rows?.length ? (
          <div className="banner empty">
            No evaluation results yet. Choose a CSV above, then run <strong>Run evaluation</strong>{" "}
            to populate Overview, filters, and Detailed Review.
          </div>
        ) : (
          <>
            <div className="tabs" role="tablist" aria-label="Main views">
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === "overview"}
                className={`tab${activeTab === "overview" ? " active" : ""}`}
                onClick={() => setActiveTab("overview")}
              >
                Overview
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === "detail"}
                className={`tab${activeTab === "detail" ? " active" : ""}`}
                onClick={() => setActiveTab("detail")}
              >
                Detailed Review
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === "export"}
                className={`tab${activeTab === "export" ? " active" : ""}`}
                onClick={() => setActiveTab("export")}
              >
                Export
              </button>
            </div>

            {activeTab === "overview" ? (
              <>
                <p className="muted" style={{ marginBottom: "1rem" }}>
                  {rows.length} teams ranked · {topCount} automatic top-10 (by rank). Showing{" "}
                  <strong>{filteredSortedRows.length}</strong> after filters.
                </p>

                <div className="filters-grid">
                  <label>
                    Search
                    <input
                      type="search"
                      placeholder="Team, ID, category, text…"
                      value={filterSearch}
                      onChange={(e) => setFilterSearch(e.target.value)}
                    />
                  </label>
                  <label>
                    Category
                    <select
                      value={filterCategory}
                      onChange={(e) => setFilterCategory(e.target.value)}
                    >
                      <option value="all">All categories</option>
                      {categories.map((c) => (
                        <option key={c} value={c}>
                          {c}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Min total score
                    <input
                      type="number"
                      min={0}
                      max={100}
                      placeholder="0"
                      value={filterMinScore}
                      onChange={(e) => setFilterMinScore(e.target.value)}
                    />
                  </label>
                  <label>
                    Sort by
                    <select value={sortKey} onChange={(e) => setSortKey(e.target.value as SortKey)}>
                      <option value="rank">Rank (1 = best)</option>
                      <option value="score">Score (high → low)</option>
                      <option value="team">Team name (A–Z)</option>
                      <option value="category">Category (A–Z)</option>
                    </select>
                  </label>
                  <label className="filter-toggle">
                    <input
                      type="checkbox"
                      checked={filterShortlistOnly}
                      onChange={(e) => setFilterShortlistOnly(e.target.checked)}
                    />
                    Top 10 shortlist only
                  </label>
                </div>

                <div className="table-wrap">
                  <table className="results">
                    <thead>
                      <tr>
                        <th>Rank</th>
                        <th>Shortlist</th>
                        <th>Team</th>
                        <th>Submission ID</th>
                        <th>Category</th>
                        <th>Cat. OK</th>
                        <th>Total</th>
                        <th>BI (40)</th>
                        <th>FS (30)</th>
                        <th>AI (30)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredSortedRows.map((r) => {
                        const id = r.submission.submission_id;
                        const sel = selectedRow?.submission.submission_id === id;
                        return (
                          <tr
                            key={id}
                            className={sel ? "selected" : undefined}
                            role="button"
                            tabIndex={0}
                            onClick={() => onRowActivate(id)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter" || e.key === " ") {
                                e.preventDefault();
                                onRowActivate(id);
                              }
                            }}
                          >
                            <td>{r.rank}</td>
                            <td>
                              <span className={r.shortlisted ? "badge top" : "badge no"}>
                                {r.shortlisted ? "TOP 10" : "—"}
                              </span>
                            </td>
                            <td>{r.submission.team_name || "—"}</td>
                            <td>{id}</td>
                            <td>
                              <span className="badge cat" title={r.submission.category_selection}>
                                {r.submission.category_selection || "—"}
                              </span>
                            </td>
                            <td>
                              {r.submission.category_valid === false ? (
                                <span className="badge warn">Review</span>
                              ) : (
                                <span className="badge no">OK</span>
                              )}
                            </td>
                            <td>{r.evaluation.total_score}</td>
                            <td>{r.evaluation.breakdown.business_impact.score}</td>
                            <td>{r.evaluation.breakdown.feasibility_scalability.score}</td>
                            <td>{r.evaluation.breakdown.ai_depth_creativity.score}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                {filteredSortedRows.length === 0 ? (
                  <p className="muted" style={{ marginTop: "0.75rem" }}>
                    No rows match the current filters. Clear search or change category.
                  </p>
                ) : null}
              </>
            ) : null}

            {activeTab === "detail" ? (
              <>
                {!filteredSortedRows.length ? (
                  <p className="muted">No submissions match the current filters.</p>
                ) : (
                  <div className="detail-layout">
                    <div className="detail-picker">
                      <label htmlFor="submission-picker">Submission</label>
                      <select
                        id="submission-picker"
                        value={selectedRow?.submission.submission_id ?? ""}
                        onChange={(e) => setSelectedId(e.target.value)}
                      >
                        {filteredSortedRows.map((r) => (
                          <option key={r.submission.submission_id} value={r.submission.submission_id}>
                            #{r.rank} · {r.submission.team_name || r.submission.submission_id} (
                            {r.evaluation.total_score} pts)
                          </option>
                        ))}
                      </select>
                      <p className="muted" style={{ marginTop: "0.75rem" }}>
                        Same filters as Overview apply here. Open a row in Overview to jump in with
                        that team selected.
                      </p>
                    </div>

                    {selectedRow ? (
                      <div className="detail-panel">
                        <h3>{selectedRow.submission.team_name || "Unnamed team"}</h3>
                        <div className="detail-meta">
                          <span className="muted">ID: {selectedRow.submission.submission_id}</span>
                          <span className="muted">Rank: {selectedRow.rank}</span>
                          <span className="badge cat">{selectedRow.submission.category_selection}</span>
                          {selectedRow.shortlisted ? (
                            <span className="badge top">TOP 10</span>
                          ) : null}
                          {selectedRow.similarity_flag ? (
                            <span className="badge warn" title={(selectedRow.similar_submission_ids || []).join(", ")}>
                              Similarity flag
                            </span>
                          ) : null}
                        </div>
                        {selectedRow.submission.category_warning ? (
                          <div className="banner empty" style={{ marginBottom: "1rem" }}>
                            <strong>Category note:</strong> {selectedRow.submission.category_warning}
                          </div>
                        ) : null}
                        {selectedRow.similarity_flag &&
                        (selectedRow.similar_submission_ids?.length ?? 0) > 0 ? (
                          <p className="muted" style={{ marginTop: "-0.5rem", marginBottom: "1rem" }}>
                            Similar to: {(selectedRow.similar_submission_ids || []).join(", ")}
                          </p>
                        ) : null}

                        <div className="score-grid">
                          <div className="score-card">
                            <div className="title">Business impact (40)</div>
                            <div className="pts">
                              {selectedRow.evaluation.breakdown.business_impact.score}
                            </div>
                            <div className="reason">
                              {selectedRow.evaluation.breakdown.business_impact.reason || "—"}
                            </div>
                          </div>
                          <div className="score-card">
                            <div className="title">Feasibility &amp; scalability (30)</div>
                            <div className="pts">
                              {selectedRow.evaluation.breakdown.feasibility_scalability.score}
                            </div>
                            <div className="reason">
                              {selectedRow.evaluation.breakdown.feasibility_scalability.reason || "—"}
                            </div>
                          </div>
                          <div className="score-card">
                            <div className="title">AI depth &amp; creativity (30)</div>
                            <div className="pts">
                              {selectedRow.evaluation.breakdown.ai_depth_creativity.score}
                            </div>
                            <div className="reason">
                              {selectedRow.evaluation.breakdown.ai_depth_creativity.reason || "—"}
                            </div>
                          </div>
                        </div>

                        <div className="prose-block">
                          <h4>Judge summary</h4>
                          <p>{selectedRow.evaluation.final_summary || "—"}</p>
                        </div>
                        <div className="prose-block">
                          <h4>Key submission impact</h4>
                          <p>{selectedRow.submission.key_submission_impact || "—"}</p>
                        </div>
                        <div className="prose-block">
                          <h4>Business use case and impact</h4>
                          <p>{selectedRow.submission.business_use_case_and_impact || "—"}</p>
                        </div>
                        <div className="prose-block">
                          <h4>Solution / approach overview</h4>
                          <p>{selectedRow.submission.solution_approach_overview || "—"}</p>
                        </div>
                        <div className="prose-block">
                          <h4>Tools and technology</h4>
                          <p>{selectedRow.submission.tools_and_technology_used || "—"}</p>
                        </div>
                      </div>
                    ) : null}
                  </div>
                )}
              </>
            ) : null}

            {activeTab === "export" ? (
              <div>
                <p className="export-note" style={{ marginBottom: "1rem" }}>
                  Downloads use the Python export service so CSV and Excel match the CLI layout
                  (full grid or top-10 shortlist only).
                </p>
                <div className="export-actions">
                  <button type="button" className="secondary" onClick={() => downloadExport("full", "csv")}>
                    Full results · CSV
                  </button>
                  <button type="button" className="secondary" onClick={() => downloadExport("full", "xlsx")}>
                    Full results · Excel
                  </button>
                  <button type="button" className="secondary" onClick={() => downloadExport("top10", "csv")}>
                    Top 10 · CSV
                  </button>
                  <button type="button" className="secondary" onClick={() => downloadExport("top10", "xlsx")}>
                    Top 10 · Excel
                  </button>
                </div>
              </div>
            ) : null}
          </>
        )}
      </div>
    </main>
  );
}
