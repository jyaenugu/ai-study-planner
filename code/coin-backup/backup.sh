#!/bin/bash
# Coin auto-backup: mirror critical state into ~/openclaw-backup and push to GitHub.
# Excludes tokens/credentials and ephemeral files. Runs daily via systemd timer.
set -e

BACKUP="$HOME/openclaw-backup"
mkdir -p "$BACKUP"

# 1) Code (~/openclaw-tools/) — exclude venvs, caches, this script's parent itself is fine to mirror
rsync -a --delete \
  --exclude '.venv/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude 'node_modules/' \
  "$HOME/openclaw-tools/" "$BACKUP/openclaw-tools/"

# 2) Workspace (Coin persona files) — exclude nested .git so backup repo treats it as plain files
rsync -a --delete \
  --exclude '.git/' \
  --exclude '.openclaw/' \
  "$HOME/.openclaw/workspace/" "$BACKUP/openclaw-workspace/"

# 3) Cron jobs (just the definitions)
mkdir -p "$BACKUP/openclaw-cron"
cp -a "$HOME/.openclaw/cron/jobs.json" "$BACKUP/openclaw-cron/jobs.json" 2>/dev/null || true

# 4) Obsidian Vault — exclude obsidian state files that churn every keystroke
rsync -a --delete \
  --exclude '.obsidian/workspace*' \
  --exclude '.obsidian/cache/' \
  --exclude '.trash/' \
  --exclude '.DS_Store' \
  "$HOME/Documents/Obsidian Vault/" "$BACKUP/obsidian-vault/"

cd "$BACKUP"

# Initialize git on first run
if [ ! -d .git ]; then
  git init -q -b main
  git remote add origin "https://github.com/jyaenugu/openclaw-backup.git"
  cat > .gitignore <<'EOF'
# venvs / caches (already excluded by rsync but defense-in-depth)
.venv/
__pycache__/
*.pyc

# never commit credentials
openclaw.json
spotify.json
notion.json
*.pem
*.key

# OS junk
.DS_Store
EOF
  cat > README.md <<'EOF'
# openclaw-backup

Automated backup of Coin/OpenClaw state. Updated daily by `coin-backup.timer`.

Contents:
- `openclaw-tools/` — MCP server code + shared `data/*.db`
- `openclaw-workspace/` — Coin persona (SOUL, USER, TOOLS, IDENTITY)
- `openclaw-cron/jobs.json` — cron job definitions
- `obsidian-vault/` — Obsidian vault markdown (Daily, Brain, Schedule, 가사, ...)

Credentials (`*.json` tokens, `*.pem` keys) are deliberately excluded.
EOF
fi

git add -A
if git diff --cached --quiet; then
  echo "no changes"
else
  COUNT=$(git diff --cached --name-only | wc -l)
  git commit -q -m "backup $(date -Iminutes) — $COUNT files changed"
  git push -q origin main 2>&1 || { echo "push failed"; exit 1; }
  echo "pushed $COUNT files"
fi
