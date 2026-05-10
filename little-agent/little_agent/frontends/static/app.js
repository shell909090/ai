"use strict";
// WebSocket message payload types
let ws = null;
let sessionId = null;
let isProcessing = false;
const chatContainer = document.getElementById("chat-container");
const messageInput = document.getElementById("message-input");
const sendBtn = document.getElementById("send-btn");
const cancelBtn = document.getElementById("cancelButton");
const statusEl = document.getElementById("status");
const sessionInfo = document.getElementById("session-info");
const permissionModal = document.getElementById("permission-modal");
const permissionText = document.getElementById("permission-text");
const permAllowBtn = document.getElementById("perm-allow");
const permDenyBtn = document.getElementById("perm-deny");
let pendingPermId = null;
function connect() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${protocol}//${window.location.host}/ws`);
    ws.onopen = () => {
        statusEl.textContent = "Connected";
        messageInput.disabled = false;
        sendBtn.disabled = false;
        createSession();
    };
    ws.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            handleMessage(msg);
        }
        catch (_a) {
            console.error("Invalid JSON from server");
        }
    };
    ws.onclose = () => {
        statusEl.textContent = "Disconnected - reconnecting...";
        messageInput.disabled = true;
        sendBtn.disabled = true;
        setTimeout(connect, 2000);
    };
    ws.onerror = () => {
        statusEl.textContent = "Connection error";
        isProcessing = false;
        sendBtn.disabled = false;
        messageInput.disabled = false;
        cancelBtn.style.display = "none";
    };
}
function createSession() {
    sendMessage({ type: "session/new" });
}
function sendMessage(msg) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(msg));
    }
}
function handleMessage(msg) {
    var _a;
    switch (msg.type) {
        case "session/new_response":
            sessionId = msg.session_id;
            sessionInfo.textContent = `Session: ${(_a = sessionId === null || sessionId === void 0 ? void 0 : sessionId.slice(0, 8)) !== null && _a !== void 0 ? _a : "unknown"}...`;
            break;
        case "session/prompt_response":
            isProcessing = false;
            updateInputState();
            if (msg.text) {
                appendMessage("agent", msg.text);
            }
            break;
        case "session/update":
            handleUpdate(msg.update);
            break;
        case "session/request_permission":
            showPermissionModal(msg.id, msg.kind, msg.payload);
            break;
        case "error":
            isProcessing = false;
            updateInputState();
            appendMessage("agent", `Error: ${msg.error}`);
            break;
    }
}
function handleUpdate(update) {
    var _a, _b, _c, _d, _e, _f, _g, _h, _j, _k, _l, _m, _o, _p;
    switch (update.type) {
        case "agent_message_chunk":
            appendOrUpdateMessage("agent", String((_b = (_a = update.data) === null || _a === void 0 ? void 0 : _a.text) !== null && _b !== void 0 ? _b : ""), "Agent");
            break;
        case "thinking_chunk":
            appendOrUpdateMessage("thinking", String((_d = (_c = update.data) === null || _c === void 0 ? void 0 : _c.text) !== null && _d !== void 0 ? _d : ""), "Thinking");
            break;
        case "tool_call": {
            const calls = (_f = (_e = update.data) === null || _e === void 0 ? void 0 : _e.calls) !== null && _f !== void 0 ? _f : {};
            for (const [callId, callData] of Object.entries(calls)) {
                const toolName = (_g = callData === null || callData === void 0 ? void 0 : callData.tool_name) !== null && _g !== void 0 ? _g : "unknown";
                const args = JSON.stringify((_h = callData === null || callData === void 0 ? void 0 : callData.arguments) !== null && _h !== void 0 ? _h : {});
                appendMessage("tool-call", `${callId}: ${String(toolName)}\n${args}`);
            }
            break;
        }
        case "tool_call_update": {
            const status = (_k = (_j = update.data) === null || _j === void 0 ? void 0 : _j.status) !== null && _k !== void 0 ? _k : "unknown";
            const content = (_m = (_l = update.data) === null || _l === void 0 ? void 0 : _l.content) !== null && _m !== void 0 ? _m : "";
            const callId = (_p = (_o = update.data) === null || _o === void 0 ? void 0 : _o.call_id) !== null && _p !== void 0 ? _p : "";
            appendMessage("tool-result", `${String(callId)}: ${String(status)}\n${String(content)}`);
            break;
        }
    }
}
function appendOrUpdateMessage(type, text, label) {
    const lastMsg = chatContainer.lastElementChild;
    if (lastMsg && lastMsg.dataset.type === type && lastMsg.dataset.streaming === "true") {
        const contentEl = lastMsg.querySelector(".content");
        if (contentEl) {
            contentEl.textContent += text;
        }
        const isNearBottom = chatContainer.scrollHeight - chatContainer.scrollTop - chatContainer.clientHeight <= 50;
        if (isNearBottom) {
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }
        return;
    }
    const div = document.createElement("div");
    div.className = `message ${type}`;
    div.dataset.type = type;
    div.dataset.streaming = "true";
    if (label) {
        const labelEl = document.createElement("div");
        labelEl.className = "label";
        labelEl.textContent = label;
        div.appendChild(labelEl);
    }
    const contentEl = document.createElement("div");
    contentEl.className = "content";
    contentEl.textContent = text;
    div.appendChild(contentEl);
    chatContainer.appendChild(div);
    const isNearBottom2 = chatContainer.scrollHeight - chatContainer.scrollTop - chatContainer.clientHeight <= 50;
    if (isNearBottom2) {
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }
}
function appendMessage(type, text) {
    const lastMsg = chatContainer.lastElementChild;
    if (lastMsg && lastMsg.dataset.streaming === "true") {
        lastMsg.dataset.streaming = "false";
    }
    const div = document.createElement("div");
    div.className = `message ${type}`;
    div.dataset.type = type;
    div.dataset.streaming = "false";
    const contentEl = document.createElement("div");
    contentEl.className = "content";
    contentEl.textContent = text;
    div.appendChild(contentEl);
    chatContainer.appendChild(div);
    const isNearBottom = chatContainer.scrollHeight - chatContainer.scrollTop - chatContainer.clientHeight <= 50;
    if (isNearBottom) {
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }
}
function updateInputState() {
    messageInput.disabled = isProcessing;
    sendBtn.disabled = isProcessing;
    cancelBtn.style.display = isProcessing ? "inline-block" : "none";
    if (isProcessing) {
        statusEl.textContent = "Processing...";
    }
    else {
        statusEl.textContent = "Connected";
    }
}
function sendPrompt() {
    const text = messageInput.value.trim();
    if (!text || !sessionId || isProcessing)
        return;
    appendMessage("user", text);
    messageInput.value = "";
    isProcessing = true;
    updateInputState();
    sendMessage({
        type: "session/prompt",
        session_id: sessionId,
        prompt: text,
    });
}
sendBtn.addEventListener("click", sendPrompt);
messageInput.addEventListener("keypress", (e) => {
    if (e.key === "Enter")
        sendPrompt();
});
cancelBtn.addEventListener("click", () => {
    if (sessionId) {
        sendMessage({ type: "session/cancel", session_id: sessionId });
    }
});
function showPermissionModal(reqId, kind, payload) {
    var _a;
    pendingPermId = reqId;
    const args = JSON.stringify((_a = payload === null || payload === void 0 ? void 0 : payload.arguments) !== null && _a !== void 0 ? _a : {});
    permissionText.textContent = `Allow tool "${kind}" with arguments: ${args}`;
    permissionModal.classList.add("active");
}
function hidePermissionModal() {
    permissionModal.classList.remove("active");
    pendingPermId = null;
}
permAllowBtn.addEventListener("click", () => {
    if (pendingPermId) {
        sendMessage({
            type: "session/permission_response",
            id: pendingPermId,
            granted: true,
        });
    }
    hidePermissionModal();
});
permDenyBtn.addEventListener("click", () => {
    if (pendingPermId) {
        sendMessage({
            type: "session/permission_response",
            id: pendingPermId,
            granted: false,
        });
    }
    hidePermissionModal();
});
connect();
