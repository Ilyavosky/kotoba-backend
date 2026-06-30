# Kotoba Backend — Deployment Guide

## Overview

Kotoba Backend is deployed on [Railway](https://railway.app) using a multi-stage Docker build.
Any push to the `develop` branch triggers an automatic redeploy.

**Production URL:** `https://kotoba-backend-production-e6b7.up.railway.app`

---

## Prerequisites

- Access to the Railway project (`Kotoba-Backend`)
- Access to the GitHub repository connected to the service
- Must add the following credentials (never hardcode these):
  - Supabase URL, Anon Key, JWT Secret, and Service Role key
  - Upstash Redis URL and Token
  - Groq API key
  - Supabase Storage bucket names for TTS audio and lesson JSONs
  - Groq model identifier for the pedagogical agent

---

## Environment Variables

Set these in Railway under **Service → Variables**:

| Variable | Description |
|---|---|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_ANON_KEY` | Supabase anonymous key |
| `SUPABASE_JWT_SECRET` | Supabase JWT secret for token validation |
| `SUPABASE_SERVICE_ROLE` | Supabase service role key — used for server-side DB writes (bypasses RLS) |
| `UPSTASH_REDIS_URL` | Upstash Redis connection URL (`rediss://` protocol) |
| `UPSTASH_REDIS_TOKEN` | Upstash Redis authentication token |
| `GROQ_API_KEY` | Groq API key — used for ASR (Whisper), LLM agent, and TTS |
| `TTS_BUCKET` | Supabase Storage bucket name for synthesized TTS audio files |
| `LESSONS_BUCKET` | Supabase Storage bucket name for lesson JSON files |
| `LLM_MODEL` | Groq model ID for the pedagogical agent (e.g. `llama-3.3-70b-versatile`) |

> **Note:** `SUPABASE_SERVICE_ROLE` was added in K-06.1. Earlier deployments only had the anon key. The service role key is required for server-side upserts to `user_progress` that bypass Row Level Security.

---

## Build

Railway auto-detects the `Dockerfile` at the root of the repository.

The build uses a **multi-stage** strategy:

- **Builder stage** — installs dependencies with `uv` into a virtual environment
- **Runtime stage** — copies only the `.venv` and `app/` folder; runs as a non-root user (`kotoba`)

No manual build configuration is needed in Railway.

---

## Deploy

1. Push changes to the `develop` branch
2. Railway detects the push and starts a new deployment automatically
3. Wait for **Deployment successful** in the Railway dashboard

To redeploy manually: go to **Service → Deployments** and click **Redeploy**.

---

## Verify

After deployment, confirm the service is healthy:

```bash
curl https://kotoba-backend-production-e6b7.up.railway.app/health
```

Expected response:

```json
{"status": "ok"}
```

---

## Networking

- **Public domain:** `kotoba-backend-production-e6b7.up.railway.app` (HTTPS, port 8000)
- **Internal domain:** `kotoba-backend.railway.internal` (private Railway network)
- TLS is enabled automatically by Railway

---

## Database migrations

Before deploying a new version, apply any pending migrations to your Supabase project via the SQL editor or `supabase db push`. Migrations are located in `migrations/` and must be run in numeric order:

| File | What it does |
|---|---|
| `001_initial_schema.sql` | Base tables: `users`, `lessons`, `user_progress`, `conversation_turns` |
| `002_rls_policies.sql` | Row Level Security policies |
| `003_fix_rls_policies.sql` | RLS policy corrections |
| `004_add_current_step.sql` | Adds `current_step` column to `user_progress` (K-06.1) |
| `005_add_modules_table.sql` | Creates `modules` table for multi-lesson progression (K-05.2) |
