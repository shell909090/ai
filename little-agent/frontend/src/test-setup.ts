// Polyfill WebSocket constants if not available in happy-dom.
if (typeof WebSocket === "undefined" || typeof WebSocket.OPEN === "undefined") {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (globalThis as any).WebSocket = class MockWebSocket {
        static readonly CONNECTING = 0;
        static readonly OPEN = 1;
        static readonly CLOSING = 2;
        static readonly CLOSED = 3;
        readonly CONNECTING = 0;
        readonly OPEN = 1;
        readonly CLOSING = 2;
        readonly CLOSED = 3;
        readyState = 0;
        onopen: (() => void) | null = null;
        onmessage: ((e: MessageEvent) => void) | null = null;
        onclose: (() => void) | null = null;
        onerror: (() => void) | null = null;
        // eslint-disable-next-line @typescript-eslint/no-unused-vars
        send(_data: string): void {}
        close(): void {}
    };
}

// Global DOM setup for tests that import modules with module-level getElementById calls.
document.body.innerHTML = `
<div id="chat-container"></div>
<input id="message-input" />
<button id="send-btn"></button>
<button id="cancelButton"></button>
<div id="spinner"></div>
<div id="status"></div>
<div id="session-info"></div>
<div id="permission-modal"></div>
<p id="permission-text"></p>
<button id="perm-allow"></button>
<button id="perm-deny"></button>
<div id="session-list"></div>
<button id="new-session-btn"></button>
<button id="fork-session-btn"></button>
<button id="compact-session-btn"></button>
<button id="delete-session-btn"></button>
`;
