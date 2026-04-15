# Hackathon Stage 1 Evaluator

Document-only judging pipeline: ingest a submissions CSV, score each row (OpenAI or deterministic mock), clamp criteria to the Stage 1 rubric (40 / 30 / 30), rank with tie-breakers, mark an automatic **top 10** shortlist, and export CSV or Excel.

This repository is structured for **GitHub + Vercel**: a **Next.js** UI at the repo root and **Python serverless functions** under `api/` that reuse the existing evaluator package in `src/`.

---

## 1. Reusable Python modules (unchanged core)

These modules stay as the single source of truth for business logic:

| Module | Role |
|--------|------|
| `src/models.py` | Pydantic models: `Submission`, `LLMEvaluationPayload`, `EvaluationResult`, `RankedEvaluation` |
| `src/validate_data.py` | Required CSV columns, header canonicalization |
| `src/load_data.py` | `load_submissions(path)` and **`load_submissions_from_bytes`** (uploads / APIs) |
| `src/transform.py` | DataFrame → `Submission` list, category normalization |
| `src/evaluator.py` | OpenAI + JSON parsing + mock mode |
| `src/scoring.py` | Clamp scores and recompute totals |
| `src/ranking.py` | Sort, tie-break, top-10 flags, optional similarity hints |
| `src/exporter.py` | Tabular export helpers (used by CLI, Streamlit, and **`/api/export`**) |
| `src/pipeline.py` | **`run_evaluation_ranking`** (in-memory, for serverless) and `run_pipeline` (CLI: writes under `output/`) |
| `src/config.py` | Paths to `data/`, `prompts/`, `output/` |
| `src/http_evaluate.py` / `src/http_export.py` | Shared request handling for Vercel handlers |

Prompts remain in `prompts/`.

---

## 2. Repository layout

```text
.
├── app/                      # Next.js App Router (UI)
├── api/                      # Vercel Python serverless (HTTP)
│   ├── evaluate.py           # POST /api/evaluate
│   └── export.py             # POST /api/export
├── src/                      # Python evaluator package
├── prompts/                  # LLM system + evaluation templates
├── data/                     # Sample CSV (optional)
├── streamlit_ui/             # Legacy Streamlit reviewer (optional)
├── main.py                   # CLI (preview / validate / evaluate)
├── package.json              # Next.js
├── requirements.txt          # Python deps for Vercel + CLI core
├── requirements-dev.txt    # Streamlit, FastAPI-style local extras
├── vercel.json               # Function timeouts
└── .env.example              # Documented environment variables
```

---

## 3. Environment variables

| Variable | Where | Purpose |
|----------|--------|---------|
| `OPENAI_API_KEY` | Local `.env`, Vercel **Environment Variables** | Required for live judging (unless mock). |
| `OPENAI_MODEL` | Optional | Defaults to `gpt-4o-mini` in code if unset. |
| `MOCK_EVALUATION` | Optional | When `true` / `1` / `yes`, forces mock scoring server-side even if a key exists. |

Copy `.env.example` to `.env` for local CLI or `vercel dev`.

---

## 4. Local development

### Python CLI (CSV on disk)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
pip install -r requirements-dev.txt   # optional: Streamlit + pytest
copy .env.example .env                # then edit values
python main.py validate
python main.py evaluate --mock
```

### Next.js + Python APIs together

Vercel’s dev server wires Next.js and Python `/api/*` routes:

```bash
npm install
npm install -g vercel          # or: npx vercel dev
vercel dev
```

Open the URL shown (usually `http://localhost:3000`). Use **Mock scoring** for quick tests without an API key.

### Next.js UI only (no Python routes)

```bash
npm install
npm run dev
```

`/api/evaluate` will not work in this mode; use `vercel dev` for full stack.

### Streamlit (optional legacy UI)

```bash
pip install -r requirements-dev.txt
streamlit run streamlit_ui/streamlit_app.py
```

---

## 5. Deploying to Vercel (from GitHub)

1. Push this repository to GitHub.
2. In [Vercel](https://vercel.com), **Import** the repo. Use the **repository root** as the project root (default).
3. Framework preset: **Next.js** (detected from `package.json`).
4. **Build** command: `npm run build` (default). **Output**: Next default (`.next`).
5. Vercel will also detect **`api/*.py`** and deploy Python serverless functions using root **`requirements.txt`**.
6. Under **Settings → Environment Variables**, add `OPENAI_API_KEY` (and optionally `OPENAI_MODEL`, `MOCK_EVALUATION`) for **Production** / **Preview** as needed.
7. Redeploy after changing env vars.

**Limits:** `vercel.json` sets `maxDuration` to 60s for `/api/evaluate`. Large CSVs or slow models may need a higher limit (paid tiers) or batching outside this demo.

---

## 6. HTTP API (production shape)

### `POST /api/evaluate`

- **Content-Type:** `application/json`
- **Body:** `{ "csv_base64": "<base64-encoded CSV file>", "mock": true|false, "model": "optional-model-id" }`
- **Response:** `{ "results": [ RankedEvaluation... ], "count": N }` (JSON-serialized Pydantic models).

Alternatively send **raw CSV** with `Content-Type: text/csv` and optional headers `X-Mock-Mode: true`, `X-OpenAI-Model: gpt-4o-mini`.

### `POST /api/export`

- **Body:** `{ "results": [ ...same as evaluate response... ], "scope": "full" | "top10", "format": "csv" | "xlsx" }`
- **Response:** File bytes with `Content-Disposition: attachment`.

---

## 7. Commands to run next

From the repository root (`hackathon-evaluator-agent`):

```bash
npm install
pip install -r requirements.txt
copy .env.example .env
vercel dev
```

Then open the local URL, upload `data/submissions.csv`, toggle **Mock scoring**, and click **Run evaluation**.

To deploy:

```bash
npx vercel --prod
```

(or connect the GitHub repo in the Vercel dashboard and push to `main`).
