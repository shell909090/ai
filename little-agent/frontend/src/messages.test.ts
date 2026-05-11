import { describe, it, expect, beforeEach } from "vitest";

// Set up DOM before importing modules.
document.body.innerHTML = `<div id="chat-container"></div>`;

import {
    appendMessage,
    buildBubble,
    finalizeStreaming,
    showEmptyState,
    hideEmptyState,
} from "./messages.js";

const chatContainer = document.getElementById("chat-container") as HTMLDivElement;

beforeEach(() => {
    chatContainer.innerHTML = "";
});

describe("buildBubble", () => {
    it("creates a user bubble with correct class and content", () => {
        const bubble = buildBubble("user", "hello");
        expect(bubble.className).toContain("user");
        expect(bubble.querySelector(".content")?.textContent).toBe("hello");
    });

    it("creates an agent bubble with label", () => {
        const bubble = buildBubble("agent", "hi there", "Agent");
        expect(bubble.querySelector(".label")?.textContent).toBe("Agent");
        expect(bubble.querySelector(".content")?.textContent).toBe("hi there");
    });

    it("creates a thinking bubble with details/summary structure", () => {
        const bubble = buildBubble("thinking", "deep thought");
        expect(bubble.querySelector("details")).not.toBeNull();
        expect(bubble.querySelector("summary.thinking-summary")).not.toBeNull();
        expect(bubble.querySelector(".content")?.textContent).toBe("deep thought");
    });

    it("creates a user bubble without label by default", () => {
        const bubble = buildBubble("user", "text");
        expect(bubble.querySelector(".label")).toBeNull();
    });

    it("sets data-type attribute correctly", () => {
        const bubble = buildBubble("agent", "response");
        expect(bubble.dataset.type).toBe("agent");
    });
});

describe("appendMessage (non-streaming)", () => {
    it("appends a user bubble containing the text", () => {
        appendMessage("user", "hello");
        const bubble = chatContainer.lastElementChild as HTMLElement;
        expect(bubble).not.toBeNull();
        expect(bubble.dataset.type).toBe("user");
        expect(bubble.querySelector(".content")?.textContent).toBe("hello");
    });

    it("sets streaming=false on non-streaming append", () => {
        appendMessage("agent", "response");
        const bubble = chatContainer.lastElementChild as HTMLElement;
        expect(bubble.dataset.streaming).toBe("false");
    });

    it("appends a thinking bubble with correct structure", () => {
        appendMessage("thinking", "pondering");
        const bubble = chatContainer.lastElementChild as HTMLElement;
        expect(bubble.dataset.type).toBe("thinking");
        expect(bubble.querySelector("details")).not.toBeNull();
    });

    it("appends multiple non-streaming bubbles", () => {
        appendMessage("user", "msg1");
        appendMessage("agent", "msg2");
        expect(chatContainer.children.length).toBe(2);
    });
});

describe("appendMessage (streaming)", () => {
    it("creates a new bubble when none exists with streaming=true", () => {
        appendMessage("agent", "chunk1", { streaming: true });
        expect(chatContainer.children.length).toBe(1);
        const bubble = chatContainer.lastElementChild as HTMLElement;
        expect(bubble.dataset.streaming).toBe("true");
        expect(bubble.querySelector(".content")?.textContent).toBe("chunk1");
    });

    it("appends to existing streaming bubble of same type", () => {
        appendMessage("agent", "chunk1", { streaming: true });
        appendMessage("agent", " chunk2", { streaming: true });
        expect(chatContainer.children.length).toBe(1);
        const bubble = chatContainer.lastElementChild as HTMLElement;
        expect(bubble.querySelector(".content")?.textContent).toBe("chunk1 chunk2");
    });

    it("creates a new bubble when last bubble is different type", () => {
        appendMessage("user", "msg", { streaming: true });
        appendMessage("agent", "reply", { streaming: true });
        expect(chatContainer.children.length).toBe(2);
    });

    it("ignores blank initial streaming content", () => {
        appendMessage("agent", "   ", { streaming: true });
        expect(chatContainer.children.length).toBe(0);
    });
});

describe("finalizeStreaming", () => {
    it("sets streaming=false on last streaming element", () => {
        appendMessage("agent", "text", { streaming: true });
        const bubble = chatContainer.lastElementChild as HTMLElement;
        expect(bubble.dataset.streaming).toBe("true");
        finalizeStreaming();
        expect(bubble.dataset.streaming).toBe("false");
    });

    it("does nothing when last element is already finalized", () => {
        appendMessage("agent", "text");
        const bubble = chatContainer.lastElementChild as HTMLElement;
        expect(bubble.dataset.streaming).toBe("false");
        finalizeStreaming();
        expect(bubble.dataset.streaming).toBe("false");
    });

    it("does nothing when container is empty", () => {
        expect(() => finalizeStreaming()).not.toThrow();
    });
});

describe("showEmptyState / hideEmptyState", () => {
    it("showEmptyState adds placeholder when container is empty", () => {
        showEmptyState();
        const el = chatContainer.querySelector(".empty-state");
        expect(el).not.toBeNull();
        expect(el?.textContent).toBe("Start a conversation by typing below");
    });

    it("showEmptyState does not add placeholder when messages exist", () => {
        appendMessage("user", "hello");
        showEmptyState();
        const empties = chatContainer.querySelectorAll(".empty-state");
        expect(empties.length).toBe(0);
    });

    it("showEmptyState does not add duplicate placeholders", () => {
        showEmptyState();
        showEmptyState();
        const empties = chatContainer.querySelectorAll(".empty-state");
        expect(empties.length).toBe(1);
    });

    it("hideEmptyState removes the placeholder", () => {
        showEmptyState();
        expect(chatContainer.querySelector(".empty-state")).not.toBeNull();
        hideEmptyState();
        expect(chatContainer.querySelector(".empty-state")).toBeNull();
    });

    it("hideEmptyState is a no-op when no placeholder exists", () => {
        expect(() => hideEmptyState()).not.toThrow();
    });

    it("appendMessage removes the placeholder automatically", () => {
        showEmptyState();
        expect(chatContainer.querySelector(".empty-state")).not.toBeNull();
        appendMessage("user", "hello");
        expect(chatContainer.querySelector(".empty-state")).toBeNull();
    });

    it("streaming appendMessage removes placeholder when first chunk arrives", () => {
        showEmptyState();
        appendMessage("agent", "chunk", { streaming: true });
        expect(chatContainer.querySelector(".empty-state")).toBeNull();
    });

    it("blank streaming chunk does not remove placeholder", () => {
        showEmptyState();
        appendMessage("agent", "   ", { streaming: true });
        expect(chatContainer.querySelector(".empty-state")).not.toBeNull();
    });
});
