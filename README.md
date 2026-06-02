# Trixxie — Friendly Companion Agent
![Trixxie HUD Banner](trixxiebanner.png)

A self-hosted AI companion that lives simultaneously in **Second Life** (or OpenSimulator) and **Discord**. Powered by **Claude (Anthropic)**, **OpenAI**, **Gemini**, **Grok**, **OpenRouter**, or any local model via **Ollama** or **LM Studio**. Personality, memory, tools, and platform behavior are configurable through a browser-based **Command Center** that unifies setup, chat, library management, and debugging — no code editing required.

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
| **Semantic recall** | Meaning-based memory search via ChromaDB — finds relevant memories even when the exact words differ |
| **Importance scoring** | Background agent scores every turn 0–1; only high-value content graduates to long-term memory |
| **Library modules** | Drop-in reference documents (lore guides, setting rules, style notes) injected into context on demand or always-on |
| **Supporting agents** | Specialist background agents (Memory Curator, Librarian, Semantic Recall) each with configurable provider and model |
| **Multiple companions** | Create several distinct companion personas, each with its own identity, tools, and separate memory — switchable in the command center (Second Life and Discord use the default companion only) |
| **Group chat** | Multiple companions converse in one command-center thread — name a companion (or a configured nickname) to pull it into the conversation; they address each other by name to keep it going |
| **Command Center** | Unified web UI for chat, setup, debug, and library management at `/command` |
| **Document uploads** | Browser chat accepts images, text-like files, PDF, and DOCX; library ingest turns documents into modules in `data/library` |

---

## Choose Your Path

| I want… | What to do |
|---|---|
| 🎮 **Discord only** | Fast Setup → Wizard (skip Second Life in Step 3) → done |
| 🌐 **Second Life only** | Fast Setup → Wizard → Second Life Setup |
| ✨ **Both platforms** | Fast Setup → Wizard → Second Life Setup |
| 🔲 **OpenSimulator** | Same as Second Life + one script change — see the OpenSimulator section |

> **Second Life viewers:** Your own viewer can be anything — Firestorm, Alchemy, the official viewer, whatever you prefer. **The agent's avatar must run Cool VL Viewer.** The Lua automation script runs inside Cool VL Viewer's native Lua API and is the primary in-world interface — handling avatars, environment, chat, IMs, and agent state at the viewer level with no LSL memory limits. The LSL HUD remains available as a fallback for the agent's viewer if needed (and is still used for object scanning), but Cool VL Viewer for the agent's avatar will eventually be required.

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

2. **Verify the installation** *(optional but recommended)*
   ```bash
   python check_install.py
   ```
   Should print `Installation OK`. If it fails, the output tells you exactly what's missing.

3. **Start the agent**
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
3. **Install, verify, and run**
```powershell
pip install -r requirements.txt
python check_install.py
.\run.bat
```

**Companion Setup**

1. **Open the command center** → **[http://localhost:8080/command](http://localhost:8080/command)**

2. **Pick your AI model** — paste your Anthropic, OpenAI, or other provider API key, or point it at your local Ollama instance

3. **Enable your platforms** — paste your Discord bot token and/or set a bridge secret for Second Life

4. **Write your agent's persona** — name, personality, identity files. Be specific; vague descriptions produce vague personalities

5. **Save** — the wizard writes your config and the agent begins responding immediately. Use the Chat panel in the same command center to test messages and uploads right away.

> For Second Life, continue to the **Second Life Setup** section after completing setup.

## Command Center

The main browser entry point is **[http://localhost:8080/command](http://localhost:8080/command)**.

It combines four workflows in one place:

- **Chat** — talk to the agent directly from the browser using the real `AgentCore` pipeline.
- **Library** — browse imported modules, preview content, toggle `always_on`, and delete modules.
- **Setup** — the existing setup wizard embedded in-place.
- **Debug** — the existing live debug view embedded in-place.

The Chat panel supports:

- image uploads (`png`, `jpg`, `gif`, `webp`)
- text-like documents (`txt`, `md`, `json`, `py`, `html`, `css`, `csv`, `xml`, `yaml`, etc.)
- `PDF` and `DOCX` uploads for question-answering in chat
- a separate **Add To Library** flow that converts uploaded documents into `data/library/*.md` modules

`/setup` and `/debug` still work directly, but `/command` is the intended browser control surface.

### Multiple companions & group chat

If you've defined more than one companion in the setup wizard, the command center sidebar shows an **Active Companion** selector. Each companion keeps its own separate memory, facts, and history — switching companions switches the whole conversation context.

Flip on **Group chat** and pick which companions take part. Everyone shares one thread:

- Address a companion **by name** — its full name or any nickname/alias you gave it in the wizard (an `@mention` also works, but isn't required). An un-addressed message goes to everyone.
- Companions reply by naming whoever they're talking to, and naming another companion pulls *that* one into the conversation, so the thread can develop on its own.
- How each companion behaves in a group is governed by its **Command Center platform awareness** (wizard Step 6) — edit the *Group Chat Conduct* section to give an agent its own group style.
- Each companion's group turns still feed its own long-term memory.

> **Platform scope:** Multiple companions and group chat are **command-center features**. In Second Life and Discord the agent always resolves to the **default companion** — extra companions are not yet active on those platforms.

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
- **Second Life or OpenSimulator** (optional) — two avatar accounts if running an agent alongside your own: yours (any viewer) and the agent's (**Cool VL Viewer required** for the Lua interface). The LSL HUD works as a fallback on other viewers for the agent's avatar.
- **A public HTTPS tunnel** (required for Second Life) — cloudflared is the default; ngrok, bore, or a VPS with nginx all work too

</details>

---

<details>
<summary><strong>Setup Wizard — Step by Step</strong></summary>

<br>

### Step 1 — Agent

Set your agent's **name** (shown in all responses) and your own name (used in memory notes and context). You can also add **aliases / nicknames** — comma-separated alternate names the companion answers to in command-center group chat (the same idea as the Second Life trigger names).

> **Tip:** Pick a name that fits the persona you have in mind. You can change it any time through the wizard.

**Managing multiple companions:** On the per-companion steps (Agent, Identity, Tools, Context) a companion bar lets you **add, switch, rename, and delete** companions, and mark which one is the command-center default. Each companion gets its own identity files, tools, and separate memory.

> **Platform scope:** Extra companions are only active in the **Command Center** (including group chat). Second Life and Discord currently use the **default companion** only — per-platform companion binding is planned but not yet functional.

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
- **Platform awareness overrides** — edit the per-platform behavior instructions. **Command Center** is always shown and includes a *Group Chat Conduct* section — this is where each companion's group-chat rules live, so you can tune how an agent talks in a group. Second Life, Discord, and OpenSimulator appear when enabled in Step 3.

### Step 7 — Agents

Configure which AI model each background specialist agent uses. These agents run separately from the main model and can use cheaper or faster models to keep background costs low.

| Agent | Default model | Role |
|---|---|---|
| **Memory Curator** | Claude Haiku | Scores conversation turns for importance (0–1); gates consolidation |
| **Librarian** | Claude Haiku | Reasons about which library modules are relevant to a query |
| **Semantic Recall** | Claude Sonnet | Filters and annotates ChromaDB semantic search results |

For each agent, select a provider and enter the model name. Leave blank to use the same model as the main agent.

> **Cost tip:** Haiku is the right default for Curator and Librarian — they run batched scoring calls in the background, not real-time responses. Sonnet or better is recommended for Semantic Recall since it reasons about relevance.

### Step 8 — Save

Review and save. The wizard writes:
- `.env` — API keys and credentials
- `data/agent_config.json` — persona, tools, platform awareness, supporting agent models

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

### 2. Install the viewer interface

#### Primary: Cool VL Viewer + Lua (Recommended)

The Lua automation script is the primary in-world interface. It runs inside **Cool VL Viewer** and handles avatars, environment, agent state, chat buffering, and private IMs entirely at the viewer level — no LSL memory limits, no `/42` channel needed, and native typing indicators.

1. Ensure your agent's avatar is logged in via **Cool VL Viewer**
2. `lua/agent_companion.lua` is generated automatically by `./run.sh` with your credentials filled in
3. Copy it to the Cool VL Viewer user settings folder and rename it `automation.lua`:

| OS | Path |
|---|---|
| Linux | `~/.secondlife/user_settings/automation.lua` |
| Windows | `%APPDATA%\SecondLife\user_settings\automation.lua` |
| macOS | `~/Library/Application Support/SecondLife/user_settings/automation.lua` |

> **Same-PC warning:** If you run both your own viewer and the agent's viewer on the same machine, use **Advanced → Lua → Load Lua script...** to load the script manually on the agent's viewer only — do not rename it `automation.lua` or it will load on both viewers. See [lua/README.md](lua/README.md) for details.

The Lua script covers: avatars (radar), environment, agent state, chat buffer, and direct IMs. Object scanning in the environment still uses the LSL HUD (see below).

#### Fallback: LSL HUD (other viewers)

If you are not using Cool VL Viewer, the LSL HUD provides sensor context and the `/42` conversation channel for any SL viewer. It is also required alongside the Lua script for object scanning.

1. In Second Life, rez a small prim in-world
2. Open its **Contents** tab and create a new script
3. Delete the default content and paste `lsl/companion_bridge.lsl`
   > `lsl/companion_bridge.lsl` is generated by `./run.sh` with credentials filled in. If it doesn't exist yet, run `./run.sh` first, or use `lsl/companion_bridge.lsl.template` and fill in values manually.
4. Save — it compiles automatically (use Mono compiler)
5. Right-click the prim → **More → Attach HUD** → any HUD position

When attached, the HUD says `Trixxie Sensory HUD active. Touch to open controls.` in local chat (owner-only). Touch it to open the sensor control panel.

### 3. Log your agent's avatar in

Log into the avatar's account through Cool VL Viewer (recommended) or any other SL viewer. Sensor data begins streaming to the bridge automatically on login.

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
<summary><strong>Cool VL Viewer — Lua Interface (Primary)</strong></summary>

<br>

**Cool VL Viewer is the recommended viewer for this framework.** The Lua automation script runs natively inside the viewer and serves as the primary in-world bridge — handling avatars, environment, agent state, chat, and private IMs without any of the memory constraints of LSL. The LSL HUD remains available for object scanning and for users on other viewers, but the Lua interface is the intended path going forward.

`lua/agent_companion.lua` is generated automatically by `./run.sh` with your credentials filled in. **The preferred method is to copy this file to your Cool VL Viewer user settings folder and rename it `automation.lua`**, as this ensures the viewer loads it automatically on startup. If you use the viewer's built-in file selector instead (**Advanced → Lua → Load Lua script...**), you will need to manually load it every time the viewer starts. See [lua/README.md](lua/README.md) for full installation details and the same-PC warning.

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

Your agent maintains several layers of memory that work together automatically:

| Layer | Storage | Description |
|---|---|---|
| **Conversation history** | JSON files | Recent turns per user and channel — automatically trimmed to last 20 |
| **Curated notes** | `MEMORY.md` per person | ~2,000 chars — the agent writes its own bullet-point notes about you |
| **Identity files** | `agent.md`, `soul.md`, `user.md` | Your preferences, the agent's personality, loaded every session |
| **Notes tool** | JSON | Free-form notes saved and retrieved on request |
| **Session archive** | SQLite FTS5 | Every turn ever — full-text searchable by keyword |
| **Semantic memory** | ChromaDB vectors | Meaning-based search — finds relevant memories even when words differ |
| **Library modules** | Markdown files | Lore guides, setting rules, reference docs — injected on demand or always-on |

### How consolidation works

After 30+ total turns with a person, a background pipeline runs every 6 hours:

1. **Score** — the Memory Curator agent rates every unscored turn 0.0–1.0 (filler → pivotal)
2. **Gate** — the curator decides if there's anything new worth writing down
3. **Filter** — only turns scored ≥ 0.6 are included in the consolidation transcript
4. **Write** — the main model writes journal-style notes and appends them to `MEMORY.md`
5. **Trim** — conversation files are cut back to 10 turns to keep context lean

### Using library modules

Drop Markdown files into `data/library/` with a front-matter header:

```markdown
---
id: gorean_rp
title: Gorean Roleplay Setting
description: Reference for Gor-based RP
always_on: false
platforms: ["sl"]
tags: ["roleplay", "gor"]
---

# Lore content here...
```

- `always_on: true` — injected into every system prompt automatically (watch total size)
- `always_on: false` — the Librarian agent retrieves it when the conversation calls for it
- `platforms` — restrict a module to `sl`, `discord`, or leave empty for both

You can also create and manage modules from the Command Center:

- open `/command`
- in **Chat**, use the library-ingest upload controls to import text-like files, PDF, or DOCX into `data/library`
- in **Library**, preview modules, toggle `always_on`, refresh the list, or delete modules

Example interactions:
```
"Remember that I love the Botanical sim."
"What did we talk about last week in SL?"
"Find anything in memory about my build project."
"Make a note: shopping list — new boots, glam hair."
"What do you know about me so far?"
```

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

The same debug view is embedded inside the Command Center, so you can inspect logs and prompts without leaving `/command`.

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
├── command/
│   ├── index.html               Command Center shell (Chat, Library, Setup, Debug)
│   ├── style.css                Command Center styling
│   └── app.js                   Command Center client logic + library browser
├── core/
│   ├── agent.py                 AgentCore — shared brain, async tool loop
│   ├── model_adapter.py         Anthropic and OpenAI-compatible backends, prompt caching
│   ├── persona.py               System prompt assembly, identity file loading
│   ├── tools.py                 Tool registry and dispatch
│   ├── supporting_agent.py      Base class for specialist background agents
│   ├── memory_curator.py        Importance scoring + consolidation gate agent
│   ├── librarian_agent.py       Library module retrieval with reasoning pass
│   ├── recall_agent.py          Semantic recall reasoning agent
│   └── tool_handlers/           One file per tool (web_search, notes, memory, sl_action, library, semantic_recall, …)
├── memory/
│   ├── file_store.py            JSON conversation files with asyncio locking
│   ├── consolidator.py          Background summarization job (every 6h)
│   ├── session_index.py         SQLite FTS5 full-text index + importance scores
│   ├── vector_store.py          ChromaDB semantic vector store
│   ├── library_store.py         Library module filesystem layer
│   ├── person_map.py            Links Discord and SL identities to one canonical person
│   └── location_store.py        SL region/parcel visit history
├── interfaces/
│   ├── discord_bot/             Discord interface (discord.py)
│   ├── sl_bridge/               FastAPI HTTP bridge — /sl/message and /sl/sensor
│   ├── command_center.py        Command Center router (chat, uploads, library browser)
│   ├── setup_server.py          Wizard API router (includes library CRUD)
│   └── debug_server.py          Debug page + SSE log stream
├── setup/
│   ├── index.html               Wizard shell
│   ├── style.css                Dark theme
│   └── wizard.js                8-step configuration wizard
├── lsl/
│   └── companion_bridge.lsl     HUD script worn by the agent's avatar (Mono compiler)
├── lua/
│   ├── agent_companion.lua      Cool VL Viewer automation script
│   └── README.md                Lua interface setup guide
└── data/                        Runtime data — created on first run, gitignored
    ├── agent_config.json        Persona, tools, platform awareness, supporting agent models
    ├── identity/                agent.md, soul.md, user.md (written by wizard)
    ├── library/                 Library module Markdown files (*.md with front-matter)
    └── memory/
        ├── sessions.db          SQLite FTS5 index + importance scores
        ├── chroma/              ChromaDB vector store (semantic memory)
        └── {user_id}/           JSON conversations, MEMORY.md, facts per person
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

**Not getting responses in Second Life:**
- Confirm `SERVER_URL` in the Lua script (or LSL script if using the HUD) matches your current public HTTPS URL
- Verify `run.sh` is running and the bridge is on port 8080
- For Lua: open **Advanced → Lua → Show Lua console** in Cool VL Viewer and check for network errors
- For LSL HUD: the tunnel URL changes on every cloudflared restart — update and recompile when it does
- Check that `SECRET` matches `SL_BRIDGE_SECRET` in `.env` (Lua sends it in the JSON body; LSL sends it as an HTTP header — both are accepted)
- If you lost the HUD script, go to **Settings → Step 8** and use the Copy or Save button to recover the fully-patched LSL script

**"My Outfit" scan says "RLV not ready":**
- RLV must be enabled in your SL viewer (look for a RestrainedLove or RestrainedLife toggle in viewer settings)
- Wait ~3 seconds after wearing the HUD before clicking — the RLV handshake fires on the first timer tick

**Garbled characters in SL replies:**
- LSL cannot handle 4-byte UTF-8 (emoji, some Unicode). The bridge strips these before delivery. If you still see garbled bytes, check that `interfaces/sl_bridge/formatters.py` is up to date.

**LSL memory low — resetting (SL local chat):**
- **Known v1.x Limitation**: Crowded sims (lots of objects/avatars) bloat memory when the HUD generates JSON payloads. Currently, the HUD blindly resends sensor data at intervals even if nothing has changed, which consumes memory and processing power.
- **Workaround:** Click the HUD and disable `Objects` or `Avatars` sensors in busy regions. This inefficient data broadcasting will be fixed and optimized in version 2.0.

**Slow first startup (downloading embedding model):**
- On first run, ChromaDB downloads the ONNX embedding model (~80 MB). This is a one-time download and happens silently in the background. If startup takes longer than expected the first time, this is why. Subsequent startups are instant.

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
| `IMPORTANCE_THRESHOLD` | No | Minimum importance score for long-term memory (default: 0.6) |
| `IMPORTANCE_SCORE_BATCH_SIZE` | No | Turns scored per curator API call (default: 20) |
| `LIBRARY_DIR` | No | Path to library modules directory (default: `./data/library`) |
| `LIBRARY_ALWAYS_ON_CAP` | No | Max chars of always-on library content per message (default: 4000) |

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
