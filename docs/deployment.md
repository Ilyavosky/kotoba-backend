# Kotoba Backend — Deployment Guide

## Overview

Kotoba Backend is deployed on [Railway](https://railway.app) using a multi-stage Docker build.
Any push to the `develop` branch triggers an automatic redeploy.

**Production URL:** `https://kotoba-backend-production-e6b7.up.railway.app`

---

## Prerequisites

- Access to the Railway project (`zoological-exploration`)
- Access to the GitHub repository connected to the service
- The following credentials (never hardcode these):
  - Supabase URL, Anon Key, and JWT Secret
  - Upstash Redis URL and Token

---

## Environment Variables

Set these in Railway under **Service → Variables**:

| Variable | Description |
|---|---|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_ANON_KEY` | Supabase anonymous key |
| `SUPABASE_JWT_SECRET` | Supabase JWT secret for token validation |
| `UPSTASH_REDIS_URL` | Upstash Redis connection URL (`rediss://` protocol) |
| `UPSTASH_REDIS_TOKEN` | Upstash Redis authentication token |

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
