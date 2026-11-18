import eslint from "@eslint/js";
import globals from "globals";
import tseslint from "typescript-eslint";

const aLayerFiles = [
  "src/features/api/**/*.{ts,tsx}",
  "src/features/bundle/**/*.{ts,tsx}",
  "src/features/session/**/*.{ts,tsx}",
  "src/features/view-model/**/*.{ts,tsx}",
];

const forbidden = (segment, message) => ({ regex: `(^|/)${segment}(/|$)`, message });

export default tseslint.config(
  {
    ignores: [
      "dist/**",
      "node_modules/**",
      "coverage/**",
      "playwright-report/**",
      "test-results/**",
      "src/features/api/generated/openapi.d.ts",
    ],
  },
  eslint.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: { globals: globals.browser },
  },
  {
    files: ["src/design-system/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            forbidden("features", "设计系统组件不得依赖 features 层。"),
            forbidden("pages", "设计系统组件不得依赖 pages 层。"),
          ],
        },
      ],
    },
  },
  {
    files: aLayerFiles,
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            forbidden("design-system", "A 层模块不得依赖 design-system（B 层）。"),
            forbidden("pages", "A 层模块不得依赖 pages（C 层）。"),
            forbidden("workbench", "A 层模块不得依赖 workbench（C 层）。"),
            forbidden("dev", "A 层模块不得依赖 dev 辅助模块。"),
          ],
        },
      ],
    },
  },
  {
    files: [
      "src/features/api/**/*.test.{ts,tsx}",
      "src/features/bundle/**/*.test.{ts,tsx}",
      "src/features/session/**/*.test.{ts,tsx}",
      "src/features/view-model/**/*.test.{ts,tsx}",
    ],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            forbidden("design-system", "A 层模块不得依赖 design-system（B 层）。"),
            forbidden("pages", "A 层模块不得依赖 pages（C 层）。"),
            forbidden("workbench", "A 层模块不得依赖 workbench（C 层）。"),
          ],
        },
      ],
    },
  },
  {
    files: ["src/features/workbench/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [forbidden("pages", "features/workbench 不得依赖 pages（C 层）。")],
        },
      ],
    },
  },
  {
    files: ["scripts/**/*.mjs"],
    languageOptions: { globals: globals.node },
  },
  {
    files: ["*.config.{js,ts}", "eslint.config.js"],
    languageOptions: { globals: globals.node },
  },
);
