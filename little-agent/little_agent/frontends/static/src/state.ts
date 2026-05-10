import type { SessionInfo, SessionUpdatePayload } from "./types.js";

export let ws: WebSocket | null = null;
export let sessionId: string | null = null;
export let isProcessing: boolean = false;
export let autoScroll: boolean = true;
export let sessionList: SessionInfo[] = [];
export let autoResumeOnNextList: boolean = false;

// Track live tool-call bubbles by call_id so tool_call_update can recolor them.
export const toolCallElements: Map<string, HTMLDivElement> = new Map();

// While waiting for session/history, buffer session/update events so they don't
// interleave with the history render, then replay them afterwards.
export let historyPending: boolean = false;
export let pendingUpdates: SessionUpdatePayload[] = [];

export let pendingPermId: string | null = null;

export function setWs(value: WebSocket | null): void {
    ws = value;
}

export function setSessionId(value: string | null): void {
    sessionId = value;
}

export function setIsProcessing(value: boolean): void {
    isProcessing = value;
}

export function setAutoScroll(value: boolean): void {
    autoScroll = value;
}

export function setSessionList(value: SessionInfo[]): void {
    sessionList = value;
}

export function setAutoResumeOnNextList(value: boolean): void {
    autoResumeOnNextList = value;
}

export function setHistoryPending(value: boolean): void {
    historyPending = value;
}

export function setPendingUpdates(value: SessionUpdatePayload[]): void {
    pendingUpdates = value;
}

export function pushPendingUpdate(value: SessionUpdatePayload): void {
    pendingUpdates.push(value);
}

export function setPendingPermId(value: string | null): void {
    pendingPermId = value;
}
