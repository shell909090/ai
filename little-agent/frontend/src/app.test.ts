import { describe, it, expect, vi, beforeEach } from "vitest";
import { handleSlashCommand, sendPrompt } from "./app.js";
import { setSessionId, setIsProcessing } from "./state.js";
import {
    compactSession,
    cancelSession,
    listTools,
    newSession,
    forkCurrentSession,
    sendMessage,
} from "./ws.js";

// Mock ws.js to avoid real WebSocket calls.
vi.mock("./ws.js", async (importOriginal) => {
    const actual = await importOriginal<typeof import("./ws.js")>();
    return {
        ...actual,
        connect: vi.fn(),
        initSessionButtons: vi.fn(),
        sendMessage: vi.fn(),
        updateInputState: vi.fn(),
        compactSession: vi.fn(),
        cancelSession: vi.fn(),
        listTools: vi.fn(),
        newSession: vi.fn(),
        forkCurrentSession: vi.fn(),
    };
});

const chatContainer = document.getElementById("chat-container") as HTMLDivElement;
const messageInput = document.getElementById("message-input") as HTMLInputElement;

beforeEach(() => {
    chatContainer.innerHTML = "";
    messageInput.value = "";
    setSessionId("test-session");
    setIsProcessing(false);
    vi.clearAllMocks();
});

describe("handleSlashCommand", () => {
    it("calls compactSession for /compact", () => {
        handleSlashCommand("/compact");
        expect(compactSession).toHaveBeenCalledOnce();
    });

    it("calls cancelSession for /cancel", () => {
        handleSlashCommand("/cancel");
        expect(cancelSession).toHaveBeenCalledOnce();
    });

    it("calls listTools for /list-tools", () => {
        handleSlashCommand("/list-tools");
        expect(listTools).toHaveBeenCalledOnce();
    });

    it("calls newSession for /new", () => {
        handleSlashCommand("/new");
        expect(newSession).toHaveBeenCalledOnce();
    });

    it("calls forkCurrentSession for /fork", () => {
        handleSlashCommand("/fork");
        expect(forkCurrentSession).toHaveBeenCalledOnce();
    });

    it("appends unknown-command system message for unrecognized command", () => {
        handleSlashCommand("/unknown");
        expect(chatContainer.querySelector(".message")).not.toBeNull();
    });
});

describe("sendPrompt", () => {
    it("does nothing when input is empty", () => {
        messageInput.value = "   ";
        sendPrompt();
        expect(sendMessage).not.toHaveBeenCalled();
    });

    it("dispatches slash command and clears input", () => {
        messageInput.value = "/compact";
        sendPrompt();
        expect(messageInput.value).toBe("");
        expect(compactSession).toHaveBeenCalledOnce();
    });

    it("does nothing when sessionId is null", () => {
        setSessionId(null);
        messageInput.value = "hello";
        sendPrompt();
        expect(sendMessage).not.toHaveBeenCalled();
    });

    it("does nothing when isProcessing is true", () => {
        setIsProcessing(true);
        messageInput.value = "hello";
        sendPrompt();
        expect(sendMessage).not.toHaveBeenCalled();
    });

    it("sends session/prompt and clears input", () => {
        messageInput.value = "hello world";
        sendPrompt();
        expect(messageInput.value).toBe("");
        expect(sendMessage).toHaveBeenCalledWith(
            expect.objectContaining({ type: "session/prompt", prompt: "hello world" }),
        );
    });

    it("appends user message bubble on send", () => {
        messageInput.value = "test prompt";
        sendPrompt();
        expect(chatContainer.querySelector(".message.user")).not.toBeNull();
    });
});
