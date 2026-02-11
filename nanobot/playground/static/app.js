/**
 * nanobot Playground — Frontend Application
 * Handles chat, model switching, custom endpoints, sessions, and UI interactions.
 */

// ============================================================
// State
// ============================================================

const state = {
    config: null,
    currentModel: '',
    currentProvider: '',
    sessionId: 'playground:default',
    isThinking: false,
    messageCount: 0,
    customEndpoint: null, // {url, key, model}
};

// Preset endpoint configurations
const ENDPOINT_PRESETS = {
    genplus_gemini: {
        name: 'GenPlus Gemini API',
        url: 'https://gemini-api.genplusmedia.com/v1/chat/completions',
        key: 'sk-gemini-93LP0t8JjG4o4oqEF5MzRQ',
        models: [
            { id: 'gemini-3.0-pro', name: 'Gemini 3.0 Pro' },
            { id: 'gemini-2.5-pro', name: 'Gemini 2.5 Pro' },
            { id: 'gemini-2.5-flash', name: 'Gemini 2.5 Flash' },
            { id: 'gemini-2.0-flash', name: 'Gemini 2.0 Flash' },
            { id: 'gemini-2.0-flash-thinking', name: 'Gemini 2.0 Flash Thinking' },
            { id: 'unspecified', name: 'Default Model' },
        ],
        defaultModel: 'gemini-3.0-pro',
    },
    pollinations: {
        name: 'Pollinations AI',
        url: 'https://gen.pollinations.ai/v1/chat/completions',
        key: 'plln_sk_CtcGj14XKaIKRXm8XeqguwQiQxmZ6a6tHAMMpdrhLTxiIomsp1Qv9U9nS6HfBviF',
        models: [
            { id: 'nova-fast', name: 'Amazon Nova Micro' },
            { id: 'qwen-coder', name: 'Qwen3 Coder 30B' },
            { id: 'mistral', name: 'Mistral Small 3.2 24B' },
            { id: 'gemini-fast', name: 'Google Gemini 2.5 Flash Lite' },
            { id: 'openai-fast', name: 'OpenAI GPT-5 Nano' },
            { id: 'openai', name: 'OpenAI GPT-5 Mini' },
            { id: 'grok', name: 'xAI Grok 4 Fast (Paid)' },
            { id: 'perplexity-fast', name: 'Perplexity Sonar' },
            { id: 'minimax', name: 'MiniMax M2.1' },
            { id: 'deepseek', name: 'DeepSeek V3.2' },
        ],
        defaultModel: 'gemini-fast',
    },
};

// ============================================================
// DOM refs
// ============================================================

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const els = {
    sidebar: $('#sidebar'),
    hamburger: $('#hamburger'),
    sidebarClose: $('#sidebarClose'),
    providerSelect: $('#providerSelect'),
    modelSelect: $('#modelSelect'),
    modelBadge: $('#modelBadge'),
    customModel: $('#customModel'),
    applyCustomModel: $('#applyCustomModel'),
    endpointPreset: $('#endpointPreset'),
    endpointUrl: $('#endpointUrl'),
    endpointKey: $('#endpointKey'),
    endpointModel: $('#endpointModel'),
    endpointModelSelect: $('#endpointModelSelect'),
    applyEndpoint: $('#applyEndpoint'),
    clearEndpoint: $('#clearEndpoint'),
    endpointStatus: $('#endpointStatus'),
    temperature: $('#temperature'),
    tempValue: $('#tempValue'),
    maxTokens: $('#maxTokens'),
    maxTokensValue: $('#maxTokensValue'),
    newSession: $('#newSession'),
    clearSession: $('#clearSession'),
    statusDot: null,
    statusText: null,
    headerModel: $('#headerModel'),
    themeToggle: $('#themeToggle'),
    themeIcon: $('#themeIcon'),
    messages: $('#messages'),
    welcome: $('#welcome'),
    messageInput: $('#messageInput'),
    sendBtn: $('#sendBtn'),
};

// ============================================================
// Init
// ============================================================

document.addEventListener('DOMContentLoaded', async () => {
    els.statusDot = $('.status-dot');
    els.statusText = $('.status-text');

    setupEventListeners();
    loadTheme();
    loadSavedEndpoint();
    await loadConfig();
});

// ============================================================
// API
// ============================================================

async function api(path, options = {}) {
    try {
        const resp = await fetch(path, {
            headers: { 'Content-Type': 'application/json' },
            ...options,
        });
        return await resp.json();
    } catch (err) {
        console.error(`API error (${path}):`, err);
        toast('Connection error', 'error');
        return null;
    }
}

// ============================================================
// Config / Providers / Models
// ============================================================

async function loadConfig() {
    const data = await api('/api/config');
    if (!data) return;

    state.config = data;
    state.currentModel = data.currentModel || '';
    state.currentProvider = data.currentProvider || '';

    // Populate providers
    els.providerSelect.innerHTML = '';
    const configured = (data.providers || []).filter(p => p.configured);

    if (configured.length === 0) {
        els.providerSelect.innerHTML = '<option value="">No providers configured</option>';
        return;
    }

    configured.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.name;
        opt.textContent = p.displayName;
        if (p.name === data.currentProvider) opt.selected = true;
        els.providerSelect.appendChild(opt);
    });

    // Populate models for current provider
    updateModelList(state.currentProvider || configured[0]?.name);

    // Set UI values
    els.temperature.value = data.temperature ?? 0.7;
    els.tempValue.textContent = data.temperature ?? 0.7;
    els.maxTokens.value = data.maxTokens ?? 8192;
    els.maxTokensValue.textContent = data.maxTokens ?? 8192;
    updateHeaderModel();
}

function updateModelList(providerName) {
    const provider = (state.config?.providers || []).find(p => p.name === providerName);
    els.modelSelect.innerHTML = '';

    if (!provider || !provider.models.length) {
        els.modelSelect.innerHTML = '<option value="">No models available</option>';
        return;
    }

    provider.models.forEach(m => {
        const opt = document.createElement('option');
        opt.value = m.id;
        opt.textContent = `${m.name}`;
        opt.title = m.description || '';
        if (m.id === state.currentModel) opt.selected = true;
        els.modelSelect.appendChild(opt);
    });

    // Update badge
    els.modelBadge.textContent = state.currentModel;
}

function updateHeaderModel() {
    const label = state.customEndpoint
        ? `⚡ ${state.currentModel}`
        : (state.currentModel || 'No model');
    els.headerModel.textContent = label;
}

async function switchModel(modelId) {
    if (!modelId) return;

    // If same model and no force, skip
    if (modelId === state.currentModel && !state.customEndpoint) return;

    const payload = {
        model: modelId,
        temperature: parseFloat(els.temperature.value),
        maxTokens: parseInt(els.maxTokens.value),
    };

    const data = await api('/api/model', {
        method: 'POST',
        body: JSON.stringify(payload),
    });

    if (data?.success) {
        state.currentModel = data.model;
        state.currentProvider = data.provider || state.currentProvider;
        state.customEndpoint = null; // Clear custom endpoint when switching to built-in
        els.modelBadge.textContent = data.model;
        updateEndpointStatusUI(false);
        updateHeaderModel();
        toast(`Switched to ${data.model}`, 'success');
    }
}

// Provider switch → auto-select first model and apply
async function switchProvider(providerName) {
    const provider = (state.config?.providers || []).find(p => p.name === providerName);
    if (!provider || !provider.models.length) return;

    // Update model list UI
    updateModelList(providerName);

    // Auto-select and apply the first model of this provider
    const firstModel = provider.models[0];
    if (firstModel) {
        els.modelSelect.value = firstModel.id;
        await switchModel(firstModel.id);
    }
}

// ============================================================
// Custom Endpoint
// ============================================================

async function applyCustomEndpoint() {
    const url = els.endpointUrl.value.trim();
    const key = els.endpointKey.value.trim();
    // Use model select if visible, otherwise text input
    const modelSelectVisible = els.endpointModelSelect.style.display !== 'none';
    const model = modelSelectVisible
        ? els.endpointModelSelect.value
        : els.endpointModel.value.trim();

    if (!url) {
        toast('Please enter API Base URL', 'error');
        return;
    }
    if (!model) {
        toast('Please enter model name', 'error');
        return;
    }

    // Send to server
    const data = await api('/api/endpoint', {
        method: 'POST',
        body: JSON.stringify({
            apiBase: url,
            apiKey: key,
            model: model,
        }),
    });

    if (data?.success) {
        const presetId = els.endpointPreset.value;
        state.customEndpoint = { url, key, model, preset: presetId };
        state.currentModel = data.model;
        state.currentProvider = 'custom';

        // Save to localStorage
        localStorage.setItem('nanobot-custom-endpoint', JSON.stringify({ url, key, model, preset: presetId }));

        updateEndpointStatusUI(true);
        updateHeaderModel();
        els.modelBadge.textContent = data.model;
        toast(`Connected: ${model}`, 'success');
    } else {
        toast(data?.error || 'Failed to connect', 'error');
    }
}

function clearCustomEndpoint() {
    state.customEndpoint = null;
    els.endpointPreset.value = '';
    els.endpointUrl.value = '';
    els.endpointKey.value = '';
    els.endpointModel.value = '';
    els.endpointModelSelect.style.display = 'none';
    els.endpointModel.style.display = '';
    localStorage.removeItem('nanobot-custom-endpoint');
    updateEndpointStatusUI(false);
    toast('Endpoint disconnected', 'success');

    // Switch back to default provider model
    const selectedProvider = els.providerSelect.value;
    if (selectedProvider) {
        switchProvider(selectedProvider);
    }
}

function loadSavedEndpoint() {
    try {
        const saved = localStorage.getItem('nanobot-custom-endpoint');
        if (saved) {
            const { url, key, model, preset } = JSON.parse(saved);
            if (preset && ENDPOINT_PRESETS[preset]) {
                els.endpointPreset.value = preset;
                selectEndpointPreset(preset);
            }
            els.endpointUrl.value = url || '';
            els.endpointKey.value = key || '';
            if (els.endpointModelSelect.style.display !== 'none') {
                els.endpointModelSelect.value = model || '';
            }
            els.endpointModel.value = model || '';
        }
    } catch { }
}

function updateEndpointStatusUI(connected) {
    if (els.endpointStatus) {
        els.endpointStatus.textContent = connected ? '🟢' : '';
    }
}

function selectEndpointPreset(presetId) {
    const preset = ENDPOINT_PRESETS[presetId];
    if (!preset) {
        // Manual / custom input
        els.endpointModelSelect.style.display = 'none';
        els.endpointModel.style.display = '';
        return;
    }

    // Fill URL and Key
    els.endpointUrl.value = preset.url;
    els.endpointKey.value = preset.key;

    // Populate model dropdown
    els.endpointModelSelect.innerHTML = '';
    preset.models.forEach(m => {
        const opt = document.createElement('option');
        opt.value = m.id;
        opt.textContent = m.name;
        if (m.id === preset.defaultModel) opt.selected = true;
        els.endpointModelSelect.appendChild(opt);
    });

    // Show dropdown, hide text input
    els.endpointModelSelect.style.display = '';
    els.endpointModel.style.display = 'none';
    els.endpointModel.value = preset.defaultModel;
}

// ============================================================
// Chat
// ============================================================

async function sendMessage() {
    const text = els.messageInput.value.trim();
    if (!text || state.isThinking) return;

    // Hide welcome
    if (els.welcome) {
        els.welcome.style.display = 'none';
    }

    // Add user message
    appendMessage('user', text);
    els.messageInput.value = '';
    autoResize(els.messageInput);

    // Show thinking
    setThinking(true);
    const thinkingEl = appendThinking();

    // Call API
    const data = await api('/api/chat', {
        method: 'POST',
        body: JSON.stringify({
            message: text,
            sessionId: state.sessionId,
            model: state.currentModel,
        }),
    });

    // Remove thinking
    thinkingEl?.remove();
    setThinking(false);

    if (data?.response) {
        appendMessage('assistant', data.response);
    } else if (data?.error) {
        appendMessage('assistant', `⚠️ Error: ${data.error}`);
    } else {
        appendMessage('assistant', '⚠️ Failed to get response.');
    }
}

function appendMessage(role, content) {
    state.messageCount++;
    const wrapper = document.createElement('div');
    wrapper.className = `message ${role}`;

    const avatar = role === 'user' ? '👤' : '🦉';
    const label = role === 'user' ? 'You' : 'GenBot';

    let rendered = content;
    if (role === 'assistant') {
        try {
            rendered = marked.parse(content, { breaks: true });
        } catch { rendered = escapeHtml(content); }
    } else {
        rendered = escapeHtml(content);
    }

    wrapper.innerHTML = `
        <div class="message-avatar">${avatar}</div>
        <div class="message-body">
            <div class="message-role">${label}</div>
            <div class="message-content">${rendered}</div>
        </div>
    `;

    els.messages.appendChild(wrapper);

    // Highlight code blocks
    wrapper.querySelectorAll('pre code').forEach(block => {
        hljs.highlightElement(block);
    });

    // Add copy buttons to code blocks
    wrapper.querySelectorAll('pre').forEach(pre => {
        addCopyButton(pre);
    });

    scrollToBottom();
}

function appendThinking() {
    const el = document.createElement('div');
    el.className = 'message assistant';
    el.id = 'thinking-msg';
    el.innerHTML = `
        <div class="message-avatar">🦉</div>
        <div class="message-body">
            <div class="message-role">GenBot</div>
            <div class="thinking-dots">
                <span></span><span></span><span></span>
            </div>
        </div>
    `;
    els.messages.appendChild(el);
    scrollToBottom();
    return el;
}

function setThinking(thinking) {
    state.isThinking = thinking;
    els.sendBtn.disabled = thinking;

    if (els.statusDot) {
        els.statusDot.className = thinking ? 'status-dot thinking' : 'status-dot';
    }
    if (els.statusText) {
        els.statusText.textContent = thinking ? 'Thinking...' : 'Ready';
    }
}

function scrollToBottom() {
    requestAnimationFrame(() => {
        els.messages.scrollTop = els.messages.scrollHeight;
    });
}

function addCopyButton(pre) {
    const code = pre.querySelector('code');
    if (!code) return;

    // Detect language
    const langClass = Array.from(code.classList).find(c => c.startsWith('language-'));
    const lang = langClass ? langClass.replace('language-', '') : 'code';

    const header = document.createElement('div');
    header.className = 'code-header';
    header.innerHTML = `
        <span>${lang}</span>
        <button class="copy-btn" onclick="copyCode(this)">Copy</button>
    `;

    pre.parentNode.insertBefore(header, pre);
    pre.style.borderTopLeftRadius = '0';
    pre.style.borderTopRightRadius = '0';
    pre.style.marginTop = '0';
    header.style.marginTop = '10px';
}

window.copyCode = function (btn) {
    const pre = btn.closest('.code-header').nextElementSibling;
    const code = pre?.querySelector('code') || pre;
    navigator.clipboard.writeText(code.textContent).then(() => {
        btn.textContent = 'Copied!';
        setTimeout(() => { btn.textContent = 'Copy'; }, 2000);
    });
};

// ============================================================
// Sessions
// ============================================================

function newSession() {
    state.sessionId = `playground:${Date.now()}`;
    state.messageCount = 0;

    // Clear chat display
    els.messages.innerHTML = '';
    const welcome = document.createElement('div');
    welcome.className = 'welcome';
    welcome.id = 'welcome';
    welcome.innerHTML = `
        <div class="welcome-icon">🦉</div>
        <h2>New Conversation</h2>
        <p>Start chatting with a fresh context.</p>
    `;
    els.messages.appendChild(welcome);

    toast('New chat started', 'success');
}

async function clearSession() {
    await api('/api/sessions/clear', {
        method: 'POST',
        body: JSON.stringify({ sessionId: state.sessionId }),
    });
    newSession();
}

// ============================================================
// Theme
// ============================================================

function loadTheme() {
    const saved = localStorage.getItem('nanobot-theme') || 'dark';
    document.documentElement.setAttribute('data-theme', saved);
    els.themeIcon.textContent = saved === 'dark' ? '🌙' : '☀️';
}

function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('nanobot-theme', next);
    els.themeIcon.textContent = next === 'dark' ? '🌙' : '☀️';
}

// ============================================================
// UI Helpers
// ============================================================

function toast(msg, type = 'success') {
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => {
        el.style.animation = 'toastOut 0.3s forwards';
        setTimeout(() => el.remove(), 300);
    }, 3000);
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
}

function autoResize(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 160) + 'px';
}

function toggleSidebar(show) {
    els.sidebar.classList.toggle('open', show);
    let overlay = $('.sidebar-overlay');
    if (show && !overlay) {
        overlay = document.createElement('div');
        overlay.className = 'sidebar-overlay show';
        overlay.addEventListener('click', () => toggleSidebar(false));
        document.body.appendChild(overlay);
    } else if (!show && overlay) {
        overlay.remove();
    }
}

// ============================================================
// Event Listeners
// ============================================================

function setupEventListeners() {
    // Sidebar toggle
    els.hamburger.addEventListener('click', () => toggleSidebar(true));
    els.sidebarClose.addEventListener('click', () => toggleSidebar(false));

    // Provider change → auto-switch to first model
    els.providerSelect.addEventListener('change', (e) => {
        if (e.target.value) switchProvider(e.target.value);
    });

    // Model change → auto-apply
    els.modelSelect.addEventListener('change', (e) => {
        if (e.target.value) switchModel(e.target.value);
    });

    // Custom model
    els.applyCustomModel.addEventListener('click', () => {
        const val = els.customModel.value.trim();
        if (val) switchModel(val);
    });
    els.customModel.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            const val = els.customModel.value.trim();
            if (val) switchModel(val);
        }
    });

    // Custom endpoint
    els.endpointPreset.addEventListener('change', (e) => {
        selectEndpointPreset(e.target.value);
    });
    els.endpointModelSelect.addEventListener('change', (e) => {
        els.endpointModel.value = e.target.value;
    });
    els.applyEndpoint.addEventListener('click', applyCustomEndpoint);
    els.clearEndpoint.addEventListener('click', clearCustomEndpoint);

    // Temperature
    els.temperature.addEventListener('input', (e) => {
        els.tempValue.textContent = parseFloat(e.target.value).toFixed(1);
    });

    // Max tokens
    els.maxTokens.addEventListener('input', (e) => {
        els.maxTokensValue.textContent = e.target.value;
    });

    // Sessions
    els.newSession.addEventListener('click', newSession);
    els.clearSession.addEventListener('click', clearSession);

    // Theme
    els.themeToggle.addEventListener('click', toggleTheme);

    // Send message
    els.sendBtn.addEventListener('click', sendMessage);

    // Textarea
    els.messageInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    els.messageInput.addEventListener('input', () => {
        autoResize(els.messageInput);
    });

    // Quick prompts
    $$('.quick-prompt').forEach(btn => {
        btn.addEventListener('click', () => {
            els.messageInput.value = btn.dataset.prompt;
            sendMessage();
        });
    });
}
