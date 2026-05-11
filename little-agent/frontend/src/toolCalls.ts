import { formatArgs, formatResult } from "./format.js";
import type { CallData } from "./types.js";

export function createToolCallBubble(callId: string, callData: CallData): HTMLDivElement {
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

export function updateToolCallBubble(elem: HTMLDivElement, status: string, content: unknown): void {
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
