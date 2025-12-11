---
id: "054-utility-markdown-mermaid-conversion"
type: "operational"
created: 2025-09-01
last_updated: 2025-11-17
scope: "documentation"
---

# 054: Markdown to HTML Conversion with Mermaid

## 1. Default Implementation

**ALWAYS use** `convert_md_to_teams_static.py` for Mermaid conversion.

**Root cause of "syntax error in text"**: Pandoc outputs `<pre class="mermaid">` but Mermaid.js expects `<div class="mermaid">`.

**Solution**: Convert Mermaid to static PNG images using mermaid-cli, embed as base64.

```bash
# Required setup (already installed)
npm install -g @mermaid-js/mermaid-cli
pip install pypandoc

# Usage
pdm run python convert_md_to_teams_static.py "file.md"
```

## 2. Modern Color Scheme

**MUST use** these colors for professional appearance:

```css
classDef core fill:#f0f9ff,stroke:#0ea5e9,stroke-width:2px,color:#0c4a6e
classDef service fill:#f0fdf4,stroke:#22c55e,stroke-width:2px,color:#14532d  
classDef comm fill:#fffbeb,stroke:#f59e0b,stroke-width:2px,color:#92400e
classDef infra fill:#fafafa,stroke:#71717a,stroke-width:2px,color:#3f3f46
classDef obs fill:#faf5ff,stroke:#8b5cf6,stroke-width:2px,color:#581c87
```

## 3. Mermaid Syntax Rules

- Use ASCII identifiers: `subgraph CoreModules ["Display Name"]`
- Avoid experimental syntax like `@{shape:}`
- Use Mermaid 10.9.1 for stability
- Test syntax before deployment

## 4. Teams Compatibility

- Static images work in Teams chat (no JavaScript restrictions)
- JavaScript versions fail in Teams (security limitations)
- Base64 embedding ensures offline functionality
- 1200x800 resolution for professional quality
