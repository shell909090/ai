import { describe, it, expect } from "vitest";
import { formatArgs, formatResult } from "./format.js";

describe("formatArgs", () => {
    it("returns empty string for empty args", () => {
        expect(formatArgs({})).toBe("");
    });

    it("does not truncate short args", () => {
        const result = formatArgs({ key: "value" });
        expect(result).toBe("key: value");
        expect(result).not.toContain("lines...");
    });

    it("truncates args exceeding 5 lines and includes line count", () => {
        // Six key-value pairs where each value has a newline → many lines
        const longValue = "a\nb\nc\nd\ne\nf";
        const result = formatArgs({ x: longValue });
        expect(result).toContain("lines...");
    });

    it("handles multiple keys joined with newlines", () => {
        const result = formatArgs({ a: "1", b: "2" });
        expect(result).toContain("a: 1");
        expect(result).toContain("b: 2");
    });

    it("serializes non-string values as JSON", () => {
        const result = formatArgs({ obj: { nested: true } });
        expect(result).toContain("obj:");
        expect(result).toContain("nested");
    });
});

describe("formatResult", () => {
    it("returns string content as-is when within maxLines", () => {
        const result = formatResult("hello world");
        expect(result).toBe("hello world");
    });

    it("truncates content exceeding maxLines with more lines message", () => {
        const longText = Array.from({ length: 25 }, (_, i) => `line ${i}`).join("\n");
        const result = formatResult(longText, 20);
        expect(result).toContain("more lines...");
        expect(result.split("\n").length).toBeLessThan(25);
    });

    it("formats object content as key: value lines", () => {
        const result = formatResult({ status: "ok", code: 200 });
        expect(result).toContain("status: ok");
        expect(result).toContain("code: 200");
    });

    it("formats null/undefined as empty string", () => {
        expect(formatResult(null)).toBe("");
        expect(formatResult(undefined)).toBe("");
    });

    it("formats completed status string result", () => {
        const result = formatResult("completed successfully");
        expect(result).toBe("completed successfully");
    });

    it("formats failed status object result", () => {
        const result = formatResult({ error: "timeout", code: 408 });
        expect(result).toContain("error: timeout");
    });
});
