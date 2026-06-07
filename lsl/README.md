# OpenPalAI — Sensory HUD

An LSL HUD script for Second Life that gives OpenPalAI continuous environmental awareness by streaming sensor data to an external AI bridge server. OpenPalAI can see who is nearby, what is being said around her, what the environment looks like, and what objects and attachments are present — all in real time.

---

## Requirements

- A Second Life account with the ability to attach HUD objects
- A running instance of the companion bridge server (see the server-side `README`)
- A publicly accessible HTTPS URL for the bridge (e.g. via Cloudflare Tunnel)

---

## Setup

1. Open [companion_bridge.lsl](companion_bridge.lsl) and set the two config values at the top:

   ```lsl
   string SERVER_URL = "https://your-tunnel.trycloudflare.com";
   string SECRET     = "your_secret_here";   // leave "" to disable auth
   ```

   `SECRET` must match `SL_BRIDGE_SECRET` in the server's `.env` file.

2. Create a new object in Second Life, paste the script inside it, and attach it to OpenPalAI as a HUD (any HUD attachment point works).

3. The HUD announces `OpenPalAI Sensory HUD active` in local owner-only chat when it is ready. An initial environment scan is sent to the server immediately on attach.

---

## Usage

**Touch the HUD** to open the control menu. A dialog appears with the following options:

| Button | Action |
|---|---|
| Avatars | Toggle avatar proximity scanning on/off |
| Chat | Toggle local chat forwarding on/off |
| Environment | Toggle environment scanning on/off |
| Objects | Toggle nearby object scanning on/off |
| Scan Target | Scan the nearest avatar's worn attachments |
| Chat Filter | Switch between *DJ/Objects only* and *All Chat* |
| Status | Print current HUD settings to local chat |
| Close | Dismiss the dialog |

**Talk to OpenPalAI** on channel 42 by prefixing your message with `/42`:

```
/42 Hey OpenPalAI, what's the vibe in here?
```

The HUD forwards your message plus any queued local chat lines to the bridge server, and delivers OpenPalAI's reply back to you via instant message.

**Name trigger (local chat):** if a name in `TRIGGER_NAMES` at the top of the script appears anywhere in local chat (channel 0), the HUD fires a `/sl/message` POST and delivers the reply publicly via `llSay(0)`. Default trigger names: `OpenPalAI`, `OpenPal`, `PalAI`. Replace with your agent's name. This applies to all nearby avatars, including the owner.

---

## Sensor Behaviour

| Sensor | Default | How often |
|---|---|---|
| Environment | ON | On attach, on region/parcel change, every 600 s |
| Avatars | ON | Every 60 s (2 timer ticks × 30 s) |
| Chat | ON | Flushed every 90 s and immediately before each `/42` message |
| Objects | ON | On attach, on region/parcel change, every 300 s |
| RLV / avatar state | ON | Every 30 s (every tick) |

**Chat buffer:** the HUD keeps a rolling window of the last **10** local chat lines. The buffer is flushed to `/sl/sensor` (type `chat`) every 90 seconds and immediately when a `/42` message is received. The server accumulates up to 30 lines and injects only lines received since the user's last message.

**Avatar scanning:** always scans the full region via `llGetAgentList` and returns the **25 closest avatars** to OpenPalAI, sorted by distance. The list is capped at 25 regardless of how many avatars are present — this keeps memory stable and prevents stack-heap collisions in crowded regions (Mono compiler, up to 100 avatars).

---

## Security

If `SECRET` is set, every outbound HTTP request includes the header:

```
X-SL-Secret: <your secret>
```

The bridge server rejects requests that do not present this header or the matching body field. The Lua script (`lua/agent_companion.lua`) cannot send custom HTTP headers, so it includes the secret in the JSON body instead — the server accepts both locations.

`SECRET` and `SERVER_URL` can be patched automatically via the setup wizard (Step 3 → **Update Scripts**), or manually at the top of the script before compiling.

---

## Channels

| Channel | Purpose |
|---|---|
| `0` | Local chat monitoring (listen-only) |
| `42` | Conversation with OpenPalAI |
| `-7654321` | Internal HUD dialog responses (owner-only) |
