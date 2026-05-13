// WebSocket message payload types

export interface SessionNewResponseMsg {
    type: "session/new_response";
    session_id: string;
}

export interface SessionPromptResponseMsg {
    type: "session/prompt_response";
    text?: string;
}

export interface AgentMessageChunkUpdate {
    type: "agent_message_chunk";
    data?: { text?: unknown };
}

export interface ThinkingChunkUpdate {
    type: "thinking_chunk";
    data?: { text?: unknown };
}

export interface CallData {
    tool_name?: unknown;
    arguments?: unknown;
}

export interface ToolCallUpdate {
    type: "tool_call";
    data?: { calls?: Record<string, CallData> };
}

export interface ToolCallUpdateMsg {
    type: "tool_call_update";
    data?: { status?: unknown; content?: unknown; call_id?: unknown };
}

export type SessionUpdatePayload =
    | AgentMessageChunkUpdate
    | ThinkingChunkUpdate
    | ToolCallUpdate
    | ToolCallUpdateMsg;

export interface SessionUpdateMsg {
    type: "session/update";
    session_id?: string;
    update: SessionUpdatePayload;
}

export interface SessionRequestPermissionMsg {
    type: "session/request_permission";
    id: string;
    kind: string;
    payload?: { arguments?: unknown };
}

export interface ErrorMsg {
    type: "error";
    error: string;
}

export interface SessionInfo {
    id: string;
    updated_at: string;
    preview: string;
}

export interface SessionListResponseMsg {
    type: "session/list_response";
    sessions: SessionInfo[];
}

export interface SessionHistoryNode {
    kind: string;
    id: string;
    created_at?: string;
    prompt?: string;
    text?: string;
    thinking?: string;
    tool_calls?: Record<string, unknown>;
    results?: Record<string, unknown>;
}

export interface SessionHistoryMsg {
    type: "session/history";
    session_id: string;
    nodes: SessionHistoryNode[];
}

export interface SessionForkResponseMsg {
    type: "session/fork_response";
    session_id: string;
}

export interface SessionDeleteResponseMsg {
    type: "session/delete_response";
    session_id: string;
}

export interface SessionCompactResponseMsg {
    type: "session/compact_response";
    ok: boolean;
    error?: string;
}

export interface ToolsListResponseMsg {
    type: "tools/list_response";
    tools: Array<{ name: string; desc: string }>;
}

export type ServerMessage =
    | SessionNewResponseMsg
    | SessionPromptResponseMsg
    | SessionUpdateMsg
    | SessionRequestPermissionMsg
    | ErrorMsg
    | SessionListResponseMsg
    | SessionHistoryMsg
    | SessionForkResponseMsg
    | SessionDeleteResponseMsg
    | SessionCompactResponseMsg
    | ToolsListResponseMsg;

export interface ClientMessage {
    type: string;
    [key: string]: unknown;
}
