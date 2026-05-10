// WebSocket message payload types

interface SessionNewResponseMsg {
    type: "session/new_response";
    session_id: string;
}

interface SessionPromptResponseMsg {
    type: "session/prompt_response";
    text?: string;
}

interface AgentMessageChunkUpdate {
    type: "agent_message_chunk";
    data?: { text?: unknown };
}

interface ThinkingChunkUpdate {
    type: "thinking_chunk";
    data?: { text?: unknown };
}

interface CallData {
    tool_name?: unknown;
    arguments?: unknown;
}

interface ToolCallUpdate {
    type: "tool_call";
    data?: { calls?: Record<string, CallData> };
}

interface ToolCallUpdateMsg {
    type: "tool_call_update";
    data?: { status?: unknown; content?: unknown; call_id?: unknown };
}

type SessionUpdatePayload =
    | AgentMessageChunkUpdate
    | ThinkingChunkUpdate
    | ToolCallUpdate
    | ToolCallUpdateMsg;

interface SessionUpdateMsg {
    type: "session/update";
    update: SessionUpdatePayload;
}

interface SessionRequestPermissionMsg {
    type: "session/request_permission";
    id: string;
    kind: string;
    payload?: { arguments?: unknown };
}

interface ErrorMsg {
    type: "error";
    error: string;
}

type ServerMessage =
    | SessionNewResponseMsg
    | SessionPromptResponseMsg
    | SessionUpdateMsg
    | SessionRequestPermissionMsg
    | ErrorMsg;

interface ClientMessage {
    type: string;
    [key: string]: unknown;
}

let ws: WebSocket | null = null;
let sessionId: string | null = null;
let isProcessing: boolean = false;

const chatContainer = document.getElementById("chat-container") as HTMLDivElement;
const messageInput = document.getElementById("message-input") as HTMLInputElement;
const sendBtn = document.getElementById("send-btn") as HTMLButtonElement;
const cancelBtn = document.getElementById("cancelButton") as HTMLButtonElement;
const statusEl = document.getElementById("status") as HTMLDivElement;
const sessionInfo = document.getElementById("session-info") as HTMLDivElement;
const permissionModal = document.getElementById("permission-modal") as HTMLDivElement;
const permissionText = document.getElementById("permission-text") as HTMLParagraphElement;
const permAllowBtn = document.getElementById("perm-allow") as HTMLButtonElement;
const permDenyBtn = document.getElementById("perm-deny") as HTMLButtonElement;

let pendingPermId: string | null = null;

function connect(): void {
    const protocol: string = window.location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

    ws.onopen = (): void => {
        statusEl.textContent = "Connected";
        messageInput.disabled = false;
        sendBtn.disabled = false;
        createSession();
    };

    ws.onmessage = (event: MessageEvent): void => {
        try {
            const msg: ServerMessage = JSON.parse(event.data as string) as ServerMessage;
            handleMessage(msg);
        } catch {
            console.error("Invalid JSON from server");
        }
    };

    ws.onclose = (): void => {
        statusEl.textContent = "Disconnected - reconnecting...";
        messageInput.disabled = true;
        sendBtn.disabled = true;
        setTimeout(connect, 2000);
    };

    ws.onerror = (): void => {
        statusEl.textContent = "Connection error";
        isProcessing = false;
        sendBtn.disabled = false;
        messageInput.disabled = false;
        cancelBtn.style.display = "none";
    };
}

function createSession(): void {
    sendMessage({ type: "session/new" });
}

function sendMessage(msg: ClientMessage): void {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(msg));
    }
}

function handleMessage(msg: ServerMessage): void {
    switch (msg.type) {
        case "session/new_response":
            sessionId = msg.session_id;
            sessionInfo.textContent = `Session: ${sessionId?.slice(0, 8) ?? "unknown"}...`;
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

function handleUpdate(update: SessionUpdatePayload): void {
    switch (update.type) {
        case "agent_message_chunk":
            appendOrUpdateMessage("agent", String(update.data?.text ?? ""), "Agent");
            break;
        case "thinking_chunk":
            appendOrUpdateMessage("thinking", String(update.data?.text ?? ""), "Thinking");
            break;
        case "tool_call": {
            const calls: Record<string, CallData> = update.data?.calls ?? {};
            for (const [callId, callData] of Object.entries(calls)) {
                const toolName: unknown = callData?.tool_name ?? "unknown";
                const args: string = JSON.stringify(callData?.arguments ?? {});
                appendMessage("tool-call", `${callId}: ${String(toolName)}\n${args}`);
            }
            break;
        }
        case "tool_call_update": {
            const status: unknown = update.data?.status ?? "unknown";
            const content: unknown = update.data?.content ?? "";
            const callId: unknown = update.data?.call_id ?? "";
            appendMessage("tool-result", `${String(callId)}: ${String(status)}\n${String(content)}`);
            break;
        }
    }
}

function appendOrUpdateMessage(type: string, text: string, label?: string): void {
    const lastMsg = chatContainer.lastElementChild as HTMLElement | null;
    if (lastMsg && lastMsg.dataset.type === type && lastMsg.dataset.streaming === "true") {
        const contentEl = lastMsg.querySelector(".content");
        if (contentEl) {
            contentEl.textContent += text;
        }
        const isNearBottom: boolean =
            chatContainer.scrollHeight - chatContainer.scrollTop - chatContainer.clientHeight <= 50;
        if (isNearBottom) {
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }
        return;
    }
    const div: HTMLDivElement = document.createElement("div");
    div.className = `message ${type}`;
    div.dataset.type = type;
    div.dataset.streaming = "true";
    if (label) {
        const labelEl: HTMLDivElement = document.createElement("div");
        labelEl.className = "label";
        labelEl.textContent = label;
        div.appendChild(labelEl);
    }
    const contentEl: HTMLDivElement = document.createElement("div");
    contentEl.className = "content";
    contentEl.textContent = text;
    div.appendChild(contentEl);
    chatContainer.appendChild(div);
    const isNearBottom2: boolean =
        chatContainer.scrollHeight - chatContainer.scrollTop - chatContainer.clientHeight <= 50;
    if (isNearBottom2) {
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }
}

function appendMessage(type: string, text: string): void {
    const lastMsg = chatContainer.lastElementChild as HTMLElement | null;
    if (lastMsg && lastMsg.dataset.streaming === "true") {
        lastMsg.dataset.streaming = "false";
    }
    const div: HTMLDivElement = document.createElement("div");
    div.className = `message ${type}`;
    div.dataset.type = type;
    div.dataset.streaming = "false";
    const contentEl: HTMLDivElement = document.createElement("div");
    contentEl.className = "content";
    contentEl.textContent = text;
    div.appendChild(contentEl);
    chatContainer.appendChild(div);
    const isNearBottom: boolean =
        chatContainer.scrollHeight - chatContainer.scrollTop - chatContainer.clientHeight <= 50;
    if (isNearBottom) {
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }
}

function updateInputState(): void {
    messageInput.disabled = isProcessing;
    sendBtn.disabled = isProcessing;
    cancelBtn.style.display = isProcessing ? "inline-block" : "none";
    if (isProcessing) {
        statusEl.textContent = "Processing...";
    } else {
        statusEl.textContent = "Connected";
    }
}

function sendPrompt(): void {
    const text: string = messageInput.value.trim();
    if (!text || !sessionId || isProcessing) return;

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
messageInput.addEventListener("keypress", (e: KeyboardEvent): void => {
    if (e.key === "Enter") sendPrompt();
});
cancelBtn.addEventListener("click", (): void => {
    if (sessionId) {
        sendMessage({ type: "session/cancel", session_id: sessionId });
    }
});

function showPermissionModal(
    reqId: string,
    kind: string,
    payload: { arguments?: unknown } | undefined
): void {
    pendingPermId = reqId;
    const args: string = JSON.stringify(payload?.arguments ?? {});
    permissionText.textContent = `Allow tool "${kind}" with arguments: ${args}`;
    permissionModal.classList.add("active");
}

function hidePermissionModal(): void {
    permissionModal.classList.remove("active");
    pendingPermId = null;
}

permAllowBtn.addEventListener("click", (): void => {
    if (pendingPermId) {
        sendMessage({
            type: "session/permission_response",
            id: pendingPermId,
            granted: true,
        });
    }
    hidePermissionModal();
});

permDenyBtn.addEventListener("click", (): void => {
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
