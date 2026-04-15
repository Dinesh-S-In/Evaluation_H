"use client";

import { useCallback, useMemo, useState } from "react";
import type { ApiError, EvaluateResponse, RankedRow } from "@/lib/types";

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

export default function HomePage() {
  const [file, setFile] = useState<File | null>(null);
  const [mock, setMock] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rows, setRows] = useState<RankedRow[] | null>(null);

  const topCount = useMemo(() => rows?.filter((r) => r.shortlisted).length ?? 0, [rows]);

  const runEvaluate = useCallback(async () => {
    setError(null);
    setRows(null);
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

  return (
    <main>
      <div className="card">
        <h1>Stage 1 Evaluation</h1>
        <p className="subtitle">
          Upload a hackathon submissions CSV, score each row (mock or OpenAI), review the ranked
          table, and export full results or the top-10 shortlist.
        </p>

        <div className="banner info">
          For local development, run <code>vercel dev</code> so both the Next.js UI and Python{" "}
          <code>/api/*</code> routes are served together. Plain <code>npm run dev</code> serves the
          UI only.
        </div>

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
          <label className="toggle">
            <input
              type="checkbox"
              checked={mock}
              onChange={(e) => setMock(e.target.checked)}
            />
            Mock scoring (no API key)
          </label>
          <button type="button" className="primary" disabled={loading} onClick={runEvaluate}>
            {loading ? "Evaluating…" : "Run evaluation"}
          </button>
        </div>

        {rows?.length ? (
          <p className="muted" style={{ marginTop: "1rem" }}>
            {rows.length} teams ranked · {topCount} in automatic top-10 shortlist (by rank).
          </p>
        ) : null}
      </div>

      {rows?.length ? (
        <div className="card">
          <div className="row" style={{ marginBottom: "1rem" }}>
            <span className="muted">Export</span>
            <button type="button" className="secondary" onClick={() => downloadExport("full", "csv")}>
              Full CSV
            </button>
            <button type="button" className="secondary" onClick={() => downloadExport("full", "xlsx")}>
              Full Excel
            </button>
            <button type="button" className="secondary" onClick={() => downloadExport("top10", "csv")}>
              Top 10 CSV
            </button>
            <button type="button" className="secondary" onClick={() => downloadExport("top10", "xlsx")}>
              Top 10 Excel
            </button>
          </div>

          <div className="table-wrap">
            <table className="results">
              <thead>
                <tr>
                  <th>Rank</th>
                  <th>Shortlist</th>
                  <th>Team</th>
                  <th>Submission ID</th>
                  <th>Total</th>
                  <th>Business (40)</th>
                  <th>Feasibility (30)</th>
                  <th>AI depth (30)</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.submission.submission_id}>
                    <td>{r.rank}</td>
                    <td>
                      <span className={r.shortlisted ? "badge top" : "badge no"}>
                        {r.shortlisted ? "TOP 10" : "—"}
                      </span>
                    </td>
                    <td>{r.submission.team_name || "—"}</td>
                    <td>{r.submission.submission_id}</td>
                    <td>{r.evaluation.total_score}</td>
                    <td>{r.evaluation.breakdown.business_impact.score}</td>
                    <td>{r.evaluation.breakdown.feasibility_scalability.score}</td>
                    <td>{r.evaluation.breakdown.ai_depth_creativity.score}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </main>
  );
}
