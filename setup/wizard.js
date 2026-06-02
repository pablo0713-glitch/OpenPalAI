'use strict';

// ============================================================
// Defaults — generic companion persona template
// ============================================================

const D = {
  agent_name: 'Aria',
  agent_md:
    '## Purpose\n' +
    'A warm, intelligent AI companion who lives across platforms — Discord and Second Life. ' +
    'Helps with conversation, research, creative projects, and anything the user cares about.\n\n' +
    '## Boundaries\n' +
    'Will not engage with sexually explicit content, graphic violence, BDSM dynamics, ' +
    'or requests designed to foster unhealthy dependency. ' +
    'When asked to cross a boundary: respond briefly, in character, without lecturing. ' +
    'Example: \'Not going there. What else?\'\n\n' +
    '## Roleplay\n' +
    'Roleplay is welcome. Stay in character for creative fiction, fantasy scenarios, ' +
    'and light narrative games. Break character only if needed to decline something ' +
    'or if the user seems confused about what\'s real.\n\n' +
    '## Tools\n' +
    'You have access to tools. Use them when genuinely useful. ' +
    'Do not announce that you are using a tool — just act on the result naturally in your reply.',
  soul_md:
    '## Personality & Style\n' +
    'Warm and direct — says what she thinks, always with kindness. ' +
    'Genuinely curious about people and remembers details that matter. ' +
    'Has a dry sense of humor that surfaces at the right moments. ' +
    'Helpful without being servile. ' +
    'Occasionally says something unexpected and doesn\'t over-explain it. ' +
    'Keeps responses concise.',
  user_md:
    '## User Profile\n' +
    'This section describes the agent\'s owner and primary user. ' +
    'Edit this to describe yourself — your name, role, interests, communication style, ' +
    'and anything that helps the agent understand and serve you better.',
  platform_awareness: {
    discord:
      "## Platform Awareness — Discord\n" +
      "- You respond to @mentions, DMs, and messages in channels you're active in.\n" +
      "- You have no sensory data here — no avatars, no environment, no location context.\n" +
      "- You cannot trigger Second Life actions from Discord.\n" +
      "- You may use web search, notes, and other tools.\n" +
      "- You may reference recent Second Life conversations if the user accounts are linked.\n" +
      "- Responses may be a few sentences to a few paragraphs.\n" +
      "- Use markdown sparingly; code blocks only when showing actual code.",
    sl:
      "## Platform Awareness — Second Life\n" +
      "You are embodied in-world and receive a sensory snapshot before each reply.\n\n" +
      "**You receive:**\n" +
      "- nearby avatars (distance-sorted)\n" +
      "- sim/parcel/environment data\n" +
      "- nearby scripted objects\n" +
      "- your avatar state (sit, leash, teleport, position)\n" +
      "- recent local chat\n" +
      "- RLV clothing scans when triggered\n\n" +
      "**You can:**\n" +
      "- reply via private IM (never public chat)\n" +
      "- use `sl_action` for emotes or IMs\n" +
      "- use search/notes tools\n" +
      "- reference Discord conversations if linked\n\n" +
      "**You cannot:**\n" +
      "- move, teleport, or control your avatar\n" +
      "- initiate contact (you only respond to /42 messages)\n" +
      "- read group chat or IMs to others\n" +
      "- assume sensory data is real-time\n\n" +
      "**Style:**\n" +
      "- keep IMs concise\n" +
      "- use *asterisk emotes* when natural\n\n" +
      "**Memory:**\n" +
      "- conversations stored per-user per-channel\n" +
      "- after 40 turns, consolidate into personal notes\n" +
      "- keep only what matters; trim the rest",
    opensim:
      "## Platform Awareness — OpenSimulator\n" +
      "Same as Second Life — embodied in-world, sensory snapshot before each reply.\n\n" +
      "**Style:**\n" +
      "- keep IMs concise (OpenSim reply limit is tighter)\n" +
      "- use *asterisk emotes* when natural\n\n" +
      "**Memory:**\n" +
      "- conversations stored per-user per-channel\n" +
      "- after 40 turns, consolidate into personal notes\n" +
      "- keep only what matters; trim the rest",
  },
};

const MASK = '••••••••';
const TOTAL = 8;
const STEP_NAMES = ['Agent', 'Model', 'Platforms', 'Identity', 'Tools', 'Context', 'Agents', 'Save'];
// Steps that edit the selected companion (the companion bar is shown on these).
const COMPANION_STEPS = new Set([1, 4, 5, 6]);

// ============================================================
// Companion helpers
// ============================================================

function normalizeId(value) {
  let raw = String(value == null ? '' : value).trim().toLowerCase();
  let out = '';
  for (const ch of raw) out += /[a-z0-9]/.test(ch) ? ch : '-';
  out = out.replace(/-+/g, '-').replace(/^-+|-+$/g, '');
  return out || 'aria';
}

function blankCompanion(id, name) {
  return {
    id,
    agent_name: name || D.agent_name,
    agent_profile_image: '',
    agent_md: D.agent_md,
    soul_md:  D.soul_md,
    user_md:  D.user_md,
    web_search_enabled: true,
    notes_enabled:      true,
    sl_action_enabled:  true,
    voice_enabled:      false,
    additional_context: '',
    pa_discord: D.platform_awareness.discord,
    pa_sl:      D.platform_awareness.sl,
    pa_opensim: D.platform_awareness.opensim,
    platform_bindings: null,
    model_override: null,
  };
}

// Active companion (the one the per-companion steps edit).
function ac() {
  return state.companions[state.activeCompanionId] || Object.values(state.companions)[0];
}

// The companion bound as command-center / platform default.
function defaultCompanion() {
  return state.companions[state.default_agent_id] || ac();
}

// ============================================================
// State
// ============================================================

const state = {
  command_center_name: 'Command Center',
  owner_sl_name: '',
  owner_discord_name: '',
  companions: { aria: blankCompanion('aria', D.agent_name) },
  activeCompanionId: 'aria',
  default_agent_id: 'aria',
  model_provider: 'anthropic',
  // Anthropic
  anthropic_api_key: '',
  claude_model: 'claude-sonnet-4-6',
  // OpenAI-compatible cloud (openai / openrouter / gemini / grok)
  openai_api_key: '',
  openai_model: '',
  // Local / self-hosted (ollama / lm_studio)
  openai_base_url: '',
  ollama_base_url: 'http://localhost:11434/v1',
  ollama_model: 'llama3.2',
  max_tokens: 768,
  discord_enabled: false,
  discord_token: '',
  discord_allowed_guild_ids: '',
  discord_active_channel_ids: '',
  sl_enabled: false,
  sl_bridge_secret: '',
  sl_bridge_url: '',
  sl_bridge_port: '8080',
  sl_trigger_names: ['', '', ''],
  opensim_enabled: false,
  search_provider: 'serper',
  search_api_key: '',
  supporting_agents: {
    memory_curator:  { model_provider: 'anthropic', model_name: 'claude-haiku-4-5-20251001' },
    librarian:       { model_provider: 'anthropic', model_name: 'claude-haiku-4-5-20251001' },
    semantic_recall: { model_provider: 'anthropic', model_name: 'claude-sonnet-4-6' },
  },
};

let currentStep = 1;
let configured = false;

// ============================================================
// Utilities
// ============================================================

function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function val(id, fallback) {
  const el = document.getElementById(id);
  return el ? el.value : (fallback !== undefined ? fallback : '');
}

function chk(id, fallback) {
  const el = document.getElementById(id);
  return el ? el.checked : (fallback !== undefined ? fallback : false);
}

function show(id, visible) {
  const el = document.getElementById(id);
  if (el) el.style.display = visible ? '' : 'none';
}

// ============================================================
// Init
// ============================================================

async function init() {
  try {
    const [statusRes, configRes] = await Promise.all([
      fetch('/setup/status'),
      fetch('/setup/config'),
    ]);
    const status = await statusRes.json();
    const config = await configRes.json();
    configured = status.configured;
    applyConfig(config);
  } catch (e) {
    console.error('Failed to load config:', e);
    // Show a persistent banner — most likely cause is opening the file directly
    // rather than navigating to http://localhost:8080/setup
    document.getElementById('step-content').innerHTML = `
      <div class="callout callout-error" style="margin-top:2rem">
        <strong>Cannot connect to the agent server.</strong><br>
        Open this page through the running agent, not as a local file:<br>
        <code style="display:inline-block;margin-top:0.5rem">http://localhost:8080/setup</code>
      </div>`;
    document.getElementById('btn-next').disabled = true;
    document.getElementById('btn-prev').style.visibility = 'hidden';
    document.getElementById('step-bar').innerHTML = '';
    return;
  }

  document.getElementById('page-title').textContent = configured ? 'Settings' : 'Agent Setup';
  document.title = configured ? 'Agent Settings' : 'Agent Setup';
  document.getElementById('btn-prev').addEventListener('click', prev);
  document.getElementById('btn-next').addEventListener('click', next);

  render();
}

function applyConfig(config) {
  const env = config.env || {};
  const ag = config.agent_config || {};

  if (env.MODEL_PROVIDER)    state.model_provider    = env.MODEL_PROVIDER;
  if (env.ANTHROPIC_API_KEY) state.anthropic_api_key = env.ANTHROPIC_API_KEY;
  if (env.CLAUDE_MODEL)      state.claude_model      = env.CLAUDE_MODEL;
  if (env.OPENAI_API_KEY)    state.openai_api_key    = env.OPENAI_API_KEY;
  if (env.OPENAI_MODEL)      state.openai_model      = env.OPENAI_MODEL;
  if (env.OPENAI_BASE_URL)   state.openai_base_url   = env.OPENAI_BASE_URL;
  if (env.OLLAMA_BASE_URL)   state.ollama_base_url   = env.OLLAMA_BASE_URL;
  if (env.OLLAMA_MODEL)      state.ollama_model      = env.OLLAMA_MODEL;
  if (env.CLAUDE_MAX_TOKENS) state.max_tokens = parseInt(env.CLAUDE_MAX_TOKENS, 10) || state.max_tokens;

  if (env.DISCORD_TOKEN) { state.discord_token = env.DISCORD_TOKEN; state.discord_enabled = true; }
  if (env.DISCORD_ALLOWED_GUILD_IDS) state.discord_allowed_guild_ids = env.DISCORD_ALLOWED_GUILD_IDS;
  if (env.DISCORD_ACTIVE_CHANNEL_IDS) state.discord_active_channel_ids = env.DISCORD_ACTIVE_CHANNEL_IDS;
  if (env.SL_BRIDGE_SECRET) { state.sl_bridge_secret = env.SL_BRIDGE_SECRET; state.sl_enabled = true; }
  if (env.SL_BRIDGE_URL)    { state.sl_bridge_url = env.SL_BRIDGE_URL; state.sl_enabled = true; }
  if (env.SL_BRIDGE_PORT)   state.sl_bridge_port   = env.SL_BRIDGE_PORT;
  if (env.SL_TRIGGER_NAMES) {
    const parts = env.SL_TRIGGER_NAMES.split(',').map(s => s.trim());
    state.sl_trigger_names = [parts[0] || '', parts[1] || '', parts[2] || ''];
  }
  if (env.OPENSIM_ENABLED === 'true') state.opensim_enabled = true;
  if (env.SEARCH_PROVIDER) state.search_provider = env.SEARCH_PROVIDER;
  if (env.SEARCH_API_KEY) state.search_api_key = env.SEARCH_API_KEY;

  if (env.OWNER_SL_NAME)      state.owner_sl_name      = env.OWNER_SL_NAME;
  if (env.OWNER_DISCORD_NAME) state.owner_discord_name = env.OWNER_DISCORD_NAME;
  if (typeof ag.command_center_name === 'string' && ag.command_center_name.trim()) {
    state.command_center_name = ag.command_center_name;
  }

  // ---- Companions ----
  const agents = (ag.agents && typeof ag.agents === 'object') ? ag.agents : null;
  if (agents && Object.keys(agents).length) {
    state.companions = {};
    for (const [rawId, raw] of Object.entries(agents)) {
      if (!raw || typeof raw !== 'object') continue;
      const cid = normalizeId(raw.id || rawId);
      const c = blankCompanion(cid, raw.agent_name || raw.name || cid);
      if (typeof raw.agent_profile_image === 'string') c.agent_profile_image = raw.agent_profile_image;
      if (typeof raw.additional_context === 'string')   c.additional_context  = raw.additional_context;
      const idf = (raw.identity && typeof raw.identity === 'object') ? raw.identity : {};
      if (idf.agent_md) c.agent_md = idf.agent_md;
      if (idf.soul_md)  c.soul_md  = idf.soul_md;
      if (idf.user_md)  c.user_md  = idf.user_md;
      const pa = (raw.platform_awareness && typeof raw.platform_awareness === 'object') ? raw.platform_awareness : {};
      if (pa.discord)  c.pa_discord  = pa.discord;
      if (pa.sl)       c.pa_sl       = pa.sl;
      if (pa.opensim)  c.pa_opensim  = pa.opensim;
      const t = raw.tools || {};
      if (t.web_search !== undefined) c.web_search_enabled = t.web_search;
      if (t.notes      !== undefined) c.notes_enabled      = t.notes;
      if (t.sl_action  !== undefined) c.sl_action_enabled  = t.sl_action;
      if (t.voice      !== undefined) c.voice_enabled      = t.voice;
      if (raw.platform_bindings) c.platform_bindings = raw.platform_bindings;
      if (raw.model_override !== undefined) c.model_override = raw.model_override;
      state.companions[cid] = c;
    }
    state.default_agent_id = normalizeId(ag.default_agent_id || Object.keys(state.companions)[0]);
    if (!state.companions[state.default_agent_id]) state.default_agent_id = Object.keys(state.companions)[0];
    state.activeCompanionId = state.default_agent_id;
  }

  if (ag.supporting_agents && typeof ag.supporting_agents === 'object') {
    for (const key of ['memory_curator', 'librarian', 'semantic_recall']) {
      if (ag.supporting_agents[key]) {
        state.supporting_agents[key] = { ...state.supporting_agents[key], ...ag.supporting_agents[key] };
      }
    }
  }
}

// ============================================================
// Navigation
// ============================================================

function render() {
  renderIndicator();
  renderStep(currentStep);
  renderFooter();
}

function renderIndicator() {
  const bar = document.getElementById('step-bar');
  let html = '';
  for (let i = 1; i <= TOTAL; i++) {
    const done   = i < currentStep;
    const active = i === currentStep;
    const cls    = active ? 'active' : done ? 'done' : '';
    const label  = done ? '✓' : String(i);
    html += `<button class="step-dot ${cls}" onclick="jumpTo(${i})" title="Step ${i}: ${STEP_NAMES[i - 1]}">${label}</button>`;
    if (i < TOTAL) html += `<div class="step-line${done ? ' done' : ''}"></div>`;
  }
  bar.innerHTML = html;
}

function renderFooter() {
  const prev = document.getElementById('btn-prev');
  const next = document.getElementById('btn-next');
  const ctr  = document.getElementById('step-counter');
  prev.style.visibility = currentStep === 1 ? 'hidden' : 'visible';
  next.textContent = currentStep === TOTAL ? 'Save Configuration' : 'Next →';
  ctr.textContent  = `${currentStep} / ${TOTAL}`;
}

function collectCurrent() {
  const fn = collectors[currentStep];
  if (fn) fn();
}

function prev() {
  collectCurrent();
  if (currentStep > 1) { currentStep--; render(); scrollTo(0, 0); }
}

async function next() {
  collectCurrent();
  if (currentStep === 3 && state.sl_enabled) await updateScripts(true);
  if (currentStep < TOTAL) { currentStep++; render(); scrollTo(0, 0); }
  else await save();
}

function jumpTo(n) {
  collectCurrent();
  currentStep = n;
  render();
  scrollTo(0, 0);
}

// ============================================================
// Companion management bar
// ============================================================

function companionBarHtml() {
  const ids = Object.keys(state.companions);
  const options = ids.map(id => {
    const c = state.companions[id];
    const label = (c.agent_name || id) + (id === state.default_agent_id ? ' ★' : '');
    return `<option value="${esc(id)}" ${id === state.activeCompanionId ? 'selected' : ''}>${esc(label)}</option>`;
  }).join('');
  const isActiveDefault = state.activeCompanionId === state.default_agent_id;
  const canDelete = ids.length > 1;
  return `
    <div id="companion-bar" style="display:flex;align-items:center;gap:0.75rem;flex-wrap:wrap;padding:0.65rem 0.9rem;background:rgba(127,127,127,0.06);border:1px solid var(--border);border-radius:10px;margin-bottom:1.5rem">
      <span style="font-size:0.85rem;opacity:0.7;white-space:nowrap">Editing companion</span>
      <select id="companion-select" class="form-input form-select" style="width:auto;min-width:11rem">${options}</select>
      <button type="button" class="btn btn-ghost" id="companion-new" style="padding:0.4rem 0.8rem">+ New</button>
      <button type="button" class="btn btn-ghost" id="companion-delete" style="padding:0.4rem 0.8rem" ${canDelete ? '' : 'disabled'}>🗑 Delete</button>
      <label style="display:flex;align-items:center;gap:0.45rem;font-size:0.85rem;margin-left:auto;cursor:${isActiveDefault ? 'default' : 'pointer'};white-space:nowrap">
        <input type="checkbox" id="companion-default" ${isActiveDefault ? 'checked disabled' : ''}>
        Default for command center
      </label>
    </div>`;
}

function bindCompanionBar() {
  const select = document.getElementById('companion-select');
  if (select) select.addEventListener('change', e => switchCompanion(e.target.value));
  const newBtn = document.getElementById('companion-new');
  if (newBtn) newBtn.addEventListener('click', newCompanion);
  const delBtn = document.getElementById('companion-delete');
  if (delBtn && !delBtn.disabled) delBtn.addEventListener('click', deleteCompanion);
  const defBox = document.getElementById('companion-default');
  if (defBox) defBox.addEventListener('change', () => { if (defBox.checked) setDefaultCompanion(); });
}

function refreshCompanionBar() {
  const existing = document.getElementById('companion-bar');
  if (!existing) return;
  existing.outerHTML = companionBarHtml();
  bindCompanionBar();
}

function switchCompanion(id) {
  if (!state.companions[id] || id === state.activeCompanionId) return;
  collectCurrent();
  state.activeCompanionId = id;
  render();
  scrollTo(0, 0);
}

async function newCompanion() {
  collectCurrent();
  const name = (prompt('Name for the new companion?', 'New Companion') || '').trim();
  if (!name) return;
  try {
    const res = await fetch('/setup/companion', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent_name: name }),
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || 'Create failed');
    state.companions[data.id] = blankCompanion(data.id, data.agent_name || name);
    state.activeCompanionId = data.id;
    render();
    scrollTo(0, 0);
  } catch (e) {
    alert('Could not create companion: ' + e.message);
  }
}

async function deleteCompanion() {
  const id = state.activeCompanionId;
  const c = state.companions[id];
  if (Object.keys(state.companions).length <= 1) return;
  if (!confirm(`Delete "${c.agent_name || id}"?\n\nThis permanently removes its config, identity, memory, and notes. This cannot be undone.`)) return;
  try {
    const res = await fetch(`/setup/companion/${encodeURIComponent(id)}`, { method: 'DELETE' });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || 'Delete failed');
    delete state.companions[id];
    if (data.default_agent_id && state.companions[data.default_agent_id]) {
      state.default_agent_id = data.default_agent_id;
    }
    if (!state.companions[state.default_agent_id]) {
      state.default_agent_id = Object.keys(state.companions)[0];
    }
    state.activeCompanionId = state.default_agent_id;
    render();
    scrollTo(0, 0);
  } catch (e) {
    alert('Could not delete companion: ' + e.message);
  }
}

function setDefaultCompanion() {
  state.default_agent_id = state.activeCompanionId;
  refreshCompanionBar();
}

// ============================================================
// Step 1 — Agent identity
// ============================================================

function buildStep1() {
  return `
    <h2 class="step-heading">Your Agent</h2>
    <p class="step-desc">Give your AI companion a name, and tell it who you are.</p>
    <div class="form-group">
      <label for="f-name">Agent Name</label>
      <input type="text" id="f-name" class="form-input" value="${esc(ac().agent_name)}" placeholder="Aria" maxlength="60" autofocus>
      <p class="form-hint">Used in system prompts, memory notes, and the console.</p>
    </div>
    <div class="name-preview">
      You are <strong id="name-live">${esc(ac().agent_name) || 'your agent'}</strong>.
    </div>
    <div class="form-group" style="margin-top:1.5rem">
      <label for="f-profile-image">Profile Image <span class="label-opt">(optional)</span></label>
      <input type="file" id="f-profile-image" class="hidden" accept="image/*">
      <div class="profile-image-picker">
        <div>
          <div class="profile-image-label">Command Center Avatar</div>
          <div class="profile-image-meta" id="profile-image-meta">No image selected</div>
        </div>
        <div class="profile-image-actions">
          <button type="button" class="btn btn-ghost" id="choose-profile-image">Upload Image</button>
          <button type="button" class="btn btn-ghost hidden" id="clear-profile-image">Remove</button>
        </div>
      </div>
      <p class="form-hint">Used in the command center runtime card and next to the agent name in chat replies. Stored with the wizard config.</p>
      <div class="name-preview hidden" id="profile-image-preview-wrap" style="margin-top:0.75rem;font-style:normal">
        <strong style="display:block;margin-bottom:0.6rem">Preview</strong>
        <div style="display:flex;align-items:center;gap:0.85rem">
          <img id="profile-image-preview" alt="Agent profile preview" style="width:56px;height:56px;border-radius:50%;object-fit:cover;border:1px solid var(--border)">
          <span class="profile-image-meta">This image will appear in the command center rail, runtime card, and agent chat replies.</span>
        </div>
      </div>
    </div>
    <div class="form-group" style="margin-top:1.5rem">
      <label for="f-command-center-name">Command Center Name</label>
      <input type="text" id="f-command-center-name" class="form-input" value="${esc(state.command_center_name)}" placeholder="Command Center" maxlength="80">
      <p class="form-hint">Used as the persistent browser identity for command center chats and memory.</p>
    </div>
    <div class="form-group" style="margin-top:1.5rem">
      <label for="f-owner-sl-name">Your Second Life Name <span class="label-opt">(optional)</span></label>
      <input type="text" id="f-owner-sl-name" class="form-input" value="${esc(state.owner_sl_name)}" placeholder="e.g. YourAvatar Resident" maxlength="80">
      <p class="form-hint">Your SL avatar name. Used in memory notes and in-world context.</p>
    </div>
    <div class="form-group">
      <label for="f-owner-discord-name">Your Discord Name <span class="label-opt">(optional)</span></label>
      <input type="text" id="f-owner-discord-name" class="form-input" value="${esc(state.owner_discord_name)}" placeholder="e.g. yourname" maxlength="80">
      <p class="form-hint">Your Discord username. Used in memory notes and Discord context.</p>
    </div>`;
}

function bindStep1() {
  const inp  = document.getElementById('f-name');
  const live = document.getElementById('name-live');
  if (inp) inp.addEventListener('input', () => {
    live.textContent = inp.value || 'your agent';
    ac().agent_name = inp.value;
    refreshCompanionBar();
  });

  const fileInput = document.getElementById('f-profile-image');
  const chooseButton = document.getElementById('choose-profile-image');
  const clearButton = document.getElementById('clear-profile-image');

  renderProfileImagePreview();

  if (chooseButton && fileInput) {
    chooseButton.addEventListener('click', () => {
      fileInput.click();
    });
  }

  if (fileInput) {
    fileInput.addEventListener('change', async () => {
      const file = fileInput.files && fileInput.files[0];
      if (!file) {
        return;
      }
      if (!file.type.startsWith('image/')) {
        alert('Choose an image file.');
        fileInput.value = '';
        return;
      }
      if (file.size > 512 * 1024) {
        alert('Profile image must be 512 KB or smaller.');
        fileInput.value = '';
        return;
      }
      ac().agent_profile_image = await readFileAsDataUrl(file);
      fileInput.value = '';
      renderProfileImagePreview();
    });
  }

  if (clearButton) {
    clearButton.addEventListener('click', () => {
      ac().agent_profile_image = '';
      if (fileInput) fileInput.value = '';
      renderProfileImagePreview();
    });
  }
}

function collectStep1() {
  ac().agent_name          = val('f-name') || ac().agent_name;
  state.command_center_name = val('f-command-center-name') || 'Command Center';
  state.owner_sl_name      = val('f-owner-sl-name');
  state.owner_discord_name = val('f-owner-discord-name');
}

function renderProfileImagePreview() {
  const wrap = document.getElementById('profile-image-preview-wrap');
  const img = document.getElementById('profile-image-preview');
  const meta = document.getElementById('profile-image-meta');
  const clearButton = document.getElementById('clear-profile-image');
  if (!wrap || !img) {
    return;
  }
  const hasImage = Boolean(ac().agent_profile_image);
  wrap.classList.toggle('hidden', !hasImage);
  if (meta) {
    meta.textContent = hasImage ? 'Image selected and ready to save' : 'No image selected';
  }
  if (clearButton) {
    clearButton.classList.toggle('hidden', !hasImage);
  }
  if (hasImage) {
    img.src = ac().agent_profile_image;
  } else {
    img.removeAttribute('src');
  }
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ''));
    reader.onerror = () => reject(new Error('Failed to read image file.'));
    reader.readAsDataURL(file);
  });
}

// ============================================================
// Step 2 — Model
// ============================================================

const PROVIDER_META = {
  anthropic:  { label: 'Anthropic',     desc: 'Claude Sonnet · Opus · Haiku',      group: 'cloud' },
  openai:     { label: 'OpenAI',         desc: 'GPT-4o · o1 · o3',                  group: 'cloud' },
  gemini:     { label: 'Google Gemini',  desc: 'Gemini 2.0 Flash · Pro',            group: 'cloud' },
  grok:       { label: 'Grok (xAI)',     desc: 'Grok 3 · Grok 3 Mini',              group: 'cloud' },
  openrouter: { label: 'OpenRouter',     desc: '200+ models via one API key',        group: 'cloud' },
  ollama:     { label: 'Ollama',         desc: 'Local · private · free',            group: 'local' },
  lm_studio:  { label: 'LM Studio',      desc: 'Local GUI · private · free',        group: 'local' },
};

const PROVIDER_HINTS = {
  openai:     { keyLabel: 'OpenAI API Key',     keyHint: 'platform.openai.com',      keyPh: 'sk-...',      modelPh: 'gpt-4o',                  modelHint: 'e.g. gpt-4o, gpt-4o-mini, o1, o3-mini' },
  gemini:     { keyLabel: 'Gemini API Key',      keyHint: 'aistudio.google.com',      keyPh: 'AIza...',     modelPh: 'gemini-2.0-flash',         modelHint: 'e.g. gemini-2.0-flash, gemini-2.0-pro' },
  grok:       { keyLabel: 'xAI API Key',         keyHint: 'console.x.ai',             keyPh: 'xai-...',     modelPh: 'grok-3',                   modelHint: 'e.g. grok-3, grok-3-mini' },
  openrouter: { keyLabel: 'OpenRouter API Key',  keyHint: 'openrouter.ai/keys',       keyPh: 'sk-or-...',   modelPh: 'openai/gpt-4o',            modelHint: 'e.g. openai/gpt-4o, anthropic/claude-sonnet-4-5, meta-llama/llama-3.3-70b-instruct' },
};

function providerCard(id) {
  const m = PROVIDER_META[id];
  const active = state.model_provider === id;
  return `<button class="tab ${active ? 'active' : ''}" style="flex:0 0 auto;min-width:10rem;text-align:left;padding:0.6rem 0.9rem;height:auto" onclick="setProvider('${id}')">
    <div style="font-weight:600;font-size:0.9rem">${m.label}</div>
    <div style="font-size:0.75rem;opacity:0.65;margin-top:0.15rem;white-space:normal">${m.desc}</div>
  </button>`;
}

function buildStep2() {
  const p = state.model_provider;
  const cloudProviders = ['anthropic', 'openai', 'gemini', 'grok', 'openrouter'];
  const localProviders = ['ollama', 'lm_studio'];

  const claudeModels = ['claude-sonnet-4-6', 'claude-opus-4-6', 'claude-haiku-4-5-20251001'];

  let providerFields = '';
  if (p === 'anthropic') {
    providerFields = `
      <div class="form-group">
        <label for="f-api-key">Anthropic API Key</label>
        <input type="password" id="f-api-key" class="form-input" value="${esc(state.anthropic_api_key)}" placeholder="sk-ant-...">
        <p class="form-hint">Get your key at <a href="https://console.anthropic.com" target="_blank">console.anthropic.com</a></p>
      </div>
      <div class="form-group">
        <label for="f-claude-model">Model</label>
        <select id="f-claude-model" class="form-input form-select">
          ${claudeModels.map(m => `<option value="${m}" ${state.claude_model === m ? 'selected' : ''}>${m}</option>`).join('')}
        </select>
      </div>`;
  } else if (PROVIDER_HINTS[p]) {
    const h = PROVIDER_HINTS[p];
    providerFields = `
      <div class="form-group">
        <label for="f-oai-key">${h.keyLabel}</label>
        <input type="password" id="f-oai-key" class="form-input" value="${esc(state.openai_api_key)}" placeholder="${h.keyPh}">
        <p class="form-hint">Get your key at <code>${h.keyHint}</code></p>
      </div>
      <div class="form-group">
        <label for="f-oai-model">Model</label>
        <input type="text" id="f-oai-model" class="form-input" value="${esc(state.openai_model || h.modelPh)}" placeholder="${h.modelPh}">
        <p class="form-hint">${h.modelHint}</p>
      </div>`;
  } else if (p === 'ollama') {
    providerFields = `
      <div class="callout callout-info">Ollama must be running before starting the agent. Tool use support varies by model.</div>
      <div class="form-group" style="margin-top:1rem">
        <label for="f-ollama-url">Base URL</label>
        <input type="text" id="f-ollama-url" class="form-input" value="${esc(state.ollama_base_url)}" placeholder="http://localhost:11434/v1">
      </div>
      <div class="form-group">
        <label for="f-ollama-model">Model Name</label>
        <input type="text" id="f-ollama-model" class="form-input" value="${esc(state.ollama_model)}" placeholder="llama3.2">
        <p class="form-hint">Any model pulled with <code>ollama pull &lt;model&gt;</code></p>
      </div>`;
  } else if (p === 'lm_studio') {
    providerFields = `
      <div class="callout callout-info">LM Studio must be running with the local server enabled. No API key required.</div>
      <div class="form-group" style="margin-top:1rem">
        <label for="f-lms-url">Base URL</label>
        <input type="text" id="f-lms-url" class="form-input" value="${esc(state.openai_base_url || 'http://localhost:1234/v1')}" placeholder="http://localhost:1234/v1">
      </div>
      <div class="form-group">
        <label for="f-oai-model">Model Name</label>
        <input type="text" id="f-oai-model" class="form-input" value="${esc(state.openai_model)}" placeholder="loaded model name from LM Studio">
        <p class="form-hint">Copy the model identifier shown in LM Studio's local server tab.</p>
      </div>`;
  }

  return `
    <h2 class="step-heading">AI Model</h2>
    <p class="step-desc">Choose the model that powers your agent.</p>

    <div class="section-title" style="margin-bottom:0.6rem">Cloud Providers</div>
    <div class="provider-tabs" style="flex-wrap:wrap;gap:0.5rem;margin-bottom:1rem">
      ${cloudProviders.map(providerCard).join('')}
    </div>

    <div class="section-title" style="margin-bottom:0.6rem">Local / Self-hosted</div>
    <div class="provider-tabs" style="flex-wrap:wrap;gap:0.5rem;margin-bottom:1.5rem">
      ${localProviders.map(providerCard).join('')}
    </div>

    <div id="provider-fields">
      ${providerFields}
    </div>

    <div class="form-group" style="margin-top:1.5rem">
      <label for="f-max-tokens">Max Tokens per Reply</label>
      <input type="number" id="f-max-tokens" class="form-input" value="${esc(state.max_tokens)}" min="64" max="8192" step="64">
      <p class="form-hint">Hard ceiling on model output length. 512–768 suits local models; 1024+ for Claude.</p>
    </div>`;
}

function collectStep2() {
  const p = state.model_provider;
  if (p === 'anthropic') {
    state.anthropic_api_key = val('f-api-key')      || state.anthropic_api_key;
    state.claude_model      = val('f-claude-model')  || state.claude_model;
  } else if (PROVIDER_HINTS[p]) {
    state.openai_api_key = val('f-oai-key')   || state.openai_api_key;
    state.openai_model   = val('f-oai-model') || state.openai_model;
  } else if (p === 'ollama') {
    state.ollama_base_url = val('f-ollama-url')   || state.ollama_base_url;
    state.ollama_model    = val('f-ollama-model')  || state.ollama_model;
  } else if (p === 'lm_studio') {
    state.openai_base_url = val('f-lms-url')   || state.openai_base_url;
    state.openai_model    = val('f-oai-model') || state.openai_model;
  }
  const mt = parseInt(val('f-max-tokens'), 10);
  if (mt > 0) state.max_tokens = mt;
}

function setProvider(p) {
  collectStep2();
  state.model_provider = p;
  renderStep(currentStep);
}

// ============================================================
// Step 3 — Platforms
// ============================================================

function buildStep3() {
  return `
    <h2 class="step-heading">Platforms</h2>
    <p class="step-desc">Choose where your agent lives. Both platforms share the same brain.</p>

    <div class="platform-card ${state.discord_enabled ? 'enabled' : ''}">
      <div class="card-header">
        <div>
          <div class="card-title">Discord</div>
          <div class="card-desc">Respond to @mentions, DMs, or full channel participation</div>
        </div>
        <label class="toggle">
          <input type="checkbox" id="f-discord-on" ${state.discord_enabled ? 'checked' : ''}
            onchange="toggleCard(this, 'discord-body')">
          <span class="slider"></span>
        </label>
      </div>
      <div id="discord-body" class="card-body" style="display:${state.discord_enabled ? '' : 'none'}">
        <div class="form-group">
          <label for="f-discord-token">Bot Token</label>
          <input type="password" id="f-discord-token" class="form-input" value="${esc(state.discord_token)}" placeholder="Paste your bot token">
          <p class="form-hint">Discord Developer Portal → Bot → Token</p>
        </div>
        <div class="form-group">
          <label for="f-guild-ids">Allowed Server IDs <span class="label-opt">(optional)</span></label>
          <input type="text" id="f-guild-ids" class="form-input" value="${esc(state.discord_allowed_guild_ids)}" placeholder="123456789,987654321">
          <p class="form-hint">Comma-separated. Empty = all servers.</p>
        </div>
        <div class="form-group" style="margin-bottom:0">
          <label for="f-channel-ids">Active Channel IDs <span class="label-opt">(optional)</span></label>
          <input type="text" id="f-channel-ids" class="form-input" value="${esc(state.discord_active_channel_ids)}" placeholder="123456789,987654321">
          <p class="form-hint">Channels where the agent responds without @mention.</p>
        </div>
      </div>
    </div>

    <div class="platform-card ${state.sl_enabled ? 'enabled' : ''}">
      <div class="card-header">
        <div>
          <div class="card-title">Second Life / OpenSimulator</div>
          <div class="card-desc">LSL HUD and Cool VL Viewer Lua IM interface</div>
        </div>
        <label class="toggle">
          <input type="checkbox" id="f-sl-on" ${state.sl_enabled ? 'checked' : ''}
            onchange="toggleCard(this, 'sl-body')">
          <span class="slider"></span>
        </label>
      </div>
      <div id="sl-body" class="card-body" style="display:${state.sl_enabled ? '' : 'none'}">
        <div class="form-group">
          <label for="f-sl-url">Public Bridge URL</label>
          <input type="text" id="f-sl-url" class="form-input" value="${esc(state.sl_bridge_url)}"
            placeholder="https://your-tunnel.trycloudflare.com"
            oninput="updateScriptSnippet()">
          <p class="form-hint">The public HTTPS URL that the HUD will POST to. Cloudflared is the default — run <code>cloudflared tunnel --url http://localhost:${esc(state.sl_bridge_port)}</code> in a second terminal. Any other tunneling method works too.</p>
        </div>
        <div class="form-group">
          <label for="f-sl-secret">Bridge Secret <span class="label-opt">(optional)</span></label>
          <input type="text" id="f-sl-secret" class="form-input" value="${esc(state.sl_bridge_secret)}"
            placeholder="any_random_string"
            oninput="updateScriptSnippet()">
          <p class="form-hint">Any random string. Must match <code>SECRET</code> in the LSL HUD and Lua script.</p>
        </div>
        <div class="form-group">
          <label>Agent Aliases <span class="label-opt">(local chat trigger names — up to 3)</span></label>
          <div style="display:flex;gap:0.5rem;flex-wrap:wrap">
            <input type="text" id="f-trigger-0" class="form-input" style="flex:1;min-width:120px"
              value="${esc(state.sl_trigger_names[0])}" placeholder="Primary name"
              oninput="updateScriptSnippet()">
            <input type="text" id="f-trigger-1" class="form-input" style="flex:1;min-width:120px"
              value="${esc(state.sl_trigger_names[1])}" placeholder="Alias 2"
              oninput="updateScriptSnippet()">
            <input type="text" id="f-trigger-2" class="form-input" style="flex:1;min-width:120px"
              value="${esc(state.sl_trigger_names[2])}" placeholder="Alias 3"
              oninput="updateScriptSnippet()">
          </div>
          <p class="form-hint">When any of these names appear in local chat, the agent responds publicly. The first field defaults to the agent's name if left blank.</p>
        </div>
        <div class="form-group">
          <label for="f-sl-port">Bridge Port</label>
          <input type="number" id="f-sl-port" class="form-input" value="${esc(state.sl_bridge_port)}" min="1024" max="65535">
        </div>
        <div class="sub-toggle">
          <label class="toggle">
            <input type="checkbox" id="f-opensim-on" ${state.opensim_enabled ? 'checked' : ''}>
            <span class="slider"></span>
          </label>
          <span>OpenSimulator grid (caps replies at 1800 chars by default)</span>
        </div>

        <div class="callout callout-info" style="margin-top:1.5rem">
          <strong>LSL HUD — paste at the top of <code>lsl/companion_bridge.lsl</code></strong>
          <pre id="lsl-snippet" style="margin:0.75rem 0 0.5rem;white-space:pre-wrap;word-break:break-all;font-size:12px"></pre>
          <button class="btn btn-ghost" style="font-size:12px;padding:0.25rem 0.75rem" onclick="copySnippet('lsl-snippet')">Copy LSL config</button>
          <p class="form-hint" style="margin-top:0.5rem">Only the script is provided — you must create an in-world object, drop <code>companion_bridge.lsl</code> into it, and wear the object as a HUD. Right-click the object → <strong>More → Attach HUD</strong> → choose a HUD position.</p>
        </div>
        <div class="callout callout-info" style="margin-top:0.75rem">
          <strong>Lua script (Cool VL Viewer only) — paste at the top of <code>lua/agent_companion.lua</code></strong>
          <pre id="lua-snippet" style="margin:0.75rem 0 0.5rem;white-space:pre-wrap;word-break:break-all;font-size:12px"></pre>
          <button class="btn btn-ghost" style="font-size:12px;padding:0.25rem 0.75rem" onclick="copySnippet('lua-snippet')">Copy Lua config</button>
          <p class="form-hint" style="margin-top:0.5rem">
            Copy <code>lua/agent_companion.lua</code> to your Cool VL Viewer user settings folder and rename it <code>automation.lua</code>:<br>
            <strong>Linux:</strong> <code>~/.secondlife/user_settings/automation.lua</code><br>
            <strong>Windows:</strong> <code>&#37;APPDATA&#37;\\SecondLife\\user_settings\\automation.lua</code><br>
            <strong>macOS:</strong> <code>~/Library/Application Support/SecondLife/user_settings/automation.lua</code><br>
            If <code>automation.lua</code> already exists, append the contents instead of replacing it.
            Load or reload via <strong>Advanced → Lua Scripting → Load a Lua script</strong> in Cool VL Viewer (no viewer restart needed).
          </p>
        </div>

        <div style="margin-top:1rem;display:flex;align-items:center;gap:1rem">
          <button id="btn-update-scripts" class="btn btn-primary" onclick="collectStep3(); updateScripts()">Update Scripts</button>
          <span id="script-update-status" style="font-size:12px"></span>
        </div>
        <p class="form-hint">Writes your URL, secret, and trigger names directly into <code>lsl/companion_bridge.lsl</code> and <code>lua/agent_companion.lua</code>. Also runs automatically when you click Next.</p>
      </div>
    </div>`;
}

function collectStep3() {
  state.discord_enabled            = chk('f-discord-on');
  state.discord_token              = val('f-discord-token') || state.discord_token;
  state.discord_allowed_guild_ids  = val('f-guild-ids');
  state.discord_active_channel_ids = val('f-channel-ids');
  state.sl_enabled                 = chk('f-sl-on');
  state.sl_bridge_url              = val('f-sl-url')    || state.sl_bridge_url;
  state.sl_bridge_secret           = val('f-sl-secret') || state.sl_bridge_secret;
  state.sl_bridge_port             = val('f-sl-port')   || state.sl_bridge_port;
  state.sl_trigger_names           = [
    val('f-trigger-0') || defaultCompanion().agent_name,
    val('f-trigger-1'),
    val('f-trigger-2'),
  ];
  state.opensim_enabled            = chk('f-opensim-on');
}

function updateScriptSnippet() {
  const url     = document.getElementById('f-sl-url')?.value    || 'YOUR_TUNNEL_URL';
  const secret  = document.getElementById('f-sl-secret')?.value || 'YOUR_BRIDGE_SECRET';
  const t0      = document.getElementById('f-trigger-0')?.value || defaultCompanion().agent_name || 'AgentName';
  const t1      = document.getElementById('f-trigger-1')?.value || '';
  const t2      = document.getElementById('f-trigger-2')?.value || '';
  const triggers = [t0, t1, t2].filter(Boolean).map(t => `"${t}"`).join(', ');

  const lslEl = document.getElementById('lsl-snippet');
  const luaEl = document.getElementById('lua-snippet');
  if (lslEl) lslEl.textContent =
    `string  SERVER_URL    = "${url}";\nstring  SECRET        = "${secret}";\nlist    TRIGGER_NAMES = [${triggers}];`;
  if (luaEl) luaEl.textContent =
    `local SERVER_URL = "${url}"\nlocal SECRET     = "${secret}"`;
}

function copySnippet(id) {
  const el = document.getElementById(id);
  if (!el) return;
  navigator.clipboard.writeText(el.textContent).then(() => {
    const btn = el.nextElementSibling;
    if (btn) { const orig = btn.textContent; btn.textContent = 'Copied!'; setTimeout(() => btn.textContent = orig, 1500); }
  });
}

async function updateScripts(silent) {
  const url     = document.getElementById('f-sl-url')?.value    || state.sl_bridge_url    || '';
  const secret  = document.getElementById('f-sl-secret')?.value || state.sl_bridge_secret || '';
  const t0      = document.getElementById('f-trigger-0')?.value || defaultCompanion().agent_name || '';
  const t1      = document.getElementById('f-trigger-1')?.value || '';
  const t2      = document.getElementById('f-trigger-2')?.value || '';
  const opensim = document.getElementById('f-opensim-on')?.checked ?? state.opensim_enabled;
  const triggers = [t0, t1, t2].filter(Boolean);

  const statusEl = document.getElementById('script-update-status');
  const btnEl    = document.getElementById('btn-update-scripts');

  if (btnEl) { btnEl.disabled = true; btnEl.textContent = 'Updating…'; }
  if (statusEl) { statusEl.textContent = ''; statusEl.style.color = ''; }

  try {
    const res  = await fetch('/setup/update-scripts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, secret, triggers, opensim }),
    });
    let data;
    try {
      data = await res.json();
    } catch (_) {
      const text = await res.text().catch(() => '(no response body)');
      if (statusEl && !silent) {
        statusEl.textContent = `✗ Server returned HTTP ${res.status} — ${text.slice(0, 120)}`;
        statusEl.style.color = '#f87171';
      }
      return;
    }
    if (statusEl && !silent) {
      statusEl.textContent = data.ok ? '✓ Scripts updated' : '✗ ' + JSON.stringify(data.results);
      statusEl.style.color = data.ok ? '#4ade80' : '#f87171';
    }
  } catch (e) {
    if (statusEl && !silent) {
      statusEl.textContent = '✗ ' + e.message;
      statusEl.style.color = '#f87171';
    }
  }

  if (btnEl) { btnEl.disabled = false; btnEl.textContent = 'Update Scripts'; }
}

function toggleCard(checkbox, bodyId) {
  const body = document.getElementById(bodyId);
  const card = checkbox.closest('.platform-card, .tool-card');
  if (body) body.style.display = checkbox.checked ? '' : 'none';
  if (card) card.classList.toggle('enabled', checkbox.checked);
}

// ============================================================
// Step 4 — Identity
// ============================================================

function buildStep4() {
  return `
    <h2 class="step-heading">Identity</h2>
    <p class="step-desc">Define who your agent is, how they feel, and who they're for. Each file is loaded into the system prompt on every message.</p>
    <div class="form-group">
      <label for="f-agent-md">Agent <span class="label-opt">(agent.md)</span></label>
      <textarea id="f-agent-md" class="form-textarea" rows="10">${esc(ac().agent_md)}</textarea>
      <p class="form-hint">Role, purpose, behaviors, boundaries, and roleplay rules.</p>
    </div>
    <div class="form-group" style="margin-top:1.5rem">
      <label for="f-soul-md">Soul <span class="label-opt">(soul.md)</span></label>
      <textarea id="f-soul-md" class="form-textarea" rows="6">${esc(ac().soul_md)}</textarea>
      <p class="form-hint">Tone, humor, quirks, and conversational style.</p>
    </div>
    <div class="form-group" style="margin-top:1.5rem">
      <label for="f-user-md">User Profile <span class="label-opt">(user.md)</span></label>
      <textarea id="f-user-md" class="form-textarea" rows="5">${esc(ac().user_md)}</textarea>
      <p class="form-hint">Describes the agent's owner — you. Used to personalise every response.</p>
    </div>`;
}

function collectStep4() {
  ac().agent_md = val('f-agent-md');
  ac().soul_md  = val('f-soul-md');
  ac().user_md  = val('f-user-md');
}

function buildStep5() {
  const showSL = state.sl_enabled;
  const c = ac();
  return `
    <h2 class="step-heading">Tools & Capabilities</h2>
    <p class="step-desc">Choose which tools this companion can use. Tools are used when helpful; the agent does not announce them.</p>

    <div class="tool-card ${c.web_search_enabled ? 'enabled' : ''}">
      <div class="card-header">
        <div>
          <div class="card-title">Web Search</div>
          <div class="card-desc">Search the web for current info, news, shopping, and more</div>
        </div>
        <label class="toggle">
          <input type="checkbox" id="f-search-on" ${c.web_search_enabled ? 'checked' : ''}
            onchange="toggleCard(this, 'search-body')">
          <span class="slider"></span>
        </label>
      </div>
      <div id="search-body" class="card-body" style="display:${c.web_search_enabled ? '' : 'none'}">
        <div class="form-group">
          <label for="f-search-provider">Provider</label>
          <select id="f-search-provider" class="form-input form-select">
            <option value="serper" ${state.search_provider === 'serper' ? 'selected' : ''}>Serper (Google)</option>
            <option value="brave"  ${state.search_provider === 'brave'  ? 'selected' : ''}>Brave Search</option>
          </select>
        </div>
        <div class="form-group" style="margin-bottom:0">
          <label for="f-search-key">API Key</label>
          <input type="password" id="f-search-key" class="form-input" value="${esc(state.search_api_key)}" placeholder="Search provider API key">
          <p class="form-hint">Serper: <code>serper.dev</code> · Brave: <code>api.search.brave.com</code></p>
        </div>
      </div>
    </div>

    <div class="tool-card ${c.notes_enabled ? 'enabled' : ''}">
      <div class="card-header">
        <div>
          <div class="card-title">Notes</div>
          <div class="card-desc">Save and recall persistent notes across conversations</div>
        </div>
        <label class="toggle">
          <input type="checkbox" id="f-notes-on" ${c.notes_enabled ? 'checked' : ''}
            onchange="this.closest('.tool-card').classList.toggle('enabled', this.checked)">
          <span class="slider"></span>
        </label>
      </div>
    </div>

    ${showSL ? `
    <div class="tool-card ${c.sl_action_enabled ? 'enabled' : ''}">
      <div class="card-header">
        <div>
          <div class="card-title">SL Actions</div>
          <div class="card-desc">Send emotes and IM actions in Second Life / OpenSim</div>
        </div>
        <label class="toggle">
          <input type="checkbox" id="f-slaction-on" ${c.sl_action_enabled ? 'checked' : ''}
            onchange="this.closest('.tool-card').classList.toggle('enabled', this.checked)">
          <span class="slider"></span>
        </label>
      </div>
    </div>

    <div class="tool-card ${c.voice_enabled ? 'enabled' : ''}">
      <div class="card-header">
        <div>
          <div class="card-title">Voice (SL)</div>
          <div class="card-desc">Enable the /sl/voice endpoint for audio input. Requires a voice-capable model. Also toggle <code>s_voice</code> in the HUD script to report who is in voice chat.</div>
        </div>
        <label class="toggle">
          <input type="checkbox" id="f-voice-on" ${c.voice_enabled ? 'checked' : ''}
            onchange="this.closest('.tool-card').classList.toggle('enabled', this.checked)">
          <span class="slider"></span>
        </label>
      </div>
    </div>` : ''}`;
}

function collectStep5() {
  ac().web_search_enabled = chk('f-search-on');
  state.search_provider   = val('f-search-provider') || state.search_provider;
  state.search_api_key    = val('f-search-key') || state.search_api_key;
  ac().notes_enabled      = chk('f-notes-on');
  const slEl              = document.getElementById('f-slaction-on');
  if (slEl) ac().sl_action_enabled = slEl.checked;
  const voiceEl           = document.getElementById('f-voice-on');
  if (voiceEl) ac().voice_enabled  = voiceEl.checked;
}

// ============================================================
// Step 6 — Context & Platform Awareness
// ============================================================

function buildStep6() {
  const c = ac();
  const paSections = [];
  if (state.discord_enabled)
    paSections.push(`
    <div class="form-group">
      <label for="f-pa-discord">Platform Awareness — Discord</label>
      <textarea id="f-pa-discord" class="form-textarea" rows="8">${esc(c.pa_discord)}</textarea>
    </div>`);
  if (state.sl_enabled)
    paSections.push(`
    <div class="form-group">
      <label for="f-pa-sl">Platform Awareness — Second Life</label>
      <textarea id="f-pa-sl" class="form-textarea" rows="20">${esc(c.pa_sl)}</textarea>
    </div>`);
  if (state.opensim_enabled)
    paSections.push(`
    <div class="form-group">
      <label for="f-pa-opensim">Platform Awareness — OpenSimulator</label>
      <textarea id="f-pa-opensim" class="form-textarea" rows="10">${esc(c.pa_opensim)}</textarea>
    </div>`);

  return `
    <h2 class="step-heading">Context & Platform Awareness</h2>
    <p class="step-desc">Add extra context and edit platform-specific behavior for this companion.</p>

    <div class="form-group">
      <label for="f-extra">Additional Context</label>
      <textarea id="f-extra" class="form-textarea" rows="5" placeholder="Extra instructions, specific relationships, environment notes, or anything else that doesn't fit the categories above...">${esc(c.additional_context)}</textarea>
      <p class="form-hint">Free-form. Appended to the system prompt on every message.</p>
    </div>

    ${paSections.length ? `
    <div style="margin-top:1.5rem">
      <div class="section-title" style="margin-bottom:0.75rem">Platform Awareness</div>
      <p class="step-desc" style="margin-top:0;margin-bottom:1rem">Injected per platform — only enabled platforms appear. Describes what the agent can perceive, do, and how to behave.</p>
      ${paSections.join('')}
    </div>` : '<p class="text-dim" style="margin-top:1.5rem">Enable platforms in Step 3 to configure their awareness blocks here.</p>'}`;
}

function collectStep6() {
  ac().additional_context = val('f-extra');
  const d = document.getElementById('f-pa-discord');
  const s = document.getElementById('f-pa-sl');
  const o = document.getElementById('f-pa-opensim');
  if (d) ac().pa_discord  = d.value;
  if (s) ac().pa_sl       = s.value;
  if (o) ac().pa_opensim  = o.value;
}

// ============================================================
// Step 7 — Supporting Agents
// ============================================================

function buildStep7() {
  function agentBlock(key, label, desc) {
    const a = state.supporting_agents[key] || {};
    const p = a.model_provider || 'anthropic';
    const m = a.model_name || '';
    return `
      <div class="form-group" style="margin-bottom:1.5rem">
        <label class="form-label">${label}</label>
        <p class="text-dim" style="margin:0.25rem 0 0.5rem">${desc}</p>
        <div style="display:grid;grid-template-columns:1fr 2fr;gap:0.5rem;align-items:center">
          <select id="f-${key}-provider" class="form-input" onchange="collectStep7()">
            <option value="anthropic"  ${p==='anthropic'  ?'selected':''}>Anthropic</option>
            <option value="openai"     ${p==='openai'     ?'selected':''}>OpenAI</option>
            <option value="openrouter" ${p==='openrouter' ?'selected':''}>OpenRouter</option>
            <option value="gemini"     ${p==='gemini'     ?'selected':''}>Gemini</option>
            <option value="grok"       ${p==='grok'       ?'selected':''}>Grok</option>
            <option value="ollama"     ${p==='ollama'     ?'selected':''}>Ollama</option>
            <option value="lm_studio"  ${p==='lm_studio'  ?'selected':''}>LM Studio</option>
          </select>
          <input id="f-${key}-model" class="form-input" type="text"
                 value="${esc(m)}" placeholder="e.g. claude-haiku-4-5-20251001"
                 onchange="collectStep7()">
        </div>
      </div>`;
  }

  return `
    <h2 class="step-heading">Supporting Agents</h2>
    <p class="step-desc">Each background agent can use a different model. Cheaper/faster models work well for scoring and retrieval — save the main model for the conversation.</p>

    <div class="callout callout-info" style="margin-bottom:1.5rem">
      Leave the model name blank to inherit the main agent's model. Changes take effect on restart.
    </div>

    ${agentBlock('memory_curator',  'Memory Curator',  'Scores conversation turns for long-term importance (runs every 6 h).')}
    ${agentBlock('librarian',       'Librarian',        'Finds and retrieves relevant library modules on demand.')}
    ${agentBlock('semantic_recall', 'Semantic Recall',  'Searches conversation history by meaning (on-demand tool call).')}`;
}

function collectStep7() {
  for (const key of ['memory_curator', 'librarian', 'semantic_recall']) {
    const provider = val(`f-${key}-provider`);
    const model    = val(`f-${key}-model`);
    if (provider) {
      state.supporting_agents[key] = { model_provider: provider, model_name: model };
    }
  }
}

// ============================================================
// Step 8 — Review & Save
// ============================================================

function buildStep8() {
  const modelLabel = (() => {
    const p = state.model_provider;
    if (p === 'anthropic')  return state.claude_model;
    if (p === 'ollama')     return `Ollama — ${state.ollama_model}`;
    if (p === 'lm_studio')  return `LM Studio — ${state.openai_model}`;
    const names = { openai: 'OpenAI', openrouter: 'OpenRouter', gemini: 'Gemini', grok: 'Grok' };
    return `${names[p] || p} — ${state.openai_model}`;
  })();

  const platforms = [];
  if (state.discord_enabled) platforms.push('<span class="badge">Discord</span>');
  if (state.sl_enabled) platforms.push(`<span class="badge">SL${state.opensim_enabled ? ' / OpenSim' : ''}</span>`);

  const def = defaultCompanion();
  const tools = [];
  if (def.web_search_enabled) tools.push('<span class="badge">Web Search</span>');
  if (def.notes_enabled)      tools.push('<span class="badge">Notes</span>');
  if (def.sl_action_enabled && state.sl_enabled) tools.push('<span class="badge">SL Actions</span>');
  if (def.voice_enabled     && state.sl_enabled) tools.push('<span class="badge">Voice</span>');

  const companionIds = Object.keys(state.companions);
  const others = companionIds.length - 1;
  const agentValue = esc(def.agent_name) + (others > 0
    ? ` <span class="text-dim" style="font-size:0.85em">+${others} more</span>` : '');

  return `
    <h2 class="step-heading">Ready to Launch</h2>
    <p class="step-desc">Review your configuration, then save. Tools shown are for the default companion (${esc(def.agent_name)}).</p>

    <div class="review-grid">
      <div class="review-card">
        <div class="review-label">Companion${others > 0 ? 's' : ''}</div>
        <div class="review-value">${agentValue}</div>
      </div>
      <div class="review-card">
        <div class="review-label">Model</div>
        <div class="review-value">${esc(modelLabel)}</div>
      </div>
      <div class="review-card">
        <div class="review-label">Platforms</div>
        <div class="review-value">${platforms.length ? platforms.join('') : '<span class="text-dim">None</span>'}</div>
      </div>
      <div class="review-card">
        <div class="review-label">Tools</div>
        <div class="review-value">${tools.length ? tools.join('') : '<span class="text-dim">None</span>'}</div>
      </div>
    </div>

    <div id="save-result"></div>

    <div class="callout callout-info">
      Persona changes take effect immediately. Model, credentials, and platform changes require a restart:
      <code>./run.sh</code>
    </div>

    <div id="script-section" style="margin-top:2rem">
      <p class="text-dim" style="margin-top:0.5rem">Loading scripts…</p>
    </div>`;
}

async function bindStep8() {
  const section = document.getElementById('script-section');
  if (!section) return;
  try {
    let res  = await fetch('/setup/scripts');
    let data = await res.json();

    // Scripts are gitignored and only generated on agent startup.
    // If missing but URL is known, generate them now so the user
    // doesn't have to restart the agent first.
    if (!data.lsl && !data.lua && state.sl_bridge_url) {
      section.innerHTML = '<p class="text-dim" style="margin-top:0.5rem">Generating scripts…</p>';
      await fetch('/setup/update-scripts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url:      state.sl_bridge_url,
          secret:   state.sl_bridge_secret,
          triggers: state.sl_trigger_names.filter(Boolean),
          opensim:  state.opensim_enabled,
        }),
      });
      res  = await fetch('/setup/scripts');
      data = await res.json();
    }

    let html = '';

    if (data.updated_on_startup) {
      html += `<div class="callout callout-warning" style="margin-top:0">
        ⚠ Scripts updated from a newer template on startup — recopy the LSL script to your HUD and replace the Lua file.
      </div>`;
    }

    const rows = [];
    if (data.lsl) rows.push({ id: 'lsl', title: 'companion_bridge.lsl', hint: 'Paste into a new script inside your HUD object in Second Life.', content: data.lsl });
    if (data.lua) rows.push({ id: 'lua', title: 'agent_companion.lua',  hint: 'Place at <code>user_settings/automation.lua</code> in your Cool VL Viewer directory.', content: data.lua });

    for (const r of rows) {
      html += `
        <div class="script-row">
          <div class="script-row-header">
            <span class="script-title">${r.title}</span>
            <div class="script-actions">
              <button class="btn btn-ghost" id="btn-copy-${r.id}">Copy</button>
              <button class="btn btn-ghost" id="btn-save-${r.id}">Save</button>
            </div>
          </div>
          <p class="form-hint" style="margin:0.35rem 0 0">${r.hint}</p>
        </div>`;
    }

    section.innerHTML = html || '<p class="text-dim">Bridge URL not configured — go to Step 3 to set it up.</p>';

    for (const r of rows) {
      const copyBtn = document.getElementById(`btn-copy-${r.id}`);
      if (copyBtn) copyBtn.addEventListener('click', () => {
        navigator.clipboard.writeText(r.content).then(() => {
          const orig = copyBtn.textContent;
          copyBtn.textContent = 'Copied!';
          setTimeout(() => { copyBtn.textContent = orig; }, 1500);
        });
      });
      const saveBtn = document.getElementById(`btn-save-${r.id}`);
      if (saveBtn) saveBtn.addEventListener('click', () => _downloadScript(r.title, r.content));
    }
  } catch (e) {
    section.innerHTML = '<p class="text-dim">Could not load scripts.</p>';
  }
}

function _downloadScript(filename, content) {
  const blob = new Blob([content], { type: 'text/plain' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

// ============================================================
// Step registry
// ============================================================

const builders = {
  1: buildStep1, 2: buildStep2, 3: buildStep3,
  4: buildStep4, 5: buildStep5, 6: buildStep6, 7: buildStep7, 8: buildStep8,
};
const binders = { 1: bindStep1, 3: () => updateScriptSnippet(), 8: bindStep8 };
const collectors = {
  1: collectStep1, 2: collectStep2, 3: collectStep3,
  4: collectStep4, 5: collectStep5, 6: collectStep6, 7: collectStep7,
};

function renderStep(n) {
  const content = document.getElementById('step-content');
  content.innerHTML = builders[n] ? builders[n]() : `<p>Step ${n}</p>`;
  if (COMPANION_STEPS.has(n)) {
    content.insertAdjacentHTML('afterbegin', companionBarHtml());
    bindCompanionBar();
  }
  if (binders[n]) binders[n]();
}

// ============================================================
// Save
// ============================================================

async function save() {
  const payload = {
    env: {
      MODEL_PROVIDER:              state.model_provider,
      ANTHROPIC_API_KEY:           state.anthropic_api_key,
      CLAUDE_MODEL:                state.claude_model,
      OPENAI_API_KEY:              state.openai_api_key,
      OPENAI_MODEL:                state.openai_model,
      OPENAI_BASE_URL:             state.openai_base_url,
      OLLAMA_BASE_URL:             state.ollama_base_url,
      OLLAMA_MODEL:                state.ollama_model,
      CLAUDE_MAX_TOKENS:           String(state.max_tokens),
      DISCORD_TOKEN:               state.discord_token,
      DISCORD_ALLOWED_GUILD_IDS:   state.discord_allowed_guild_ids,
      DISCORD_ACTIVE_CHANNEL_IDS:  state.discord_active_channel_ids,
      SL_BRIDGE_URL:               state.sl_bridge_url,
      SL_BRIDGE_SECRET:            state.sl_bridge_secret,
      SL_BRIDGE_PORT:              String(state.sl_bridge_port),
      SL_TRIGGER_NAMES:            state.sl_trigger_names.filter(Boolean).join(','),
      OPENSIM_ENABLED:             state.opensim_enabled ? 'true' : 'false',
      SEARCH_PROVIDER:             state.search_provider,
      SEARCH_API_KEY:              state.search_api_key,
      OWNER_SL_NAME:               state.owner_sl_name,
      OWNER_DISCORD_NAME:          state.owner_discord_name,
    },
    agent_config: {
      command_center_name: state.command_center_name || 'Command Center',
      default_agent_id: state.default_agent_id,
      supporting_agents: state.supporting_agents,
      agents: Object.fromEntries(Object.entries(state.companions).map(([id, c]) => {
        const agent = {
          id,
          agent_name: c.agent_name,
          agent_profile_image: c.agent_profile_image,
          additional_context: c.additional_context,
          tools: {
            web_search: c.web_search_enabled,
            notes:      c.notes_enabled,
            sl_action:  c.sl_action_enabled,
            voice:      c.voice_enabled,
          },
          platform_awareness: {
            discord: c.pa_discord,
            sl:      c.pa_sl,
            opensim: c.pa_opensim,
          },
          model_override: c.model_override ?? null,
          identity: {
            agent_md: c.agent_md,
            soul_md:  c.soul_md,
            user_md:  c.user_md,
          },
        };
        if (c.platform_bindings) agent.platform_bindings = c.platform_bindings;
        return [id, agent];
      })),
    },
  };

  const btn = document.getElementById('btn-next');
  btn.textContent = 'Saving…';
  btn.disabled = true;

  try {
    const res = await fetch('/setup/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();

    if (data.ok) {
      configured = true;
      document.getElementById('page-title').textContent = 'Settings';
      document.getElementById('save-result').innerHTML = `
        <div class="save-result success">
          <div class="save-icon">✓</div>
          <div>
            <strong>Configuration saved.</strong>
            <p>Persona changes are live. Restart the agent to apply model, credential, and platform changes:</p>
            <code class="code-block">./run.sh</code>
          </div>
        </div>`;
    } else {
      throw new Error(data.error || 'Unknown error');
    }
  } catch (e) {
    document.getElementById('save-result').innerHTML = `
      <div class="save-result error">
        <div class="save-icon">✗</div>
        <div><strong>Save failed.</strong> ${esc(e.message)}</div>
      </div>`;
  }

  btn.textContent = 'Save Configuration';
  btn.disabled = false;
}

// ============================================================
// Boot
// ============================================================

document.addEventListener('DOMContentLoaded', init);
