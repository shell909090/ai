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
    session_id?: string;
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

interface SessionInfo {
    id: string;
    updated_at: string;
    preview: string;
}

interface SessionListResponseMsg {
    type: "session/list_response";
    sessions: SessionInfo[];
}

interface SessionHistoryNode {
    kind: string;
    id: string;
    created_at?: string;
    prompt?: string;
    text?: string;
    output_text?: string;
    calls?: Record<string, unknown>;
    results?: Record<string, unknown>;
}

interface SessionHistoryMsg {
    type: "session/history";
    session_id: string;
    nodes: SessionHistoryNode[];
}

interface SessionForkResponseMsg {
    type: "session/fork_response";
    session_id: string;
}

interface SessionDeleteResponseMsg {
    type: "session/delete_response";
    session_id: string;
}

type ServerMessage =
    | SessionNewResponseMsg
    | SessionPromptResponseMsg
    | SessionUpdateMsg
    | SessionRequestPermissionMsg
    | ErrorMsg
    | SessionListResponseMsg
    | SessionHistoryMsg
    | SessionForkResponseMsg
    | SessionDeleteResponseMsg;

interface ClientMessage {
    type: string;
    [key: string]: unknown;
}

let ws: WebSocket | null = null;
let sessionId: string | null = null;
let isProcessing: boolean = false;
let sessionList: SessionInfo[] = [];

// Track live tool-call bubbles by call_id so tool_call_update can recolor them.
const toolCallElements: Map<string, HTMLDivElement> = new Map();

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
const sessionListEl = document.getElementById("session-list") as HTMLDivElement;

let pendingPermId: string | null = null;

// --- Formatting helpers ---

function formatArgs(args: Record<string, unknown>): string {
    const lines: string[] = [];
    for (const [k, v] of Object.entries(args)) {
        const val = typeof v === "string" ? v : JSON.stringify(v, null, 2);
        lines.push(`${k}: ${val}`);
    }
    return lines.join("\n");
}

function formatResult(content: unknown, maxLines: number = 20): string {
    let text: string;
    if (typeof content === "string") {
        text = content;
    } else if (content !== null && typeof content === "object") {
        const obj = content as Record<string, unknown>;
        text = Object.entries(obj)
            .map(([k, v]) => `${k}: ${typeof v === "string" ? v : JSON.stringify(v)}`)
            .join("\n");
    } else {
        text = String(content ?? "");
    }
    const lines = text.split("\n");
    if (lines.length > maxLines) {
        return lines.slice(0, maxLines).join("\n") + `\n...${lines.length - maxLines} more lines...`;
    }
    return text;
}

// --- Tool call bubble helpers ---

function createToolCallBubble(callId: string, callData: CallData): HTMLDivElement {
    const div = document.createElement("div");
    div.className = "message tool-call";
    div.dataset.type = "tool-call";
    div.dataset.callId = callId;
    div.dataset.streaming = "false";

    const toolName = String(callData?.tool_name ?? "unknown");

    const label = document.createElement("div");
    label.className = "label";
    label.textContent = toolName;
    div.appendChild(label);

    const details = document.createElement("details");
    const summary = document.createElement("summary");
    summary.className = "tool-call-summary";
    summary.textContent = callId;
    details.appendChild(summary);

    // eslint-disable-next-line @typescript-eslint/no-unnecessary-type-assertion
    const args = (callData?.arguments ?? {}) as Record<string, unknown>;
    const argsText = formatArgs(args);
    if (argsText) {
        const argsDiv = document.createElement("div");
        argsDiv.className = "content tool-args-content";
        argsDiv.textContent = argsText;
        details.appendChild(argsDiv);
    }

    div.appendChild(details);
    return div;
}

function updateToolCallBubble(elem: HTMLDivElement, status: string, content: unknown): void {
    elem.classList.remove("tool-call");
    if (status === "completed") {
        elem.classList.add("tool-call-completed");
    } else if (status === "failed") {
        elem.classList.add("tool-call-failed");
    } else {
        elem.classList.add("tool-call-cancelled");
    }

    const details = elem.querySelector("details");
    if (details && content !== undefined && content !== null && content !== "") {
        const resultDiv = document.createElement("div");
        resultDiv.className = "content tool-result-content";
        resultDiv.textContent = formatResult(content);
        details.appendChild(resultDiv);
    }
}

// --- Scroll helper ---

function scrollIfNearBottom(): void {
    const isNearBottom =
        chatContainer.scrollHeight - chatContainer.scrollTop - chatContainer.clientHeight <= 50;
    if (isNearBottom) {
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }
}

// --- Streaming message state ---

function finalizeStreaming(): void {
    const lastMsg = chatContainer.lastElementChild as HTMLElement | null;
    if (lastMsg && lastMsg.dataset.streaming === "true") {
        lastMsg.dataset.streaming = "false";
    }
}

function connect(): void {
    const protocol: string = window.location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

    ws.onopen = (): void => {
        statusEl.textContent = "Connected";
        messageInput.disabled = false;
        sendBtn.disabled = false;
        sendMessage({ type: "session/list" });
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

function resumeSession(id: string): void {
    setActiveSession(id);
    // Clear chat immediately to avoid stale content while history loads.
    chatContainer.innerHTML = "";
    toolCallElements.clear();
    sendMessage({ type: "session/resume", session_id: id });
}

function forkSession(): void {
    if (!sessionId) return;
    sendMessage({ type: "session/fork", session_id: sessionId });
}

function deleteSession(): void {
    if (!sessionId) return;
    const confirmed = window.confirm("Delete this session?");
    if (!confirmed) return;
    sendMessage({ type: "session/delete", session_id: sessionId });
}

function setActiveSession(id: string | null): void {
    sessionId = id;
    if (id) {
        sessionInfo.textContent = `Session: ${id.slice(0, 8)}...`;
    } else {
        sessionInfo.textContent = "No session";
    }
    const items = sessionListEl.querySelectorAll(".session-item");
    items.forEach((item) => {
        const el = item as HTMLElement;
        if (el.dataset.sessionId === id) {
            el.style.background = "#0f3460";
        } else {
            el.style.background = "transparent";
        }
    });
}

function formatSessionDate(updated_at: string): string {
    const date = new Date(updated_at);
    const now = new Date();
    const isToday =
        date.getFullYear() === now.getFullYear() &&
        date.getMonth() === now.getMonth() &&
        date.getDate() === now.getDate();
    if (isToday) {
        return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    }
    return date.toLocaleDateString([], { month: "short", day: "numeric" });
}

function renderSessionList(sessions: SessionInfo[]): void {
    sessionList = sessions;
    sessionListEl.innerHTML = "";

    if (sessions.length === 0) {
        const placeholder = document.createElement("div");
        placeholder.style.cssText =
            "padding: 1rem 0.75rem; color: #666; font-size: 0.85rem; text-align: center;";
        placeholder.textContent = "No sessions";
        sessionListEl.appendChild(placeholder);
        return;
    }

    for (const session of sessions) {
        const item = document.createElement("div");
        item.className = "session-item";
        item.dataset.sessionId = session.id;
        item.style.cssText =
            "padding: 0.5rem 0.75rem; cursor: pointer; border-bottom: 1px solid #0f3460;" +
            "background: " + (session.id === sessionId ? "#0f3460" : "transparent") + ";";

        const topRow = document.createElement("div");
        topRow.style.cssText =
            "display: flex; justify-content: space-between; align-items: baseline;" +
            "font-size: 0.8rem; color: #ccc; margin-bottom: 0.2rem;";

        const idSpan = document.createElement("span");
        idSpan.textContent = session.id.slice(0, 8);
        idSpan.style.cssText = "font-family: monospace; font-weight: 600;";

        const dateSpan = document.createElement("span");
        dateSpan.textContent = formatSessionDate(session.updated_at);
        dateSpan.style.cssText = "color: #888; font-size: 0.75rem;";

        topRow.appendChild(idSpan);
        topRow.appendChild(dateSpan);

        const preview = document.createElement("div");
        const previewText = session.preview.length > 40
            ? session.preview.slice(0, 40) + "…"
            : session.preview;
        preview.textContent = previewText;
        preview.style.cssText =
            "font-size: 0.75rem; color: #888; white-space: nowrap; overflow: hidden;" +
            "text-overflow: ellipsis;";

        item.appendChild(topRow);
        item.appendChild(preview);

        item.addEventListener("mouseenter", () => {
            if (item.dataset.sessionId !== sessionId) {
                item.style.background = "#1e2d4e";
            }
        });
        item.addEventListener("mouseleave", () => {
            if (item.dataset.sessionId !== sessionId) {
                item.style.background = "transparent";
            }
        });

        item.addEventListener("click", () => {
            const sid = item.dataset.sessionId;
            if (sid) {
                resumeSession(sid);
            }
        });

        sessionListEl.appendChild(item);
    }
}

function renderHistory(nodes: SessionHistoryNode[]): void {
    chatContainer.innerHTML = "";
    toolCallElements.clear();

    // Local map for pairing tool_call / tool_result nodes during history replay.
    const historyCallMap = new Map<string, HTMLDivElement>();

    for (const node of nodes) {
        switch (node.kind) {
            case "user_prompt":
                if (node.prompt) {
                    appendMessage("user", node.prompt);
                }
                break;
            case "assistant_response":
                if (node.text && node.text.trim()) {
                    appendMessage("agent", node.text);
                }
                break;
            case "tool_call": {
                // output_text is pre-call reasoning; render as agent message if present.
                if (node.output_text) {
                    appendMessage("agent", node.output_text);
                }
                const calls = (node.calls ?? {}) as Record<string, CallData>;
                for (const [callId, callData] of Object.entries(calls)) {
                    const bubble = createToolCallBubble(callId, callData as CallData);
                    chatContainer.appendChild(bubble);
                    historyCallMap.set(callId, bubble);
                    scrollIfNearBottom();
                }
                break;
            }
            case "tool_result": {
                const results = (node.results ?? {}) as Record<
                    string,
                    { status?: unknown; content?: unknown }
                >;
                for (const [callId, resultData] of Object.entries(results)) {
                    const elem = historyCallMap.get(callId);
                    if (elem) {
                        updateToolCallBubble(
                            elem,
                            String(resultData?.status ?? "unknown"),
                            resultData?.content
                        );
                    }
                }
                break;
            }
        }
    }
}

function handleMessage(msg: ServerMessage): void {
    switch (msg.type) {
        case "session/new_response":
            setActiveSession(msg.session_id);
            sendMessage({ type: "session/list" });
            break;
        case "session/list_response": {
            const sorted = [...msg.sessions].sort(
                (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
            );
            renderSessionList(sorted);
            if (sorted.length > 0) {
                resumeSession(sorted[0].id);
            } else {
                createSession();
            }
            break;
        }
        case "session/history":
            // Ignore stale histories from rapid session switches.
            if (msg.session_id === sessionId) {
                renderHistory(msg.nodes);
            }
            break;
        case "session/fork_response":
            setActiveSession(msg.session_id);
            sendMessage({ type: "session/list" });
            break;
        case "session/delete_response": {
            const deletedId = msg.session_id;
            const wasActive = sessionId === deletedId;
            const remaining = sessionList.filter((s) => s.id !== deletedId);
            renderSessionList(remaining);
            if (wasActive) {
                if (remaining.length > 0) {
                    resumeSession(remaining[0].id);
                } else {
                    setActiveSession(null);
                    chatContainer.innerHTML = "";
                    toolCallElements.clear();
                    createSession();
                }
            }
            break;
        }
        case "session/prompt_response":
            isProcessing = false;
            updateInputState();
            // Streaming already rendered the text via agent_message_chunk; skip duplicate.
            break;
        case "session/update":
            // Ignore updates for sessions other than the currently active one.
            if (!msg.session_id || msg.session_id === sessionId) {
                handleUpdate(msg.update);
            }
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
        case "agent_message_chunk": {
            // Skip empty chunks to avoid creating empty bubbles (e.g. thinking-only turns).
            const text = String(update.data?.text ?? "");
            if (text) {
                appendOrUpdateMessage("agent", text, "Agent");
            }
            break;
        }
        case "thinking_chunk": {
            const text = String(update.data?.text ?? "");
            if (text) {
                appendOrUpdateMessage("thinking", text, "Thinking");
            }
            break;
        }
        case "tool_call": {
            finalizeStreaming();
            const calls: Record<string, CallData> = update.data?.calls ?? {};
            for (const [callId, callData] of Object.entries(calls)) {
                const bubble = createToolCallBubble(callId, callData);
                chatContainer.appendChild(bubble);
                toolCallElements.set(callId, bubble);
                scrollIfNearBottom();
            }
            break;
        }
        case "tool_call_update": {
            const status = String(update.data?.status ?? "unknown");
            const content: unknown = update.data?.content ?? "";
            const callId = String(update.data?.call_id ?? "");
            const elem = toolCallElements.get(callId);
            if (elem) {
                updateToolCallBubble(elem, status, content);
            }
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
        scrollIfNearBottom();
        return;
    }
    // Don't create a new bubble for blank initial content (e.g. thinking-only turns).
    if (!text.trim()) {
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
    scrollIfNearBottom();
}

function appendMessage(type: string, text: string): void {
    finalizeStreaming();
    const div: HTMLDivElement = document.createElement("div");
    div.className = `message ${type}`;
    div.dataset.type = type;
    div.dataset.streaming = "false";
    const contentEl: HTMLDivElement = document.createElement("div");
    contentEl.className = "content";
    contentEl.textContent = text;
    div.appendChild(contentEl);
    chatContainer.appendChild(div);
    scrollIfNearBottom();
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

const newSessionBtn = document.getElementById("new-session-btn") as HTMLButtonElement;
const forkSessionBtn = document.getElementById("fork-session-btn") as HTMLButtonElement;
const deleteSessionBtn = document.getElementById("delete-session-btn") as HTMLButtonElement;

newSessionBtn.addEventListener("click", (): void => {
    createSession();
});
forkSessionBtn.addEventListener("click", (): void => {
    forkSession();
});
deleteSessionBtn.addEventListener("click", (): void => {
    deleteSession();
});

function showPermissionModal(
    reqId: string,
    kind: string,
    payload: { arguments?: unknown } | undefined
): void {
    pendingPermId = reqId;
    const args: string = JSON.stringify(payload?.arguments ?? {}, null, 2);
    permissionText.textContent = `Allow tool "${kind}" with arguments:\n${args}`;
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
