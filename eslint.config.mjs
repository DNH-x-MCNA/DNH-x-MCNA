import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // Archived/generated trees are not part of the production app.
    "_deprecated/**",
    "bao-cao-canh-bao/**",
    "frontend/**",
    ".tmp-codex-*/**",
    "handoff_private/**",
    "outputs/**",
  ]),
]);

export default eslintConfig;
