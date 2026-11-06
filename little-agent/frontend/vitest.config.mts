import { defineConfig } from "vitest/config";

export default defineConfig({
    test: {
        environment: "happy-dom",
        include: ["src/**/*.test.ts"],
        setupFiles: ["src/test-setup.ts"],
        coverage: {
            provider: "v8",
            include: ["src/**/*.ts"],
            exclude: ["src/**/*.test.ts"],
            reporter: ["text", "json-summary"],
        },
    },
});
