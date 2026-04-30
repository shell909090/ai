/** @type {WebSocket | null} */
let ws = null;
/** @type {string | null} */
let sessionId = null;
/** @type {boolean} */
let isProcessing = false;

const chatContainer = document.getElementById('chat-container');
const messageInput = document.getElementById('message-input');
const sendBtn = document.getElementById('send-btn');
const statusEl = document.getElementById('status');
const sessionInfo = document.getElementById('session-info');
const permissionModal = document.getElementById('permission-modal');
const permissionText = document.getElementById('permission-text');
const permAllowBtn = document.getElementById('perm-allow');
const permDenyBtn = document.getElementById('perm-deny');

/** @type {string | null} */
let pendingPermId = null;

function connect() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

    ws.onopen = () => {
        statusEl.textContent = 'Connected';
        messageInput.disabled = false;
        sendBtn.disabled = false;
        createSession();
    };

    ws.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            handleMessage(msg);
        } catch {
            console.error('Invalid JSON from server');
        }
    };

    ws.onclose = () => {
        statusEl.textContent = 'Disconnected - reconnecting...';
        messageInput.disabled = true;
        sendBtn.disabled = true;
        setTimeout(connect, 2000);
    };

    ws.onerror = () => {
        statusEl.textContent = 'Connection error';
    };
}

function createSession() {
    sendMessage({ type: 'session/new' });
}

/**
 * @param {object} msg
 */
function sendMessage(msg) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(msg));
    }
}

/**
 * @param {object} msg
 */
function handleMessage(msg) {
    switch (msg.type) {
        case 'session/new_response':
            sessionId = msg.session_id;
            sessionInfo.textContent = `Session: ${sessionId?.slice(0, 8) ?? 'unknown'}...`;
            break;
        case 'session/prompt_response':
            isProcessing = false;
            updateInputState();
            if (msg.text) {
                appendMessage('agent', msg.text);
            }
            break;
        case 'session/update':
            handleUpdate(msg.update);
            break;
        case 'session/request_permission':
            showPermissionModal(msg.id, msg.kind, msg.payload);
            break;
        case 'error':
            isProcessing = false;
            updateInputState();
            appendMessage('agent', `Error: ${msg.error}`);
            break;
    }
}

/**
 * @param {object} update
 */
function handleUpdate(update) {
    switch (update.type) {
        case 'agent_message_chunk':
            appendOrUpdateMessage('agent', String(update.data?.text ?? ''), 'Agent');
            break;
        case 'thinking_chunk':
            appendOrUpdateMessage('thinking', String(update.data?.text ?? ''), 'Thinking');
            break;
        case 'tool_call': {
            const calls = update.data?.calls ?? {};
            for (const [callId, callData] of Object.entries(calls)) {
                const toolName = callData?.tool_name ?? 'unknown';
                const args = JSON.stringify(callData?.arguments ?? {});
                appendMessage('tool-call', `${callId}: ${toolName}\n${args}`);
            }
            break;
        }
        case 'tool_call_update': {
            const status = update.data?.status ?? 'unknown';
            const content = update.data?.content ?? '';
            const callId = update.data?.call_id ?? '';
            appendMessage('tool-result', `${callId}: ${status}\n${content}`);
            break;
        }
    }
}

/**
 * @param {string} type
 * @param {string} text
 * @param {string} [label]
 */
function appendOrUpdateMessage(type, text, label) {
    const lastMsg = chatContainer.lastElementChild;
    if (lastMsg && lastMsg.dataset.type === type && lastMsg.dataset.streaming === 'true') {
        const contentEl = lastMsg.querySelector('.content');
        if (contentEl) {
            contentEl.textContent += text;
        }
        chatContainer.scrollTop = chatContainer.scrollHeight;
        return;
    }
    const div = document.createElement('div');
    div.className = `message ${type}`;
    div.dataset.type = type;
    div.dataset.streaming = 'true';
    if (label) {
        const labelEl = document.createElement('div');
        labelEl.className = 'label';
        labelEl.textContent = label;
        div.appendChild(labelEl);
    }
    const contentEl = document.createElement('div');
    contentEl.className = 'content';
    contentEl.textContent = text;
    div.appendChild(contentEl);
    chatContainer.appendChild(div);
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

/**
 * @param {string} type
 * @param {string} text
 */
function appendMessage(type, text) {
    const lastMsg = chatContainer.lastElementChild;
    if (lastMsg && lastMsg.dataset.streaming === 'true') {
        lastMsg.dataset.streaming = 'false';
    }
    const div = document.createElement('div');
    div.className = `message ${type}`;
    div.dataset.type = type;
    div.dataset.streaming = 'false';
    const contentEl = document.createElement('div');
    contentEl.className = 'content';
    contentEl.textContent = text;
    div.appendChild(contentEl);
    chatContainer.appendChild(div);
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

function updateInputState() {
    messageInput.disabled = isProcessing;
    sendBtn.disabled = isProcessing;
    if (isProcessing) {
        statusEl.textContent = 'Processing...';
    } else {
        statusEl.textContent = 'Connected';
    }
}

function sendPrompt() {
    const text = messageInput.value.trim();
    if (!text || !sessionId || isProcessing) return;

    appendMessage('user', text);
    messageInput.value = '';
    isProcessing = true;
    updateInputState();

    sendMessage({
        type: 'session/prompt',
        session_id: sessionId,
        prompt: text,
    });
}

sendBtn.addEventListener('click', sendPrompt);
messageInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') sendPrompt();
});

/**
 * @param {string} reqId
 * @param {string} kind
 * @param {object} payload
 */
function showPermissionModal(reqId, kind, payload) {
    pendingPermId = reqId;
    const args = JSON.stringify(payload?.arguments ?? {});
    permissionText.textContent = `Allow tool "${kind}" with arguments: ${args}`;
    permissionModal.classList.add('active');
}

function hidePermissionModal() {
    permissionModal.classList.remove('active');
    pendingPermId = null;
}

permAllowBtn.addEventListener('click', () => {
    if (pendingPermId) {
        sendMessage({
            type: 'session/permission_response',
            id: pendingPermId,
            granted: true,
        });
    }
    hidePermissionModal();
});

permDenyBtn.addEventListener('click', () => {
    if (pendingPermId) {
        sendMessage({
            type: 'session/permission_response',
            id: pendingPermId,
            granted: false,
        });
    }
    hidePermissionModal();
});

connect();
