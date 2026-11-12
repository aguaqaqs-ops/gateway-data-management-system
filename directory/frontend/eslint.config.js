import eslint from "@eslint/js";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist/**", "node_modules/**", "test-results/**", "playwright-report/**"] },
  eslint.configs.recommended,
  ...tseslint.configs.recommended,
  { files: ["**/*.{ts,tsx}"], languageOptions: { globals: globals.browser } },
  { files: ["*.config.{js,ts}", "e2e/**/*.ts"], languageOptions: { globals: globals.node } }
);
