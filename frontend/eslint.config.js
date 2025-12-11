import js from "@eslint/js";
import tseslint from "typescript-eslint";
import pluginVue from "eslint-plugin-vue";

export default tseslint.config(
  // Ignore patterns
  {
    ignores: ["dist/**", "node_modules/**", "*.d.ts", "docs/**"],
  },

  // Base JS recommended rules
  js.configs.recommended,

  // TypeScript recommended rules
  ...tseslint.configs.recommended,

  // Vue 3 recommended rules
  ...pluginVue.configs["flat/recommended"],

  // Vue files: use vue-eslint-parser with TypeScript
  {
    files: ["**/*.vue"],
    languageOptions: {
      parserOptions: {
        parser: tseslint.parser,
      },
    },
  },

  // Project-specific rules for all files
  {
    files: ["**/*.{js,ts,vue}"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: {
        // Browser globals
        window: "readonly",
        document: "readonly",
        console: "readonly",
        fetch: "readonly",
        URL: "readonly",
        URLSearchParams: "readonly",
        localStorage: "readonly",
        sessionStorage: "readonly",
        setTimeout: "readonly",
        clearTimeout: "readonly",
        setInterval: "readonly",
        clearInterval: "readonly",
        WebSocket: "readonly",
        Headers: "readonly",
        Request: "readonly",
        Response: "readonly",
        FormData: "readonly",
        Blob: "readonly",
        File: "readonly",
        FileReader: "readonly",
        AbortController: "readonly",
        AbortSignal: "readonly",
        EventSource: "readonly",
        CustomEvent: "readonly",
        Event: "readonly",
        HTMLElement: "readonly",
        HTMLInputElement: "readonly",
        HTMLTextAreaElement: "readonly",
        HTMLSelectElement: "readonly",
        HTMLFormElement: "readonly",
        Element: "readonly",
        Node: "readonly",
        NodeList: "readonly",
        MutationObserver: "readonly",
        IntersectionObserver: "readonly",
        ResizeObserver: "readonly",
        requestAnimationFrame: "readonly",
        cancelAnimationFrame: "readonly",
        history: "readonly",
        location: "readonly",
        navigator: "readonly",
        performance: "readonly",
        crypto: "readonly",
        atob: "readonly",
        btoa: "readonly",
      },
    },
    rules: {
      // Formatting - match backend standards
      "max-len": [
        "warn",
        { code: 100, ignoreUrls: true, ignoreStrings: true, ignoreTemplateLiterals: true },
      ],
      "quotes": ["error", "double", { avoidEscape: true }],
      "indent": ["error", 2, { SwitchCase: 1 }],
      "semi": ["error", "always"],
      "comma-dangle": ["error", "always-multiline"],

      // TypeScript rules
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
      "@typescript-eslint/explicit-function-return-type": "off",
      "@typescript-eslint/no-explicit-any": "warn",

      // Vue 3 rules
      "vue/component-api-style": ["error", ["script-setup"]],
      "vue/define-macros-order": [
        "error",
        { order: ["defineProps", "defineEmits", "defineSlots"] },
      ],
      "vue/block-order": ["error", { order: ["script", "template", "style"] }],
      "vue/multi-word-component-names": "off",
      "vue/html-indent": ["error", 2],
      "vue/max-attributes-per-line": [
        "error",
        { singleline: 3, multiline: 1 },
      ],
      "vue/singleline-html-element-content-newline": "off",
      "vue/html-self-closing": [
        "error",
        {
          html: { void: "always", normal: "never", component: "always" },
          svg: "always",
          math: "always",
        },
      ],
      // Optional props without defaults are valid TypeScript
      "vue/require-default-prop": "off",
    },
  },

  // Disable max-len for Vue files (Tailwind classes cause long lines)
  {
    files: ["**/*.vue"],
    rules: {
      "max-len": "off",
    },
  },
);
