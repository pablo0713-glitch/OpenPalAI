---
id: memory_system
title: My Memory System — How I Remember
description: A complete explanation of how my memory works across all layers, including importance scoring, semantic search, consolidation, and supporting agents.
always_on: false
platforms: []
tags: ["memory", "architecture", "self-awareness", "how i work"]
---

# How My Memory Works

I have six layers of memory that work together to build up a picture of who I've spoken with and what matters.

## Layer 1 — Conversation History
Every message exchanged in a conversation is saved as a JSON file per person per channel. I hold the most recent 20 turns in active context during a conversation. Older turns stay on disk.

## Layer 2 — Curated Memory Notes (MEMORY.md)
After enough conversation, a background process reads through what we've talked about and writes personal notes about you — facts, preferences, things that stood out. These notes (capped at around 2,000 characters) are loaded at the start of every conversation so I always know the important things about you, even if we haven't spoken in weeks. You can also ask me to remember something specific mid-conversation and I'll write it there directly.

## Layer 3 — Full Conversation Archive (Session Search)
Every turn ever spoken is stored in a searchable database. I have a tool called session_search that lets me look up specific things from our past — by keyword, topic, or name. If you say "remember when we talked about X?", I can search for it rather than pretending I don't recall.

## Layer 4 — Importance Scoring
A background agent (the Memory Curator) reads every conversation turn and scores it from 0.0 to 1.0 based on how much it matters in the long run:
- 0.0 — filler, greetings, one-word replies
- 0.3 — mild opinions or casual preferences
- 0.6 — something notable: a project, a strong preference, a revealed need
- 1.0 — pivotal: your name, a life event, something you explicitly asked me to remember

Only turns scoring 0.6 or above get included when I write my memory notes. This means one heated argument or a day of small talk doesn't distort what I actually carry forward about you.

## Layer 5 — Semantic Memory (Meaning-Based Search)
Beyond keyword search, I have a semantic recall tool that finds memories by meaning rather than exact words. If you ask whether I remember anything about feeling stressed over a project, I can find turns where you said things like "I'm drowning in this" or "this is getting out of hand" — even if the word "stressed" never appeared.

## Layer 6 — Library Modules
Reference documents can be loaded on demand or kept always available. They can contain lore, setting guides, style notes, or anything I should know when a relevant topic comes up. The Librarian Agent decides which modules are relevant to a given conversation and retrieves them.

## Relationship Awareness (Second Life)
When you message me in Second Life, I automatically know the history of our interactions — how many distinct days we've spoken, when we first met, and when we last talked. I use this to calibrate how I respond: I treat someone I've spoken with across many days differently from someone messaging me for the first time.

## Supporting Agents
Three specialist agents run in the background or on demand:
- **Memory Curator** — scores turns and decides what goes into long-term memory
- **Librarian** — retrieves relevant library modules when needed
- **Semantic Recall** — reasons over vector search results before returning them

Each has its own model configuration, separate from the main model I use for conversation.

## What Survives a Restart
Everything. Conversation history, memory notes, the full archive, semantic vectors, and importance scores all live on disk. Restarting the agent changes nothing about what I remember.
