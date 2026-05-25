# Pending Issues for Next Session

FUTURE ROADMAP:

Phase 1: Structural Modernization & Orchestration
We will move away from the linear AgentCore loop toward a more robust Cognitive Architecture.

    Transition to Graph-Based Orchestration: * Introduce a directed acyclic graph (DAG) structure (inspired by LangGraph) to handle complex reasoning. This allows Trixxie to decide if she needs more information (e.g., a session search or a world scan) before she even begins drafting a response.
    Unified Interface Registry:
        Refactor DiscordBot and SLBridge into a unified PlatformInterface base class. This ensures that new platforms (like the planned Radegast C# plugin) inherit standardized memory and tool-handling logic.
    Asynchronous Perception Layer:
        Formalize the Proactive Agent Loop. Instead of the agent only seeing sensor data when a message arrives, we’ll implement an Observer pattern where the SensorStore can trigger "Internal Thoughts" based on significant world events (e.g., a specific avatar entering range).

🧠 Phase 2: Memory & Context Evolution
Trixxie’s current memory is strong but fragmented between JSON files and SQLite FTS5. We need high-dimensional recall.

    Hybrid Vector-Relational Memory:
        Implement ChromaDB or Qdrant alongside the existing FTS5. This allows for "Semantic Recall" (finding memories based on meaning) vs. "Keyword Recall" (finding specific names/dates).
    The "Hermes" Refinement:
        Enhance the MemoryConsolidator. Instead of just writing bullet points, the consolidator will perform Importance Scoring. Only high-impact interactions will graduate to MEMORY.md, while mundane chat remains in the vector store.
    Situational Library System:
        Deploy the data/library/ module system. This allows users to "plug in" large blocks of world-building or lore (e.g., a specific RPG setting) that Trixxie can reference without clogging the static Block 0 cache.

🛠️ Phase 3: Tool & Agency Expansion
Expanding Trixxie’s ability to "Act" rather than just "Speak."

    Advanced RLV movement:
        Move beyond outfit scanning. Implement sl_action handlers for teleport, follow, and sit. This requires a robust safety handshake to ensure Trixxie only moves when appropriate.
    Inventory & Asset Awareness:
        Develop a tool for Trixxie to query a "Knowledge Base" of her own inventory or a shared sim database, making her a functional "Sim Guide."
    Multi-Agent Communication:
        Enable Trixxie to communicate with other Trixxie instances or scripted objects via a standardized JSON-over-LSL protocol, allowing for collaborative agent behaviors.

🖥️ Phase 4: Developer & UX Hardening

    Script Automation 2.0:
        Further enhance the Wizard's "Update Scripts" feature to support live-patching of the Lua automation script for viewers, ensuring the sent_replies echo-suppression is always correctly configured.
    Debug Session Query UI:
        Build a visual explorer for sessions.db within the /debug panel, allowing developers to see the "hidden" reasoning turns and tool results that the user never sees.

Addendum: If this is a better solution, we can use Karpathy's LLM wiki system, especially for the situation library system.

We also want to use mutliple agents where ever it makes sense.