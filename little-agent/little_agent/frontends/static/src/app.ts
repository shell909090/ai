import { chatContainer, messageInput, sendBtn, cancelBtn } from "./dom.js";
import { appendMessage } from "./messages.js";
import { connect, sendMessage, initSessionButtons, updateInputState } from "./ws.js";
import { sessionId, isProcessing, setIsProcessing, setAutoScroll } from "./state.js";

function sendPrompt(): void {
    const text: string = messageInput.value.trim();
    if (!text || !sessionId || isProcessing) return;

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

    chatContainer.addEventListener("scroll", (): void => {
        const distanceFromBottom =
            chatContainer.scrollHeight - chatContainer.scrollTop - chatContainer.clientHeight;
        setAutoScroll(distanceFromBottom <= 50);
    });

    initSessionButtons();
    connect();
});
