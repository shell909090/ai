import js from "@eslint/js";
import tseslint from "typescript-eslint";
import prettier from "eslint-config-prettier";

export default [
    js.configs.recommended,
    ...tseslint.configs.recommended,
    prettier,
    {
        files: ["src/**/*.ts"],
        languageOptions: {
            parserOptions: { project: "./tsconfig.json" },
        },
    },
    {
        files: ["**/*.config.{js,mjs,ts}", "eslint.config.mjs"],
        rules: { "@typescript-eslint/no-require-imports": "off" },
    },
];
