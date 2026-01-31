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
    enhancedLogs: [],
    activeTab: 'goal',
    queuedPrompts: [],
    chatSessions: [],
    currentChatSession: null,
    chatMessages: [],
    tournaments: [],
    currentTournament: null,
    currentContainer: null,
    files: [],
    currentFile: null,
    logViewMode: 'standard' // 'standard' or 'enhanced'
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
    goalWarning: document.getElementById('goal-warning'),
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
    // Factory reset modal elements
    factoryResetBtn: document.getElementById('factory-reset-btn'),
    factoryResetModal: document.getElementById('factory-reset-modal'),
    factoryResetModalClose: document.getElementById('factory-reset-modal-close'),
    factoryResetConfirm: document.getElementById('factory-reset-confirm'),
    factoryResetConfirmBtn: document.getElementById('factory-reset-confirm-btn'),
    factoryResetBackupBtn: document.getElementById('factory-reset-backup-btn'),
    factoryResetCancelBtn: document.getElementById('factory-reset-cancel-btn'),
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
    logsRefresh: document.getElementById('logs-refresh'),
    // Enhanced logs
    logsStandardBtn: document.getElementById('logs-standard-btn'),
    logsEnhancedBtn: document.getElementById('logs-enhanced-btn'),
    enhancedLogs: document.getElementById('enhanced-logs'),
    enhancedLogsList: document.getElementById('enhanced-logs-list'),
    // Tournament elements
    tournamentCreateBtn: document.getElementById('tournament-create-btn'),
    tournamentCreateForm: document.getElementById('tournament-create-form'),
    tournamentTopic: document.getElementById('tournament-topic'),
    tournamentStages: document.getElementById('tournament-stages'),
    tournamentRounds: document.getElementById('tournament-rounds'),
    tournamentSubmitBtn: document.getElementById('tournament-submit-btn'),
    tournamentCancelBtn: document.getElementById('tournament-cancel-btn'),
    tournamentList: document.getElementById('tournament-list'),
    tournamentDetail: document.getElementById('tournament-detail'),
    tournamentBackBtn: document.getElementById('tournament-back-btn'),
    tournamentDetailTitle: document.getElementById('tournament-detail-title'),
    tournamentDetailStatus: document.getElementById('tournament-detail-status'),
    tournamentDetailTopic: document.getElementById('tournament-detail-topic'),
    synthesisRounds: document.getElementById('synthesis-rounds'),
    finalFilesSection: document.getElementById('final-files-section'),
    finalFilesList: document.getElementById('final-files-list'),
    // Container detail
    containerDetail: document.getElementById('container-detail'),
    containerBackBtn: document.getElementById('container-back-btn'),
    containerDetailTitle: document.getElementById('container-detail-title'),
    containerDetailStatus: document.getElementById('container-detail-status'),
    containerLogs: document.getElementById('container-logs'),
    containerFiles: document.getElementById('container-files'),
    containerRevealed: document.getElementById('container-revealed'),
    // Files tab
    fileTree: document.getElementById('file-tree'),
    filePreviewName: document.getElementById('file-preview-name'),
    filePreviewMeta: document.getElementById('file-preview-meta'),
    filePreviewContent: document.getElementById('file-preview-content'),
    filesRefresh: document.getElementById('files-refresh')
  };

  let logsAutoRefreshInterval = null;
  let tournamentAutoRefreshInterval = null;

  function formatNumber(value) {
    const number = Number(value || 0);
    return Number.isFinite(number) ? number.toLocaleString() : '0';
  }

  function isGoalEmpty() {
    return !state.goal || !state.goal.trim();
  }

  function updateStartAvailability() {
    const statusValue = (state.status && state.status.status) || 'unknown';
    const isRunning = statusValue === 'running';
    const goalEmpty = isGoalEmpty();

    if (ui.btnStart) {
      ui.btnStart.disabled = isRunning || goalEmpty;
      ui.btnStart.title = goalEmpty ? 'Set a goal to start the agent.' : '';
    }

    if (ui.btnRestart) {
      ui.btnRestart.disabled = goalEmpty;
      ui.btnRestart.title = goalEmpty ? 'Set a goal to restart the agent.' : '';
    }

    if (ui.goalWarning) {
      ui.goalWarning.classList.toggle('is-hidden', !goalEmpty);
    }
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

    const isPaused = statusValue === 'paused';

    if (ui.btnStop) ui.btnStop.disabled = statusValue === 'stopped';

    if (ui.btnPause) {
      ui.btnPause.textContent = isPaused ? 'Resume' : 'Pause';
      ui.btnPause.classList.toggle('btn-success', isPaused);
      ui.btnPause.classList.toggle('btn-warning', !isPaused);
      ui.btnPause.disabled = statusValue === 'stopped';
    }

    updateStartAvailability();
  }

  function createElement(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (typeof text !== 'undefined') el.textContent = text;
    return el;
  }

  async function readErrorMessage(res) {
    try {
      const data = await res.json();
      return data.detail || data.error || 'Request failed.';
    } catch (e) {
      return 'Request failed.';
    }
  }

  function getDownloadFilename(headers, fallback) {
    const disposition = headers.get('content-disposition') || '';
    const match = /filename=\"([^\"]+)\"/.exec(disposition);
    return match ? match[1] : fallback;
  }

  function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
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
      case 'tournament':
        fetchTournaments();
        break;
      case 'files':
        fetchFiles();
        break;
    }

    setupTournamentAutoRefresh(tabName === 'tournament');
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

  function setupTournamentAutoRefresh(isActive) {
    if (tournamentAutoRefreshInterval) {
      clearInterval(tournamentAutoRefreshInterval);
      tournamentAutoRefreshInterval = null;
    }

    if (isActive) {
      tournamentAutoRefreshInterval = setInterval(refreshTournamentData, 2000);
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
    updateStartAvailability();
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
    if (isGoalEmpty()) {
      alert('Set a goal before starting the agent.');
      return;
    }

    const res = await fetch('/api/start', { 
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({})
    });

    if (!res.ok) {
      alert(await readErrorMessage(res));
      return;
    }

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

    if (isGoalEmpty()) {
      alert('Set a goal before restarting the agent.');
      return;
    }

    const res = await fetch('/api/restart', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: prompt || null, keep_context: keepContext })
    });

    if (!res.ok) {
      alert(await readErrorMessage(res));
      return;
    }

    await fetchStatus();
  }

  // ==================== Factory Reset ====================

  function showFactoryResetModal() {
    if (!ui.factoryResetModal) return;
    ui.factoryResetModal.classList.add('active');
    if (ui.factoryResetConfirm) ui.factoryResetConfirm.checked = false;
    updateFactoryResetActions();
  }

  function closeFactoryResetModal() {
    if (ui.factoryResetModal) ui.factoryResetModal.classList.remove('active');
  }

  function updateFactoryResetActions() {
    const confirmed = ui.factoryResetConfirm && ui.factoryResetConfirm.checked;
    if (ui.factoryResetConfirmBtn) ui.factoryResetConfirmBtn.disabled = !confirmed;
    if (ui.factoryResetBackupBtn) ui.factoryResetBackupBtn.disabled = !confirmed;
  }

  async function runFactoryReset(withBackup) {
    if (!ui.factoryResetConfirm || !ui.factoryResetConfirm.checked) return;

    const res = await fetch('/api/factory-reset', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ confirm: true, backup: Boolean(withBackup) })
    });

    if (!res.ok) {
      alert(await readErrorMessage(res));
      return;
    }

    if (withBackup) {
      const blob = await res.blob();
      const filename = getDownloadFilename(res.headers, 'curiosity-agent-backup.zip');
      downloadBlob(blob, filename);
    } else {
      await res.json().catch(() => ({}));
    }

    closeFactoryResetModal();
    await fetchAll();
    await fetchStatus();
    alert('Factory reset complete.');
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

  // ==================== Tournaments ====================

  async function fetchTournaments() {
    try {
      const res = await fetch('/api/tournaments');
      if (!res.ok) return;
      const data = await res.json();
      state.tournaments = data.tournaments || [];
      renderTournaments();
    } catch (e) {
      console.error('Failed to fetch tournaments:', e);
    }
  }

  async function refreshTournamentData() {
    if (state.currentTournament) {
      await refreshTournamentDetail();
      return;
    }
    await fetchTournaments();
  }

  function renderTournaments() {
    if (!ui.tournamentList) return;

    if (state.currentTournament) {
      // Detail view is shown
      return;
    }

    if (state.tournaments.length === 0) {
      ui.tournamentList.innerHTML = '<div class="tournament-empty">No tournaments yet. Create one to start collaborative problem solving.</div>';
      return;
    }

    ui.tournamentList.innerHTML = state.tournaments.map(t => `
      <div class="tournament-card" data-id="${t.id}">
        <div class="tournament-card-header">
          <span class="tournament-card-title">${t.id.substring(0, 20)}</span>
          <span class="status-pill status-${t.status}">${t.status}</span>
        </div>
        <div class="tournament-card-topic">${escapeHtml(t.topic)}</div>
        <div class="tournament-card-meta">
          <span>Stages: ${t.stages ? t.stages.join(' → ') : 'N/A'}</span>
          <span>Containers: ${t.container_count || 0}</span>
        </div>
      </div>
    `).join('');

    // Add click handlers
    ui.tournamentList.querySelectorAll('.tournament-card').forEach(card => {
      card.addEventListener('click', () => loadTournamentDetail(card.dataset.id));
    });
  }

  async function loadTournamentDetail(tournamentId) {
    try {
      const res = await fetch(`/api/tournaments/${tournamentId}`);
      if (!res.ok) return;
      state.currentTournament = await res.json();
      state.currentContainer = null;
      renderTournamentDetail();
    } catch (e) {
      console.error('Failed to load tournament:', e);
    }
  }

  async function refreshTournamentDetail() {
    const t = state.currentTournament;
    if (!t) return;
    try {
      const res = await fetch(`/api/tournaments/${t.id}`);
      if (!res.ok) return;
      state.currentTournament = await res.json();
      renderTournamentDetail();
      if (state.currentContainer) {
        const containerId = state.currentContainer.id || state.currentContainer.agent_id;
        if (containerId) {
          await loadContainerDetail(containerId);
        }
      }
    } catch (e) {
      console.error('Failed to refresh tournament:', e);
    }
  }

  function renderTournamentDetail() {
    const t = state.currentTournament;
    if (!t) return;

    // Hide list, show detail
    if (ui.tournamentList) ui.tournamentList.classList.add('is-hidden');
    if (ui.tournamentCreateForm) ui.tournamentCreateForm.classList.add('is-hidden');
    if (ui.tournamentDetail) ui.tournamentDetail.classList.remove('is-hidden');

    if (ui.tournamentDetailTitle) ui.tournamentDetailTitle.textContent = t.id;
    if (ui.tournamentDetailStatus) {
      ui.tournamentDetailStatus.textContent = t.status;
      ui.tournamentDetailStatus.className = `status-pill status-${t.status}`;
    }
    if (ui.tournamentDetailTopic) ui.tournamentDetailTopic.textContent = t.topic;

    // Render synthesis rounds
    if (ui.synthesisRounds) {
      const rounds = t.synthesis_rounds || [];
      if (rounds.length === 0) {
        ui.synthesisRounds.innerHTML = '<div class="section-note">No rounds executed yet.</div>';
      } else {
        ui.synthesisRounds.innerHTML = rounds.map(round => `
          <div class="synthesis-round">
            <div class="synthesis-round-header">
              <h4>Round ${round.round_number}</h4>
              <span class="status-pill status-${round.status}">${round.status}</span>
            </div>
            <div class="synthesis-round-containers">
              ${(round.containers || round.agents || []).map(c => {
                const containerId = c.id || c.agent_id || '';
                const containerStatus = c.status || 'unknown';
                const revealedCount = c.revealed_files ? c.revealed_files.length : 0;
                return `
                <div class="container-card" data-container-id="${containerId}">
                  <div class="container-card-header">
                    <span class="container-card-id">${containerId.substring(0, 12)}</span>
                    <span class="status-pill status-${containerStatus}">${containerStatus}</span>
                  </div>
                  <div class="container-card-meta">
                    Files: ${revealedCount} revealed
                  </div>
                </div>
              `;
              }).join('')}
            </div>
          </div>
        `).join('');

        // Add click handlers to containers
        ui.synthesisRounds.querySelectorAll('.container-card').forEach(card => {
          card.addEventListener('click', () => loadContainerDetail(card.dataset.containerId));
        });
      }
    }

    // Render final files
    if (ui.finalFilesSection && ui.finalFilesList) {
      const files = t.final_files || [];
      if (files.length === 0) {
        ui.finalFilesSection.classList.add('is-hidden');
      } else {
        ui.finalFilesSection.classList.remove('is-hidden');
        ui.finalFilesList.innerHTML = files.map(f => `
          <div class="final-file-card" data-filename="${f.filename}">
            <div class="final-file-name">${f.filename}</div>
            <div class="final-file-desc">${f.description || 'No description'}</div>
          </div>
        `).join('');

        // Add click handlers for file preview
        ui.finalFilesList.querySelectorAll('.final-file-card').forEach(card => {
          card.addEventListener('click', () => showFinalFile(card.dataset.filename));
        });
      }
    }
  }

  function showFinalFile(filename, fileOverride = null) {
    const t = state.currentTournament;
    if (!t) return;

    const file = fileOverride || t.final_files.find(f => f.filename === filename);
    if (!file) return;

    if (!file.content) {
      fetch(`/api/tournaments/${t.id}/results`)
        .then(res => res.ok ? res.json() : null)
        .then(data => {
          if (!data || !Array.isArray(data.final_files)) return;
          state.currentTournament.final_files = data.final_files;
          const updated = data.final_files.find(f => f.filename === filename);
          if (updated) {
            showFinalFile(updated.filename || filename, updated);
          }
        })
        .catch(() => {});
      return;
    }

    // Show in modal
    if (ui.entryModalTitle) ui.entryModalTitle.textContent = file.filename;
    if (ui.entryModalBody) {
      ui.entryModalBody.innerHTML = `<pre style="white-space: pre-wrap;">${escapeHtml(file.content)}</pre>`;
    }
    if (ui.entryModal) ui.entryModal.classList.add('active');
  }

  async function loadContainerDetail(containerId) {
    const t = state.currentTournament;
    if (!t) return;

    try {
      const res = await fetch(`/api/tournaments/${t.id}/containers/${containerId}`);
      if (!res.ok) return;
      state.currentContainer = await res.json();
      renderContainerDetail();
    } catch (e) {
      console.error('Failed to load container:', e);
    }
  }

  function renderContainerDetail() {
    const c = state.currentContainer;
    if (!c) return;

    if (ui.containerDetail) ui.containerDetail.classList.remove('is-hidden');
    if (ui.containerDetailTitle) ui.containerDetailTitle.textContent = c.id;
    if (ui.containerDetailStatus) {
      ui.containerDetailStatus.textContent = c.status;
      ui.containerDetailStatus.className = `status-pill status-${c.status}`;
    }

    // Render logs
    if (ui.containerLogs) {
      const logs = c.logs || [];
      if (logs.length === 0) {
        ui.containerLogs.innerHTML = '<div class="section-note">No logs yet.</div>';
      } else {
        ui.containerLogs.innerHTML = logs.map(log => `
          <div class="container-log-entry">
            <div class="container-log-time">${formatTime(log.timestamp)}</div>
            <div class="container-log-message">${escapeHtml(log.message)}</div>
            ${log.description ? `<div class="container-log-description">${escapeHtml(log.description)}</div>` : ''}
          </div>
        `).join('');
      }
    }

    // Render files
    if (ui.containerFiles) {
      const files = c.files || [];
      if (files.length === 0) {
        ui.containerFiles.innerHTML = '<div class="section-note">No files yet.</div>';
      } else {
        ui.containerFiles.innerHTML = files.map(f => `
          <div class="container-file-item">
            <div class="container-file-name">${escapeHtml(f.path || 'file')}</div>
            <div class="container-file-size">${formatFileSize(f.size || 0)}</div>
          </div>
        `).join('');
      }
    }

    // Render revealed files
    if (ui.containerRevealed) {
      const files = c.revealed_files || [];
      if (files.length === 0) {
        ui.containerRevealed.innerHTML = '<div class="section-note">No files revealed yet.</div>';
      } else {
        ui.containerRevealed.innerHTML = files.map(f => `
          <div class="container-file-item" data-filename="${f.filename}">
            <div class="container-file-name">${f.filename}</div>
            ${f.description ? `<div class="container-file-size">${f.description}</div>` : ''}
          </div>
        `).join('');
      }
    }

    // Setup container tab switching
    setupContainerTabs();
  }

  function setupContainerTabs() {
    const tabs = document.querySelectorAll('.container-tab');
    const panels = document.querySelectorAll('.container-tab-panel');

    tabs.forEach(tab => {
      tab.addEventListener('click', () => {
        const target = tab.dataset.containerTab;

        tabs.forEach(t => t.classList.remove('active'));
        panels.forEach(p => p.classList.remove('active'));

        tab.classList.add('active');
        const panel = document.querySelector(`[data-container-panel="${target}"]`);
        if (panel) panel.classList.add('active');
      });
    });
  }

  function backToTournamentList() {
    state.currentTournament = null;
    state.currentContainer = null;
    if (ui.tournamentDetail) ui.tournamentDetail.classList.add('is-hidden');
    if (ui.tournamentList) ui.tournamentList.classList.remove('is-hidden');
    fetchTournaments();
  }

  function backToRounds() {
    state.currentContainer = null;
    if (ui.containerDetail) ui.containerDetail.classList.add('is-hidden');
  }

  function showTournamentCreateForm() {
    if (ui.tournamentCreateForm) ui.tournamentCreateForm.classList.remove('is-hidden');
  }

  function hideTournamentCreateForm() {
    if (ui.tournamentCreateForm) ui.tournamentCreateForm.classList.add('is-hidden');
    if (ui.tournamentTopic) ui.tournamentTopic.value = '';
    if (ui.tournamentStages) ui.tournamentStages.value = '4, 3, 2';
    if (ui.tournamentRounds) ui.tournamentRounds.value = '2';
  }

  async function createTournament() {
    const topic = ui.tournamentTopic ? ui.tournamentTopic.value.trim() : '';
    const stagesStr = ui.tournamentStages ? ui.tournamentStages.value.trim() : '4, 3, 2';
    const debateRounds = ui.tournamentRounds ? parseInt(ui.tournamentRounds.value) : 2;

    if (!topic) {
      alert('Please enter a topic for the tournament.');
      return;
    }

    const stages = stagesStr.split(',').map(s => parseInt(s.trim())).filter(n => !isNaN(n) && n > 0);
    if (stages.length === 0) {
      alert('Please enter valid stages (e.g., 4, 3, 2)');
      return;
    }

    try {
      const res = await fetch('/api/tournaments', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          topic,
          stages,
          debate_rounds: debateRounds,
          auto_start: true
        })
      });

      if (!res.ok) {
        const err = await res.json();
        alert('Failed to create tournament: ' + (err.detail || 'Unknown error'));
        return;
      }

      const data = await res.json();
      hideTournamentCreateForm();
      loadTournamentDetail(data.tournament_id);
    } catch (e) {
      console.error('Failed to create tournament:', e);
      alert('Failed to create tournament: ' + e.message);
    }
  }

  function formatTime(isoString) {
    if (!isoString) return '';
    const date = new Date(isoString);
    return date.toLocaleTimeString();
  }

  // ==================== Files Tab ====================

  async function fetchFiles() {
    try {
      const res = await fetch('/api/files/main');
      if (!res.ok) return;
      const data = await res.json();
      state.files = data.files || [];
      renderFileTree();
    } catch (e) {
      console.error('Failed to fetch files:', e);
    }
  }

  function renderFileTree() {
    if (!ui.fileTree) return;

    if (state.files.length === 0) {
      ui.fileTree.innerHTML = '<div class="file-empty">No files yet.</div>';
      return;
    }

    // Group files by directory
    const filesByDir = {};
    state.files.forEach(file => {
      const parts = file.path.split('/');
      const dir = parts.length > 1 ? parts.slice(0, -1).join('/') : '';
      if (!filesByDir[dir]) filesByDir[dir] = [];
      filesByDir[dir].push(file);
    });

    // Render flat list for now
    ui.fileTree.innerHTML = state.files.map(file => {
      const icon = getFileIcon(file.extension);
      const sizeStr = formatFileSize(file.size);
      return `
        <div class="file-tree-item" data-path="${file.path}">
          <span class="file-tree-item-icon">${icon}</span>
          <span class="file-tree-item-name">${file.path}</span>
          <span class="file-tree-item-size">${sizeStr}</span>
        </div>
      `;
    }).join('');

    // Add click handlers
    ui.fileTree.querySelectorAll('.file-tree-item').forEach(item => {
      item.addEventListener('click', () => loadFilePreview(item.dataset.path));
    });
  }

  function getFileIcon(extension) {
    const icons = {
      '.md': '📄',
      '.py': '🐍',
      '.js': '📜',
      '.json': '{}',
      '.html': '🌐',
      '.css': '🎨',
      '.txt': '📝',
      '.yaml': '⚙️',
      '.yml': '⚙️'
    };
    return icons[extension] || '📁';
  }

  function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  }

  async function loadFilePreview(filePath) {
    // Update active state
    ui.fileTree.querySelectorAll('.file-tree-item').forEach(item => {
      item.classList.toggle('active', item.dataset.path === filePath);
    });

    try {
      const res = await fetch(`/api/files/main/${encodeURIComponent(filePath)}`);
      if (!res.ok) {
        if (ui.filePreviewContent) ui.filePreviewContent.textContent = 'Failed to load file.';
        return;
      }

      const data = await res.json();
      state.currentFile = data;

      if (ui.filePreviewName) ui.filePreviewName.textContent = data.path;
      if (ui.filePreviewMeta) ui.filePreviewMeta.textContent = formatFileSize(data.size);
      if (ui.filePreviewContent) ui.filePreviewContent.textContent = data.content;
    } catch (e) {
      console.error('Failed to load file:', e);
      if (ui.filePreviewContent) ui.filePreviewContent.textContent = 'Error loading file: ' + e.message;
    }
  }

  // ==================== Enhanced Logs ====================

  async function fetchEnhancedLogs() {
    try {
      const res = await fetch('/api/logs/enhanced?limit=100');
      if (!res.ok) return;
      const data = await res.json();
      state.enhancedLogs = data.logs || [];
      renderEnhancedLogs();
    } catch (e) {
      console.error('Failed to fetch enhanced logs:', e);
    }
  }

  function renderEnhancedLogs() {
    if (!ui.enhancedLogsList) return;

    if (state.enhancedLogs.length === 0) {
      ui.enhancedLogsList.innerHTML = '<div class="section-note">No enhanced logs yet.</div>';
      return;
    }

    ui.enhancedLogsList.innerHTML = state.enhancedLogs.map(log => {
      // Build tool details section
      let toolHtml = '';
      if (log.tool_name) {
        // Filter out tool_description from displayed args
        let displayArgs = log.tool_args;
        if (displayArgs && displayArgs.tool_description) {
          displayArgs = {...displayArgs};
          delete displayArgs.tool_description;
        }
        const argsStr = displayArgs && Object.keys(displayArgs).length > 0
          ? JSON.stringify(displayArgs, null, 2).substring(0, 300)
          : '';

        toolHtml = `
          <div class="enhanced-log-tool">
            <div class="enhanced-log-tool-name">${log.tool_name}</div>
            ${argsStr ? `<div class="enhanced-log-tool-args">${escapeHtml(argsStr)}</div>` : ''}
          </div>
        `;
      }

      // Description is the primary display element - shown prominently
      const descriptionHtml = log.description
        ? `<div class="enhanced-log-description-primary">${escapeHtml(log.description)}</div>`
        : '';

      return `
        <div class="enhanced-log-entry ${log.description ? 'has-description' : ''}">
          <div class="enhanced-log-header">
            <span class="enhanced-log-category ${log.category}">${log.category}</span>
            <span class="enhanced-log-time">${formatTime(log.timestamp)}</span>
          </div>
          ${descriptionHtml}
          <div class="enhanced-log-message">${escapeHtml(log.message)}</div>
          ${toolHtml}
        </div>
      `;
    }).join('');
  }

  function switchLogView(mode) {
    state.logViewMode = mode;

    if (ui.logsStandardBtn) ui.logsStandardBtn.classList.toggle('active', mode === 'standard');
    if (ui.logsEnhancedBtn) ui.logsEnhancedBtn.classList.toggle('active', mode === 'enhanced');

    if (mode === 'standard') {
      if (ui.logOutput) ui.logOutput.classList.remove('is-hidden');
      if (ui.enhancedLogs) ui.enhancedLogs.classList.add('is-hidden');
      fetchLogs();
    } else {
      if (ui.logOutput) ui.logOutput.classList.add('is-hidden');
      if (ui.enhancedLogs) ui.enhancedLogs.classList.remove('is-hidden');
      fetchEnhancedLogs();
    }
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

    // Factory reset modal
    if (ui.factoryResetBtn) ui.factoryResetBtn.addEventListener('click', showFactoryResetModal);
    if (ui.factoryResetModalClose) ui.factoryResetModalClose.addEventListener('click', closeFactoryResetModal);
    if (ui.factoryResetCancelBtn) ui.factoryResetCancelBtn.addEventListener('click', closeFactoryResetModal);
    if (ui.factoryResetConfirm) ui.factoryResetConfirm.addEventListener('change', updateFactoryResetActions);
    if (ui.factoryResetConfirmBtn) ui.factoryResetConfirmBtn.addEventListener('click', () => runFactoryReset(false));
    if (ui.factoryResetBackupBtn) ui.factoryResetBackupBtn.addEventListener('click', () => runFactoryReset(true));
    if (ui.factoryResetModal) {
      ui.factoryResetModal.addEventListener('click', (e) => {
        if (e.target === ui.factoryResetModal) closeFactoryResetModal();
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

    // Log view toggle
    if (ui.logsStandardBtn) ui.logsStandardBtn.addEventListener('click', () => switchLogView('standard'));
    if (ui.logsEnhancedBtn) ui.logsEnhancedBtn.addEventListener('click', () => switchLogView('enhanced'));

    // Tournament controls
    if (ui.tournamentCreateBtn) ui.tournamentCreateBtn.addEventListener('click', showTournamentCreateForm);
    if (ui.tournamentCancelBtn) ui.tournamentCancelBtn.addEventListener('click', hideTournamentCreateForm);
    if (ui.tournamentSubmitBtn) ui.tournamentSubmitBtn.addEventListener('click', createTournament);
    if (ui.tournamentBackBtn) ui.tournamentBackBtn.addEventListener('click', backToTournamentList);
    if (ui.containerBackBtn) ui.containerBackBtn.addEventListener('click', backToRounds);

    // Files controls
    if (ui.filesRefresh) ui.filesRefresh.addEventListener('click', fetchFiles);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
