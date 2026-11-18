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

- **Access key:** the backend requires `Authorization: Bearer <ACCESS_KEY>` on every endpoint except `GET /api/health`. The frontend asks for the key once and keeps it in `localStorage`. The key is not part of the frontend bundle, so the public site is useless without it.
- **Rate limit:** `RATE_LIMIT_PER_MINUTE` (default 30) per client IP on the endpoints that call the LLM or the speech models.
- **Spend limit:** set a monthly limit in the Anthropic console as the last line of defence.
- **Secrets:** the Anthropic key and the access key live only in `deploy/.env` on the server. GitHub stores only the SSH key and the Vercel token.

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
   - On the VM (Oracle's Ubuntu images block them in iptables too):

     ```bash
     sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
     sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
     sudo netfilter-persistent save
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
nano .env    # API_DOMAIN, ANTHROPIC_API_KEY, ACCESS_KEY (openssl rand -base64 32), CORS_ORIGINS
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

To restore: stop the backend (`docker compose stop backend`), copy `checkpoints.db` and `memory.db` from the archive into the `tutor-data` volume (`docker compose cp <file> backend:/data/`), then start it again.

## Everyday use

| Task | How |
|---|---|
| Deploy | Push to `main` (or merge a PR). Tests run first; a failing test stops the deploy. |
| Redeploy | Actions → Backend / Frontend → Run workflow |
| Roll back | `git revert <commit>` and push. Faster, for the backend: `ssh` in, `git checkout --detach <good-sha>`, `deploy/deploy.sh`. |
| Logs | `ssh ubuntu@<public-ip>`, then `cd ~/language-tutor/deploy && docker compose logs -f backend` |
| Change settings | Edit `deploy/.env` on the server, then `docker compose up -d` |
| Rotate the access key | Change `ACCESS_KEY`, `docker compose up -d`; every device asks for the new key |

## Notes

- **Speech on CPU:** measured on a desktop CPU, Kokoro needs ≈ 0.6 s for a 5 s reply, Whisper `small` ≈ 1.1 s and `large-v3-turbo` ≈ 2.5 s per answer. Expect roughly 2–4× that on 4 Ampere cores. `small` has not been checked as carefully as `large-v3-turbo` for keeping learner mistakes verbatim; switch `WHISPER_MODEL` if it "fixes" grammar.
- **Branch protection:** the workflows are path-filtered, so do not make their checks *required* in branch protection (a PR that touches only the frontend would wait forever for the backend check).
- **GitHub Actions minutes:** the private repo gets 2000 free minutes a month; one run takes a few minutes.
- **SQLite** is fine for a single backend process. Moving to Postgres means swapping in `PostgresSaver` / `PostgresStore` and adding a Postgres service to `compose.yaml`.
