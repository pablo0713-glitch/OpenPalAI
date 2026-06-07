# Persistent Sandboxes

Use sandboxes to test long-running memory behavior without touching live `data/` or `.env`.

## Linux / Fedora / VPS Container Sandbox

This mirrors the hosted Fedora Podman deployment while keeping state in `.sandbox/linux/`.

```bash
chmod +x scripts/sandbox-linux.sh
./scripts/sandbox-linux.sh up
```

Open:

```text
http://127.0.0.1:18080/command
```

Useful commands:

```bash
./scripts/sandbox-linux.sh logs
./scripts/sandbox-linux.sh ps
./scripts/sandbox-linux.sh down
```

State lives at:

```text
.sandbox/linux/.env
.sandbox/linux/data/
.sandbox/linux/cache/
```

The sandbox copies your current `.env` on first creation if one exists. After that, it is independent.

To use Docker instead of Podman:

```bash
ENGINE=docker ./scripts/sandbox-linux.sh up
```

To use another port:

```bash
SANDBOX_BIND=127.0.0.1:18081 ./scripts/sandbox-linux.sh up
```

## Windows Local Sandbox

This validates the Windows local-venv installation path while keeping state in `.sandbox/windows/`.

Run from PowerShell:

```powershell
.\scripts\sandbox-windows.ps1 up
```

Open:

```text
http://127.0.0.1:18080/command
```

Run the install smoke test inside the Windows sandbox:

```powershell
.\scripts\sandbox-windows.ps1 check
```

State lives at:

```text
.sandbox\windows\.env
.sandbox\windows\data\
.sandbox\windows\.venv\
```

Use a different port:

```powershell
.\scripts\sandbox-windows.ps1 up -Port 18081
```

## What Is Isolated

- `OPENPALAI_DATA_DIR` redirects `agent_config.json`, identity files, person map, notes, memory, and library modules.
- `OPENPALAI_ENV_FILE` redirects the setup wizard's `.env` reads/writes.
- Linux container sandbox bind-mounts `.sandbox/linux/data` to `/app/data`.
- Windows sandbox sets `MEMORY_DIR`, `NOTES_DIR`, and `LIBRARY_DIR` to `.sandbox/windows/data/...`.

## Pull Live VPS Data Into a Sandbox

Local does not need to keep live data. Pull remote state into a sandbox only when you want to test against it.

### Linux / Fedora

Requires `rsync` and SSH access to the VPS:

```bash
REMOTE=user@155.138.223.115 \
REMOTE_PATH=/path/to/companion-agent \
./scripts/pull-live-data.sh
```

This copies remote `data/` into `.sandbox/linux/data/` and leaves `.env`, ChromaDB vectors, and cache out by default. Chroma will rebuild locally from `sessions.db`.

Optional:

```bash
INCLUDE_ENV=1 ./scripts/pull-live-data.sh      # also copy remote .env
INCLUDE_CHROMA=1 ./scripts/pull-live-data.sh   # also copy Chroma/cache
TARGET=./.sandbox/repro ./scripts/pull-live-data.sh
```

### Windows

Requires Windows OpenSSH client and `tar`:

```powershell
.\scripts\pull-live-data-windows.ps1 `
  -Remote user@155.138.223.115 `
  -RemotePath /path/to/companion-agent
```

Optional:

```powershell
.\scripts\pull-live-data-windows.ps1 -Remote user@host -RemotePath /srv/openpalai -IncludeEnv
.\scripts\pull-live-data-windows.ps1 -Remote user@host -RemotePath /srv/openpalai -IncludeChroma
```

After pulling, start the sandbox normally:

```bash
./scripts/sandbox-linux.sh up
```

```powershell
.\scripts\sandbox-windows.ps1 up
```

## Memory Compatibility Checks

For long-running memory tests, inspect the sandbox debug page:

- Memory Pipeline should group by Command Center root identity.
- `Unscored` should drain after background scoring.
- `Pending notes` should drain after consolidation.
- `MEMORY.md` should update under `.sandbox/.../data/memory/agents/{agent_id}/{person}/`.
- Audit provenance should appear in `.sandbox/.../data/notes/{agent_id}/{person}/consolidation_runs.jsonl`.
