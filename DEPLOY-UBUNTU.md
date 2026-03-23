# 🚀 Deploy TaskFlow on Ubuntu Cloud — Complete Guide

This guide covers deploying TaskFlow on an Ubuntu machine using GitHub + Railway.

---

## Prerequisites

- Ubuntu (18.04+)
- Shell access with sudo privileges
- Internet connection

---

## Step 1: Install Dependencies

### Install GitHub CLI
```bash
# Add GitHub CLI repo key
curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg

# Add repository
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null

# Install
sudo apt update
sudo apt install -y gh
```

### Install Node.js (for Railway CLI)
```bash
# NodeSource repository for Node.js 20
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

### Install Railway CLI
```bash
sudo npm install -g @railway/cli
```

**If `sudo npm` fails** (permission error), use:
```bash
npm install -g @railway/cli
# Then add to PATH:
echo 'export PATH="$PATH:$HOME/.npm-global/bin"' >> ~/.bashrc
source ~/.bashrc
```

---

## Step 2: Authenticate

### GitHub
```bash
gh auth login
# Follow prompts:
# - GitHub.com
# - HTTPS
# - Login via browser (opens URL, paste code)
```

### Railway
```bash
railway login
# Opens browser, approve access
```

---

## Step 3: One-Command Deploy

```bash
cd /root/.openclaw/workspace/demos/demo-01-taskflow
./deploy.sh
```

The script will:
1. Verify CLI authentication
2. Create/connect GitHub repo
3. Push code
4. Create Railway project
5. Add PostgreSQL plugin
6. Set `SECRET_KEY` automatically
7. Trigger deployment
8. Output live URLs

---

## Step 4: Verify

After script completes:

- **Frontend:** `https://taskflow-frontend.up.railway.app`
- **Backend API:** `https://taskflow-backend.up.railway.app/docs`

Test:
1. Open Backend `/docs` → Swagger UI appears
2. Register user via POST `/api/v1/auth/register`
3. Login via frontend
4. Create tasks!

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `gh: command not found` | Reinstall GitHub CLI, ensure `/usr/bin` in PATH |
| `railway: command not found` | Check npm global bin: `npm bin -g` is in PATH |
| Auth failures | Run `gh auth refresh` or `railway logout && railway login` |
| Build fails | Check GitHub repo has all files (Dockerfiles, railway.json) |
| Port conflicts (local) | Not an issue on Railway (uses dynamic ports) |

---

## What the Script Does

See `deploy.sh` comments for detailed steps.

---

## Need Help?

- GitHub CLI: https://cli.github.com/manual/
- Railway CLI: https://docs.railway.app/develop/cli
- Check logs in Railway dashboard if build fails

---

**Ready?** Run the install steps, then `./deploy.sh`. 🎉