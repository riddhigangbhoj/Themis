<img width="2006" height="1191" alt="Screenshot 2026-02-15 at 4 41 07 PM" src="https://github.com/user-attachments/assets/860b4467-c018-48d7-b1d8-a968f56b5716" />

# Themis — AI Legal Research Platform for Indian Law

Themis is an AI-powered legal research assistant built for Indian courts. Given a complex legal case, it dispatches multiple parallel AI agents that search through hundreds of thousands of real court judgments to surface relevant precedents, judge history, lawyer patterns, timelines, and associated laws — and synthesizes all of it into a structured case outcome prediction.

---

## What It Does

You describe your case. Themis breaks it down into parallel research tasks and investigates:

- **Relevant case precedents** — semantically similar judgments from Indian courts
- **Judge information** — past rulings, tendencies, and bench composition
- **Lawyer information** — known advocates, their history and success rates in similar cases
- **Case timeline** — hearing dates, adjournments, and progression patterns from past cases
- **Hearing finalization** — inferred from how similar cases concluded
- **Associated laws and sections** — statutes, IPC sections, constitutional provisions cited
- **Case outcome prediction** — a reasoned prediction of how your case might proceed and conclude, backed entirely by retrieved real case data

---

## Data

- **380,000+ JSON files** of Indian court case metadata stored in open AWS S3 buckets, partitioned by year, court, and bench
- **127,000+ cases** indexed for semantic search
- **Full judgment PDFs** available on S3, fetched and parsed on demand

---

## How RAG Works Here

Three retrieval layers, used together:

1. **ChromaDB (semantic search)** — cases are embedded as vectors. A query like "property dispute with illegal tenant" finds semantically similar judgments even if the exact words don't match

2. **DuckDB (structured retrieval)** — the 380k+ JSON metadata files are queried with SQL to filter by court, year, judge, disposal type, bench, etc. Fast and precise for factual queries

3. **S3 PDF fetch (full text)** — JSON files hold metadata and previews only. When the full judgment text is needed, the agent downloads the PDF from S3 and extracts it using PyMuPDF

The LLM never answers from memory. Every response is grounded in retrieved case data.

---

## Architecture

A **Planner Agent** receives the user query, breaks it into independent research tasks, and dispatches up to 3 **Base Agents** in parallel. Each Base Agent runs its own agentic loop — picking tools, executing them, and reasoning over results — until it has a confident answer. The Planner then synthesizes all results into a final response.

```
User Query
    ↓
Planner Agent
    ↓ (parallel)
Base Agent 1    Base Agent 2    Base Agent 3
    ↓               ↓               ↓
[tool loop]     [tool loop]     [tool loop]
    ↓               ↓               ↓
         Planner synthesizes
                ↓
         Final prediction
```

Each Base Agent has access to four tools:

| Tool | Purpose |
|------|---------|
| **search_cases** | Semantic search over 127k cases using ChromaDB |
| **sql** | SQL queries on 380k+ JSON files using DuckDB |
| **bash** | Sandboxed file explorer — ls, grep, find, cat on the data directory |
| **read_pdf** | Download judgment PDF from S3 and extract full text using PyMuPDF |

LLM: Claude Sonnet 4 via OpenRouter.
