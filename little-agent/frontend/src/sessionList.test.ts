import { describe, it, expect, beforeEach, vi } from "vitest";
import { renderSessionList, updateSessionActiveState, initSessionList } from "./sessionList.js";
import { setSessionId } from "./state.js";
import type { SessionInfo } from "./types.js";

const sessionListEl = document.getElementById("session-list") as HTMLDivElement;

beforeEach(() => {
    sessionListEl.innerHTML = "";
    setSessionId(null);
});

const makeSession = (id: string, preview = "hello"): SessionInfo => ({
    id,
    updated_at: "2024-06-01T10:00:00Z",
    preview,
});

describe("initSessionList", () => {
    it("sets the resumeSession callback without throwing", () => {
        const fn = vi.fn();
        expect(() => initSessionList(fn)).not.toThrow();
    });
});

describe("renderSessionList", () => {
    it("shows placeholder when no sessions", () => {
        renderSessionList([]);
        expect(sessionListEl.querySelector(".session-placeholder")?.textContent).toBe(
            "No sessions",
        );
    });

    it("renders one session item", () => {
        renderSessionList([makeSession("aabbccdd-1111-2222-3333-444455556666")]);
        const item = sessionListEl.querySelector(".session-item");
        expect(item).not.toBeNull();
        expect(item?.querySelector(".session-id")?.textContent).toBe("aabbccdd");
    });

    it("truncates preview longer than 40 chars", () => {
        const long = "a".repeat(50);
        renderSessionList([makeSession("id-123", long)]);
        const preview = sessionListEl.querySelector(".session-preview")?.textContent ?? "";
        expect(preview.length).toBeLessThanOrEqual(42); // 40 + "…"
        expect(preview.endsWith("…")).toBe(true);
    });

    it("does not truncate preview within 40 chars", () => {
        renderSessionList([makeSession("id-123", "short")]);
        const preview = sessionListEl.querySelector(".session-preview")?.textContent ?? "";
        expect(preview).toBe("short");
    });

    it("marks active session with session-item-active class", () => {
        setSessionId("active-id");
        renderSessionList([makeSession("active-id"), makeSession("other-id")]);
        const items = sessionListEl.querySelectorAll(".session-item");
        expect(items[0].classList.contains("session-item-active")).toBe(true);
        expect(items[1].classList.contains("session-item-active")).toBe(false);
    });

    it("calls resumeSession on click", () => {
        const onResume = vi.fn();
        initSessionList(onResume);
        renderSessionList([makeSession("click-id")]);
        const item = sessionListEl.querySelector(".session-item") as HTMLElement;
        item.click();
        expect(onResume).toHaveBeenCalledWith("click-id");
    });

    it("adds hover class on mouseenter when not active", () => {
        renderSessionList([makeSession("hover-id")]);
        const item = sessionListEl.querySelector(".session-item") as HTMLElement;
        item.dispatchEvent(new MouseEvent("mouseenter"));
        expect(item.classList.contains("session-item-hover")).toBe(true);
    });

    it("removes hover class on mouseleave", () => {
        renderSessionList([makeSession("leave-id")]);
        const item = sessionListEl.querySelector(".session-item") as HTMLElement;
        item.dispatchEvent(new MouseEvent("mouseenter"));
        item.dispatchEvent(new MouseEvent("mouseleave"));
        expect(item.classList.contains("session-item-hover")).toBe(false);
    });

    it("does not add hover class on mouseenter when item is active", () => {
        setSessionId("hover-active-id");
        renderSessionList([makeSession("hover-active-id")]);
        const item = sessionListEl.querySelector(".session-item") as HTMLElement;
        item.dispatchEvent(new MouseEvent("mouseenter"));
        expect(item.classList.contains("session-item-hover")).toBe(false);
    });
});

describe("updateSessionActiveState", () => {
    it("marks matching item as active", () => {
        renderSessionList([makeSession("s1"), makeSession("s2")]);
        updateSessionActiveState("s1");
        const items = sessionListEl.querySelectorAll(".session-item");
        expect(items[0].classList.contains("session-item-active")).toBe(true);
        expect(items[1].classList.contains("session-item-active")).toBe(false);
    });

    it("removes active class when null passed", () => {
        setSessionId("s1");
        renderSessionList([makeSession("s1")]);
        updateSessionActiveState(null);
        const item = sessionListEl.querySelector(".session-item");
        expect(item?.classList.contains("session-item-active")).toBe(false);
    });
});
