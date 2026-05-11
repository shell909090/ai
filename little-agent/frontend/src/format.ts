export function formatArgs(args: Record<string, unknown>): string {
    const lines: string[] = [];
    for (const [k, v] of Object.entries(args)) {
        const val = typeof v === "string" ? v : JSON.stringify(v, null, 2);
        lines.push(`${k}: ${val}`);
    }
    const joined = lines.join("\n");
    const splitLines = joined.split("\n");
    const maxLines = 5;
    if (splitLines.length > maxLines) {
        return (
            splitLines.slice(0, maxLines).join("\n") +
            `\n...${splitLines.length - maxLines} lines...`
        );
    }
    return joined;
}

export function formatResult(content: unknown, maxLines: number = 20): string {
    let text: string;
    if (typeof content === "string") {
        text = content;
    } else if (content !== null && typeof content === "object") {
        const obj = content as Record<string, unknown>;
        text = Object.entries(obj)
            .map(([k, v]) => `${k}: ${typeof v === "string" ? v : JSON.stringify(v)}`)
            .join("\n");
    } else {
        text = String(content ?? "");
    }
    const lines = text.split("\n");
    if (lines.length > maxLines) {
        return (
            lines.slice(0, maxLines).join("\n") + `\n...${lines.length - maxLines} more lines...`
        );
    }
    return text;
}

export function formatSessionDate(updated_at: string): string {
    const date = new Date(updated_at);
    const now = new Date();
    const isToday =
        date.getFullYear() === now.getFullYear() &&
        date.getMonth() === now.getMonth() &&
        date.getDate() === now.getDate();
    if (isToday) {
        return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    }
    return date.toLocaleDateString([], { month: "short", day: "numeric" });
}
