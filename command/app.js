const panelTitle = document.getElementById('panel-title');
const navLinks = Array.from(document.querySelectorAll('.nav-link'));
const panels = Array.from(document.querySelectorAll('.panel'));
const openStandalone = document.getElementById('open-standalone');
const newSessionButton = document.getElementById('new-session');
const sendButton = document.getElementById('send-button');
const sendStatus = document.getElementById('send-status');
const messageInput = document.getElementById('message-input');
const displayNameInput = document.getElementById('display-name');
const fileInput = document.getElementById('file-input');
const attachmentList = document.getElementById('attachment-list');
const libraryTitleInput = document.getElementById('library-title');
const libraryTagsInput = document.getElementById('library-tags');
const libraryPlatformsInput = document.getElementById('library-platforms');
const libraryAlwaysOnInput = document.getElementById('library-always-on');
const libraryFileInput = document.getElementById('library-file-input');
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
const providerName = document.getElementById('provider-name');
const modelName = document.getElementById('model-name');
const uploadNote = document.getElementById('upload-note');

const sessionKey = 'trixxie-command-session';
let conversationId = localStorage.getItem(sessionKey) || createSessionId();
let libraryModules = [];
let selectedLibraryId = '';
localStorage.setItem(sessionKey, conversationId);

for (const link of navLinks) {
  link.addEventListener('click', () => setPanel(link.dataset.panel || 'chat-panel'));
}

newSessionButton.addEventListener('click', () => {
  conversationId = createSessionId();
  localStorage.setItem(sessionKey, conversationId);
  chatStream.innerHTML = '';
  appendMessage('agent', 'Started a fresh chat session.');
  sendStatus.textContent = 'New session ready';
});

fileInput.addEventListener('change', renderAttachmentList);
libraryFileInput.addEventListener('change', renderLibraryAttachmentList);
libraryRefreshButton.addEventListener('click', () => {
  void loadLibraryModules();
});
libraryDetailAlwaysOn.addEventListener('change', () => {
  librarySaveButton.disabled = !selectedLibraryId;
});

messageInput.addEventListener('keydown', (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
    event.preventDefault();
    sendMessage();
  }
});

sendButton.addEventListener('click', sendMessage);
libraryUploadButton.addEventListener('click', uploadLibraryFiles);
librarySaveButton.addEventListener('click', saveSelectedLibraryModule);
libraryDeleteButton.addEventListener('click', deleteSelectedLibraryModule);

void loadStatus();
void loadLibraryModules();
renderAttachmentList();
renderLibraryAttachmentList();
setPanel('chat-panel');

async function loadStatus() {
  try {
    const response = await fetch('/command/status');
    const data = await response.json();
    agentName.textContent = data.agent_name || 'Agent';
    providerName.textContent = data.model_provider || '—';
    modelName.textContent = data.model_name || '—';
    const maxMb = Math.round((data.uploads?.max_upload_bytes || 0) / (1024 * 1024));
    uploadNote.textContent = `Uploads: images, text-like docs, PDF, and DOCX, up to ${maxMb || 5} MB each`;
  } catch {
    uploadNote.textContent = 'Status unavailable';
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
  const text = messageInput.value.trim();
  const files = Array.from(fileInput.files || []);
  if (!text && !files.length) {
    sendStatus.textContent = 'Add a message or an attachment';
    return;
  }

  const displayName = displayNameInput.value.trim() || 'Command Center';
  appendMessage('user', text || buildAttachmentPrompt(files), files);

  const formData = new FormData();
  formData.append('message', text);
  formData.append('conversation_id', conversationId);
  formData.append('display_name', displayName);
  for (const file of files) {
    formData.append('files', file);
  }

  messageInput.value = '';
  fileInput.value = '';
  renderAttachmentList();
  sendButton.disabled = true;
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
    appendMessage('agent', data.reply || '(no reply)');
    sendStatus.textContent = data.rate_limited ? 'Rate limited' : 'Ready';
  } catch (error) {
    appendMessage('agent', `Request failed: ${error.message}`);
    sendStatus.textContent = 'Request failed';
  } finally {
    sendButton.disabled = false;
    chatStream.scrollTop = chatStream.scrollHeight;
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

function appendMessage(role, text, files = []) {
  const article = document.createElement('article');
  article.className = `message ${role}`;

  const title = document.createElement('p');
  title.className = 'message-role';
  title.textContent = role === 'user' ? 'You' : 'Agent';
  article.appendChild(title);

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