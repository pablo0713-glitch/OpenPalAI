import re

with open('CHANGELOG.md', 'r') as f:
    content = f.read()

changelog_addition = """
### Added
- **Hybrid Architecture (Cool VL Viewer Native Lua)** — Migrated heavy sensory load (Avatars, Environment, Avatar State, and Ambient Chat) directly into the viewer's `automation.lua` scripting engine natively. This comprehensively resolves the out-of-memory crashes experienced with LSL HUDs in highly congested sims! 

### Fixed
- **Radar Distance Math** — Corrected astronomical distance values reported by the agent's radar by extracting pure `global_x` and `global_y` properties direct from `GetRadarData` via `pairs()` looping rather than using unsupported legacy vector arrays.
"""

new_content = content.replace("## [Unreleased]", "## [Unreleased]\n" + changelog_addition)

with open('CHANGELOG.md', 'w') as f:
    f.write(new_content)
