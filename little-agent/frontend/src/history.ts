import { chatContainer } from "./dom.js";
import { appendMessage } from "./messages.js";
import { createToolCallBubble, updateToolCallBubble } from "./toolCalls.js";
import { autoScroll } from "./state.js";
import type { CallData, SessionHistoryNode } from "./types.js";

function scrollIfAutoScroll(): void {
    if (autoScroll) {
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }
}

export function renderHistory(nodes: SessionHistoryNode[]): void {
    chatContainer.innerHTML = "";

    // Local map for pairing tool_call / tool_result nodes during history replay.
    const historyCallMap = new Map<string, HTMLDivElement>();

    for (const node of nodes) {
        switch (node.kind) {
            case "user_prompt":
                if (node.prompt) {
                    appendMessage("user", node.prompt, { label: undefined });
                }
                break;
            case "assistant_response":
                if (node.thinking?.trim()) {
                    appendMessage("thinking", node.thinking, { label: "Thinking" });
                }
                if (node.text && node.text.trim()) {
                    appendMessage("agent", node.text, { label: "Agent" });
                }
                break;
            case "tool_call": {
                if (node.thinking?.trim()) {
                    appendMessage("thinking", node.thinking, { label: "Thinking" });
                }
                // output_text is pre-call reasoning; render as agent message if present.
                if (node.output_text?.trim()) {
                    appendMessage("agent", node.output_text, { label: "Agent" });
                }
                const calls = (node.calls ?? {}) as Record<string, CallData>;
                for (const [callId, callData] of Object.entries(calls)) {
                    const bubble = createToolCallBubble(callId, callData as CallData);
                    chatContainer.appendChild(bubble);
                    historyCallMap.set(callId, bubble);
                    scrollIfAutoScroll();
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
                            resultData?.content,
                        );
                    }
                }
                break;
            }
        }
    }
}
