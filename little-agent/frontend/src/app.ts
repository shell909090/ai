import { chatContainer, messageInput, sendBtn, cancelBtn } from "./dom.js";
import { appendMessage, appendSystemMessage } from "./messages.js";
import {
    connect,
    sendMessage,
    initSessionButtons,
    updateInputState,
    compactSession,
    cancelSession,
    listTools,
    newSession,
    forkCurrentSession,
} from "./ws.js";
import { sessionId, isProcessing, setIsProcessing, setAutoScroll } from "./state.js";

const SLASH_COMMANDS: string[] = ["/cancel", "/compact", "/fork", "/list-tools", "/new"];

export function handleSlashCommand(cmd: string): void {
    switch (cmd) {
        case "/compact":
            compactSession();
            break;
        case "/cancel":
            cancelSession();
            break;
        case "/list-tools":
            listTools();
            break;
        case "/new":
            newSession();
            break;
        case "/fork":
            forkCurrentSession();
            break;
        default:
            appendSystemMessage(`Unknown command: ${cmd}. Available: ${SLASH_COMMANDS.join(" ")}`);
    }
}

export function sendPrompt(): void {
    const text: string = messageInput.value.trim();
    if (!text) return;

    if (text.startsWith("/")) {
        messageInput.value = "";
        handleSlashCommand(text);
        return;
    }

    if (!sessionId || isProcessing) return;

    setAutoScroll(true);
    appendMessage("user", text);
    messageInput.value = "";
    setIsProcessing(true);
    updateInputState();

    sendMessage({
        type: "session/prompt",
        session_id: sessionId,
        prompt: text,
    });
}

document.addEventListener("DOMContentLoaded", (): void => {
    sendBtn.addEventListener("click", sendPrompt);
    messageInput.addEventListener("keypress", (e: KeyboardEvent): void => {
        if (e.key === "Enter") sendPrompt();
    });
    cancelBtn.addEventListener("click", (): void => {
        if (sessionId) {
            cancelBtn.disabled = true;
            cancelBtn.textContent = "Cancelling…";
            sendMessage({ type: "session/cancel", session_id: sessionId });
        }
    });

    messageInput.addEventListener("input", (): void => {
        if (messageInput.value.startsWith("/")) {
            messageInput.setAttribute("list", "slash-commands");
        } else {
            messageInput.removeAttribute("list");
        }
    });

    chatContainer.addEventListener("scroll", (): void => {
        const distanceFromBottom =
            chatContainer.scrollHeight - chatContainer.scrollTop - chatContainer.clientHeight;
        setAutoScroll(distanceFromBottom <= 50);
    });

    initSessionButtons();
    connect();
});
