import { chatContainer, messageInput, sendBtn, cancelBtn } from "./dom.js";
import { appendMessage } from "./messages.js";
import { connect, sendMessage, initSessionButtons } from "./ws.js";
import { sessionId, isProcessing, setIsProcessing, setAutoScroll } from "./state.js";

function updateInputState(): void {
    messageInput.disabled = isProcessing;
    sendBtn.disabled = isProcessing;
    const spinnerEl = document.getElementById("spinner") as HTMLDivElement;
    spinnerEl.style.display = isProcessing ? "inline-block" : "none";
    cancelBtn.style.display = isProcessing ? "inline-block" : "none";
    if (!isProcessing) {
        cancelBtn.textContent = "Cancel";
        cancelBtn.disabled = false;
        const statusEl = document.getElementById("status") as HTMLDivElement;
        statusEl.textContent = "Connected";
    }
}

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
