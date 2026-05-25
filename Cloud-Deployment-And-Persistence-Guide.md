# Cloud Deployment & Persistence Guide

This guide covers deploying the agent to a VPS so it runs 24/7. The recommended approach is **containerized** — the agent runs inside a Podman or Docker container, making updates, rollbacks, and clean restarts a matter of three commands. Your personal data and config live on the host and survive every rebuild.

If you are already running the agent directly on a VPS (via systemd + venv), see the [Migrating from a Direct Install](#migrating-from-a-direct-install) section.

---

## Why Containerize?

| Concern | Direct install | Containerized |
|---|---|---|
| Python version conflicts | Risk | Isolated — always uses exactly the right version |
| Dependency drift after `git pull` | `pip install -r requirements.txt` may break | `compose build` rebuilds cleanly every time |
| Rollback | Hard | Tag images, `podman compose up` with old tag |
| System Python pollution | Possible | Zero — nothing touches the host |
| Update workflow | Several steps | `git pull && compose build && compose up -d` |

Your `data/` directory and `.env` are **never inside the container image** — they are bind-mounted from the host. A full rebuild leaves your memory, config, and conversation history completely untouched.

---

## What You'll Need

- A VPS running **Fedora/RHEL/Rocky** (Podman) or **Ubuntu/Debian** (Docker)
- A public IP address or domain name
- SSH access
- Your API key(s) and Discord bot token (if applicable)

Minimum VPS specs: 1 vCPU, 1 GB RAM, 10 GB disk. ChromaDB's ONNX embedding model requires ~200 MB of RAM at idle.

---

## Step 1 — Install the Container Runtime

### Podman (Fedora / RHEL / Rocky / AlmaLinux)

Podman ships by default on Fedora and most RHEL-family systems.

```bash
# Verify Podman is installed
podman --version

# Install podman-compose if not already present
sudo dnf install podman-compose -y

# Firewall
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload

# SELinux — allows Nginx to proxy to the container
sudo setsebool -P httpd_can_network_connect 1
```

### Docker (Ubuntu / Debian)

```bash
# Install Docker (official script — see docs.docker.com for manual install)
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER   # allow running docker without sudo (re-login required)
newgrp docker                   # apply group change in current shell

# Firewall
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

---

## Step 2 — Clone and Configure

```bash
git clone https://github.com/pablo0713-glitch/trixxie-companion-agent.git
cd trixxie-companion-agent
```

Create your `.env` file. The easiest way is to run the setup wizard — but since the wizard requires the agent to be running, do a minimal `.env` first:

```bash
cp .env.example .env    # if the example exists, otherwise create from scratch
nano .env
```

At minimum you need `ANTHROPIC_API_KEY` (or equivalent). The wizard will fill in the rest after first boot. See the Environment Variables section in the README for the full reference.

---

## Step 3 — Build the Container

```bash
# Podman
podman compose build

# Docker
docker compose build
```

This step:
1. Pulls `python:3.12-slim`
2. Installs `libgomp1` (required by ChromaDB's ONNX runtime)
3. Installs all Python dependencies from `requirements.txt`
4. Copies the source code

The `data/` directory and `.env` are **excluded** from the image (see `.containerignore`). They are mounted at runtime.

> **First build takes 3–5 minutes** depending on your VPS network speed — mostly downloading Python packages. Subsequent builds that only change source files take under 30 seconds because the dependency layer is cached.

---

## Step 4 — Start the Agent

```bash
# Podman
podman compose up -d

# Docker
docker compose up -d
```

The agent starts on `127.0.0.1:8080`. On first boot:

- `data/` is created automatically if it doesn't exist
- ChromaDB downloads its ONNX embedding model (~80 MB) — one-time only, cached in `data/.cache/`
- The setup wizard is available at `http://your-server-ip:8080/setup` (once you add Nginx below)

Check that it's running:

```bash
podman compose logs -f      # Podman — follow logs
docker compose logs -f      # Docker — follow logs
```

You should see `Uvicorn running on http://0.0.0.0:8080`.

---

## Step 5 — HTTPS with Nginx

The container only listens on `127.0.0.1:8080`. Nginx handles public HTTPS access — required for Second Life, since LSL will not send HTTP to a non-HTTPS URL in production.

### Install Nginx and Certbot

**Fedora/RHEL:**
```bash
sudo dnf install nginx certbot python3-certbot-nginx -y
sudo systemctl enable --now nginx
```

**Ubuntu/Debian:**
```bash
sudo apt install nginx certbot python3-certbot-nginx -y
sudo systemctl enable --now nginx
```

### Create the Nginx config

Create `/etc/nginx/conf.d/trixxie.conf`:

```nginx
server {
    listen 80;
    server_name your-domain-or-ip.nip.io;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;

        # Long timeouts for LLM inference — do not reduce these.
        proxy_read_timeout    300s;
        proxy_connect_timeout 300s;
        proxy_send_timeout    300s;
    }
}
```

> **No domain?** Use `nip.io` — if your VPS IP is `1.2.3.4`, your domain is `1.2.3.4.nip.io`. Free, instant, no DNS setup required.

```bash
sudo nginx -t && sudo systemctl reload nginx
```

### Obtain an SSL certificate

```bash
sudo certbot --nginx -d your-domain-or-ip.nip.io
```

Certbot auto-renews. Verify with `sudo certbot renew --dry-run`.

### Set the bridge URL in `.env`

```bash
# In your .env file on the VPS
SL_BRIDGE_URL=https://your-domain-or-ip.nip.io
```

This tells the setup wizard to generate LSL/Lua scripts with the correct server address.

---

## Step 6 — Run as a Persistent System Service

The container should restart automatically after reboots. Create a systemd service that manages it.

### Podman — rootless systemd service

Create `/etc/systemd/system/trixxie.service`:

```ini
[Unit]
Description=Trixxie AI Companion Agent (Podman)
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/home/your-user/trixxie-companion-agent
ExecStart=/usr/bin/podman compose up
ExecStop=/usr/bin/podman compose down
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

### Docker — systemd service

Create `/etc/systemd/system/trixxie.service`:

```ini
[Unit]
Description=Trixxie AI Companion Agent (Docker)
Wants=network-online.target docker.service
After=network-online.target docker.service

[Service]
Type=simple
User=your-user
WorkingDirectory=/home/your-user/trixxie-companion-agent
ExecStart=/usr/bin/docker compose up
ExecStop=/usr/bin/docker compose down
Restart=on-failure
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

### Enable and start

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now trixxie
sudo systemctl status trixxie
```

---

## Updating the Agent

When a new version is available:

```bash
cd ~/trixxie-companion-agent
git pull
podman compose build    # or: docker compose build
podman compose up -d    # or: docker compose up -d
```

That's it. The agent restarts with the new code. Your `data/` directory and `.env` are untouched.

> If the update adds new Python dependencies (visible in `CHANGELOG.md`), `compose build` handles them automatically — no manual `pip install` needed.

---

## Automatic Update Notifications

A daily timer checks whether new commits are available on `main` and logs the result. It does not update automatically — you decide when to pull.

### Set up the timer

**Service file** — `/etc/systemd/system/trixxie-update-check.service`:

```ini
[Unit]
Description=Trixxie Update Check

[Service]
Type=oneshot
User=your-user
WorkingDirectory=/home/your-user/trixxie-companion-agent
ExecStart=/home/your-user/trixxie-companion-agent/scripts/check_updates.sh
StandardOutput=journal
StandardError=journal
```

**Timer file** — `/etc/systemd/system/trixxie-update-check.timer`:

```ini
[Unit]
Description=Check for Trixxie updates daily

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
```

**Enable:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now trixxie-update-check.timer
```

**Check the log:**
```bash
journalctl -u trixxie-update-check -n 20
```

Example output when an update is available:
```
======================================
  UPDATE AVAILABLE — 3 new commit(s)
======================================
  Local:  a1b2c3d
  Remote: f4e5d6c

  To update (Podman):
    cd /home/your-user/trixxie-companion-agent
    git pull
    podman compose build
    podman compose up -d
======================================
```

### Optional: Discord webhook notification

Open `scripts/check_updates.sh` and uncomment the Discord webhook block near the bottom. Set your webhook URL there or export `DISCORD_WEBHOOK_URL` in the service environment. The webhook URL is never committed to the repo.

---

## Migrating from a Direct Install

If you are already running the agent via a plain systemd service (venv + `python main.py`):

```bash
# 1. Stop and disable the old service
sudo systemctl stop trixxie
sudo systemctl disable trixxie

# 2. Your data/ and .env are already in place — nothing moves.
#    The container will mount them from the same location.

# 3. Install compose support if not already present
#    Fedora / RHEL / Rocky:
sudo dnf install podman-compose -y
#    Ubuntu / Debian:
#    sudo apt install docker-compose-plugin -y
#    (docker-compose-plugin provides the 'docker compose' subcommand)

# Then build and start the container
cd ~/trixxie-companion-agent
git pull                        # get Containerfile and compose.yml
podman compose build            # or: docker compose build
podman compose up -d            # or: docker compose up -d

# 4. Set up the new systemd service (see Step 6 above)

# 5. Verify
podman compose logs -f
```

The old `.venv/` directory is no longer needed once the container is running. You can remove it:

```bash
rm -rf .venv
```

---

## Data & Backups

Everything that matters lives in two places on the host:

| Path | Contents | Must survive rebuilds |
|---|---|---|
| `data/` | Memory, conversations, ChromaDB vectors, config | Yes — volume mounted |
| `.env` | API keys, credentials | Yes — volume mounted |

**To back up:**
```bash
# On the VPS — tar the data directory
tar -czf trixxie-backup-$(date +%F).tar.gz data/ .env

# Transfer to local machine
scp your-user@your-vps:~/trixxie-companion-agent/trixxie-backup-*.tar.gz .
```

**To restore on a new VPS:**
```bash
git clone https://github.com/pablo0713-glitch/trixxie-companion-agent.git
cd trixxie-companion-agent
tar -xzf trixxie-backup-YYYY-MM-DD.tar.gz
podman compose build
podman compose up -d
```

Memory, conversation history, ChromaDB vectors, and all configuration are restored exactly as they were.

---

## Troubleshooting

| Issue | Signature | Fix |
|---|---|---|
| **Container won't start** | `podman compose up` exits immediately | Run `podman compose logs` to see the error. Most common: `.env` missing or malformed. |
| **Service fails with `status=217/USER`** | `systemctl status trixxie` shows `(code=exited, status=217/USER)` | The `User=your-user` placeholder in the service file was not replaced. Edit `/etc/systemd/system/trixxie.service`, replace every instance of `your-user` with your actual Linux username (`whoami`), then run `sudo systemctl daemon-reload && sudo systemctl restart trixxie`. |
| **Service file parse warnings** | `journalctl` shows `Assignment outside of section` or `Missing '='` on line 1 or 2 | The service file has content (a comment, blank line, or stray text) before the `[Unit]` header. The file must begin with `[Unit]` on the very first line — nothing before it. Edit the file and remove any leading lines. |
| **SELinux blocks volume mount** | Container starts but `data/` is empty or read-only; `journalctl` shows AVC denials | Volume labels in `compose.yml` already include `:Z`. If still failing: `sudo chcon -Rt svirt_sandbox_file_t data/` |
| **Port 8080 not reachable** | `curl http://localhost:8080` times out | Check `podman compose ps` — container must be running. Check `compose.yml` — port must be `127.0.0.1:8080:8080` or `0.0.0.0:8080:8080`. |
| **ChromaDB fails to start** | Log: `OSError: libgomp.so.1: cannot open shared object file` | Containerfile already installs `libgomp1`. If you modified the base image, re-add it. |
| **ONNX model re-downloads every rebuild** | Slow first start after each `compose build` | `data/.cache/` volume mount handles this. Verify `./data/.cache:/root/.cache:Z` is in `compose.yml`. |
| **SELinux blocking Nginx proxy** | Nginx log: `(13: Permission denied) while connecting to upstream` | `sudo setsebool -P httpd_can_network_connect 1` |
| **Nginx 60s timeout** | SL replies: `Something went sideways` after exactly 60 seconds | Nginx default read timeout is 60s. Verify `proxy_read_timeout 300s` is in your `trixxie.conf` location block. |
| **Lua script hitting wrong URL** | SL replies fail instantly; server logs show no incoming request | Your viewer's `automation.lua` has an old `SERVER_URL`. Update it to match the VPS HTTPS address. |
| **Update check timer never fires** | `journalctl -u trixxie-update-check` is empty | Run `sudo systemctl list-timers trixxie-update-check` — check `NEXT` column. Run the service manually: `sudo systemctl start trixxie-update-check`. |
| **`compose build` fails on pip install** | Network error during `pip install` | Transient VPS network issue. Re-run `compose build` — packages already downloaded in a partial layer may still be cached. |
