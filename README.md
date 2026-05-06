# Trixxie — Friendly Companion Agent
![Trixxie HUD Banner](trixxiebanner.png)

A self-hosted AI companion that lives simultaneously in **Second Life** (or OpenSimulator) and **Discord**. Powered by **Claude (Anthropic)**, **OpenAI**, **Gemini**, **Grok**, **OpenRouter**, or any local model via **Ollama** or **LM Studio**. Personality, memory, tools, and platform behavior are fully configurable through a browser-based setup wizard — no code editing required. 

Now with Cloud deployment and persistence! Read the Cloud Deployment & Persistence Guide to learn more.
---

## What Your Agent Can Do

| Capability | Detail |
|---|---|
| **Natural conversation** | Discord (@mention or DM) and Second Life (private channel or local chat trigger) |
| **Persistent memory** | Remembers facts, preferences, and past conversations across sessions |
| **Web search** | Current news, prices, music, SL Marketplace listings, anything time-sensitive |
| **Notes** | Saves and retrieves items on request — shopping lists, sim recommendations, goals |
| **SL sensor awareness** | Nearby avatars, sim/parcel info, environment, ambient chat, scripted objects, outfit |
| **SL actions** | Emotes, IMs to specific avatars, local chat, animations, mute/unmute |
| **Cross-platform context** | Carries context between Discord and Second Life when the same person is linked |
| **Memory consolidation** | Background job writes concise notes from long conversation history every 6 hours |
| **Session search** | Full-text search over all past conversations — the agent can recall specific exchanges |

---

## Choose Your Path

| I want… | What to do |
|---|---|
| 🎮 **Discord only** | Fast Setup → Wizard (skip Second Life in Step 3) → done |
| 🌐 **Second Life only** | Fast Setup → Wizard → Second Life Setup |
| ✨ **Both platforms** | Fast Setup → Wizard → Second Life Setup |
| 🔲 **OpenSimulator** | Same as Second Life + one script change — see the OpenSimulator section |

> **OpenSim note:** The HUD works on OpenSimulator 0.9.3.0+. Set `string GRID = "opensim";` at the top of `lsl/companion_bridge.lsl` before compiling. See the OpenSimulator section for details.

---

## ⚡ Fast Setup

**Have your API key and (if using Discord) your bot token ready. The whole thing takes about 5 minutes.**

**Linux**

1. **Clone and install**
   ```bash
   git clone https://github.com/pablo0713-glitch/trixxie-companion-agent.git
   cd trixxie-companion-agent
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Start the agent**
   ```bash
   ./run.sh
   ```

**Windows Powershell**

1. **Clone**
```powershell
git clone https://github.com/pablo0713-glitch/trixxie-companion-agent.git
cd trixxie-companion-agent
```
2. **Setup Virtual Environment**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```
3. **Install & Run**
```powershell
pip install -r requirements.txt
python main.py
```

**Companion Setup**

1. **Open the wizard** → **[http://localhost:8080/setup](http://localhost:8080/setup)**

2. **Pick your AI model** — paste your Anthropic, OpenAI, or other provider API key, or point it at your local Ollama instance

3. **Enable your platforms** — paste your Discord bot token and/or set a bridge secret for Second Life

4. **Write your agent's persona** — name, personality, identity files. Be specific; vague descriptions produce vague personalities

5. **Save** — the wizard writes your config and the agent begins responding immediately

> For Second Life, continue to the **Second Life Setup** section after completing the wizard.

---

## Keeping Up to Date

```bash
git pull
./run.sh
```

Your `.env`, `data/`, and configured scripts are not touched by a pull. The LSL and Lua scripts live as `*.template` files in the repo. On every startup, the agent generates the actual scripts from those templates and fills in your credentials from `.env` automatically — no manual steps needed.

---

<details>
<summary><strong>Prerequisites</strong></summary>

<br>

- **Python 3.10+**
- Your LLM service provider **API key** — or a local [Ollama](https://ollama.com) install
- **Discord** (optional) — a bot application from the [Discord Developer Portal](https://discord.com/developers)
- **Second Life or OpenSimulator** (optional) — an avatar account and the viewer of your choice
- **A public HTTPS tunnel** (required for Second Life) — cloudflared is the default; ngrok, bore, or a VPS with nginx all work too

</details>

---

<details>
<summary><strong>Setup Wizard — Step by Step</strong></summary>

<br>

### Step 1 — Agent

Set your agent's **name** (shown in all responses) and your own name (used in memory notes and context).

> **Tip:** Pick a name that fits the persona you have in mind. You can change it any time through the wizard.

### Step 2 — Model

Choose your AI backend:

| Option | When to use |
|---|---|
| **Anthropic (Claude)** | Best quality — requires an API key and incurs per-token cost |
| **OpenAI** | GPT-4o and friends — requires an OpenAI API key |
| **Gemini** | Google's models via the OpenAI-compatible endpoint |
| **Grok** | xAI's models — requires an xAI API key |
| **OpenRouter** | Access many models through one key — great for experimenting |
| **Ollama (local)** | Free and private — requires a local GPU; tool use support varies by model |
| **LM Studio** | Local models via LM Studio's built-in server |

For cloud providers, paste your API key. For Ollama or LM Studio, enter the model name. The wizard validates connectivity before letting you proceed.

### Step 3 — Platforms

Enable the platforms you want:

**Discord**
- Paste your Discord bot token
- The bot responds to @mentions and DMs by default
- Optionally paste guild IDs (comma-separated) to limit which servers it joins
- Optionally paste channel IDs where it should respond to all messages without an @mention

> **Discord bot setup:** In the [Discord Developer Portal](https://discord.com/developers), create an application → Bot → enable **Message Content Intent** under Privileged Gateway Intents. Copy the bot token from that page.

**Second Life / OpenSimulator**
- Paste a bridge secret (any random string — used to authenticate HUD requests)
- Set the port if you need something other than 8080

After filling in the Second Life fields, click **Update Scripts** to automatically write your `SERVER_URL`, `SECRET`, and `GRID` values into both `lsl/companion_bridge.lsl` and `lua/agent_companion.lua`. This saves you from editing the scripts manually. The scripts are also updated automatically when you click **Next** on this step.

### Step 4 — Identity

Define your agent's character through three markdown files edited directly in the wizard:

| File | Purpose | Suggested length |
|---|---|---|
| **agent.md** | Role, purpose, hard limits | 200–400 words |
| **soul.md** | Voice, personality, quirks, aesthetic | 200–400 words |
| **user.md** | Who the owner is — background, preferences, style | 100–200 words |

These files are loaded into every system prompt. Write them in first person from the agent's perspective. Be specific — vague descriptions produce vague personalities.

> **Example soul.md opener:** *"I'm warm and a little wry. I notice texture in things — the light in a sim, the way someone phrases a question. I give honest opinions when asked and unsolicited ones when they're worth having."*

### Step 5 — Tools

Toggle which tools your agent can use:

| Tool | What it does |
|---|---|
| **Web search** | Live web results via Brave Search or Serper API |
| **Notes** | Persistent per-user note storage |
| **SL actions** | In-world effects (emotes, IMs, animations, mute) |

If you enable web search, paste your search API key (Brave or Serper).

### Step 6 — Context

Two optional fields:

- **Additional context** — anything else the agent should always know (e.g. your timezone, a shared fictional setting, house rules)
- **Platform awareness overrides** — edit the per-platform behavior instructions for Discord, Second Life, and OpenSimulator if the defaults don't fit your setup

### Step 7 — Save

Review and save. The wizard writes:
- `.env` — API keys and credentials
- `data/agent_config.json` — persona, tools, platform awareness

Persona changes take effect immediately on the next message. Model and credential changes require restarting `run.sh`.

If Second Life is configured, this step also shows **Copy** and **Save** buttons for the fully-patched LSL and Lua scripts (credentials already filled in). Use these to recover a lost HUD script or save the Lua file to a non-standard location without opening a terminal.

</details>

---

<details>
<summary><strong>Second Life Setup</strong></summary>

<br>

### 1. Expose the bridge

SL servers make outbound HTTP calls — `localhost` is unreachable from their side. You need a public HTTPS URL pointing at your local bridge. **Cloudflared is the default and easiest method**, but any tunneling solution works (ngrok, bore, a VPS with nginx, a named Cloudflare tunnel, etc.).

**Cloudflared (recommended):**

```bash
# Install cloudflared
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared-linux-amd64.deb

# Run alongside run.sh (in a second terminal)
cloudflared tunnel --url http://localhost:8080
```

Copy the `https://` URL it prints — you'll enter it into the wizard and paste it into the HUD script.

> **Note:** The temporary tunnel URL changes every time cloudflared restarts. For a permanent URL, set up a [named tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) — recommended for any install you plan to leave running.

### 2. Create and wear the HUD

1. In Second Life, rez a small prim in-world
2. Open its **Contents** tab and create a new script
3. Delete the default script content and paste the full contents of `lsl/companion_bridge.lsl`
   > **Note:** `lsl/companion_bridge.lsl` is generated by `./run.sh` with your credentials already filled in. If it doesn't exist yet, run `./run.sh` first or use the contents of `lsl/companion_bridge.lsl.template` and set the values manually.
4. Save the script — it compiles automatically
6. Right-click the prim → **More → Attach HUD** → pick any HUD position

When attached, the HUD says `Trixxie Sensory HUD active. Touch to open controls.` in local chat (only visible to you). Touch it to open the sensor control panel.

### 3. Log your agent's avatar in

Log into the avatar's account through any SL viewer. The HUD does the rest — it begins streaming sensor data (nearby avatars, environment, chat) to the bridge automatically.

### 4. Talk to your agent

**Private channel (recommended):**
```
/42 hey, what do you think of this outfit?
```
No one else sees channel 42 messages. The reply arrives as a private IM.

**Local chat trigger:**
```
Hey Trixxie, what's the vibe in this sim?
```
If your agent's name (or any alias in `TRIGGER_NAMES` at the top of the HUD script) appears in local chat, it responds publicly. Default aliases: `["Trixxie", "Trix", "Trixx"]` — replace with your agent's name.

### 5. HUD sensor controls

Touch the HUD to open the control panel. Toggle each sensor on/off, switch between streaming mode (continuous background posts) and per-message mode (sensors only fire when someone speaks):

| Button | Sensor | Streaming interval | Per-message mode |
|---|---|---|---|
| Avatars | Nearby avatar list with distances | Every 60s | On each message |
| Chat | Ambient local chat buffer (last 10 lines) | Flushed every 90s | On each message |
| Environment | Sim, parcel, time of day, rating | Every 600s | On each message |
| Objects | Nearby scripted and non-scripted objects | Every 300s | On region change only |
| RLV | Avatar state — sitting, flying, position | Every 30s | On each message |
| My Outfit | RLV outfit scan (requires RLV-enabled viewer) | On demand | On demand |

</details>

---

<details>
<summary><strong>RLV — Avatar Autonomy</strong></summary>

<br>

**RLV (RestrainedLove / RestrainedLife)** is a viewer extension that allows external scripts — like the HUD — to issue commands that directly control the avatar. Without RLV, the HUD can only *read* the world and *send* messages. With RLV, it can *act*.

### What RLV enables

| Capability | Status |
|---|---|
| **Outfit scanning** | Read which attachment slots and clothing layers are worn — **active now** |
| **Teleport** | Move the avatar to a specific location or to another avatar |
| **Sit / unsit** | Force-sit on a nearby object or stand up |
| **Follow** | Leash the avatar to follow someone around the sim |
| **Detach / attach** | Manage worn items programmatically |

Outfit scanning is active now. Teleport, sit, follow, and other movement controls are planned for a future release — they will also go through RLV.

### Enabling RLV

RLV must be turned on in the viewer settings before wearing the HUD. The exact location varies by viewer:

| Viewer | Where to enable |
|---|---|
| **Firestorm** | Preferences → Firestorm → RestrainedLove API |
| **Cool VL Viewer** | Advanced → RestrainedLove API |
| **Alchemy** | Preferences → Privacy → RestrainedLove API |
| **Black Dragon** | Preferences → General → RestrainedLove |

After enabling, restart the viewer and wear the HUD. The RLV handshake fires automatically on the first timer tick (~3 seconds after attach). The HUD will confirm readiness in local chat.

> **Note:** RLV gives the HUD — and by extension, the AI — real control over the avatar. Only use it with a HUD you trust. The companion HUD only issues RLV commands in direct response to requests from the owner.

</details>

---

<details>
<summary><strong>Cool VL Viewer — Lua Interface (Optional)</strong></summary>

<br>

If your agent's avatar uses **Cool VL Viewer**, you can install the Lua automation script for a native private IM experience — no `/42` channel command needed. The avatar shows a typing indicator while the model processes and delivers the reply in the IM window directly.

`lua/agent_companion.lua` is generated automatically by `./run.sh` with your credentials filled in. **The preferred method is to copy this file to your Cool VL Viewer user settings folder and rename it `automation.lua`**, as this ensures the viewer loads it automatically on startup. If you use the viewer's built-in file selector to point directly to `lua/agent_companion.lua` instead, you will need to manually load the script every time you run the viewer. See lua/README.md for details. The LSL HUD is still required for sensor context.

</details>

---

<details>
<summary><strong>OpenSimulator Setup</strong></summary>

<br>

The HUD works on OpenSimulator 0.9.3.0+. One script change required:

```lsl
// lsl/companion_bridge.lsl — top of file
string GRID = "opensim";   // change from "sl"
```

This caps replies at 1800 chars to stay inside OpenSim's default HTTP body limit. If you control the OpenSim server config and want longer replies, add this to `OpenSim.ini` and revert `GRID` to `"sl"`:

```ini
[Network]
    HttpBodyMaxLenMAX = 16384
```

Tested grids: **OSGrid**, **Metropolis**, standalone deployments.

</details>

---

<details>
<summary><strong>Memory and Notes</strong></summary>

<br>

Your agent maintains several layers of memory across sessions:

| Layer | Description |
|---|---|
| **Conversation history** | Recent turns per user and channel — automatically trimmed |
| **MEMORY.md** | ~2,000 chars — context, facts, and notes the agent curates itself |
| **USER.md** | ~1,200 chars — your preferences, style, and background |
| **Notes** | Free-form notes the agent saves and retrieves on request |
| **Session search** | Full-text search over all past turns via SQLite FTS5 |

Example interactions:
```
"Remember that I love the Botanical sim."
"What did we talk about last week in SL?"
"Make a note: shopping list — new boots, glam hair."
"What do you know about me so far?"
```

Memory consolidation runs every 6 hours in the background — long conversation histories are summarized into notes and trimmed.

</details>

---

<details>
<summary><strong>Debug Page</strong></summary>

<br>

While the agent is running, **[http://localhost:8080/debug](http://localhost:8080/debug)** gives live visibility into its internal state:

| Tab | What it shows |
|---|---|
| **Logs** | Real-time Python log stream. Filter by level and logger name. |
| **Sensors** | Live sensor snapshot per region — raw JSON and formatted view. Auto-refreshes every 5s. |
| **Prompts & Exchanges** | The exact system prompt and messages array sent for each user. Auto-refreshes every 10s. |

Use this to verify sensor data is arriving, inspect what the model actually sees, and diagnose unexpected behavior.

The page also includes a **Reset Memory** button (top right, red). Clicking it shows a confirmation modal — confirming wipes all conversation history, memory files, session index, and avatar records. Useful for a clean-slate restart without stopping the agent.

</details>

---

<details>
<summary><strong>Project Layout</strong></summary>

<br>

```
companion-agent/
├── main.py                      Entry point — starts Discord bot + SL bridge + wizard
├── run.sh                       Activates venv and starts main.py
├── config/settings.py           Loads all config from environment variables
├── core/
│   ├── agent.py                 AgentCore — shared brain, async tool loop
│   ├── model_adapter.py         Anthropic and OpenAI-compatible backends, prompt caching
│   ├── persona.py               System prompt assembly, identity file loading
│   ├── tools.py                 Tool registry and dispatch
│   └── tool_handlers/           One file per tool (web_search, notes, memory, sl_action, …)
├── memory/
│   ├── file_store.py            JSON conversation files with asyncio locking
│   ├── consolidator.py          Background summarization job (every 6h)
│   ├── session_index.py         SQLite FTS5 full-text index
│   ├── person_map.py            Links Discord and SL identities to one canonical person
│   └── location_store.py        SL region/parcel visit history
├── interfaces/
│   ├── discord_bot/             Discord interface (discord.py)
│   ├── sl_bridge/               FastAPI HTTP bridge — /sl/message and /sl/sensor
│   ├── setup_server.py          Wizard API router
│   └── debug_server.py          Debug page + SSE log stream
├── setup/
│   ├── index.html               Wizard shell
│   ├── style.css                Dark theme
│   └── wizard.js                7-step configuration wizard
├── lsl/
│   └── companion_bridge.lsl     HUD script worn by the agent's avatar (Mono compiler)
├── lua/
│   ├── agent_companion.lua      Cool VL Viewer automation script
│   └── README.md                Lua interface setup guide
└── data/                        Runtime data — created on first run, gitignored
    ├── agent_config.json        Persona, tools, platform awareness (written by wizard)
    ├── identity/                agent.md, soul.md, user.md (written by wizard)
    └── memory/                  Conversations, notes, session index, memory files
```

</details>

---

<details>
<summary><strong>Troubleshooting</strong></summary>

<br>

**Agent isn't responding on Discord:**
- Check that `DISCORD_TOKEN` is set in `.env`
- Confirm **Message Content Intent** is enabled in the Discord Developer Portal (Bot → Privileged Gateway Intents)
- In servers, the bot only responds when @mentioned unless the channel ID is in `DISCORD_ACTIVE_CHANNEL_IDS`

**SL HUD isn't triggering responses:**
- Confirm `SERVER_URL` in the LSL script matches your current cloudflared tunnel URL
- Verify `run.sh` is running and the bridge started on port 8080
- The tunnel URL changes on every cloudflared restart — update the script and recompile when it does
- Check that `SECRET` in the LSL script matches `SL_BRIDGE_SECRET` in `.env`
- If you lost the HUD script, go to **Settings → Step 7** and use the Copy or Save button to recover the fully-patched LSL script

**"My Outfit" scan says "RLV not ready":**
- RLV must be enabled in your SL viewer (look for a RestrainedLove or RestrainedLife toggle in viewer settings)
- Wait ~3 seconds after wearing the HUD before clicking — the RLV handshake fires on the first timer tick

**Garbled characters in SL replies:**
- LSL cannot handle 4-byte UTF-8 (emoji, some Unicode). The bridge strips these before delivery. If you still see garbled bytes, check that `interfaces/sl_bridge/formatters.py` is up to date.

**LSL memory low — resetting (SL local chat):**
- **Known v1.x Limitation**: Crowded sims (lots of objects/avatars) bloat memory when the HUD generates JSON payloads. Currently, the HUD blindly resends sensor data at intervals even if nothing has changed, which consumes memory and processing power.
- **Workaround:** Click the HUD and disable `Objects` or `Avatars` sensors in busy regions. This inefficient data broadcasting will be fixed and optimized in version 2.0.

**Agent makes up conversation history:**
- This shouldn't happen — the system prompt instructs the agent to use `session_search` before claiming it doesn't recall something
- If it persists, check `data/memory/sl_{uuid}/sl_42.json` for hallucinated turns and delete them

</details>

---

<details>
<summary><strong>Environment Variables</strong></summary>

<br>

All configuration lives in `.env` (created by the wizard). Reference:

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | If using Claude | Your Anthropic API key |
| `OPENAI_API_KEY` | If using OpenAI / OpenRouter / Gemini / Grok | Your provider API key |
| `OPENAI_MODEL` | If using OpenAI-compatible provider | Model name (e.g. `gpt-4o`, `gemini-2.0-flash`) |
| `OPENAI_BASE_URL` | If using LM Studio or custom endpoint | Base URL override |
| `OLLAMA_MODEL` | If using Ollama | Model name (e.g. `llama3.2`) |
| `DISCORD_TOKEN` | If using Discord | Discord bot token |
| `DISCORD_ALLOWED_GUILD_IDS` | No | Comma-separated guild IDs — empty means all guilds |
| `DISCORD_ACTIVE_CHANNEL_IDS` | No | Channels where the bot responds without @mention |
| `SL_BRIDGE_SECRET` | No | Shared secret — must match `SECRET` in the LSL script |
| `SL_BRIDGE_PORT` | No | Default: 8080 |
| `SEARCH_PROVIDER` | If web search enabled | `brave` or `serper` |
| `SEARCH_API_KEY` | If web search enabled | Brave or Serper API key |
| `MEMORY_MAX_HISTORY` | No | Turns kept per conversation file (default: 20) |
| `OWNER_NAME` | No | Your name — used in memory notes and context |

</details>

---

## Support

I'm always happy to help — whether you're stuck on setup, hit a bug, or just have questions about how something works.

| Platform | Contact |
|---|---|
| **Second Life** | Drop a notecard to **StonedGrits** — IMs can get capped and lost, so a notecard is the safest way to reach me in-world |
| **Discord** | **tanmojo** |
| **Email** | pablo071372@outlook.com |
| **GitHub** | [pablo0713-glitch](https://github.com/pablo0713-glitch) — open an issue for bugs or feature requests |

---

## License

MIT — see [LICENSE](LICENSE).
