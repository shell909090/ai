import { describe, it, expect, beforeEach } from "vitest";
import { createToolCallBubble, updateToolCallBubble } from "./toolCalls.js";
import type { CallData } from "./types.js";

describe("createToolCallBubble", () => {
    it("creates a div with class 'message tool-call'", () => {
        const callData: CallData = { tool_name: "bash", arguments: { cmd: "ls" } };
        const bubble = createToolCallBubble("call-1", callData);
        expect(bubble.className).toContain("tool-call");
        expect(bubble.className).toContain("message");
    });

    it("shows the tool name in the label", () => {
        const callData: CallData = { tool_name: "read_file", arguments: {} };
        const bubble = createToolCallBubble("call-2", callData);
        const label = bubble.querySelector(".label");
        expect(label?.textContent).toBe("read_file");
    });

    it("shows the callId in the summary", () => {
        const callData: CallData = { tool_name: "write_file", arguments: {} };
        const bubble = createToolCallBubble("call-abc-123", callData);
        const summary = bubble.querySelector("summary.tool-call-summary");
        expect(summary?.textContent).toBe("call-abc-123");
    });

    it("uses 'unknown' when tool_name is missing", () => {
        const callData: CallData = {};
        const bubble = createToolCallBubble("call-3", callData);
        const label = bubble.querySelector(".label");
        expect(label?.textContent).toBe("unknown");
    });

    it("renders args inside a details element", () => {
        const callData: CallData = { tool_name: "search", arguments: { query: "test" } };
        const bubble = createToolCallBubble("call-4", callData);
        const details = bubble.querySelector("details");
        expect(details).not.toBeNull();
        const argsDiv = details?.querySelector(".tool-args-content");
        expect(argsDiv?.textContent).toContain("query");
    });

    it("sets data-call-id attribute", () => {
        const callData: CallData = { tool_name: "ping", arguments: {} };
        const bubble = createToolCallBubble("my-call-id", callData);
        expect(bubble.dataset.callId).toBe("my-call-id");
    });
});

describe("updateToolCallBubble", () => {
    let bubble: HTMLDivElement;

    beforeEach(() => {
        const callData: CallData = { tool_name: "bash", arguments: { cmd: "echo hi" } };
        bubble = createToolCallBubble("upd-1", callData);
    });

    it("adds 'tool-call-completed' class on completed status", () => {
        updateToolCallBubble(bubble, "completed", "done");
        expect(bubble.classList.contains("tool-call-completed")).toBe(true);
        expect(bubble.classList.contains("tool-call")).toBe(false);
    });

    it("adds 'tool-call-failed' class on failed status", () => {
        updateToolCallBubble(bubble, "failed", "error occurred");
        expect(bubble.classList.contains("tool-call-failed")).toBe(true);
        expect(bubble.classList.contains("tool-call")).toBe(false);
    });

    it("adds 'tool-call-cancelled' class for unknown status", () => {
        updateToolCallBubble(bubble, "cancelled", null);
        expect(bubble.classList.contains("tool-call-cancelled")).toBe(true);
    });

    it("appends result content to details element", () => {
        updateToolCallBubble(bubble, "completed", "output text here");
        const resultDiv = bubble.querySelector(".tool-result-content");
        expect(resultDiv?.textContent).toContain("output text here");
    });

    it("does not append result div when content is empty string", () => {
        updateToolCallBubble(bubble, "completed", "");
        const resultDiv = bubble.querySelector(".tool-result-content");
        expect(resultDiv).toBeNull();
    });

    it("does not append result div when content is null", () => {
        updateToolCallBubble(bubble, "failed", null);
        const resultDiv = bubble.querySelector(".tool-result-content");
        expect(resultDiv).toBeNull();
    });
});
