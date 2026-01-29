(() => {
  'use strict';

  const state = {
    status: {},
    questions: { pending: [], answered: [] },
    journal: { entries: [], stats: {} },
    goal: '',
    tools: [],
    todos: { items: [], stats: {} },
    logs: { logs: [], total_lines: 0 },
    activeTab: 'goal',
    queuedPrompts: [],
    chatSessions: [],
    currentChatSession: null,
    chatMessages: []
  };

  const ui = {
    statusText: document.getElementById('status-text'),
    statusChip: document.getElementById('status-chip'),
    statusDot: document.getElementById('status-dot'),
    statusPill: document.getElementById('status-pill'),
    loopCount: document.getElementById('loop-count'),
    totalTokens: document.getElementById('total-tokens'),
    lastAction: document.getElementById('last-action'),
    contextValue: document.getElementById('context-value'),
    contextFill: document.getElementById('context-fill'),
    pendingCount: document.getElementById('pending-count'),
    pendingList: document.getElementById('questions-pending'),
    answeredSection: document.getElementById('answered-section'),
    answeredList: document.getElementById('questions-answered'),
    journalSearch: document.getElementById('journal-search'),
    journalSearchBtn: document.getElementById('journal-search-btn'),
    statIdeas: document.getElementById('stat-ideas'),
    statExperiments: document.getElementById('stat-experiments'),
    statTools: document.getElementById('stat-tools'),
    statFailed: document.getElementById('stat-failed'),
    journalEntries: document.getElementById('journal-entries'),
    goalDisplay: document.getElementById('goal-display'),
    goalEdit: document.getElementById('goal-edit'),
    goalView: document.getElementById('goal-view'),
    goalEditor: document.getElementById('goal-editor'),
    goalEditBtn: document.getElementById('goal-edit-btn'),
    goalSaveBtn: document.getElementById('goal-save-btn'),
    goalCancelBtn: document.getElementById('goal-cancel-btn'),
    toolsList: document.getElementById('tools-list'),
    entryModal: document.getElementById('entry-modal'),
    entryModalTitle: document.getElementById('entry-modal-title'),
    entryModalBody: document.getElementById('entry-modal-body'),
    entryModalClose: document.getElementById('entry-modal-close'),
    btnStart: document.getElementById('btn-start'),
    btnPause: document.getElementById('btn-pause'),
    btnStop: document.getElementById('btn-stop'),
    btnCompact: document.getElementById('btn-compact'),
    btnRestart: document.getElementById('btn-restart'),
    // Prompt queue elements
    promptQueueCount: document.getElementById('prompt-queue-count'),
    promptQueueList: document.getElementById('prompt-queue-list'),
    promptQueueText: document.getElementById('prompt-queue-text'),
    promptQueueBtn: document.getElementById('prompt-queue-btn'),
    promptPriorityHigh: document.getElementById('prompt-priority-high'),
    // Restart modal elements
    restartModal: document.getElementById('restart-modal'),
    restartModalClose: document.getElementById('restart-modal-close'),
    restartPrompt: document.getElementById('restart-prompt'),
    restartKeepContext: document.getElementById('restart-keep-context'),
    restartConfirmBtn: document.getElementById('restart-confirm-btn'),
    restartCancelBtn: document.getElementById('restart-cancel-btn'),
    // Chat elements
    chatNewBtn: document.getElementById('chat-new-btn'),
    chatSessionSelect: document.getElementById('chat-session-select'),
    chatDeleteBtn: document.getElementById('chat-delete-btn'),
    chatMessages: document.getElementById('chat-messages'),
    chatInput: document.getElementById('chat-input'),
    chatSendBtn: document.getElementById('chat-send-btn'),
    // Tab elements
    tabs: document.getElementById('tabs'),
    todoList: document.getElementById('todo-list'),
    todoStatPending: document.getElementById('todo-stat-pending'),
    todoStatProgress: document.getElementById('todo-stat-progress'),
    todoStatDone: document.getElementById('todo-stat-done'),
    logOutput: document.getElementById('log-output'),
    logsMeta: document.getElementById('logs-meta'),
    logsLines: document.getElementById('logs-lines'),
    logsLevel: document.getElementById('logs-level'),
    logsAuto: document.getElementById('logs-auto'),
    logsRefresh: document.getElementById('logs-refresh')
  };

  let logsAutoRefreshInterval = null;

  function formatNumber(value) {
    const number = Number(value || 0);
    return Number.isFinite(number) ? number.toLocaleString() : '0';
  }

  function setStatusClasses(status) {
    const statusValue = status || 'unknown';
    const statusClass = `status-${statusValue}`;
    [ui.statusPill, ui.statusChip].forEach((node) => {
      if (!node) return;
      node.classList.remove('status-running', 'status-paused', 'status-stopped', 'status-error', 'status-unknown');
      node.classList.add(statusClass);
    });
  }

  function setStatusDot(status) {
    if (!ui.statusDot) return;
    let color = 'var(--gray)';
    if (status === 'running') color = 'var(--accent-green)';
    if (status === 'paused') color = 'var(--accent-yellow)';
    if (status === 'error') color = 'var(--accent-red)';
    ui.statusDot.style.background = color;
  }

  function updateContextUsage(percentValue) {
    const percent = Math.max(0, Math.min(100, Number(percentValue || 0)));
    if (ui.contextValue) ui.contextValue.textContent = `${percent.toFixed(1)}%`;
    if (ui.contextFill) {
      ui.contextFill.style.width = `${percent}%`;
      ui.contextFill.classList.remove('context-warn', 'context-high');
      if (percent > 85) {
        ui.contextFill.classList.add('context-high');
      } else if (percent > 70) {
        ui.contextFill.classList.add('context-warn');
      }
    }
  }

  function updateStatus() {
    const status = state.status || {};
    const statusValue = status.status || 'unknown';
    if (ui.statusText) ui.statusText.textContent = statusValue;
    if (ui.statusPill) ui.statusPill.textContent = statusValue;
    setStatusClasses(statusValue);
    setStatusDot(statusValue);

    if (ui.loopCount) ui.loopCount.textContent = formatNumber(status.loop_count);
    if (ui.totalTokens) ui.totalTokens.textContent = formatNumber(status.total_tokens);
    if (ui.lastAction) ui.lastAction.textContent = status.last_action || '-';

    const usage = status.context && typeof status.context.usage_percent !== 'undefined'
      ? status.context.usage_percent
      : 0;
    updateContextUsage(usage);

    const isRunning = statusValue === 'running';
    const isPaused = statusValue === 'paused';

    if (ui.btnStart) ui.btnStart.disabled = isRunning;
    if (ui.btnStop) ui.btnStop.disabled = statusValue === 'stopped';

    if (ui.btnPause) {
      ui.btnPause.textContent = isPaused ? 'Resume' : 'Pause';
      ui.btnPause.classList.toggle('btn-success', isPaused);
      ui.btnPause.classList.toggle('btn-warning', !isPaused);
      ui.btnPause.disabled = statusValue === 'stopped';
    }
  }

  function createElement(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (typeof text !== 'undefined') el.textContent = text;
    return el;
  }

  // ==================== Tab Switching ====================

  function initTabs() {
    if (!ui.tabs) return;

    const tabs = ui.tabs.querySelectorAll('.tab');
    const panels = document.querySelectorAll('.tab-panel');

    tabs.forEach(tab => {
      tab.addEventListener('click', () => {
        const targetTab = tab.dataset.tab;
        state.activeTab = targetTab;

        // Update active states
        tabs.forEach(t => {
          t.classList.remove('active');
          t.setAttribute('aria-selected', 'false');
        });
        panels.forEach(p => p.classList.remove('active'));

        tab.classList.add('active');
        tab.setAttribute('aria-selected', 'true');

        const panel = document.querySelector(`[data-tab-panel="${targetTab}"]`);
        if (panel) panel.classList.add('active');

        // Load data for the tab
        loadTabData(targetTab);
      });
    });
  }

  function loadTabData(tabName) {
    switch (tabName) {
      case 'logs':
        fetchLogs();
        break;
      case 'todo':
        fetchTodos();
        break;
      case 'journal':
        fetchJournal();
        break;
      case 'questions':
        fetchQuestions();
        break;
      case 'tools':
        fetchTools();
        break;
      case 'goal':
        fetchGoal();
        break;
      case 'chat':
        fetchChatSessions();
        break;
    }
  }

  // ==================== Todos ====================

  function renderTodos() {
    if (!ui.todoList) return;

    const items = state.todos.items || [];
    const stats = state.todos.stats || {};

    // Update stats
    if (ui.todoStatPending) ui.todoStatPending.textContent = `${stats.pending || 0} pending`;
    if (ui.todoStatProgress) ui.todoStatProgress.textContent = `${stats.in_progress || 0} in progress`;
    if (ui.todoStatDone) ui.todoStatDone.textContent = `${stats.done || 0} done`;

    ui.todoList.innerHTML = '';

    if (items.length === 0) {
      ui.todoList.innerHTML = '<div class="todo-empty">No tasks yet. The agent will add tasks as it works.</div>';
      return;
    }

    items.forEach(item => {
      const el = createTodoItem(item);
      ui.todoList.appendChild(el);
    });
  }

  function createTodoItem(item, isSubtask = false) {
    const div = createElement('div', `todo-item status-${item.status}${isSubtask ? ' subtask' : ''}`);
    div.dataset.id = item.id;

    // Checkbox
    const checkbox = createElement('input', 'todo-checkbox');
    checkbox.type = 'checkbox';
    checkbox.checked = item.status === 'done';
    checkbox.addEventListener('change', () => toggleTodoStatus(item.id, checkbox.checked));

    // Content
    const content = createElement('div', 'todo-content');

    const title = createElement('div', 'todo-title', item.title);
    content.appendChild(title);

    if (item.description) {
      const desc = createElement('div', 'todo-desc', item.description.substring(0, 100) + (item.description.length > 100 ? '...' : ''));
      content.appendChild(desc);
    }

    const meta = createElement('div', 'todo-meta');
    const priority = createElement('span', `todo-priority priority-${item.priority}`, item.priority);
    meta.appendChild(priority);
    content.appendChild(meta);

    div.appendChild(checkbox);
    div.appendChild(content);

    // Subtasks
    if (item.subtasks && item.subtasks.length > 0) {
      const subtasksContainer = createElement('div', 'todo-subtasks');
      item.subtasks.forEach(sub => {
        subtasksContainer.appendChild(createTodoItem(sub, true));
      });
      div.appendChild(subtasksContainer);
    }

    return div;
  }

  async function toggleTodoStatus(itemId, isDone) {
    const newStatus = isDone ? 'done' : 'pending';
    await fetch('/api/todos', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'update', item_id: itemId, status: newStatus })
    });
    await fetchTodos();
  }

  async function fetchTodos() {
    try {
      const res = await fetch('/api/todos');
      if (!res.ok) return;
      state.todos = await res.json();
      renderTodos();
    } catch (e) {
      console.error('Failed to fetch todos:', e);
    }
  }

  // ==================== Logs ====================

  function renderLogs() {
    if (!ui.logOutput) return;

    const logs = state.logs.logs || [];
    const total = state.logs.total_lines || 0;
    const returned = state.logs.returned_lines || logs.length;

    if (ui.logsMeta) {
      ui.logsMeta.textContent = `Showing ${returned} of ${total} lines`;
    }

    if (logs.length === 0) {
      ui.logOutput.innerHTML = '<span class="log-line log-info">No log entries yet.</span>';
      return;
    }

    ui.logOutput.innerHTML = logs.map(line => {
      let levelClass = 'log-info';
      if (line.includes('[WARNING]')) levelClass = 'log-warning';
      if (line.includes('[ERROR]')) levelClass = 'log-error';
      return `<span class="log-line ${levelClass}">${escapeHtml(line)}</span>`;
    }).join('\n');

    // Scroll to bottom
    ui.logOutput.scrollTop = ui.logOutput.scrollHeight;
  }

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  async function fetchLogs() {
    try {
      const lines = ui.logsLines ? ui.logsLines.value : '200';
      const level = ui.logsLevel ? ui.logsLevel.value : '';
      const params = new URLSearchParams({ lines });
      if (level) params.set('level', level);

      const res = await fetch(`/api/logs?${params.toString()}`);
      if (!res.ok) return;
      state.logs = await res.json();
      renderLogs();
    } catch (e) {
      console.error('Failed to fetch logs:', e);
    }
  }

  function setupLogsAutoRefresh() {
    if (logsAutoRefreshInterval) {
      clearInterval(logsAutoRefreshInterval);
      logsAutoRefreshInterval = null;
    }

    if (ui.logsAuto && ui.logsAuto.checked && state.activeTab === 'logs') {
      logsAutoRefreshInterval = setInterval(fetchLogs, 3000);
    }
  }

  // ==================== Questions ====================

  function renderQuestions() {
    if (!ui.pendingList) return;

    const pending = state.questions.pending || [];
    const answered = state.questions.answered || [];

    if (ui.pendingCount) ui.pendingCount.textContent = `${pending.length} pending`;
    ui.pendingList.innerHTML = '';

    if (pending.length === 0) {
      ui.pendingList.innerHTML = '<div class="questions-empty">No pending questions from the agent.</div>';
    } else {
      pending.forEach((question) => {
        const card = createElement('div', `question-card priority-${question.priority || 'low'}`);
        card.appendChild(createElement('p', 'question-text', question.question_text || 'Question'));

        if (question.context) {
          card.appendChild(createElement('p', 'question-context', question.context));
        }

        if (question.question_type === 'free_text') {
          const row = createElement('div', 'input-row');
          const input = createElement('input', 'input');
          input.type = 'text';
          input.placeholder = 'Type your answer';
          input.addEventListener('keydown', (event) => {
            if (event.key === 'Enter') {
              answerQuestion(question.id, input.value);
            }
          });
          const btn = createElement('button', 'btn btn-primary', 'Send');
          btn.addEventListener('click', () => answerQuestion(question.id, input.value));
          row.appendChild(input);
          row.appendChild(btn);
          card.appendChild(row);
        } else {
          const options = Array.isArray(question.options) && question.options.length > 0
            ? question.options
            : (question.question_type === 'yes_no' ? ['Yes', 'No'] : []);
          const optionsWrap = createElement('div', 'question-options');
          options.forEach((option) => {
            const btn = createElement('button', 'btn btn-outline', option);
            btn.addEventListener('click', () => answerQuestion(question.id, option));
            optionsWrap.appendChild(btn);
          });
          if (options.length === 0) {
            optionsWrap.appendChild(createElement('span', 'section-note', 'No options provided.'));
          }
          card.appendChild(optionsWrap);
        }

        ui.pendingList.appendChild(card);
      });
    }

    if (ui.answeredList) {
      ui.answeredList.innerHTML = '';
      if (answered.length > 0) {
        if (ui.answeredSection) ui.answeredSection.classList.remove('is-hidden');
        ui.answeredList.classList.remove('is-hidden');
        answered.slice(0, 5).forEach((entry) => {
          const row = createElement('div', 'status-item');
          row.appendChild(createElement('span', 'section-note', entry.question_text || 'Answered'));
          row.appendChild(createElement('span', 'mono', entry.answer || ''));
          ui.answeredList.appendChild(row);
        });
      } else {
        if (ui.answeredSection) ui.answeredSection.classList.add('is-hidden');
        ui.answeredList.classList.add('is-hidden');
      }
    }
  }

  // ==================== Journal ====================

  function renderJournal() {
    const stats = state.journal.stats || {};
    if (ui.statIdeas) ui.statIdeas.textContent = formatNumber(stats.ideas);
    if (ui.statExperiments) ui.statExperiments.textContent = formatNumber(stats.empirical_results);
    if (ui.statTools) ui.statTools.textContent = formatNumber(stats.tool_specs);
    if (ui.statFailed) ui.statFailed.textContent = formatNumber(stats.failed_attempts);

    if (!ui.journalEntries) return;

    ui.journalEntries.innerHTML = '';
    const entries = state.journal.entries || [];
    if (entries.length === 0) {
      ui.journalEntries.appendChild(createElement('p', 'section-note', 'No journal entries yet.'));
      return;
    }

    entries.slice(0, 10).forEach((entry) => {
      const card = createElement('div', 'entry-card');
      const title = createElement('div', 'entry-title', entry.title || 'Untitled');
      const meta = createElement('div', 'entry-meta', entry.entry_type || 'entry');
      card.appendChild(title);
      card.appendChild(meta);
      card.addEventListener('click', () => showEntry(entry));
      ui.journalEntries.appendChild(card);
    });
  }

  // ==================== Goal ====================

  function renderGoal() {
    if (ui.goalDisplay) ui.goalDisplay.textContent = state.goal || 'No goal set.';
    if (ui.goalEdit) ui.goalEdit.value = state.goal || '';
  }

  // ==================== Tools ====================

  function renderTools() {
    if (!ui.toolsList) return;

    ui.toolsList.innerHTML = '';
    const tools = state.tools || [];
    if (tools.length === 0) {
      ui.toolsList.appendChild(createElement('span', 'section-note', 'No tools registered.'));
      return;
    }

    tools.forEach((tool) => {
      const card = createElement('div', `tool-card${tool.protected ? ' protected' : ''}`);

      const name = createElement('div', 'tool-name');
      name.textContent = tool.name;
      if (tool.protected) {
        const badge = createElement('span', 'tool-badge', 'protected');
        name.appendChild(badge);
      }
      card.appendChild(name);

      if (tool.description) {
        const desc = createElement('div', 'tool-desc', tool.description);
        card.appendChild(desc);
      }

      ui.toolsList.appendChild(card);
    });
  }

  // ==================== API Fetches ====================

  async function fetchStatus() {
    try {
      const res = await fetch('/api/status');
      if (!res.ok) return;
      state.status = await res.json();
      updateStatus();
    } catch (e) {
      console.error('Failed to fetch status:', e);
    }
  }

  async function fetchQuestions() {
    try {
      const res = await fetch('/api/questions');
      if (!res.ok) return;
      state.questions = await res.json();
      renderQuestions();
    } catch (e) {
      console.error('Failed to fetch questions:', e);
    }
  }

  async function fetchJournal(query = '') {
    try {
      const params = new URLSearchParams();
      if (query) params.set('query', query);
      params.set('limit', '20');
      const res = await fetch(`/api/journal?${params.toString()}`);
      if (!res.ok) return;
      state.journal = await res.json();
      renderJournal();
    } catch (e) {
      console.error('Failed to fetch journal:', e);
    }
  }

  async function fetchGoal() {
    try {
      const res = await fetch('/api/goal');
      if (!res.ok) return;
      const data = await res.json();
      state.goal = data.content || '';
      renderGoal();
    } catch (e) {
      console.error('Failed to fetch goal:', e);
    }
  }

  async function fetchTools() {
    try {
      const res = await fetch('/api/tools');
      if (!res.ok) return;
      const data = await res.json();
      state.tools = data.tools || [];
      renderTools();
    } catch (e) {
      console.error('Failed to fetch tools:', e);
    }
  }

  async function fetchAll() {
    await Promise.allSettled([
      fetchStatus(),
      fetchGoal(),
      fetchTodos(),
      fetchTools(),
      fetchPromptQueue()
    ]);
  }

  // ==================== Actions ====================

  async function startAgent() {
    await fetch('/api/start', { 
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({})
    });
    await fetchStatus();
  }

  async function stopAgent() {
    await fetch('/api/stop', { method: 'POST' });
    await fetchStatus();
  }

  async function pauseOrResume() {
    const statusValue = state.status.status;
    if (statusValue === 'paused') {
      await fetch('/api/resume', { method: 'POST' });
    } else {
      await fetch('/api/pause', { method: 'POST' });
    }
    await fetchStatus();
  }

  async function forceCompact() {
    await fetch('/api/compact', { method: 'POST' });
  }

  async function answerQuestion(id, answer) {
    const text = String(answer || '').trim();
    if (!text) return;
    await fetch('/api/questions/answer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question_id: id, answer: text })
    });
    await fetchQuestions();
  }

  async function saveGoal() {
    const content = ui.goalEdit ? ui.goalEdit.value : '';
    await fetch('/api/goal', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content })
    });
    state.goal = content;
    renderGoal();
    toggleGoalEditor(false);
  }

  function toggleGoalEditor(show) {
    if (!ui.goalEditor || !ui.goalView) return;
    const shouldShow = typeof show === 'boolean' ? show : ui.goalEditor.classList.contains('is-hidden');
    ui.goalEditor.classList.toggle('is-hidden', !shouldShow);
    ui.goalView.classList.toggle('is-hidden', shouldShow);
  }

  function showEntry(entry) {
    if (ui.entryModalTitle) ui.entryModalTitle.textContent = entry.title || 'Journal entry';
    if (ui.entryModalBody) ui.entryModalBody.textContent = entry.content || '';
    if (ui.entryModal) ui.entryModal.classList.add('active');
  }

  function closeEntryModal() {
    if (ui.entryModal) ui.entryModal.classList.remove('active');
  }

  // ==================== Prompt Queue ====================

  function renderPromptQueue() {
    if (!ui.promptQueueList) return;

    const prompts = state.queuedPrompts || [];

    if (ui.promptQueueCount) {
      ui.promptQueueCount.textContent = prompts.length;
    }

    if (prompts.length === 0) {
      ui.promptQueueList.innerHTML = '<div class="prompt-queue-empty">No prompts queued</div>';
      return;
    }

    ui.promptQueueList.innerHTML = prompts.map(p => `
      <div class="prompt-queue-item ${p.priority === 'high' ? 'priority-high' : ''}">
        <div class="prompt-queue-item-text">${escapeHtml(p.prompt.substring(0, 60))}${p.prompt.length > 60 ? '...' : ''}</div>
        <button class="prompt-queue-remove" data-id="${p.id}" title="Remove">&times;</button>
      </div>
    `).join('');

    // Add click handlers for remove buttons
    ui.promptQueueList.querySelectorAll('.prompt-queue-remove').forEach(btn => {
      btn.addEventListener('click', () => removeQueuedPrompt(btn.dataset.id));
    });
  }

  async function queuePrompt() {
    if (!ui.promptQueueText) return;

    const prompt = ui.promptQueueText.value.trim();
    if (!prompt) return;

    const priority = ui.promptPriorityHigh && ui.promptPriorityHigh.checked ? 'high' : 'normal';

    await fetch('/api/prompts/queue', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt, priority })
    });

    ui.promptQueueText.value = '';
    if (ui.promptPriorityHigh) ui.promptPriorityHigh.checked = false;

    await fetchPromptQueue();
  }

  async function fetchPromptQueue() {
    try {
      const res = await fetch('/api/prompts/queue');
      if (!res.ok) return;
      const data = await res.json();
      state.queuedPrompts = data.prompts || [];
      renderPromptQueue();
    } catch (e) {
      console.error('Failed to fetch prompt queue:', e);
    }
  }

  async function removeQueuedPrompt(promptId) {
    await fetch(`/api/prompts/queue/${promptId}`, { method: 'DELETE' });
    await fetchPromptQueue();
  }

  // ==================== Restart Modal ====================

  function showRestartModal() {
    if (ui.restartModal) {
      ui.restartModal.classList.add('active');
      if (ui.restartPrompt) ui.restartPrompt.value = '';
      if (ui.restartKeepContext) ui.restartKeepContext.checked = false;
    }
  }

  function closeRestartModal() {
    if (ui.restartModal) ui.restartModal.classList.remove('active');
  }

  async function restartAgent() {
    const prompt = ui.restartPrompt ? ui.restartPrompt.value.trim() : '';
    const keepContext = ui.restartKeepContext ? ui.restartKeepContext.checked : false;

    closeRestartModal();

    await fetch('/api/restart', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: prompt || null, keep_context: keepContext })
    });

    await fetchStatus();
  }

  // ==================== Chat ====================

  async function createNewChat() {
    const res = await fetch('/api/chat/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: `Chat ${new Date().toLocaleString()}` })
    });
    if (!res.ok) return;
    const data = await res.json();
    state.currentChatSession = data.session_id;
    await fetchChatSessions();
    await loadChatSession(data.session_id);
  }

  async function fetchChatSessions() {
    try {
      const res = await fetch('/api/chat/sessions');
      if (!res.ok) return;
      const data = await res.json();
      state.chatSessions = data.sessions || [];
      renderChatSessionSelect();
    } catch (e) {
      console.error('Failed to fetch chat sessions:', e);
    }
  }

  function renderChatSessionSelect() {
    if (!ui.chatSessionSelect) return;

    ui.chatSessionSelect.innerHTML = '<option value="">Select a chat session...</option>';
    state.chatSessions.forEach(session => {
      const option = document.createElement('option');
      option.value = session.id;
      option.textContent = session.title || session.id;
      if (session.id === state.currentChatSession) {
        option.selected = true;
      }
      ui.chatSessionSelect.appendChild(option);
    });
  }

  async function loadChatSession(sessionId) {
    if (!sessionId) {
      state.currentChatSession = null;
      state.chatMessages = [];
      renderChatMessages();
      setChatInputEnabled(false);
      return;
    }

    try {
      const res = await fetch(`/api/chat/session/${sessionId}`);
      if (!res.ok) return;
      const session = await res.json();
      state.currentChatSession = sessionId;
      state.chatMessages = session.messages || [];
      renderChatMessages();
      setChatInputEnabled(true);
    } catch (e) {
      console.error('Failed to load chat session:', e);
    }
  }

  function renderChatMessages() {
    if (!ui.chatMessages) return;

    if (state.chatMessages.length === 0) {
      ui.chatMessages.innerHTML = '<div class="chat-empty">No messages yet. Start typing to chat.</div>';
      return;
    }

    ui.chatMessages.innerHTML = state.chatMessages.map(msg => {
      const cls = msg.role === 'user' ? 'chat-message-user' : 'chat-message-assistant';
      return `<div class="chat-message ${cls}">
        <div class="chat-message-role">${msg.role === 'user' ? 'You' : 'Agent'}</div>
        <div class="chat-message-content">${escapeHtml(msg.content)}</div>
      </div>`;
    }).join('');

    // Scroll to bottom
    ui.chatMessages.scrollTop = ui.chatMessages.scrollHeight;
  }

  function setChatInputEnabled(enabled) {
    if (ui.chatInput) ui.chatInput.disabled = !enabled;
    if (ui.chatSendBtn) ui.chatSendBtn.disabled = !enabled;
  }

  async function sendChatMessage() {
    if (!state.currentChatSession || !ui.chatInput) return;

    const message = ui.chatInput.value.trim();
    if (!message) return;

    // Optimistically add user message
    state.chatMessages.push({ role: 'user', content: message, timestamp: new Date().toISOString() });
    renderChatMessages();
    ui.chatInput.value = '';
    ui.chatSendBtn.disabled = true;

    try {
      const res = await fetch('/api/chat/message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: state.currentChatSession, message })
      });

      if (!res.ok) throw new Error('Failed to send');
      const data = await res.json();

      // Add assistant response
      state.chatMessages.push({ role: 'assistant', content: data.response, timestamp: new Date().toISOString() });
      renderChatMessages();
    } catch (e) {
      console.error('Failed to send chat message:', e);
    } finally {
      ui.chatSendBtn.disabled = false;
    }
  }

  async function deleteCurrentChat() {
    if (!state.currentChatSession) return;
    if (!confirm('Delete this chat session?')) return;

    await fetch(`/api/chat/session/${state.currentChatSession}`, { method: 'DELETE' });
    state.currentChatSession = null;
    await fetchChatSessions();
    loadChatSession(null);
  }

  // ==================== WebSocket ====================

  function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const socket = new WebSocket(`${protocol}//${window.location.host}/ws`);

    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload.type === 'status') {
          state.status = payload.data || {};
          updateStatus();

          // Update todos from WebSocket if available
          if (payload.todos) {
            const oldItems = JSON.stringify(state.todos.items);
            state.todos.items = payload.todos;
            state.todos.stats = {
              total: payload.todos.length,
              pending: payload.todos.filter(t => t.status === 'pending').length,
              in_progress: payload.todos.filter(t => t.status === 'in_progress').length,
              done: payload.todos.filter(t => t.status === 'done').length
            };
            // Only re-render if todos changed
            if (oldItems !== JSON.stringify(payload.todos)) {
              renderTodos();
            }
          }

          // Update queued prompts from WebSocket
          if (payload.queued_prompts) {
            state.queuedPrompts = payload.queued_prompts;
            renderPromptQueue();
          }
        }
      } catch (error) {
        console.error('WebSocket message error:', error);
      }
    };

    socket.onclose = () => {
      setTimeout(connectWebSocket, 3000);
    };
  }

  // ==================== Init ====================

  function init() {
    initTabs();
    fetchAll();
    connectWebSocket();

    // Control buttons
    if (ui.btnStart) ui.btnStart.addEventListener('click', startAgent);
    if (ui.btnStop) ui.btnStop.addEventListener('click', stopAgent);
    if (ui.btnPause) ui.btnPause.addEventListener('click', pauseOrResume);
    if (ui.btnCompact) ui.btnCompact.addEventListener('click', forceCompact);
    if (ui.btnRestart) ui.btnRestart.addEventListener('click', showRestartModal);

    // Prompt queue
    if (ui.promptQueueBtn) ui.promptQueueBtn.addEventListener('click', queuePrompt);
    if (ui.promptQueueText) {
      ui.promptQueueText.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          queuePrompt();
        }
      });
    }

    // Restart modal
    if (ui.restartModalClose) ui.restartModalClose.addEventListener('click', closeRestartModal);
    if (ui.restartCancelBtn) ui.restartCancelBtn.addEventListener('click', closeRestartModal);
    if (ui.restartConfirmBtn) ui.restartConfirmBtn.addEventListener('click', restartAgent);
    if (ui.restartModal) {
      ui.restartModal.addEventListener('click', (e) => {
        if (e.target === ui.restartModal) closeRestartModal();
      });
    }

    // Chat
    if (ui.chatNewBtn) ui.chatNewBtn.addEventListener('click', createNewChat);
    if (ui.chatSessionSelect) ui.chatSessionSelect.addEventListener('change', (e) => loadChatSession(e.target.value));
    if (ui.chatDeleteBtn) ui.chatDeleteBtn.addEventListener('click', deleteCurrentChat);
    if (ui.chatSendBtn) ui.chatSendBtn.addEventListener('click', sendChatMessage);
    if (ui.chatInput) {
      ui.chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          sendChatMessage();
        }
      });
    }

    // Journal search
    if (ui.journalSearchBtn) {
      ui.journalSearchBtn.addEventListener('click', () => fetchJournal(ui.journalSearch ? ui.journalSearch.value : ''));
    }
    if (ui.journalSearch) {
      ui.journalSearch.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
          fetchJournal(ui.journalSearch.value);
        }
      });
    }

    // Goal editing
    if (ui.goalEditBtn) ui.goalEditBtn.addEventListener('click', () => toggleGoalEditor());
    if (ui.goalCancelBtn) ui.goalCancelBtn.addEventListener('click', () => toggleGoalEditor(false));
    if (ui.goalSaveBtn) ui.goalSaveBtn.addEventListener('click', saveGoal);

    // Modal
    if (ui.entryModalClose) ui.entryModalClose.addEventListener('click', closeEntryModal);
    if (ui.entryModal) {
      ui.entryModal.addEventListener('click', (event) => {
        if (event.target === ui.entryModal) {
          closeEntryModal();
        }
      });
    }

    // Logs controls
    if (ui.logsRefresh) ui.logsRefresh.addEventListener('click', fetchLogs);
    if (ui.logsLines) ui.logsLines.addEventListener('change', fetchLogs);
    if (ui.logsLevel) ui.logsLevel.addEventListener('change', fetchLogs);
    if (ui.logsAuto) {
      ui.logsAuto.addEventListener('change', setupLogsAutoRefresh);
      setupLogsAutoRefresh();
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
