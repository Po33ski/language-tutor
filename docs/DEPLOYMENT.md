# Deployment

The frontend runs on **Vercel** (Hobby plan) and the backend on an **Oracle Cloud Always Free** ARM VM, behind Caddy for HTTPS. Both cost nothing. GitHub Actions tests every push and pull request, and deploys `main` once the tests pass.

```
 browser ──► https://<project>.vercel.app          (Next.js, Vercel)
    │
    └──────► https://<API_DOMAIN>/api/...           (Oracle VM)
              Caddy :443 ──► backend :8000 (Docker)
                             ├─ volume tutor-data    SQLite databases
                             └─ volume tutor-models  Whisper + Kokoro

 git push main ──► GitHub Actions
                   ├─ Backend:  ruff + pytest ──► SSH: git checkout <sha> ──► deploy/deploy.sh ──► health check
                   └─ Frontend: lint + tsc + build ──► vercel build + deploy --prod
```

Each workflow runs only when its part of the repo changed (`backend/` + `deploy/`, or `frontend/`). To redeploy without a change, open **Actions → Backend / Frontend → Run workflow** on `main`.

## Files

| Path | Purpose |
|---|---|
| `backend/Dockerfile` | CPU-only backend image (`uv sync --extra cpu`), built on the server |
| `deploy/compose.yaml` | Backend + Caddy, with volumes for data, models and certificates |
| `deploy/Caddyfile` | Reverse proxy with automatic Let's Encrypt HTTPS |
| `deploy/.env.example` | Template for the server's `deploy/.env` (secrets live only on the server) |
| `deploy/deploy.sh` | Rebuild, restart and wait for a healthy backend (run by CI) |
| `deploy/backup.sh` | Consistent SQLite backup to `~/backups` |
| `.github/workflows/backend.yml`, `frontend.yml` | CI/CD |
| `frontend/vercel.json` | Turns off Vercel's own Git deployments, so only tested commits are deployed |

## Security model

- **Accounts:** anyone can sign up (email + password); every endpoint except health, signup and login needs a session token. Passwords are Argon2id hashes; sessions are stored as SHA-256 hashes in `users.db`. Details: [ARCHITECTURE.md](ARCHITECTURE.md#accounts-and-authentication).
- **Cost limits** (because signup is open): tutor turns and transcriptions per account per day, tutor turns for the whole app per day, signups per network per hour (`USER_DAILY_*`, `DAILY_TUTOR_TURNS_TOTAL`, `SIGNUPS_PER_IP_PER_HOUR` in `deploy/.env`), plus `RATE_LIMIT_PER_MINUTE` per account.
- **Spend limit:** set a monthly limit in the Anthropic console as the last line of defence.
- **Secrets:** the Anthropic and Groq keys live only in `deploy/.env` on the server. GitHub stores only the SSH key and the Vercel token.

## 1. Create the Oracle Cloud VM

1. Sign up at https://signup.cloud.oracle.com/ (a payment card is needed for verification; Always Free resources are not charged). Pick a home region that is not overloaded; it cannot be changed later.
2. **Compute → Instances → Create instance:**
   - Image: **Canonical Ubuntu 24.04** (aarch64).
   - Shape: **VM.Standard.A1.Flex**, **4 OCPU, 12 GB RAM**. The speech models use about 3 GB. On free accounts Oracle reclaims instances that stay below 20% CPU, network *and* memory use for 7 days, and 12 GB keeps memory use above that line. Upgrading the account to Pay As You Go removes the reclaiming entirely (Always Free resources stay free; set a budget alert).
   - Boot volume: 100 GB.
   - Add your SSH public key.
   - If you get "Out of capacity", try another availability domain or try again later.
3. **Open ports 80 and 443:**
   - Networking → your VCN → Security Lists → Default → **Add Ingress Rules**: source `0.0.0.0/0`, TCP, destination ports `80,443`.
   - On the VM (Oracle's Ubuntu images block them in iptables too). The rules must go *above* the final `REJECT` rule, whose position differs between image builds, so look it up:

     ```bash
     reject=$(sudo iptables -L INPUT --line-numbers | awk '$2 == "REJECT" {print $1; exit}')
     sudo iptables -I INPUT "$reject" -m state --state NEW -p tcp --dport 443 -j ACCEPT
     sudo iptables -I INPUT "$reject" -m state --state NEW -p tcp --dport 80 -j ACCEPT
     sudo netfilter-persistent save
     sudo iptables -L INPUT --line-numbers   # http and https must be listed before REJECT
     ```

## 2. Prepare the server

```bash
ssh ubuntu@<public-ip>

# Docker (official install script) and permission to use it without sudo
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
exit   # log in again so the group change applies
```

Give the server read-only access to the private repo with a **deploy key**:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/github_deploy -N "" -C "language-tutor server"
cat ~/.ssh/github_deploy.pub
# GitHub → repo → Settings → Deploy keys → Add deploy key (paste, leave "Allow write access" off)

cat >> ~/.ssh/config <<'EOF'
Host github.com
  IdentityFile ~/.ssh/github_deploy
EOF

git clone git@github.com:Po33ski/language-tutor.git ~/language-tutor
```

## 3. Configure and start the backend

Pick the API hostname. Without your own domain, use sslip.io, which resolves `<ip-with-dashes>.sslip.io` to that IP, e.g. `141-147-1-2.sslip.io` for `141.147.1.2`.

```bash
cd ~/language-tutor/deploy
cp .env.example .env
chmod 600 .env
nano .env    # API_DOMAIN, ANTHROPIC_API_KEY, GROQ_API_KEY, CORS_ORIGINS
./deploy.sh
```

The first build takes several minutes. On the first start the backend downloads the speech models (about 1 GB with `WHISPER_MODEL=small`) in the background, so the first voice request may be slow. Then check:

```bash
curl https://<API_DOMAIN>/api/health          # {"status":"ok"}
docker compose logs -f backend                # logs
```

`CORS_ORIGINS` must contain the Vercel URL from step 5. After changing `.env`, apply it with `docker compose up -d` (in `deploy/`).

## 4. Connect GitHub Actions to the server

On your own computer, create a key used only by CI and authorize it on the server:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/language-tutor-ci -N "" -C "github-actions"
ssh-copy-id -i ~/.ssh/language-tutor-ci.pub ubuntu@<public-ip>
```

Then add the secrets and the variable (GitHub → repo → Settings → Secrets and variables → Actions, or with `gh`):

```bash
gh secret set SSH_PRIVATE_KEY < ~/.ssh/language-tutor-ci
gh secret set SSH_KNOWN_HOSTS --body "$(ssh-keyscan -t ed25519 <public-ip>)"
gh secret set SSH_HOST --body "<public-ip>"
gh secret set SSH_USER --body "ubuntu"
gh variable set API_URL --body "https://<API_DOMAIN>"
```

## 5. Set up Vercel

1. Create a Hobby account at https://vercel.com (sign in with GitHub).
2. Link the project from your computer. This creates `frontend/.vercel/` (gitignored) with the project ids:

   ```bash
   cd frontend
   npx vercel@65.9.0 link
   npx vercel@65.9.0 env add NEXT_PUBLIC_API_URL production   # value: https://<API_DOMAIN>
   cat .vercel/project.json                                  # orgId, projectId
   ```

3. Create a token at https://vercel.com/account/tokens and add the secrets:

   ```bash
   gh secret set VERCEL_TOKEN --body "<token>"
   gh secret set VERCEL_ORG_ID --body "<orgId>"
   gh secret set VERCEL_PROJECT_ID --body "<projectId>"
   ```

4. Run **Actions → Frontend → Run workflow** for the first deployment. The production URL (`https://<project>.vercel.app`) goes into `CORS_ORIGINS` on the server (step 3).

Do not connect the repository in Vercel's dashboard. `frontend/vercel.json` turns Git deployments off anyway, so that only commits that passed CI go live.

## 6. Backups

```bash
crontab -e
# add:
0 3 * * * /home/ubuntu/language-tutor/deploy/backup.sh >> /home/ubuntu/backups/backup.log 2>&1
```

Backups are kept for 14 days in `~/backups`. They live on the same VM, so copy them elsewhere from time to time (`scp ubuntu@<public-ip>:backups/*.tar.gz .`), or sync them to Oracle Object Storage (20 GB free) with `rclone`.

To restore: stop the backend (`docker compose stop backend`), copy `checkpoints.db`, `memory.db` and `users.db` from the archive into the `tutor-data` volume (`docker compose cp <file> backend:/data/`), then start it again.

## Everyday use

| Task | How |
|---|---|
| Deploy | Push to `main` (or merge a PR). Tests run first; a failing test stops the deploy. |
| Redeploy | Actions → Backend / Frontend → Run workflow |
| Roll back | `git revert <commit>` and push. Faster, for the backend: `ssh` in, `git checkout --detach <good-sha>`, `deploy/deploy.sh`. |
| Logs | `ssh ubuntu@<public-ip>`, then `cd ~/language-tutor/deploy && docker compose logs -f backend` |
| Change settings | Edit `deploy/.env` on the server, then `docker compose up -d` |
| Account admin | See [Accounts](#accounts) below |

## Accounts

Admin commands run inside the backend container (in `~/language-tutor/deploy`); they work while the backend is running:

| Task | Command |
|---|---|
| List accounts | `docker compose exec backend python -m app.cli list-users` |
| Forgotten password | `docker compose exec backend python -m app.cli reset-password EMAIL` prints a temporary password and signs out every session; the user changes it under *Account* |
| Keep data from before accounts | After signing up, `docker compose exec backend python -m app.cli claim-profile EMAIL` links the most recently used old profile (with its lessons and progress) to that account. It lists the unclaimed profiles; pick another with `--profile-id ID`, and use `--force` if the account already filled in its own profile |

There is no email sending yet: no address verification, no reset links.

## Notes

- **Speech speed:** measured on the server (4 Ampere cores), Kokoro needs ≈ 1 s per sentence (≈ 4.7 s for an 8 s reply) and local Whisper `small` ≈ 6 s for an 8 s answer. Hence:
  - speech to text goes to Groq (`STT_PROVIDER=groq`, ≈ 1 s, free tier: about 2000 requests a day); local Whisper `small` is only the fallback. Without `GROQ_API_KEY` the backend logs an error and uses local Whisper;
  - replies are read aloud sentence by sentence while they stream, so the voice starts after ≈ 1 s instead of after the whole reply is synthesized.
- **Branch protection:** the workflows are path-filtered, so do not make their checks *required* in branch protection (a PR that touches only the frontend would wait forever for the backend check).
- **GitHub Actions minutes:** the private repo gets 2000 free minutes a month; one run takes a few minutes.
- **SQLite** is fine for a single backend process. Moving to Postgres means swapping in `PostgresSaver` / `PostgresStore` and adding a Postgres service to `compose.yaml`.
