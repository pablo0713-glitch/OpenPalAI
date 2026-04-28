# Cool VL Viewer — Lua Interface

An alternative to the LSL HUD that uses Cool VL Viewer's native Lua scripting API. The agent receives private IMs directly, shows a typing indicator while the model processes the message, and delivers the reply back into the same IM window — no `/42` chat command required.

This interface **replaces the conversation path only**. The LSL HUD is still needed for sensor data (avatars, environment, objects, clothing) and ambient chat context.

---

## Requirements

- **Cool VL Viewer** (any recent release with Lua v5.5 support)
- The bridge server running and reachable via a public HTTPS URL (same setup as the LSL HUD)

---

## Important — Agent's Viewer Only

This script must be installed on **the agent's viewer** (the viewer logged in as Trixxie's avatar). Do **not** install it on your own viewer. If you run `automation.lua` on your viewer, your viewer will forward Trixxie's outgoing IMs back to the bridge — triggering a second inference call for each reply and producing a hallucination loop that spirals until you stop the script (often crashing the server with a rate limit error).

> **⚠️ Running both viewers on the same PC?**
> Cool VL Viewer shares the `user_settings` folder across all instances. If you use **Option 1** below (renaming the file to `automation.lua`), *both* your viewer and Trixxie's viewer will load the AI script, immediately causing the infinite reply loop. 
> **The Fix:** Delete `automation.lua` from your `user_settings` folder completely, and use **Option 2** to load the script manually *only* on Trixxie's viewer.

---

## Installation

`lua/agent_companion.lua` is generated automatically by `./run.sh` with your credentials already filled in from `.env`. You do not need to edit it manually.

**Option 1 — Copy the file (recommended for separate PCs)**

Copy `lua/agent_companion.lua` to the Cool VL Viewer user settings folder and rename it `automation.lua`:

| OS | Path |
|---|---|
| Linux | `~/.secondlife/user_settings/automation.lua` |
| Windows | `&#37;APPDATA&#37;\SecondLife\user_settings\automation.lua` |
| macOS | `~/Library/Application Support/SecondLife/user_settings/automation.lua` |

This is the preferred method because it ensures the viewer loads the script automatically on startup. You will need to re-copy the file any time the script is updated by `./run.sh`.

**Option 2 — Point Cool VL Viewer directly at the file (required for same-PC setups)**

Cool VL Viewer has a built-in file selector for the automation script. Use it to select `lua/agent_companion.lua` from your companion-agent install folder. Note: If you point to a different script rather than the default `automation.lua` path, you must manually load that script every time the viewer runs.

---

## How It Works

| Step | What happens |
|---|---|
| Someone sends the agent a private IM | `OnInstantMsg` fires (type == 0, peer-to-peer only) |
| | Echo check — if the message matches a recently sent reply, it is discarded |
| | `SetAgentTyping(true)` — typing indicator appears immediately |
| | `PostHTTP` fires an async POST to `/sl/message` |
| Model returns a reply | `OnHTTPReply` fires |
| | `SetAgentTyping(false)` — indicator clears |
| | Reply is split into ≤ 1000-char chunks and delivered via `SendIM` |

The typing indicator is visible for exactly the duration of model inference — the same natural feel as a human typing a response.

Nearby chat context is **not** captured by this script. It is delivered via the LSL HUD's sensor pipeline (`/sl/sensor` type `chat`) and injected into the system prompt by `SensorStore.get_changes()` on each message. The HUD must be worn and active.

---

## Echo Suppression

Cool VL Viewer reflects sent IMs back through `OnInstantMsg` with the **recipient's UUID** as `origin_id` rather than the sender's. This bypasses the standard self-check (`origin_id == self_info["id"]`) and would otherwise cause Trixxie's own reply to loop back as a new incoming message.

The script maintains a `sent_replies` counter table. Each chunk increments its counter before `SendIM`. On the next `OnInstantMsg`, if the incoming text has a pending count > 0, the count is decremented and the message is dropped. Each echo is consumed exactly once, so the same text sent legitimately later is not affected.

---

## Actions

The bridge can return `actions` alongside a reply. The Lua script handles the following action types:

| Action type | What the script does |
|---|---|
| `mute_avatar` | Calls `AddMute(uuid, 1)` — mutes the target avatar by UUID |
| `unmute_avatar` | Calls `RemoveMute(uuid, 1)` — unmutes the target avatar by UUID |
| `is_muted` | Calls `IsMuted(uuid, 1)` and sends the result back as an IM |
| Any other action with text | Delivered as an IM to the conversation |

Mute/unmute actions are triggered when the agent uses the `sl_action` tool with the corresponding type. The `target_key` field in the action payload must be a valid avatar UUID.

---

## Authentication

Cool VL Viewer's `PostHTTP` cannot send custom HTTP headers, so the secret is included in the JSON request body rather than in `X-SL-Secret`. The server accepts the secret from either location, so the LSL HUD and this script can coexist without any server-side changes.

---

## Differences from the LSL HUD

| Feature | LSL HUD | Lua script |
|---|---|---|
| Conversation trigger | `/42 message` in local chat | Private IM to the agent directly |
| Sensor data (avatars, env, etc.) | Yes | No — HUD still required |
| Ambient chat buffer | Yes | No — via HUD sensor pipeline only |
| Typing indicator | No | Yes — `SetAgentTyping` |
| Reply chunking | `send_chunked()` in LSL | `split_chunks()` in Lua |
| Mute / unmute / is_muted | No | Yes — `AddMute` / `RemoveMute` / `IsMuted` |
| Custom auth header | `X-SL-Secret` | Body `secret` field |

---

## Troubleshooting

**No reply arrives:**
- Confirm `SERVER_URL` is set to the correct public HTTPS URL (not localhost).
- Check that the bridge server is running (`./run.sh`) and cloudflared is active.
- In the viewer, open **Advanced → Lua → Show Lua console** and check for errors.

**"Authentication failed." reply:**
- Confirm `SECRET` in the Lua script matches `SL_BRIDGE_SECRET` in `.env`.

**Agent gets stuck in an infinite reply loop or returns errors instantly:**
- You are likely running both viewers on the same PC and your personal viewer loaded the script by mistake. Delete `automation.lua` from your `user_settings` folder and use **Option 2** for the agent's viewer instead.

**Replies cut off mid-sentence:**
- The chunker breaks at sentence boundaries. If replies are still truncating, the `REPLY_HARD_CAP` on the server (4000 chars for SL, 1800 for OpenSim) may be too low for the conversation style — adjust in `interfaces/sl_bridge/formatters.py`.

**Mute/unmute has no effect:**
- Confirm the `target_key` in the action is a valid UUID (not a display name). The agent pulls UUIDs from the avatar radar sensor — verify the LSL HUD is active and sending avatar data.
