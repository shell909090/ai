import { describe, it, expect, vi, beforeEach } from "vitest";
import { handleSlashCommand, sendPrompt, registerEventListeners } from "./app.js";
import { setSessionId, setIsProcessing } from "./state.js";
import * as state from "./state.js";
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

describe("registerEventListeners", () => {
    // dom.ts caches element references at module load time; we must use the same
    // elements that were captured then.  registerEventListeners() is called once
    // here — subsequent tests rely on the handlers already being registered.
    // vi.clearAllMocks() in the outer beforeEach resets call counts between tests.
    registerEventListeners();

    it("sendBtn click calls sendMessage when input has content", () => {
        messageInput.value = "hello";
        document.getElementById("send-btn")!.click();
        expect(sendMessage).toHaveBeenCalledWith(
            expect.objectContaining({ type: "session/prompt", prompt: "hello" }),
        );
    });

    it("messageInput keypress Enter calls sendMessage", () => {
        messageInput.value = "hello";
        const event = new KeyboardEvent("keypress", { key: "Enter" });
        messageInput.dispatchEvent(event);
        expect(sendMessage).toHaveBeenCalledWith(
            expect.objectContaining({ type: "session/prompt" }),
        );
    });

    it("cancelBtn click sends session/cancel when sessionId is set", () => {
        document.getElementById("cancelButton")!.click();
        expect(sendMessage).toHaveBeenCalledWith(
            expect.objectContaining({ type: "session/cancel", session_id: "test-session" }),
        );
    });

    it("messageInput input with '/' prefix sets list attribute", () => {
        messageInput.value = "/compact";
        messageInput.dispatchEvent(new Event("input"));
        expect(messageInput.getAttribute("list")).toBe("slash-commands");
    });

    it("chatContainer scroll near bottom calls setAutoScroll(true)", () => {
        // Set autoScroll to false first so we can verify the handler changes it.
        state.setAutoScroll(false);
        // Simulate scrollHeight - scrollTop - clientHeight <= 50
        Object.defineProperty(chatContainer, "scrollHeight", { configurable: true, value: 500 });
        Object.defineProperty(chatContainer, "scrollTop", { configurable: true, get: () => 460 });
        Object.defineProperty(chatContainer, "clientHeight", { configurable: true, value: 40 });
        // distanceFromBottom = 500 - 460 - 40 = 0 <= 50 → setAutoScroll(true)
        chatContainer.dispatchEvent(new Event("scroll"));
        expect(state.autoScroll).toBe(true);
    });
});
