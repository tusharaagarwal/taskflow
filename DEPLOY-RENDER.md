# 🎨 Deploy TaskFlow to Render — Complete Guide

Render offers a generous free tier with PostgreSQL and automatic HTTPS.

---

## Prerequisites

- GitHub account
- Render account (free)
- Render CLI installed
- Shell access

---

## Step 1: Install Render CLI

```bash
sudo npm install -g @render/cli
```

Verify: `render --version`

---

## Step 2: Authenticate

```bash
render login
# Opens browser → approve access
```

---

## Step 3: Prepare GitHub

Ensure your code is pushed to GitHub:

```bash
cd /root/.openclaw/workspace/demos/demo-01-taskflow
git add .
git commit -m "Prepare for Render deployment"
git push origin master  # or main
```

---

## Step 4: One-Command Deploy

```bash
./deploy.sh
```

The script will:
1. Verify GitHub + Render CLI auth
2. Create/push to GitHub repo if needed
3. Create Render project (or link existing)
4. Set secrets (SECRET_KEY, DEBUG, ALLOWED_ORIGINS)
5. Trigger deployment
6. Print URLs

---

## Step 5: Wait & Verify

Deployment takes 2-5 minutes.

Check logs:
```bash
render logs --tail
```

Expected URLs:
- **Frontend:** `https://taskflow-frontend.onrender.com`
- **Backend API:** `https://taskflow-backend.onrender.com/docs`

---

## Step 6: Test

1. Open Backend `/docs` → Swagger UI
2. Register user: POST `/api/v1/auth/register`
3. Login via frontend
4. Create tasks!

---

## Render Free Tier Limits

| Resource | Limit |
|----------|-------|
| Web Services | 1 (we use 2: frontend + backend → may require paid) |
| PostgreSQL | 1 GB, 90 days idle removal |
| Build time | 15 min max |
| Bandwidth | 100 GB/month |
| Sleep after 15 min inactivity | Yes (wakes on request) |

**Note:** Render's free tier allows **1 free web service**. Our app has 2 (frontend + backend), which normally requires paid plan. However, Render sometimes allows 2 for new accounts. If you hit limits:

**Option A:** Combine frontend into backend (serve React build from FastAPI static files) — I can modify.
**Option B:** Upgrade to paid ($7/month per web service)
**Option C:** Use Railway for one service, Render for the other

---

## Environment Variables

The script sets via `render secrets set`:
- `SECRET_KEY` (auto-generated)
- `DEBUG=false`
- `ALLOWED_ORIGINS=https://taskflow-frontend.onrender.com`
- `DATABASE_URL` (auto from Postgres service in `render.yaml`)

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Build fails (Docker) | Check `render build` logs |
| DB connection error | Ensure PostgreSQL is provisioned and `DATABASE_URL` secret set |
| 502 Bad Gateway | Wait 1-2 minutes after deploy, service boots |
| Free tier limit exceeded | Delete other Render projects or upgrade |

---

## Manual Alternative (Web UI)

If CLI issues:
1. Go to [render.com](https://render.com) → New → Web Service
2. Connect GitHub repo
3. Choose Docker, set Dockerfile path (`backend/Dockerfile`)
4. Add secrets in Environment section
5. Repeat for frontend
6. Create PostgreSQL instance and link

---

**Ready?** Run `./deploy.sh` and watch the magic! 🎩✨