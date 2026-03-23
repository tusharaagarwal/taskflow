# 🚀 Deploy to Railway — Complete Guide

This guide walks you through deploying **TaskFlow** (FastAPI + React + PostgreSQL) to [Railway](https://railway.app).

---

## Prerequisites

- GitHub account
- Railway account (free, GitHub OAuth)
- Code pushed to a GitHub repository

---

## Step 1: Push to GitHub

```bash
cd demo-01-taskflow

# Initialize git repo if not already
git init
git add .
git commit -m "Initial commit: TaskFlow full-stack demo"
git branch -M main

# Add remote (replace with your repo URL)
git remote add origin https://github.com/yourusername/taskflow.git
git push -u origin main
```

---

## Step 2: Create Railway Project

1. Go to [railway.app](https://railway.app) and sign in with GitHub
2. Click **"New Project"**
3. Select **"Deploy from GitHub repo"**
4. Choose your `taskflow` repository
5. Railway will auto-detect services from `railway.json`

---

## Step 3: Configure PostgreSQL

Railway will automatically provision a PostgreSQL database from the `postgres` service definition.

- **What you get:** A `POSTGRES_PASSWORD` environment variable automatically generated and injected into the backend service
- **Connection URL:** Provided as `postgres://postgres:${POSTGRES_PASSWORD}@postgres:5432/taskflow` (internal Railway DNS)

---

## Step 4: Set Backend Environment Variables

In Railway dashboard:

1. Go to **Services** → `backend`
2. **Variables** tab → Add:

| Key | Value | Notes |
|-----|-------|-------|
| `SECRET_KEY` | Generate with: `openssl rand -hex 32` | Keep secret! |
| `DEBUG` | `false` | |
| `ALLOWED_ORIGINS` | Automatically set by Railway (`https://${FRONTEND_URL}`) | |
| `PYTHON_VERSION` | `3.11` | Optional |

Railway automatically provides:
- `POSTGRES_PASSWORD` (from DB plugin)
- `PORT` (required)
- `DATABASE_URL` (computed from service dependencies)

---

## Step 5: Frontend Configuration

Railway automatically sets:
- `VITE_API_BASE` → `https://${BACKEND_URL}/api/v1`

No manual config needed — the `railway.json` dependency graph ensures frontend waits for backend.

---

## Step 6: Deploy

- Railway builds and deploys automatically on git push
- First deployment may take 5-10 minutes (building Docker images)
- Subsequent deploys are faster due to caching

**View logs:** Services → Select service → **Logs** tab

**View URLs:** Services → Overview → **Domains** section

---

## Step 7: Test

1. Open your frontend URL (e.g., `https://taskflow-frontend.up.railway.app`)
2. API docs: `https://taskflow-backend.up.railway.app/docs`
3. Register a user via `/docs` → POST `/api/v1/auth/register`
4. Login through frontend
5. Create tasks!

---

## Step 8: Custom Domains (Optional)

1. Services → `frontend` → **Settings** → Custom Domain
2. Add your domain (e.g., `taskflow.yoursite.com`)
3. Railway provisions SSL automatically

---

## Troubleshooting

### Database connection errors
- Ensure `backend` depends on `postgres` (handled automatically by `railway.json`)
- Check PostgreSQL plugin is attached
- Verify `DATABASE_URL` format matches Railway's internal DNS

### Migrations not running
- The `entrypoint.sh` script runs `alembic upgrade head` on container start
- Check backend logs for "Running database migrations"
- If failing, manually run via Railway's **Shell** feature:
  ```bash
  alembic upgrade head
  ```

### 502 Bad Gateway
- Backend may still be starting — wait 30 seconds
- Check health: `GET /health` on backend URL
- Review logs for startup errors

### Frontend can't reach API
- Ensure `VITE_API_BASE` is set correctly in frontend env vars (should be auto)
- Check CORS: `ALLOWED_ORIGINS` should include frontend URL

---

## Cost & Limits

- **Free tier:** $5 monthly credit per project (enough for this demo)
- Sleeps after 30 days of inactivity
- PostgreSQL: Included in shared plan
- Bandwidth: 100GB/month included

---

## Production Checklist

- [ ] Set strong `SECRET_KEY` (use Railway variable)
- [ ] Enable PostgreSQL backups (Railway plugin)
- [ ] Add monitoring (Railway has basic metrics)
- [ ] Set up custom domain + SSL
- [ ] Configure Redis for caching (optional)
- [ ] Add email service (Resend, SendGrid) for notifications
- [ ] Implement proper logging (JSON logs forwarded to Railway)

---

## Files in This Repo

```
railway.json          # Railway service definitions
backend/
  Dockerfile          # Multi-stage build, production-ready
  scripts/entrypoint.sh  # Runs migrations + starts server
  requirements.txt    # Python dependencies
frontend/
  Dockerfile          # Nginx serving built React app
  nginx.conf          # Reverse proxy to backend
  ...
docker-compose.yml   # Local development only
README.md            # Full project documentation
```

---

## Need Help?

- Railway Docs: https://docs.railway.app
- TaskFlow Issues: Open an issue on GitHub
- Check logs in Railway dashboard first!

---

**Ready to deploy?** Push to GitHub and watch Railway work its magic! 🎉