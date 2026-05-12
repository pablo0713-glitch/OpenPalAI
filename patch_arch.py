import re

with open('ARCHITECTURE.md', 'r') as f:
    content = f.read()

hybrid_section = """
### Hybrid Architecture (Cool VL Viewer Native Sensors)

To overcome LSL's strict 512KB HTTP-POST dictionary string concatenation memory limits (which often crashed scripts in highly populated SIMs), a **Hybrid Architecture** runs entirely inside `automation.lua`.

```
YourAvatar is near Trixxie in Second Life
        │
        ▼
automation.lua — SensorLoop() runs on CallbackAfter timers
        │  Uses pcall(GetRadarList) to fetch surrounding avatars instantaneously
        │  Uses pcall(GetParcelInfo) & GetTimeStamp
        │  Uses pcall(GetAgentState)
        │  PostHTTP POST /sl/sensor  [secret in body]
        ▼
cloudflared tunnel  →  FastAPI bridge (localhost:8080)
        │
        ▼
SensorStore  ← updates in-memory arrays with lightning fast JSON snapshots.
```

In this mode, the LSL HUD is only relied upon to provide Scene Object data since that cannot be parsed fully by the viewer UI as effectively.
"""

new_content = content.replace("Sensor data travels a separate path in both cases", hybrid_section + "\nSensor data travels a separate path in both cases")

with open('ARCHITECTURE.md', 'w') as f:
    f.write(new_content)
