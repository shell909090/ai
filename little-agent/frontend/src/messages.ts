import { autoScroll } from "./state.js";

function getContainer(): HTMLDivElement {
    return document.getElementById("chat-container") as HTMLDivElement;
}

function scrollIfAutoScroll(): void {
    if (autoScroll) {
        const c = getContainer();
        c.scrollTop = c.scrollHeight;
    }
}

export function finalizeStreaming(): void {
    const lastMsg = getContainer().lastElementChild as HTMLElement | null;
    if (lastMsg && lastMsg.dataset.streaming === "true") {
        lastMsg.dataset.streaming = "false";
    }
}

export function buildBubble(
    type: "user" | "agent" | "thinking",
    text: string,
    label?: string,
): HTMLDivElement {
    const div: HTMLDivElement = document.createElement("div");
    div.className = `message ${type}`;
    div.dataset.type = type;
    if (type === "thinking") {
        const details: HTMLDetailsElement = document.createElement("details");
        const summary: HTMLElement = document.createElement("summary");
        summary.className = "thinking-summary";
        summary.textContent = label ?? "Thinking";
        details.appendChild(summary);
        const contentEl: HTMLDivElement = document.createElement("div");
        contentEl.className = "content";
        contentEl.textContent = text;
        details.appendChild(contentEl);
        div.appendChild(details);
    } else {
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
    }
    return div;
}

/**
 * Append a message bubble to the chat container.
 *
 * @param type    - "user" | "agent" | "thinking"
 * @param text    - Message text
 * @param opts.label     - Optional label shown above content
 * @param opts.streaming - When true, attempt to append to existing streaming bubble
 *                         of the same type before creating a new one.
 */
export function appendMessage(
    type: "user" | "agent" | "thinking",
    text: string,
    opts?: { label?: string; streaming?: boolean },
): void {
    const label = opts?.label;
    const streaming = opts?.streaming ?? false;

    const container = getContainer();
    if (streaming) {
        // Try to append to existing streaming bubble of the same type.
        const lastMsg = container.lastElementChild as HTMLElement | null;
        if (lastMsg && lastMsg.dataset.type === type && lastMsg.dataset.streaming === "true") {
            const contentEl = lastMsg.querySelector(".content");
            if (contentEl) {
                contentEl.textContent += text;
            }
            scrollIfAutoScroll();
            return;
        }
        // Don't create a new bubble for blank initial content.
        if (!text.trim()) {
            return;
        }
        const div = buildBubble(type, text, label);
        div.dataset.streaming = "true";
        container.appendChild(div);
        scrollIfAutoScroll();
    } else {
        finalizeStreaming();
        const div = buildBubble(type, text, label);
        div.dataset.streaming = "false";
        container.appendChild(div);
        scrollIfAutoScroll();
    }
}
