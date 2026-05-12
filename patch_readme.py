import re

with open('README.md', 'r') as f:
    content = f.read()

lua_section = """
### ⚡ Advanced: Bypassing LSL Memory Limitations (Cool VL Viewer Native Lua)

Second Life's default LSL scripting engine caps scripts at 64KB (or 512KB for Mono). For extremely busy sims with heavy sensor data, the LSL HUD can run out of memory. 

To bypass this entirely, you can use the **Hybrid Architecture** by running the agent directly through Cool VL Viewer's native Lua scripting API. This moves the heavy environment, radar, and chat caching directly into the viewer client, resulting in lightning-fast response times and unlimited memory.

**How to use:**
1. Ensure your agent is logged in via **Cool VL Viewer**.
2. Copy `lua/agent_companion.lua` into your `user_settings` directory as `automation.lua` (See `lua/README.md` for exact OS paths).
3. The Lua script handles IMs, Avatars, Environment, and Agent State natively. *Note: Scene Objects still require the LSL HUD worn to scan.*

See [lua/README.md](lua/README.md) for full installation instructions and the complete feature breakdown of the Lua interface.
"""

new_content = content.replace("### 3. Log your agent's avatar in", lua_section + "\n### 3. Log your agent's avatar in")

with open('README.md', 'w') as f:
    f.write(new_content)
