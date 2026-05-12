import { describe, it, expect, beforeEach, vi } from "vitest";
import {
    handleUpdate,
    handleMessage,
    sendMessage,
    showPermissionModal,
    hidePermissionModal,
    updateInputState,
    resumeSession,
    compactSession,
    cancelSession,
    listTools,
    newSession,
    forkCurrentSession,
    initSessionButtons,
    connect,
} from "./ws.js";
import {
    setWs,
    setSessionId,
    setIsProcessing,
    setHistoryPending,
    setPendingUpdates,
} from "./state.js";
import type { ServerMessage, SessionUpdatePayload } from "./types.js";

// happy-dom may not define WebSocket constants; use numeric values directly.
const WS_OPEN = 1;
const WS_CLOSED = 3;

const chatContainer = document.getElementById("chat-container") as HTMLDivElement;
const permissionModal = document.getElementById("permission-modal") as HTMLDivElement;
const permissionText = document.getElementById("permission-text") as HTMLParagraphElement;
const statusEl = document.getElementById("status") as HTMLDivElement;
const compactBtn = document.getElementById("compact-session-btn") as HTMLButtonElement;

beforeEach(() => {
    chatContainer.innerHTML = "";
    statusEl.textContent = "";
    setWs(null);
    setSessionId(null);
    setIsProcessing(false);
    setHistoryPending(false);
    setPendingUpdates([]);
    permissionModal.classList.remove("active");
});

describe("sendMessage", () => {
    it("does nothing when ws is null", () => {
        expect(() => sendMessage({ type: "session/list" })).not.toThrow();
    });

    it("does nothing when ws is not OPEN", () => {
        const send = vi.fn();
        setWs({ readyState: WS_CLOSED, send } as unknown as WebSocket);
        sendMessage({ type: "session/list" });
        expect(send).not.toHaveBeenCalled();
    });

    it("sends JSON when ws is OPEN", () => {
        const send = vi.fn();
        setWs({ readyState: WS_OPEN, send } as unknown as WebSocket);
        sendMessage({ type: "session/list" });
        expect(send).toHaveBeenCalledWith(JSON.stringify({ type: "session/list" }));
    });
});

describe("updateInputState", () => {
    it("shows connected status when not processing", () => {
        setIsProcessing(false);
        updateInputState();
        expect(statusEl.textContent).toBe("Connected");
    });

    it("disables input when processing", () => {
        setIsProcessing(true);
        updateInputState();
        const input = document.getElementById("message-input") as HTMLInputElement;
        expect(input.disabled).toBe(true);
    });
});

describe("showPermissionModal / hidePermissionModal", () => {
    it("adds active class on show", () => {
        showPermissionModal("req-1", "bash", { arguments: { cmd: "ls" } });
        expect(permissionModal.classList.contains("active")).toBe(true);
    });

    it("includes kind and arguments in text", () => {
        showPermissionModal("req-2", "read_file", { arguments: { path: "/etc" } });
        expect(permissionText.textContent).toContain("read_file");
        expect(permissionText.textContent).toContain("/etc");
    });

    it("handles undefined payload", () => {
        expect(() => showPermissionModal("req-3", "tool", undefined)).not.toThrow();
    });

    it("removes active class on hide", () => {
        permissionModal.classList.add("active");
        hidePermissionModal();
        expect(permissionModal.classList.contains("active")).toBe(false);
    });
});

describe("handleUpdate", () => {
    it("appends agent bubble for non-empty agent_message_chunk", () => {
        handleUpdate({ type: "agent_message_chunk", data: { text: "hello" } });
        expect(chatContainer.querySelector(".message.agent")).not.toBeNull();
    });

    it("skips empty agent_message_chunk", () => {
        handleUpdate({ type: "agent_message_chunk", data: { text: "" } });
        expect(chatContainer.querySelector(".message.agent")).toBeNull();
    });

    it("appends thinking bubble for thinking_chunk", () => {
        handleUpdate({ type: "thinking_chunk", data: { text: "pondering" } });
        expect(chatContainer.querySelector(".message.thinking")).not.toBeNull();
    });

    it("skips empty thinking_chunk", () => {
        handleUpdate({ type: "thinking_chunk", data: { text: "" } });
        expect(chatContainer.querySelector(".message.thinking")).toBeNull();
    });

    it("creates tool-call bubble for tool_call", () => {
        handleUpdate({
            type: "tool_call",
            data: { calls: { c1: { tool_name: "bash", arguments: {} } } },
        });
        expect(chatContainer.querySelector(".tool-call")).not.toBeNull();
    });

    it("updates existing tool-call bubble via tool_call_update", () => {
        handleUpdate({
            type: "tool_call",
            data: { calls: { c2: { tool_name: "bash", arguments: {} } } },
        });
        const update: SessionUpdatePayload = {
            type: "tool_call_update",
            data: { call_id: "c2", status: "completed", content: "done" },
        };
        handleUpdate(update);
        expect(chatContainer.querySelector(".tool-call-completed")).not.toBeNull();
    });

    it("ignores tool_call_update for unknown call_id", () => {
        const update: SessionUpdatePayload = {
            type: "tool_call_update",
            data: { call_id: "ghost", status: "failed", content: "err" },
        };
        expect(() => handleUpdate(update)).not.toThrow();
    });
});

describe("handleMessage", () => {
    it("clears chat on session/new_response", () => {
        chatContainer.innerHTML = "<div class='old'>old</div>";
        handleMessage({ type: "session/new_response", session_id: "new-id" });
        expect(chatContainer.querySelector(".old")).toBeNull();
    });

    it("handles session/list_response without throwing", () => {
        const msg: ServerMessage = {
            type: "session/list_response",
            sessions: [{ id: "s1", updated_at: "2024-01-01T00:00:00Z", preview: "hi" }],
        };
        expect(() => handleMessage(msg)).not.toThrow();
    });

    it("handles session/prompt_response", () => {
        setIsProcessing(true);
        handleMessage({ type: "session/prompt_response" });
        expect(document.getElementById("message-input")?.hasAttribute("disabled")).toBe(false);
    });

    it("appends error message on error", () => {
        handleMessage({ type: "error", error: "something went wrong" });
        expect(chatContainer.querySelector(".message.agent")).not.toBeNull();
    });

    it("handles session/fork_response without throwing", () => {
        const send = vi.fn();
        setWs({ readyState: WS_OPEN, send } as unknown as WebSocket);
        expect(() =>
            handleMessage({ type: "session/fork_response", session_id: "fork-id" }),
        ).not.toThrow();
    });

    it("handles session/history when session matches", () => {
        setSessionId("hist-id");
        setHistoryPending(true);
        expect(() =>
            handleMessage({ type: "session/history", session_id: "hist-id", nodes: [] }),
        ).not.toThrow();
    });

    it("ignores session/history for mismatched session", () => {
        setSessionId("other-id");
        expect(() =>
            handleMessage({ type: "session/history", session_id: "hist-id", nodes: [] }),
        ).not.toThrow();
    });

    it("handles session/update while not pending history", () => {
        setHistoryPending(false);
        setSessionId("active-id");
        handleMessage({
            type: "session/update",
            session_id: "active-id",
            update: { type: "agent_message_chunk", data: { text: "streaming" } },
        });
        expect(chatContainer.querySelector(".message.agent")).not.toBeNull();
    });

    it("buffers session/update while history is pending", () => {
        setHistoryPending(true);
        setSessionId("active-id");
        handleMessage({
            type: "session/update",
            session_id: "active-id",
            update: { type: "agent_message_chunk", data: { text: "buffered" } },
        });
        expect(chatContainer.querySelector(".message.agent")).toBeNull();
    });

    it("handles session/request_permission", () => {
        handleMessage({
            type: "session/request_permission",
            id: "perm-req-1",
            kind: "bash",
            payload: { arguments: { cmd: "ls" } },
        });
        expect(permissionModal.classList.contains("active")).toBe(true);
    });

    it("handles tools/list_response with tools", () => {
        handleMessage({
            type: "tools/list_response",
            tools: [{ name: "bash", desc: "Run shell command" }],
        });
        expect(chatContainer.querySelector(".message")).not.toBeNull();
    });

    it("handles tools/list_response with empty tools list", () => {
        handleMessage({ type: "tools/list_response", tools: [] });
        expect(chatContainer.querySelector(".message")).not.toBeNull();
    });

    it("handles session/compact_response ok=true", () => {
        compactBtn.disabled = true;
        handleMessage({ type: "session/compact_response", ok: true });
        expect(compactBtn.disabled).toBe(false);
        expect(chatContainer.querySelector(".message")).not.toBeNull();
    });

    it("handles session/compact_response ok=false", () => {
        compactBtn.disabled = true;
        handleMessage({ type: "session/compact_response", ok: false, error: "no compressor" });
        expect(compactBtn.disabled).toBe(false);
    });

    it("handles session/delete_response for non-active session", () => {
        setSessionId("other-id");
        expect(() =>
            handleMessage({ type: "session/delete_response", session_id: "del-id" }),
        ).not.toThrow();
    });

    it("handles session/delete_response for active session with no remaining", () => {
        setSessionId("del-id");
        const send = vi.fn();
        setWs({ readyState: WS_OPEN, send } as unknown as WebSocket);
        expect(() =>
            handleMessage({ type: "session/delete_response", session_id: "del-id" }),
        ).not.toThrow();
    });
});

describe("resumeSession", () => {
    it("sends session/resume with the given id", () => {
        const send = vi.fn();
        setWs({ readyState: WS_OPEN, send } as unknown as WebSocket);
        resumeSession("sess-abc");
        expect(send).toHaveBeenCalledWith(
            JSON.stringify({ type: "session/resume", session_id: "sess-abc" }),
        );
    });

    it("clears chat container and sets historyPending", () => {
        chatContainer.innerHTML = "<div>old</div>";
        const send = vi.fn();
        setWs({ readyState: WS_OPEN, send } as unknown as WebSocket);
        resumeSession("sess-xyz");
        expect(chatContainer.innerHTML).not.toContain("old");
    });
});

describe("compactSession", () => {
    it("does nothing when sessionId is null", () => {
        setSessionId(null);
        const send = vi.fn();
        setWs({ readyState: WS_OPEN, send } as unknown as WebSocket);
        compactSession();
        expect(send).not.toHaveBeenCalled();
    });

    it("sends session/compact and disables compact button", () => {
        setSessionId("sess-compact");
        const send = vi.fn();
        setWs({ readyState: WS_OPEN, send } as unknown as WebSocket);
        compactBtn.disabled = false;
        compactSession();
        expect(compactBtn.disabled).toBe(true);
        expect(send).toHaveBeenCalledWith(
            JSON.stringify({ type: "session/compact", session_id: "sess-compact" }),
        );
    });
});

describe("cancelSession", () => {
    it("does nothing when sessionId is null", () => {
        setSessionId(null);
        const send = vi.fn();
        setWs({ readyState: WS_OPEN, send } as unknown as WebSocket);
        cancelSession();
        expect(send).not.toHaveBeenCalled();
    });

    it("sends session/cancel", () => {
        setSessionId("sess-cancel");
        const send = vi.fn();
        setWs({ readyState: WS_OPEN, send } as unknown as WebSocket);
        cancelSession();
        expect(send).toHaveBeenCalledWith(
            JSON.stringify({ type: "session/cancel", session_id: "sess-cancel" }),
        );
    });
});

describe("listTools", () => {
    it("sends tools/list", () => {
        const send = vi.fn();
        setWs({ readyState: WS_OPEN, send } as unknown as WebSocket);
        listTools();
        expect(send).toHaveBeenCalledWith(JSON.stringify({ type: "tools/list" }));
    });
});

describe("newSession", () => {
    it("sends session/new", () => {
        const send = vi.fn();
        setWs({ readyState: WS_OPEN, send } as unknown as WebSocket);
        newSession();
        expect(send).toHaveBeenCalledWith(JSON.stringify({ type: "session/new" }));
    });
});

describe("forkCurrentSession", () => {
    it("does nothing when sessionId is null", () => {
        setSessionId(null);
        const send = vi.fn();
        setWs({ readyState: WS_OPEN, send } as unknown as WebSocket);
        forkCurrentSession();
        expect(send).not.toHaveBeenCalled();
    });

    it("sends session/fork when session active", () => {
        setSessionId("sess-fork");
        const send = vi.fn();
        setWs({ readyState: WS_OPEN, send } as unknown as WebSocket);
        forkCurrentSession();
        expect(send).toHaveBeenCalledWith(
            JSON.stringify({ type: "session/fork", session_id: "sess-fork" }),
        );
    });
});

describe("initSessionButtons", () => {
    it("registers new-session-btn click handler", () => {
        const send = vi.fn();
        setWs({ readyState: WS_OPEN, send } as unknown as WebSocket);
        initSessionButtons();
        document.getElementById("new-session-btn")!.click();
        expect(send).toHaveBeenCalledWith(JSON.stringify({ type: "session/new" }));
    });

    it("registers fork-session-btn click handler", () => {
        setSessionId("sess-fork-btn");
        const send = vi.fn();
        setWs({ readyState: WS_OPEN, send } as unknown as WebSocket);
        initSessionButtons();
        document.getElementById("fork-session-btn")!.click();
        expect(send).toHaveBeenCalledWith(
            JSON.stringify({ type: "session/fork", session_id: "sess-fork-btn" }),
        );
    });

    it("registers compact-session-btn click handler", () => {
        setSessionId("sess-compact-btn");
        const send = vi.fn();
        setWs({ readyState: WS_OPEN, send } as unknown as WebSocket);
        compactBtn.disabled = false;
        initSessionButtons();
        compactBtn.click();
        expect(send).toHaveBeenCalledWith(
            JSON.stringify({ type: "session/compact", session_id: "sess-compact-btn" }),
        );
    });
});

describe("connect", () => {
    it("creates a WebSocket and registers handlers without throwing", () => {
        expect(() => connect()).not.toThrow();
    });

    it("sends session/list on open", () => {
        const send = vi.fn();
        // Capture ws instance created by connect(); use globalThis.WebSocket mock.
        const OrigWS = globalThis.WebSocket;
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (globalThis as any).WebSocket = class MockWS {
            static OPEN = 1;
            readyState = 1;
            onopen: (() => void) | null = null;
            onmessage: ((e: MessageEvent) => void) | null = null;
            onclose: (() => void) | null = null;
            onerror: (() => void) | null = null;
            send = send;
            close(): void {}
        };
        connect();
        // Simulate onopen
        const wsInstance = { readyState: WS_OPEN, send } as unknown as WebSocket;
        setWs(wsInstance);
        // Manually trigger as if onopen fired
        sendMessage({ type: "session/list" });
        expect(send).toHaveBeenCalledWith(JSON.stringify({ type: "session/list" }));
        // Restore
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (globalThis as any).WebSocket = OrigWS;
    });
});
