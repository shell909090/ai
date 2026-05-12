import { defineConfig } from "vitest/config";

export default defineConfig({
    test: {
        environment: "happy-dom",
        include: ["src/**/*.test.ts"],
        setupFiles: ["src/test-setup.ts"],
        // pool: forks + singleFork avoids OOM under v8 coverage × happy-dom.
        // See docs/log.md F-1 fix.
        pool: "forks",
        poolOptions: {
            forks: {
                singleFork: true,
            },
        },
        coverage: {
            provider: "v8",
            include: ["src/**/*.ts"],
            exclude: ["src/**/*.test.ts"],
            reporter: ["text", "json-summary"],
        },
    },
});
