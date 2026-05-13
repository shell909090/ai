import { describe, it, expect, beforeEach } from "vitest";
import { renderHistory } from "./history.js";
import type { SessionHistoryNode } from "./types.js";

const chatContainer = document.getElementById("chat-container") as HTMLDivElement;

beforeEach(() => {
    chatContainer.innerHTML = "";
});

const node = (kind: string, extra?: Partial<SessionHistoryNode>): SessionHistoryNode => ({
    kind,
    id: `node-${kind}`,
    ...extra,
});

describe("renderHistory", () => {
    it("shows empty state when nodes is empty", () => {
        renderHistory([]);
        expect(chatContainer.querySelector(".empty-state")).not.toBeNull();
    });

    it("renders user_prompt node", () => {
        renderHistory([node("user_prompt", { prompt: "hello there" })]);
        const bubble = chatContainer.querySelector(".message.user");
        expect(bubble?.querySelector(".content")?.textContent).toBe("hello there");
    });

    it("skips user_prompt with empty prompt", () => {
        renderHistory([node("user_prompt", { prompt: "" })]);
        expect(chatContainer.querySelectorAll(".message.user")).toHaveLength(0);
    });

    it("renders assistant text", () => {
        renderHistory([node("assistant", { text: "  hello  ", thinking: "" })]);
        expect(chatContainer.querySelector(".message.agent")).not.toBeNull();
    });

    it("skips assistant with blank text and no tool_calls", () => {
        renderHistory([node("assistant", { text: "   ", thinking: "" })]);
        expect(chatContainer.querySelector(".message.agent")).toBeNull();
    });

    it("renders assistant thinking bubble when thinking is non-empty", () => {
        renderHistory([node("assistant", { text: "answer", thinking: "  deep thoughts  " })]);
        expect(chatContainer.querySelector(".message.thinking")).not.toBeNull();
    });

    it("renders assistant with tool_calls as tool-call bubbles", () => {
        renderHistory([
            node("assistant", {
                tool_calls: { "c-1": { tool_name: "bash", arguments: { command: "echo hi" } } },
            }),
        ]);
        expect(chatContainer.querySelector(".tool-call")).not.toBeNull();
    });

    it("renders assistant thinking bubble alongside tool_calls", () => {
        renderHistory([node("assistant", { thinking: "thinking...", tool_calls: {} })]);
        expect(chatContainer.querySelector(".message.thinking")).not.toBeNull();
    });

    it("renders assistant pre-call text as agent message", () => {
        renderHistory([node("assistant", { text: "before calling", tool_calls: {} })]);
        expect(chatContainer.querySelector(".message.agent")).not.toBeNull();
    });

    it("renders tool_result and updates tool-call bubble", () => {
        renderHistory([
            node("assistant", {
                tool_calls: { "c-1": { tool_name: "bash", arguments: {} } },
            }),
            node("tool_result", {
                results: { "c-1": { status: "completed", content: "output" } },
            }),
        ]);
        expect(chatContainer.querySelector(".tool-call-completed")).not.toBeNull();
    });

    it("ignores tool_result for unknown call_id", () => {
        const nodes = [
            node("tool_result", {
                results: { "unknown-id": { status: "completed", content: "" } },
            }),
        ];
        expect(() => renderHistory(nodes)).not.toThrow();
    });
});
