### 🌐 Cloud Deployment & Persistence Guide

This section covers how to transition Trixxie from a local manual run to a 24/7 "Always-On" entity in the cloud.

#### 1. Environment-Specific Setup

**Fedora / RHEL / Rocky / AlmaLinux (High Security)**

These systems use `dnf`, `firewalld`, and have **SELinux** enabled by default.

Bash

```
# 1. Install Dependencies
sudo dnf install python3 python3-pip nginx git certbot python3-certbot-nginx -y

# 2. Configure Firewall
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --permanent --add-port=8080/tcp
sudo firewall-cmd --reload

# ⚠️ CRITICAL: SELinux Permission (Fixes 'Permission Denied' 13)
# Allows Nginx to proxy traffic to the Python backend (uvicorn)
sudo setsebool -P httpd_can_network_connect 1

# 3. Framework Setup
git clone https://github.com/pablo0713-glitch/trixxie-companion-agent.git
cd trixxie-companion-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Ubuntu / Debian (Standard Production)**

Uses `apt` and `ufw`. SELinux is usually not active by default.

Bash

```
# 1. Install Dependencies
sudo apt update && sudo apt install python3-pip python3-venv nginx git certbot python3-certbot-nginx -y

# 2. Configure Firewall
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 8080/tcp
sudo ufw enable

# 3. Framework Setup
git clone https://github.com/pablo0713-glitch/trixxie-companion-agent.git
cd trixxie-companion-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows (Development & Home Hosting)**

PowerShell

```
# 1. Clone
git clone https://github.com/pablo0713-glitch/trixxie-companion-agent.git
cd trixxie-companion-agent

# 2. Virtual Environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Install & Run
pip install -r requirements.txt
python main.py
```

---

#### 2. Linux Persistence (`systemd`)

To ensure Trixxie stays online after you close your terminal or if the server reboots:

1. **Create the file:** `sudo nano /etc/systemd/system/trixxie.service`
    
2. **Paste configuration:** (Replace `your-user` with your actual username)
    

Ini, TOML

```
[Unit]
Description=Trixxie AI Companion Agent
After=network.target

[Service]
User=your-user
WorkingDirectory=/home/your-user/trixxie-companion-agent
ExecStart=/home/your-user/trixxie-companion-agent/.venv/bin/python main.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

3. **Activate:**
    

Bash

```
sudo systemctl daemon-reload
sudo systemctl enable --now trixxie
```

---

#### 3. Bypassing Tunnels (HTTPS with Nginx + nip.io)

If you have a static VPS IP (e.g., `123.456.789.012`) and no domain:

1. **Nginx Config:** Create `/etc/nginx/conf.d/trixxie.conf`:
    
    Nginx
    
    ```
    server {
        listen 80;
        server_name 123.456.789.012.nip.io;
        location / {
            proxy_pass http://127.0.0.1:8080;
            proxy_set_header Host $host;
            proxy_http_version 1.1;
            proxy_set_header Connection "";
            proxy_buffering off; # Required for Debug Page logs
            
            # Increase timeouts to prevent Nginx from dropping long LLM inference calls
            proxy_read_timeout 300s;
            proxy_connect_timeout 300s;
            proxy_send_timeout 300s;
        }
    }
    ```
    
2. **SSL:** Run `sudo certbot --nginx -d 123.456.789.012.nip.io`
    
3. **Remote .env:** Ensure `SL_BRIDGE_URL=https://123.456.789.012.nip.io` is set. This allows the Setup Wizard to generate the correct LSL scripts for your HUD.
    

---

#### 🛠 Troubleshooting & Warnings

|**Issue**|**Signature**|**Fix**|
|---|---|---|
|**SELinux Blocking**|Nginx log: `(13: Permission denied) while connecting to upstream`|`sudo setsebool -P httpd_can_network_connect 1`|
|**Port Conflict**|`bind() to 0.0.0.0:80 failed (98: Address already in use)`|`sudo pkill -9 nginx` then `sudo systemctl start nginx`|
|**Missing Service User**|`status=217/USER` or `Failed at step USER` in `journalctl`|Edit `/etc/systemd/system/trixxie.service` and replace `User=your-user` with your actual Linux username (run `whoami`). Run `sudo systemctl daemon-reload`.|
|**Service Permissions**|`status=203/EXEC` and `Permission denied` in `journalctl`|Give systemd access to your home directory: `chmod +x /home/your-user` and `chmod +x /home/your-user/trixxie-companion-agent`. If using SELinux: `sudo chcon -R -t bin_t /home/your-user/trixxie-companion-agent/.venv/bin/`|
|**Nginx 60s Timeout**|SL IM replies: `Something went sideways` after exactly 60 seconds|Nginx is dropping the LLM request. Add `proxy_read_timeout 300s; proxy_connect_timeout 300s; proxy_send_timeout 300s;` to the `location /` block in your `trixxie.conf`, then restart Nginx.|
|**Lua Script Old URL**|SL IM replies: `Something went sideways` instantly, but server log shows `POST /sl/sensor` 200 OK|Your SL viewer's local `automation.lua` is trying to hit an old or `localhost` URL. Update `SERVER_URL` in `user_settings/automation.lua` on your physical PC to match the remote server's address, and ensure `SECRET` matches `SL_BRIDGE_SECRET`.|