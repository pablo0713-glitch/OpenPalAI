# Changelog

All notable changes to Trixxie Companion Agent are documented here.

---

## 2026-05-12

### Added
- **Hybrid Architecture (Cool VL Viewer Native Lua)** — Migrated heavy sensory load (Avatars, Environment, Avatar State, and Ambient Chat) directly into the viewer's `automation.lua` scripting engine natively. This comprehensively resolves the out-of-memory crashes experienced with LSL HUDs in highly congested sims! 

### Fixed
- **Radar Distance Math** — Corrected astronomical distance values reported by the agent's radar by extracting pure `global_x` and `global_y` properties direct from `GetRadarData` via `pairs()` looping rather than using unsupported legacy vector arrays.


### Known Issues

- **LSL HUD stops responding to touch after extended uptime** — After running for some time, the HUD no longer responds to clicks (control panel doesn't open, sensor toggles stop working). Sensory data stops reaching the agent. Root cause is low or out of memory issue with LSL Mono. ~~**Workaround:** right-click the HUD object → Edit → Scripts → Reset Scripts, then close the editor. This resets script state without needing to detach and re-wear.~~

**Note:** The script will now auto reset when memory gets too low (this is the main culprit of the HUD not responding). 

---

## 2026-04-27

### Fixed

- **SL agent silent failure (history corruption loop)** — When the Anthropic API returned `stop_reason=end_turn` with an empty content block, the assistant turn was saved to history before the error was detected. On the next message, the model saw the empty turn and returned empty again, compounding indefinitely. Three changes in `core/agent.py` break the cycle:
  - `_sanitize_history()` now strips dangling `assistant[tool_use] + user[tool_result]` pairs (no final assistant response) and all trailing plain user turns before each API call.
  - The user turn is now persisted only **after** a successful non-empty reply, not before the tool loop runs.
  - `_run_tool_loop()` retries once when `stop_reason=end_turn` but text is empty, then returns a fallback string if still empty after the retry.

- **Wizard "Update Scripts" JSON parse error** — `res.json()` threw when the server returned an HTML error page (e.g. a 500). The fetch now wraps JSON parsing in a try/catch and falls back to `res.text()` to display the raw HTTP status and body.

- **LSL/Lua scripts not refreshing after `git pull`** — `_patch_scripts()` previously only copied the template when the output file was absent. Now `patch_scripts_from_env()` (called on every startup) uses `force_template=True`, which always copies the template before patching. `_template_has_changed()` compares credential-normalized content so purely cosmetic credential differences don't count as structural changes.

- **Wizard Step 7 script section not appearing** — The script section was gated on `state.sl_enabled`, which is only set when `SL_BRIDGE_SECRET` or `SL_BRIDGE_URL` appears in `.env`. Users who set up scripts manually (without using the wizard) never had these in `.env`, so the section was always hidden. Gate removed — the section always renders on Step 7.

- **Wizard Step 7 buttons absent on fresh remote deploy** — Generated scripts (`companion_bridge.lsl`, `agent_companion.lua`) are gitignored and only exist after the agent runs `patch_scripts_from_env()` on startup. On a fresh `git pull` before the first run, both were null and no buttons rendered. `bindStep7()` now auto-calls `POST /setup/update-scripts` silently when scripts are missing but a bridge URL is in state, then re-fetches before rendering.

- **Misleading Lua log on HTTP reply** — `OnHTTPReply` printed `"actions field is nil/absent in response"` whenever a reply had no action payloads — which is the normal case for most messages. Log line removed.

- **LSL HUD event queue flooding in busy regions** — The channel 0 listener (local chat) was always registered, consuming one of the 64 LSL event queue slots continuously in crowded sims and silently dropping `touch_start` events (HUD unresponsive). Channel 0 is now only registered when `s_chat = TRUE`.

### Added

- **LSL user-configurable time intervals** — Stream mode sensor intervals (`AV_TICKS`, `OBJ_TICKS`, `ENV_TICKS`, `CHAT_TICKS`, `RLV_TICKS`) were moved to the top of the LSL script config section. This is a QoL customization option to help manage data overhead until v2.0 solves the blind resend logic that contributes to "HUD memory low" resets.

- **`GET /setup/scripts` endpoint** (`interfaces/setup_server.py`) — Returns the patched LSL and Lua script content plus an `updated_on_startup` boolean flag. Used by `bindStep7()` to fetch scripts without exposing them in the initial page HTML.

- **Wizard Step 7 — Copy and Save buttons for LSL and Lua scripts** — Step 7 fetches both scripts from `/setup/scripts` and holds their content in memory only (never written to the DOM). Two buttons per script: **Copy** sends the full content to the clipboard; **Save** triggers a browser download with the correct filename. Useful for recovering a lost HUD or installing the Lua script from the settings page without a terminal. Script content is never visible in the page source or browser inspector.

- **Startup script update banner** — When `patch_scripts_from_env()` detects that a git pull brought in a structurally different template (new variables, new sections), it sets `_startup_script_updated = True`. Step 7 displays a yellow warning banner prompting the user to recopy the LSL script to their HUD and replace the Lua file.

---

## 2026-04-05 (v1.0 public release prep)

- Initial public release. See `whats-in-v10.md` for the full v1.0 feature set.

---

## Format

This changelog follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) conventions.
Categories used: **Added**, **Changed**, **Fixed**, **Removed**.
