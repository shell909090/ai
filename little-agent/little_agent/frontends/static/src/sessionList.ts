import { sessionListEl } from "./dom.js";
import { formatSessionDate } from "./format.js";
import { sessionId, setSessionList } from "./state.js";
import type { SessionInfo } from "./types.js";

// resumeSession is injected to avoid circular deps with ws.ts
let _resumeSession: (id: string) => void = () => undefined;

export function initSessionList(resumeSession: (id: string) => void): void {
    _resumeSession = resumeSession;
}

export function renderSessionList(sessions: SessionInfo[]): void {
    setSessionList(sessions);
    sessionListEl.innerHTML = "";

    if (sessions.length === 0) {
        const placeholder = document.createElement("div");
        placeholder.className = "session-placeholder";
        placeholder.textContent = "No sessions";
        sessionListEl.appendChild(placeholder);
        return;
    }

    for (const session of sessions) {
        const item = document.createElement("div");
        item.className = "session-item" + (session.id === sessionId ? " session-item-active" : "");
        item.dataset.sessionId = session.id;

        const topRow = document.createElement("div");
        topRow.className = "session-top-row";

        const idSpan = document.createElement("span");
        idSpan.textContent = session.id.slice(0, 8);
        idSpan.className = "session-id";

        const dateSpan = document.createElement("span");
        dateSpan.textContent = formatSessionDate(session.updated_at);
        dateSpan.className = "session-date";

        topRow.appendChild(idSpan);
        topRow.appendChild(dateSpan);

        const preview = document.createElement("div");
        const previewText =
            session.preview.length > 40 ? session.preview.slice(0, 40) + "…" : session.preview;
        preview.textContent = previewText;
        preview.className = "session-preview";

        item.appendChild(topRow);
        item.appendChild(preview);

        item.addEventListener("mouseenter", () => {
            if (item.dataset.sessionId !== sessionId) {
                item.classList.add("session-item-hover");
            }
        });
        item.addEventListener("mouseleave", () => {
            item.classList.remove("session-item-hover");
        });

        item.addEventListener("click", () => {
            const sid = item.dataset.sessionId;
            if (sid) {
                _resumeSession(sid);
            }
        });

        sessionListEl.appendChild(item);
    }
}

export function updateSessionActiveState(activeId: string | null): void {
    const items = sessionListEl.querySelectorAll(".session-item");
    items.forEach((item) => {
        const el = item as HTMLElement;
        if (el.dataset.sessionId === activeId) {
            el.classList.add("session-item-active");
            el.classList.remove("session-item-hover");
        } else {
            el.classList.remove("session-item-active");
        }
    });
}
