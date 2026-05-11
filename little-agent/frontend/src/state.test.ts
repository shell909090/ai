import { describe, it, expect, beforeEach } from "vitest";
import {
    ws,
    sessionId,
    isProcessing,
    autoScroll,
    sessionList,
    autoResumeOnNextList,
    historyPending,
    pendingUpdates,
    pendingPermId,
    setWs,
    setSessionId,
    setIsProcessing,
    setAutoScroll,
    setSessionList,
    setAutoResumeOnNextList,
    setHistoryPending,
    setPendingUpdates,
    pushPendingUpdate,
    setPendingPermId,
    toolCallElements,
} from "./state.js";

describe("state setters", () => {
    beforeEach(() => {
        setWs(null);
        setSessionId(null);
        setIsProcessing(false);
        setAutoScroll(true);
        setSessionList([]);
        setAutoResumeOnNextList(false);
        setHistoryPending(false);
        setPendingUpdates([]);
        setPendingPermId(null);
        toolCallElements.clear();
    });

    it("setWs updates ws", () => {
        expect(ws).toBeNull();
        const fakeWs = {} as WebSocket;
        setWs(fakeWs);
        expect(ws).toBe(fakeWs);
    });

    it("setSessionId updates sessionId", () => {
        expect(sessionId).toBeNull();
        setSessionId("abc-123");
        expect(sessionId).toBe("abc-123");
        setSessionId(null);
        expect(sessionId).toBeNull();
    });

    it("setIsProcessing updates isProcessing", () => {
        expect(isProcessing).toBe(false);
        setIsProcessing(true);
        expect(isProcessing).toBe(true);
    });

    it("setAutoScroll updates autoScroll", () => {
        expect(autoScroll).toBe(true);
        setAutoScroll(false);
        expect(autoScroll).toBe(false);
    });

    it("setSessionList updates sessionList", () => {
        expect(sessionList).toEqual([]);
        const sessions = [{ id: "s1", updated_at: "2024-01-01", preview: "hi" }];
        setSessionList(sessions);
        expect(sessionList).toEqual(sessions);
    });

    it("setAutoResumeOnNextList updates autoResumeOnNextList", () => {
        expect(autoResumeOnNextList).toBe(false);
        setAutoResumeOnNextList(true);
        expect(autoResumeOnNextList).toBe(true);
    });

    it("setHistoryPending updates historyPending", () => {
        expect(historyPending).toBe(false);
        setHistoryPending(true);
        expect(historyPending).toBe(true);
    });

    it("setPendingUpdates replaces pendingUpdates", () => {
        expect(pendingUpdates).toEqual([]);
        const updates = [{ type: "agent_message_chunk" as const, data: { text: "hi" } }];
        setPendingUpdates(updates);
        expect(pendingUpdates).toEqual(updates);
    });

    it("pushPendingUpdate appends to pendingUpdates", () => {
        setPendingUpdates([]);
        pushPendingUpdate({ type: "agent_message_chunk", data: { text: "a" } });
        pushPendingUpdate({ type: "thinking_chunk", data: { text: "b" } });
        expect(pendingUpdates).toHaveLength(2);
        expect(pendingUpdates[0].type).toBe("agent_message_chunk");
    });

    it("setPendingPermId updates pendingPermId", () => {
        expect(pendingPermId).toBeNull();
        setPendingPermId("req-42");
        expect(pendingPermId).toBe("req-42");
        setPendingPermId(null);
        expect(pendingPermId).toBeNull();
    });

    it("toolCallElements is a Map", () => {
        expect(toolCallElements).toBeInstanceOf(Map);
        const div = document.createElement("div");
        toolCallElements.set("call-1", div);
        expect(toolCallElements.get("call-1")).toBe(div);
    });
});
