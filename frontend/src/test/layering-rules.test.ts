// @vitest-environment node
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { ESLint } from "eslint";

const cwd = process.cwd();
const eslint = new ESLint({ cwd });

interface LayeringCase {
  name: string;
  file: string;
  source: string;
  forbidden: string | null;
}

const cases: LayeringCase[] = [
  {
    name: "design-system cannot import features",
    file: "src/design-system/layering-features.ts",
    source: 'import "../features/api/connection-status";\n',
    forbidden: "features 层",
  },
  {
    name: "design-system cannot import a bare features segment",
    file: "src/design-system/layering-features-bare.ts",
    source: 'import "../features";\n',
    forbidden: "features 层",
  },
  {
    name: "design-system cannot import pages",
    file: "src/design-system/layering-pages.ts",
    source: 'import "../pages/WorkbenchPage";\n',
    forbidden: "pages 层",
  },
  {
    name: "design-system may import its own components",
    file: "src/design-system/layering-own.ts",
    source: 'import "./components";\n',
    forbidden: null,
  },
  {
    name: "api cannot import design-system",
    file: "src/features/api/layering-design-system.ts",
    source: 'import "../../design-system/components";\n',
    forbidden: "design-system（B 层）",
  },
  {
    name: "bundle cannot import pages",
    file: "src/features/bundle/layering-pages.ts",
    source: 'import "../../pages/WorkbenchPage";\n',
    forbidden: "pages（C 层）",
  },
  {
    name: "session cannot import workbench",
    file: "src/features/session/layering-workbench.ts",
    source: 'import "../workbench/ConnectionStatusIndicator";\n',
    forbidden: "workbench（C 层）",
  },
  {
    name: "view-model cannot import dev helpers",
    file: "src/features/view-model/layering-dev.ts",
    source: 'import "../dev/mock";\n',
    forbidden: "dev 辅助模块",
  },
  {
    name: "api tests may import dev helpers",
    file: "src/features/api/layering-dev.test.ts",
    source: 'import "../dev/mock";\n',
    forbidden: null,
  },
  {
    name: "api tests still cannot import workbench",
    file: "src/features/api/layering-workbench.test.ts",
    source: 'import "../workbench/ConnectionStatusIndicator";\n',
    forbidden: "workbench（C 层）",
  },
  {
    name: "api may import bundle and view-model",
    file: "src/features/api/layering-lower.ts",
    source: 'import "../bundle/local-bundle";\nimport "../view-model/model";\n',
    forbidden: null,
  },
  {
    name: "workbench cannot import pages",
    file: "src/features/workbench/layering-pages.ts",
    source: 'import "../../pages/ComparisonPage";\n',
    forbidden: "pages（C 层）",
  },
  {
    name: "workbench may import the api",
    file: "src/features/workbench/layering-api.ts",
    source: 'import "../api/connection-status";\n',
    forbidden: null,
  },
];

describe("layering import rules", () => {
  it.each(cases)("$name", async ({ file, source, forbidden }) => {
    const [result] = await eslint.lintText(source, { filePath: resolve(cwd, file) });
    const restricted = result.messages.filter(
      (message) => message.ruleId === "no-restricted-imports",
    );
    if (forbidden === null) {
      expect(restricted).toEqual([]);
      return;
    }
    expect(restricted.some((message) => message.message.includes(forbidden))).toBe(true);
  });
});
