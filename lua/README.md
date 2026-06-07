# Cool VL Viewer — Lua Automation Interface

An alternative to the LSL HUD that uses Cool VL Viewer's native Lua scripting API. This script serves as the primary intelligence bridge for OpenPalAI, completely overcoming the stringent active-memory limitations (64KB/512KB) of LSL scripts.

This interface **replaces the LSL HUD for almost all heavy sensor tasks**. It handles Avatars (Radar), Environment, Agent State (RLVa), Chat buffering, and IM conversation paths. 

*(Note: Scene Object scanning is currently still pending migration and remains partially dependent on LSL, but the Lua script is self-sufficient for a fully functioning companion.)*

---

## Requirements

- **Cool VL Viewer** (any recent release with Lua v5.5 support)
- The bridge server running and reachable via a public HTTPS URL (same setup as the LSL HUD)

---

## Important — Agent's Viewer Only

This script must be installed on **the agent's viewer** (the viewer logged in as OpenPalAI's avatar). Do **not** install it on your own viewer. If you run `automation.lua` on your viewer, your viewer will mistakenly intercept and route your IMs.

> **⚠️ Running both viewers on the same PC?**
> Cool VL Viewer shares the `user_settings` folder across all instances. If you use **Option 1** below (renaming the file to `automation.lua`), *both* your viewer and OpenPalAI's viewer will load the AI script, causing chaotic bridging. 
> **The Fix:** Delete `automation.lua` from your `user_settings` folder completely, and use **Option 2** to load the script manually *only* on OpenPalAI's viewer.

---

## Installation

`lua/agent_companion.lua` is generated automatically by `./run.sh` with your credentials filled in from `.env` using `agent_companion.lua.template`.

**Option 1 — Copy the file (recommended for separate PCs)**

Copy `lua/agent_companion.lua` to the Cool VL Viewer user settings folder and rename it `automation.lua`:

| OS | Path |
|---|---|
| Linux | `~/.secondlife/user_settings/automation.lua` |
| Windows | `%APPDATA%\SecondLife\user_settings\automation.lua` |
| macOS | `~/Library/Application Support/SecondLife/user_settings/automation.lua` |

This is the preferred method because it ensures the viewer loads the script automatically on startup. 

**Option 2 — Point Cool VL Viewer directly at the file (required for same-PC setups)**

Cool VL Viewer has a built-in file selector for the automation script. Open **Advanced -> Lua -> Load Lua script...** and select `lua/agent_companion.lua` from your companion-agent install folder. Note: You must manually load that script every time the viewer runs.

---

## How It Works (The Hybrid Architecture)

Rather than forcing the SL Simulator to process heavy avatar distance calculations and string concatenations via LSL, this script directly interrogates the Cool VL Viewer client APIs.

1. **Continuous Streaming:** The script utilizes a `SensorLoop()` built on `CallbackAfter()` that fires non-blocking asynchronous HTTP POSTs to the Python Backend (`/sl/sensor`) every 4-30 seconds depending on the data type.
2. **In-Memory Caching:** The Python backend receives these payloads and overwrites the `SensorStore` in memory.
3. **Reactive AI:** OpenPalAI remains asleep until spoken to (IM or triggered local chat). Once triggered, `AgentCore` reads the latest snapshot from `SensorStore` instantly, drastically reducing latency compared to proactive scanning.

### What Lua Handles:
- **Avatars:** Extracts exact distance and global coordinates via `GetRadarList` and `GetRadarData`. (Requires the viewer Radar floater to be open or configured to background update).
- **Environment:** Simulator Region, Name, Sun/Moon phase, Time of Day (SLT), and Parcel flags.
- **Agent State:** Moving, flying, sitting, typing, sitting on object, etc.
- **Chat:** Maintains a 10-line rolling buffer of local chat without the strict string chunking limits of LSL.
- **Direct IM:** Real-time typing indicators (`SetAgentTyping`) and native unlimited chat routing directly into the active IM window.

---

## Echo Suppression

Cool VL Viewer reflects sent IMs back through `OnInstantMsg`. The script maintains a `sent_replies` counter table. Each chunk increments its counter before `SendIM`. On the next `OnInstantMsg`, if the incoming text has a pending count > 0, the count is decremented and the message is dropped, preventing hallucination loops.

---

## Authentication

Cool VL Viewer's `PostHTTP` cannot send custom HTTP headers like `X-SL-Secret`. Instead, the secret is bundled directly into the JSON `payload.secret` object. The Python backend dynamically validates both HTTP headers (for legacy LSL) and the JSON body (for Lua).

---

## Troubleshooting

**No avatars are appearing in sweeps!**
- You must keep the Radar floater open in OpenPalAI's viewer, or configure the radar preferences to update in the background. If the radar is closed, the viewer API returns `nil` to conserve CPU.

**"Authentication failed."**
- Confirm `SECRET` in the Lua script matches `SL_BRIDGE_SECRET` in `.env`.

**No reply arrives:**
- Confirm `SERVER_URL` in the script is set to the correct public HTTPS URL.
- Open **Advanced → Lua → Show Lua console** in the viewer and check for network errors.
