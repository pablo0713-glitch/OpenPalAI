const panelTitle = document.getElementById('panel-title');
const navLinks = Array.from(document.querySelectorAll('.nav-link'));
const panels = Array.from(document.querySelectorAll('.panel'));
const openStandalone = document.getElementById('open-standalone');
const newSessionButton = document.getElementById('new-session');
const filePickerButton = document.getElementById('file-picker-button');
const sendButton = document.getElementById('send-button');
const sendButtonEnabledInput = document.getElementById('send-button-enabled');
const sendStatus = document.getElementById('send-status');
const messageInput = document.getElementById('message-input');
const fileInput = document.getElementById('file-input');
const attachmentList = document.getElementById('attachment-list');
const libraryTitleInput = document.getElementById('library-title');
const libraryTagsInput = document.getElementById('library-tags');
const libraryPlatformsInput = document.getElementById('library-platforms');
const libraryAlwaysOnInput = document.getElementById('library-always-on');
const libraryFileInput = document.getElementById('library-file-input');
const libraryPickerButton = document.getElementById('library-picker-button');
const libraryAttachmentList = document.getElementById('library-attachment-list');
const libraryUploadButton = document.getElementById('library-upload-button');
const libraryStatus = document.getElementById('library-status');
const libraryRefreshButton = document.getElementById('library-refresh-button');
const libraryList = document.getElementById('library-list');
const libraryDetailTitle = document.getElementById('library-detail-title');
const libraryMeta = document.getElementById('library-meta');
const libraryPreview = document.getElementById('library-preview');
const libraryDetailAlwaysOn = document.getElementById('library-detail-always-on');
const librarySaveButton = document.getElementById('library-save-button');
const libraryDeleteButton = document.getElementById('library-delete-button');
const libraryBrowserStatus = document.getElementById('library-browser-status');
const chatStream = document.getElementById('chat-stream');
const agentName = document.getElementById('agent-name');
const agentSelector = document.getElementById('agent-selector');
const groupModeToggle = document.getElementById('group-mode-toggle');
const groupMembersContainer = document.getElementById('group-members');
const runtimeProfile = document.getElementById('runtime-profile');
const runtimeProfileImage = document.getElementById('runtime-profile-image');
const providerName = document.getElementById('provider-name');
const modelName = document.getElementById('model-name');
const uploadNote = document.getElementById('upload-note');

const sessionKey = 'trixxie-command-session';
const userKey = 'trixxie-command-user';
const agentKey = 'trixxie-command-agent';
const preferencesKey = 'trixxie-command-preferences';
const groupModeKey = 'trixxie-command-group-mode';
const groupMembersKey = 'trixxie-command-group-members';
let conversationId = localStorage.getItem(sessionKey) || createSessionId();
let commandUserId = localStorage.getItem(userKey) || createBrowserUserId();
let selectedAgentId = localStorage.getItem(agentKey) || '';
let groupMode = localStorage.getItem(groupModeKey) === '1';
let groupMembers = loadGroupMembers();
let libraryModules = [];
let selectedLibraryId = '';
let commandPreferences = loadPreferences();
let availableAgents = [];
let agentIdentity = {
  id: '',
  name: 'Agent',
  commandCenterName: 'Command Center',
  profileImage: '',
};
localStorage.setItem(sessionKey, conversationId);
localStorage.setItem(userKey, commandUserId);

sendButtonEnabledInput.checked = commandPreferences.sendButtonEnabled;
applySendButtonPreference();

for (const link of navLinks) {
  link.addEventListener('click', () => setPanel(link.dataset.panel || 'chat-panel'));
}

newSessionButton.addEventListener('click', () => {
  conversationId = createSessionId();
  localStorage.setItem(sessionKey, conversationId);
  void loadConversationHistory();
  sendStatus.textContent = 'New session ready';
});

fileInput.addEventListener('change', renderAttachmentList);
libraryFileInput.addEventListener('change', renderLibraryAttachmentList);
filePickerButton.addEventListener('click', () => fileInput.click());
libraryPickerButton.addEventListener('click', () => libraryFileInput.click());
sendButtonEnabledInput.addEventListener('change', () => {
  commandPreferences.sendButtonEnabled = sendButtonEnabledInput.checked;
  persistPreferences();
  applySendButtonPreference();
});
libraryRefreshButton.addEventListener('click', () => {
  void loadLibraryModules();
});
libraryDetailAlwaysOn.addEventListener('change', () => {
  librarySaveButton.disabled = !selectedLibraryId;
});
agentSelector.addEventListener('change', () => {
  selectedAgentId = agentSelector.value;
  localStorage.setItem(agentKey, selectedAgentId);
  void loadStatus();
  void loadConversationHistory();
});

groupModeToggle.checked = groupMode;
if (groupMode) {
  messageInput.placeholder = 'Message the group. Name a companion to address it directly, or just talk to everyone.';
}
groupModeToggle.addEventListener('change', () => {
  groupMode = groupModeToggle.checked;
  localStorage.setItem(groupModeKey, groupMode ? '1' : '0');
  groupMembersContainer.classList.toggle('hidden', !groupMode);
  messageInput.placeholder = groupMode
    ? 'Message the group. Name a companion to address it directly, or just talk to everyone.'
    : 'Talk to the agent, or attach an image/document and ask a question about it.';
  void loadConversationHistory();
});

messageInput.addEventListener('keydown', (event) => {
  if (event.isComposing) {
    return;
  }
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    void sendMessage();
  }
});

sendButton.addEventListener('click', sendMessage);
libraryUploadButton.addEventListener('click', uploadLibraryFiles);
librarySaveButton.addEventListener('click', saveSelectedLibraryModule);
libraryDeleteButton.addEventListener('click', deleteSelectedLibraryModule);

void initializeCommandCenter();

async function initializeCommandCenter() {
  await loadStatus();
  await loadConversationHistory();
  void loadLibraryModules();
  renderAttachmentList();
  renderLibraryAttachmentList();
  setPanel('chat-panel');
}

async function loadStatus() {
  try {
    const params = new URLSearchParams();
    if (selectedAgentId) {
      params.set('agent_id', selectedAgentId);
    }
    const response = await fetch(`/command/status?${params.toString()}`);
    const data = await response.json();
    availableAgents = Array.isArray(data.agents) ? data.agents : [];
    selectedAgentId = data.agent_id || data.default_agent_id || selectedAgentId || '';
    if (selectedAgentId) {
      localStorage.setItem(agentKey, selectedAgentId);
    }
    agentIdentity = {
      id: selectedAgentId,
      name: data.agent_name || 'Agent',
      commandCenterName: data.command_center_name || 'Command Center',
      profileImage: data.agent_profile_image || '',
    };
    renderAgentSelector();
    renderGroupMembers();
    agentName.textContent = agentIdentity.name;
    renderRuntimeProfile();
    providerName.textContent = data.model_provider || '—';
    modelName.textContent = data.model_name || '—';
    const maxMb = Math.round((data.uploads?.max_upload_bytes || 0) / (1024 * 1024));
    uploadNote.textContent = `Uploads: images, text-like docs, PDF, and DOCX, up to ${maxMb || 5} MB each`;
  } catch {
    uploadNote.textContent = 'Status unavailable';
  }
}

async function loadConversationHistory() {
  if (groupMode) {
    return loadGroupHistory();
  }
  chatStream.innerHTML = '';
  try {
    const params = new URLSearchParams({
      conversation_id: conversationId,
      command_user_id: commandUserId,
      agent_id: selectedAgentId,
    });
    const response = await fetch(`/command/history?${params.toString()}`);
    const data = await response.json();
    if (!response.ok || !data.ok) {
      throw new Error(data.error || 'Failed to load conversation history');
    }
    const messages = Array.isArray(data.messages) ? data.messages : [];
    if (!messages.length) {
      appendMessage('agent', `${data.agent_name || agentIdentity.name} is ready. Use this panel for direct chat, and switch tabs when you need setup or debugging.`);
      return;
    }
    for (const message of messages) {
      appendMessage(message.role === 'user' ? 'user' : 'agent', message.text || '');
    }
  } catch {
    appendMessage('agent', `${agentIdentity.name} is ready. Use this panel for direct chat, and switch tabs when you need setup or debugging.`);
  }
}

function setPanel(panelId) {
  for (const link of navLinks) {
    link.classList.toggle('active', link.dataset.panel === panelId);
  }
  for (const panel of panels) {
    panel.classList.toggle('active', panel.id === panelId);
  }

  const active = navLinks.find((link) => link.dataset.panel === panelId);
  const label = active?.textContent?.trim() || 'Command Center';
  panelTitle.textContent = label;

  if (panelId === 'setup-panel') {
    openStandalone.href = '/setup';
  } else if (panelId === 'debug-panel') {
    openStandalone.href = '/debug';
  } else {
    openStandalone.href = '/command';
  }
}

function renderAttachmentList() {
  renderFileList(fileInput, attachmentList);
}

function renderLibraryAttachmentList() {
  renderFileList(libraryFileInput, libraryAttachmentList);
}

async function sendMessage() {
  if (groupMode) {
    void sendGroupMessage();
    return;
  }
  const text = messageInput.value.trim();
  const files = Array.from(fileInput.files || []);
  if (!text && !files.length) {
    sendStatus.textContent = 'Add a message or an attachment';
    return;
  }

  appendMessage('user', text || buildAttachmentPrompt(files), files);

  const formData = new FormData();
  formData.append('message', text);
  formData.append('conversation_id', conversationId);
  formData.append('command_user_id', commandUserId);
  formData.append('display_name', agentIdentity.commandCenterName || 'Command Center');
  formData.append('agent_id', selectedAgentId);
  for (const file of files) {
    formData.append('files', file);
  }

  messageInput.value = '';
  fileInput.value = '';
  renderAttachmentList();
  setSendBusy(true);
  sendStatus.textContent = 'Sending…';

  try {
    const response = await fetch('/command/chat', {
      method: 'POST',
      body: formData,
    });
    const data = await response.json();
    if (!response.ok || !data.ok) {
      throw new Error(data.error || 'Request failed');
    }
    if (data.agent_id && data.agent_id !== selectedAgentId) {
      selectedAgentId = data.agent_id;
      localStorage.setItem(agentKey, selectedAgentId);
      renderAgentSelector();
    }
    if (data.agent_name) {
      agentIdentity.name = data.agent_name;
      agentName.textContent = agentIdentity.name;
    }
    if (typeof data.agent_profile_image === 'string') {
      agentIdentity.profileImage = data.agent_profile_image;
      renderRuntimeProfile();
    }
    appendMessage('agent', data.reply || '(no reply)');
    sendStatus.textContent = data.rate_limited ? 'Rate limited' : 'Ready';
  } catch (error) {
    appendMessage('agent', `Request failed: ${error.message}`);
    sendStatus.textContent = 'Request failed';
  } finally {
    setSendBusy(false);
    chatStream.scrollTop = chatStream.scrollHeight;
  }
}

async function sendGroupMessage() {
  const text = messageInput.value.trim();
  if (!text) {
    sendStatus.textContent = 'Add a message';
    return;
  }
  const ids = [...groupMembers];
  if (!ids.length) {
    sendStatus.textContent = 'Pick at least one companion for the group';
    return;
  }

  appendMessage('user', text);

  const formData = new FormData();
  formData.append('message', text);
  formData.append('conversation_id', conversationId);
  formData.append('command_user_id', commandUserId);
  formData.append('display_name', agentIdentity.commandCenterName || 'Command Center');
  formData.append('agent_ids', ids.join(','));

  messageInput.value = '';
  setSendBusy(true);
  sendStatus.textContent = 'Companions are talking…';

  try {
    const response = await fetch('/command/group-chat', { method: 'POST', body: formData });
    const data = await response.json();
    if (!response.ok || !data.ok) {
      throw new Error(data.error || 'Request failed');
    }
    const replies = Array.isArray(data.replies) ? data.replies : [];
    if (!replies.length) {
      appendMessage('agent', '(no companion responded — try naming one directly)', [], { name: 'Group', avatar: '' });
    }
    for (const reply of replies) {
      appendMessage('agent', reply.text || '(no reply)', [], {
        name: reply.agent_name,
        avatar: reply.agent_profile_image || '',
      });
    }
    sendStatus.textContent = 'Ready';
  } catch (error) {
    appendMessage('agent', `Request failed: ${error.message}`, [], { name: 'Group', avatar: '' });
    sendStatus.textContent = 'Request failed';
  } finally {
    setSendBusy(false);
    chatStream.scrollTop = chatStream.scrollHeight;
  }
}

async function loadGroupHistory() {
  chatStream.innerHTML = '';
  try {
    const params = new URLSearchParams({
      conversation_id: conversationId,
      command_user_id: commandUserId,
    });
    const response = await fetch(`/command/group-history?${params.toString()}`);
    const data = await response.json();
    if (!response.ok || !data.ok) {
      throw new Error(data.error || 'Failed to load group history');
    }
    const messages = Array.isArray(data.messages) ? data.messages : [];
    for (const message of messages) {
      if (message.role === 'user') {
        appendMessage('user', message.text || '');
      } else {
        appendMessage('agent', message.text || '', [], {
          name: message.name || 'Agent',
          avatar: message.agent_profile_image || '',
        });
      }
    }
  } catch {
    /* leave the stream empty — group conduct lives in each companion's prompt, not a header */
  }
}

function renderGroupMembers() {
  if (!groupMembersContainer) {
    return;
  }
  if (!groupMembers.size && availableAgents.length) {
    groupMembers = new Set(availableAgents.map((agent) => agent.id));
    persistGroupMembers();
  }
  groupMembersContainer.innerHTML = '';
  for (const agent of availableAgents) {
    const label = document.createElement('label');
    label.className = 'checkbox-row compact-checkbox group-member';
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.checked = groupMembers.has(agent.id);
    checkbox.disabled = !agent.enabled;
    checkbox.addEventListener('change', () => {
      if (checkbox.checked) {
        groupMembers.add(agent.id);
      } else {
        groupMembers.delete(agent.id);
      }
      persistGroupMembers();
    });
    const span = document.createElement('span');
    span.textContent = agent.is_default ? `${agent.agent_name} (default)` : agent.agent_name;
    label.appendChild(checkbox);
    label.appendChild(span);
    groupMembersContainer.appendChild(label);
  }
  groupMembersContainer.classList.toggle('hidden', !groupMode);
}

function loadGroupMembers() {
  try {
    const raw = localStorage.getItem(groupMembersKey);
    if (!raw) {
      return new Set();
    }
    const parsed = JSON.parse(raw);
    return new Set(Array.isArray(parsed) ? parsed : []);
  } catch {
    return new Set();
  }
}

function persistGroupMembers() {
  localStorage.setItem(groupMembersKey, JSON.stringify([...groupMembers]));
}

function renderAgentSelector() {
  if (!agentSelector) {
    return;
  }
  agentSelector.innerHTML = '';
  for (const agent of availableAgents) {
    const option = document.createElement('option');
    option.value = agent.id;
    option.textContent = agent.is_default ? `${agent.agent_name} (default)` : agent.agent_name;
    if (!agent.enabled) {
      option.disabled = true;
    }
    agentSelector.appendChild(option);
  }
  if (selectedAgentId) {
    agentSelector.value = selectedAgentId;
  }
}

async function uploadLibraryFiles() {
  const files = Array.from(libraryFileInput.files || []);
  if (!files.length) {
    libraryStatus.textContent = 'Choose one or more documents';
    return;
  }

  const formData = new FormData();
  formData.append('title', libraryTitleInput.value.trim());
  formData.append('tags', libraryTagsInput.value.trim());
  formData.append('platforms', libraryPlatformsInput.value.trim());
  formData.append('always_on', libraryAlwaysOnInput.checked ? 'true' : 'false');
  for (const file of files) {
    formData.append('files', file);
  }

  libraryUploadButton.disabled = true;
  libraryStatus.textContent = 'Importing…';

  try {
    const response = await fetch('/command/library-upload', {
      method: 'POST',
      body: formData,
    });
    const data = await response.json();
    if (!response.ok || !data.ok) {
      throw new Error(data.error || 'Library upload failed');
    }

    const created = Array.isArray(data.created) ? data.created : [];
    const summary = created.length === 1
      ? `Added ${created[0].filename} to data/library`
      : `Added ${created.length} modules to data/library`;
    appendMessage('agent', summary);
    libraryStatus.textContent = summary;
    libraryFileInput.value = '';
    if (created.length) {
      libraryTitleInput.value = '';
    }
    renderLibraryAttachmentList();
    void loadLibraryModules();
  } catch (error) {
    libraryStatus.textContent = error.message;
  } finally {
    libraryUploadButton.disabled = false;
  }
}

async function loadLibraryModules(selectedId = selectedLibraryId) {
  libraryBrowserStatus.textContent = 'Loading library…';
  try {
    const response = await fetch('/command/library');
    const data = await response.json();
    if (!response.ok || !data.ok) {
      throw new Error(data.error || 'Failed to load library');
    }
    libraryModules = Array.isArray(data.modules) ? data.modules : [];
    renderLibraryList();
    if (selectedId && libraryModules.some((module) => module.id === selectedId)) {
      await selectLibraryModule(selectedId);
    } else {
      clearLibraryDetail();
    }
    libraryBrowserStatus.textContent = 'Ready';
  } catch (error) {
    libraryBrowserStatus.textContent = error.message;
  }
}

function renderLibraryList() {
  libraryList.innerHTML = '';
  if (!libraryModules.length) {
    const empty = document.createElement('div');
    empty.className = 'library-empty';
    empty.textContent = 'No library modules yet.';
    libraryList.appendChild(empty);
    return;
  }

  for (const module of libraryModules) {
    const button = document.createElement('button');
    button.className = 'library-item';
    button.classList.toggle('active', module.id === selectedLibraryId);
    button.addEventListener('click', () => {
      void selectLibraryModule(module.id);
    });

    const title = document.createElement('strong');
    title.textContent = module.title;
    button.appendChild(title);

    const meta = document.createElement('span');
    meta.textContent = `${module.id} · ${module.char_count} chars${module.always_on ? ' · always-on' : ''}`;
    button.appendChild(meta);

    libraryList.appendChild(button);
  }
}

async function selectLibraryModule(moduleId) {
  selectedLibraryId = moduleId;
  renderLibraryList();
  libraryBrowserStatus.textContent = 'Loading module…';

  try {
    const response = await fetch(`/command/library/${encodeURIComponent(moduleId)}`);
    const data = await response.json();
    if (!response.ok || !data.ok) {
      throw new Error(data.error || 'Failed to load module');
    }

    const module = data.module;
    libraryDetailTitle.textContent = module.title;
    libraryMeta.innerHTML = '';
    for (const line of [
      `ID: ${module.id}`,
      `File: ${module.filename}`,
      `Platforms: ${(module.platforms || []).join(', ') || 'all'}`,
      `Tags: ${(module.tags || []).join(', ') || 'none'}`,
      `Description: ${module.description || '—'}`,
    ]) {
      const row = document.createElement('span');
      row.textContent = line;
      libraryMeta.appendChild(row);
    }
    libraryPreview.textContent = module.content || '(empty module)';
    libraryDetailAlwaysOn.checked = Boolean(module.always_on);
    libraryDetailAlwaysOn.disabled = false;
    librarySaveButton.disabled = true;
    libraryDeleteButton.disabled = false;
    libraryBrowserStatus.textContent = 'Ready';
  } catch (error) {
    clearLibraryDetail(error.message);
  }
}

async function saveSelectedLibraryModule() {
  if (!selectedLibraryId) {
    return;
  }
  librarySaveButton.disabled = true;
  libraryBrowserStatus.textContent = 'Saving…';
  try {
    const response = await fetch(`/command/library/${encodeURIComponent(selectedLibraryId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ always_on: libraryDetailAlwaysOn.checked }),
    });
    const data = await response.json();
    if (!response.ok || !data.ok) {
      throw new Error(data.error || 'Save failed');
    }
    await loadLibraryModules(selectedLibraryId);
    libraryBrowserStatus.textContent = 'Saved';
  } catch (error) {
    libraryBrowserStatus.textContent = error.message;
  }
}

async function deleteSelectedLibraryModule() {
  if (!selectedLibraryId) {
    return;
  }
  libraryDeleteButton.disabled = true;
  libraryBrowserStatus.textContent = 'Deleting…';
  try {
    const response = await fetch(`/command/library/${encodeURIComponent(selectedLibraryId)}`, {
      method: 'DELETE',
    });
    const data = await response.json();
    if (!response.ok || !data.ok) {
      throw new Error(data.error || 'Delete failed');
    }
    const deletedId = selectedLibraryId;
    clearLibraryDetail();
    selectedLibraryId = '';
    await loadLibraryModules('');
    libraryBrowserStatus.textContent = `Deleted ${deletedId}`;
  } catch (error) {
    libraryDeleteButton.disabled = false;
    libraryBrowserStatus.textContent = error.message;
  }
}

function clearLibraryDetail(status = 'Ready') {
  selectedLibraryId = '';
  renderLibraryList();
  libraryDetailTitle.textContent = 'Select a module';
  libraryMeta.innerHTML = '';
  libraryPreview.textContent = 'No module selected.';
  libraryDetailAlwaysOn.checked = false;
  libraryDetailAlwaysOn.disabled = true;
  librarySaveButton.disabled = true;
  libraryDeleteButton.disabled = true;
  libraryBrowserStatus.textContent = status;
}

function appendMessage(role, text, files = [], meta = null) {
  const article = document.createElement('article');
  article.className = `message ${role}`;

  const header = document.createElement('div');
  header.className = 'message-header';

  const displayName = role === 'user'
    ? (agentIdentity.commandCenterName || 'Command Center')
    : (meta && meta.name ? meta.name : agentIdentity.name);
  const avatarSrc = role === 'agent'
    ? (meta ? meta.avatar : agentIdentity.profileImage)
    : '';

  if (role === 'agent' && avatarSrc) {
    const avatar = document.createElement('img');
    avatar.className = 'message-avatar';
    avatar.src = avatarSrc;
    avatar.alt = `${displayName} profile image`;
    header.appendChild(avatar);
  }

  const title = document.createElement('p');
  title.className = 'message-role';
  title.textContent = displayName;
  header.appendChild(title);
  article.appendChild(header);

  const body = document.createElement('div');
  body.className = 'message-body';
  body.textContent = text;
  article.appendChild(body);

  if (files.length) {
    const fileRow = document.createElement('div');
    fileRow.className = 'attachment-list';
    for (const file of files) {
      const chip = document.createElement('span');
      chip.className = 'attachment-chip';
      chip.textContent = file.name;
      fileRow.appendChild(chip);
    }
    article.appendChild(fileRow);
  }

  chatStream.appendChild(article);
  chatStream.scrollTop = chatStream.scrollHeight;
}

function buildAttachmentPrompt(files) {
  if (!files.length) {
    return '';
  }
  return `Uploaded ${files.length} attachment${files.length === 1 ? '' : 's'}.`;
}

function renderFileList(input, target) {
  const files = Array.from(input.files || []);
  target.innerHTML = '';
  if (!files.length) {
    return;
  }

  for (const file of files) {
    const chip = document.createElement('span');
    chip.className = 'attachment-chip';
    chip.textContent = file.name;
    target.appendChild(chip);
  }
}

function createSessionId() {
  return Math.random().toString(36).slice(2, 10);
}

function loadPreferences() {
  try {
    const raw = localStorage.getItem(preferencesKey);
    if (!raw) {
      return {
        sendButtonEnabled: true,
      };
    }
    const parsed = JSON.parse(raw);
    return {
      sendButtonEnabled: parsed.sendButtonEnabled !== false,
    };
  } catch {
    return {
      sendButtonEnabled: true,
    };
  }
}

function persistPreferences() {
  localStorage.setItem(preferencesKey, JSON.stringify(commandPreferences));
}

function applySendButtonPreference() {
  sendButton.disabled = !sendButtonEnabledInput.checked;
}

function setSendBusy(isBusy) {
  sendButton.disabled = isBusy || !sendButtonEnabledInput.checked;
  messageInput.disabled = isBusy;
  fileInput.disabled = isBusy;
  filePickerButton.disabled = isBusy;
}

function renderRuntimeProfile() {
  const hasProfileImage = Boolean(agentIdentity.profileImage);
  runtimeProfile.classList.toggle('hidden', !hasProfileImage);
  if (hasProfileImage) {
    runtimeProfileImage.src = agentIdentity.profileImage;
  } else {
    runtimeProfileImage.removeAttribute('src');
  }
}

function createBrowserUserId() {
  return Math.random().toString(36).slice(2, 12);
}
