import {
    chatContainer,
    cancelBtn,
    messageInput,
    sendBtn,
    spinnerEl,
    statusEl,
    sessionInfo,
    permissionModal,
    permissionText,
    permAllowBtn,
    permDenyBtn,
    newSessionBtn,
    forkSessionBtn,
    deleteSessionBtn,
} from "./dom.js";
import { appendMessage, finalizeStreaming } from "./messages.js";
import { renderHistory } from "./history.js";
import { renderSessionList, updateSessionActiveState, initSessionList } from "./sessionList.js";
import { createToolCallBubble, updateToolCallBubble } from "./toolCalls.js";
import {
    ws,
    sessionId,
    isProcessing,
    autoScroll,
    sessionList,
    autoResumeOnNextList,
    historyPending,
    pendingUpdates,
    pendingPermId,
    setWs,
    setSessionId,
    setIsProcessing,
    setAutoScroll,
    setAutoResumeOnNextList,
    setHistoryPending,
    setPendingUpdates,
    pushPendingUpdate,
    setPendingPermId,
    toolCallElements,
} from "./state.js";
import type { ClientMessage, ServerMessage, SessionUpdatePayload, CallData } from "./types.js";

// Break circular dependency: sessionList.ts needs resumeSession, ws.ts provides it.
initSessionList(resumeSession);

export function sendMessage(msg: ClientMessage): void {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(msg));
    }
}

export function updateInputState(): void {
    messageInput.disabled = isProcessing;
    sendBtn.disabled = isProcessing;
    spinnerEl.style.display = isProcessing ? "inline-block" : "none";
    cancelBtn.style.display = isProcessing ? "inline-block" : "none";
    if (!isProcessing) {
        cancelBtn.textContent = "Cancel";
        cancelBtn.disabled = false;
        statusEl.textContent = "Connected";
    }
}

function scrollToBottom(): void {
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

function scrollIfAutoScroll(): void {
    if (autoScroll) {
        scrollToBottom();
    }
}

function setActiveSession(id: string | null): void {
    setSessionId(id);
    if (id) {
        sessionInfo.textContent = `Session: ${id.slice(0, 8)}...`;
    } else {
        sessionInfo.textContent = "No session";
    }
    updateSessionActiveState(id);
}

export function resumeSession(id: string): void {
    setActiveSession(id);
    // Clear chat immediately; buffer any incoming updates until history arrives.
    chatContainer.innerHTML = "";
    toolCallElements.clear();
    setHistoryPending(true);
    setPendingUpdates([]);
    sendMessage({ type: "session/resume", session_id: id });
}

function createSession(): void {
    sendMessage({ type: "session/new" });
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

export function showPermissionModal(
    reqId: string,
    kind: string,
    payload: { arguments?: unknown } | undefined,
): void {
    setPendingPermId(reqId);
    const args: string = JSON.stringify(payload?.arguments ?? {}, null, 2);
    permissionText.textContent = `Allow tool "${kind}" with arguments:\n${args}`;
    permissionModal.classList.add("active");
}

export function hidePermissionModal(): void {
    permissionModal.classList.remove("active");
    setPendingPermId(null);
}

export function handleUpdate(update: SessionUpdatePayload): void {
    switch (update.type) {
        case "agent_message_chunk": {
            // Skip empty chunks to avoid creating empty bubbles (e.g. thinking-only turns).
            const text = String(update.data?.text ?? "");
            if (text) {
                appendMessage("agent", text, { label: "Agent", streaming: true });
            }
            break;
        }
        case "thinking_chunk": {
            const text = String(update.data?.text ?? "");
            if (text) {
                appendMessage("thinking", text, { label: "Thinking", streaming: true });
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
                scrollIfAutoScroll();
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

export function handleMessage(msg: ServerMessage): void {
    switch (msg.type) {
        case "session/new_response":
            chatContainer.innerHTML = "";
            toolCallElements.clear();
            setHistoryPending(false);
            setPendingUpdates([]);
            setActiveSession(msg.session_id);
            sendMessage({ type: "session/list" });
            break;
        case "session/list_response": {
            const sorted = [...msg.sessions].sort(
                (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
            );
            renderSessionList(sorted);
            if (autoResumeOnNextList) {
                setAutoResumeOnNextList(false);
                if (sorted.length > 0) {
                    resumeSession(sorted[0].id);
                } else {
                    createSession();
                }
            }
            break;
        }
        case "session/history":
            // Ignore stale histories from rapid session switches.
            if (msg.session_id === sessionId) {
                setHistoryPending(false);
                setAutoScroll(true);
                renderHistory(msg.nodes);
                scrollToBottom();
                // Replay updates that arrived while history was loading.
                for (const u of pendingUpdates) {
                    handleUpdate(u);
                }
                setPendingUpdates([]);
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
            setIsProcessing(false);
            updateInputState();
            scrollIfAutoScroll();
            // Streaming already rendered the text via agent_message_chunk; skip duplicate.
            break;
        case "session/update":
            // Ignore updates for sessions other than the currently active one.
            if (!msg.session_id || msg.session_id === sessionId) {
                if (historyPending) {
                    // Buffer until history has rendered to prevent interleaving.
                    pushPendingUpdate(msg.update);
                } else {
                    handleUpdate(msg.update);
                }
            }
            break;
        case "session/request_permission":
            showPermissionModal(msg.id, msg.kind, msg.payload);
            break;
        case "error":
            setIsProcessing(false);
            updateInputState();
            appendMessage("agent", `Error: ${msg.error}`);
            break;
    }
}

export function connect(): void {
    const protocol: string = window.location.protocol === "https:" ? "wss:" : "ws:";
    setWs(new WebSocket(`${protocol}//${window.location.host}/ws`));

    ws!.onopen = (): void => {
        statusEl.textContent = "Connected";
        messageInput.disabled = false;
        sendBtn.disabled = false;
        setAutoResumeOnNextList(true);
        sendMessage({ type: "session/list" });
    };

    ws!.onmessage = (event: MessageEvent): void => {
        try {
            const msg: ServerMessage = JSON.parse(event.data as string) as ServerMessage;
            handleMessage(msg);
        } catch {
            console.error("Invalid JSON from server");
        }
    };

    ws!.onclose = (): void => {
        statusEl.textContent = "Disconnected - reconnecting...";
        messageInput.disabled = true;
        sendBtn.disabled = true;
        setTimeout(connect, 2000);
    };

    ws!.onerror = (): void => {
        statusEl.textContent = "Connection error";
        setIsProcessing(false);
        sendBtn.disabled = false;
        messageInput.disabled = false;
        cancelBtn.style.display = "none";
    };
}

// --- Event listeners for modal ---
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

// --- Session management buttons ---
export function initSessionButtons(): void {
    newSessionBtn.addEventListener("click", (): void => {
        createSession();
    });
    forkSessionBtn.addEventListener("click", (): void => {
        forkSession();
    });
    deleteSessionBtn.addEventListener("click", (): void => {
        deleteSession();
    });
}
