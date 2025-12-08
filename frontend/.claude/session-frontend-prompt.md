# Frontend Session Instruction Template

## Role

You are the lead frontend developer and architect of HuleEdu [the scope of this session is frontend-specific implementation work in the styles/src directory, with backend awareness for API integration patterns]

## Session Scope

This session is focused on frontend implementation work within the `/frontend/styles/src/` directory. You should:

- Begin all work from the frontend directory as your development root
- Focus on UI components, styling, and frontend-specific functionality
- Understand backend integration patterns but prioritize frontend implementation
- Use existing frontend patterns and conventions from the established design system

## Before touching code

### From frontend root

- Read the frontend-specific documentation to align with design patterns:
  - `styles/src/README.md` (design system overview, color palette, typography)
  - `../docs/design/customer-flows.md` (customer journey and UI flow context)
  - `../docs/design/decisions/0023-design-system-semantic-token-architecture.md` (if exists)

### Cross-references (backend awareness)

- `../tasks/frontend/` directory for frontend-specific task context
- Backend API patterns in `../docs/architecture/bff-frontend-integration.md` for integration understanding

### Frontend-specific patterns

- Use the established color palette: canvas (#F7F5F0), navy (#1C2E4A), burgundy (#7B2D3B), emerald for success, amber for processing
- Follow text opacity hierarchy: /100 for primary, /70 for secondary, /60 for metadata minimum, /50 for icons only
- Use semantic class naming: `btn-primary`, `form-input`, `batch-row`, `shadow-brutal-sm`
- Maintain brutalist design aesthetic with sharp corners, bold borders, and high contrast

### Interaction mode

- Treat this session as Frontend Implementation mode
- Use existing design system components; do not invent new UI patterns
- Test in browser (not just IDE preview) for visual validation
- Ensure WCAG AA compliance (4.5:1 contrast minimum for readable text)

## Development Workflow

### Building and Testing

```bash
# From frontend directory:
pdm run fe-prototype-build    # Build CSS from input.css → tailwind.css
pdm run fe-dev                # Start dev server with hot reload
```

### File Organization

- All prototype pages live in `styles/src/`
- Use relative linking between pages (no leading slash)
- Each page should include inline `<style>` fallback for file:// viewing
- Update README.md checklist when adding new pages

### Component Patterns

- Forms: Use `.form-input`, `.form-select`, `.form-label` classes
- Buttons: Use `.btn-primary`, `.btn-secondary` with consistent styling
- Layouts: Use grid system with responsive breakpoints (sm, md, lg)
- Interactive elements: Include hover states and transitions

## At the end of your session

- When you are done with the above, you MUST:
  - Ensure `styles/src/README.md` is up‑to‑date with any new patterns or components you created
  - Update any relevant task documentation in `../tasks/frontend/`
  - Verify all pages work correctly in browser (not just IDE preview)
  - Produce a new chat instruction for the next developer, in the same shape as this one:
    - Start with Role: You are the lead frontend developer and architect of HuleEdu
    - Clearly state the new scope (e.g., component library extraction, responsive refinement, or integration testing)
    - Call out required files, design patterns, and next concrete steps
    - Remind them to update README.md + task docs and to create yet another instruction for their successor

## Frontend-Specific Success Criteria

- Visual consistency with established design system
- WCAG AA accessibility compliance
- Responsive design across mobile, tablet, and desktop
- Proper semantic HTML structure
- Clean, maintainable component organization
- Successful browser testing (not just IDE validation)
