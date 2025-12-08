# Frontend Session Instructions

## Role

You are the lead frontend developer and architect of HuleEdu. The scope of this session is frontend-specific implementation work in the `styles/src` directory, with backend awareness for API integration patterns.

## Session Scope

This session is focused on frontend implementation work within the `/frontend/styles/src/` directory. You should:

- Begin all work from the frontend directory as your development root
- Focus on UI components, styling, and frontend-specific functionality
- Understand backend integration patterns but prioritize frontend implementation
- Use existing frontend patterns and conventions from the established design system

## Before Touching Code

### From frontend root

Read the frontend-specific documentation to align with design patterns:

- `styles/src/README.md` – Design system overview, color palette, typography
- `docs/design/customer-flows.md` – Customer journey and UI flow context (Swedish)
- `docs/decisions/0023-design-system-semantic-token-architecture.md` – Token architecture

### Cross-references (backend awareness)

- `../TASKS/frontend/` directory for frontend-specific task context
- Backend API patterns in `docs/architecture/bff-frontend-integration.md`
- API types in `docs/reference/apis/api-types.ts`

### Frontend-specific patterns

**Color palette:**
- `canvas` (#F9F8F2) – Warm off-white background
- `navy` (#1C2E4A) – Text, borders, structure
- `burgundy` (#6B1C2E) – CTAs, accents, action required
- `emerald-700` (#047857) – Success states
- `amber-500/600` – Processing, in-progress

**Text opacity hierarchy (WCAG AA):**
- `/100` – Primary text, headings (12:1 contrast)
- `/70` – Secondary text, descriptions (6:1)
- `/60` – Metadata, labels, timestamps (4.5:1 minimum)
- `/50` – Icons only (not for readable text)
- `/40-30` – Decorative elements only

**Semantic class naming:**
- Buttons: `btn-primary`, `btn-secondary`
- Forms: `form-input`, `form-select`, `form-label`, `form-textarea`, `form-card`
- Layout: `ledger-frame`, `batch-row`, `dashboard-layout`
- Effects: `shadow-brutal`, `shadow-brutal-sm`, `wavy-error`

**Typography:**
- `font-sans` (IBM Plex Sans) – UI text, labels
- `font-serif` (IBM Plex Serif) – Student text, quotes
- `tracking-tightest` (-0.02em) – Headings
- `tracking-label` (0.08em) – Labels, buttons

**Design aesthetic:**
- Brutalist: Sharp corners, 1px borders, hard offset shadows
- High contrast, minimal decoration
- 150ms transitions (never slower)

### Interaction mode

- Treat this session as Frontend Implementation mode
- Use existing design system components; do not invent new UI patterns
- Test in browser (not just IDE preview) for visual validation
- Ensure WCAG AA compliance (4.5:1 contrast minimum for readable text)

## Development Workflow

### Building and Testing

```bash
# From monorepo root (PDM handles working_dir):
pdm run fe-prototype-build    # Compile input.css → tailwind.css
pdm run fe-dev                # Vite dev server (localhost:5173)
pdm run fe-type-check         # TypeScript checking

# Direct file viewing:
open frontend/styles/src/huleedu-landing-final.html
```

### File Organization

```
frontend/styles/src/
├── README.md                    ← Design system docs (Swedish)
├── input.css                    ← Tailwind source + custom components
├── tailwind.css                 ← Compiled CSS (do not edit)
├── HuleEduLogo.svg              ← Brand logo
│
├── huleedu-landing-final.html   ← Landing page (public)
├── anmal-intresse.html          ← Waitlist signup (Persona A)
├── for-skolor.html              ← Contact form (Persona B) [PLANNED]
│
├── login.html                   ← Authentication
├── dashboard.html               ← Teacher command center
└── upload.html                  ← File upload & batch management
```

### Component Patterns

**Forms:**
```html
<form class="form-card">
  <label class="form-label">E-post *</label>
  <input type="email" class="form-input" placeholder="namn@skola.se">
  <select class="form-select">...</select>
  <textarea class="form-textarea" rows="3">...</textarea>
  <button type="submit" class="btn-primary w-full">Skicka</button>
</form>
```

**Interactive feedback (hover tooltips):**
```html
<span class="relative inline-block group/name">
  <span class="highlighted-text cursor-help">text</span>
  <span class="absolute bottom-full left-1/2 -translate-x-1/2 mb-2
               bg-burgundy text-canvas text-xs font-sans py-1.5 px-3
               opacity-0 invisible group-hover/name:opacity-100 group-hover/name:visible
               transition-all duration-150">
    Feedback text
    <span class="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-burgundy"></span>
  </span>
</span>
```

**Conditional fields (JS pattern):**
```html
<select data-toggle="field-id">
  <option value="annat">Annat</option>
</select>
<div id="field-id" class="hidden mt-2">
  <input type="text" class="form-input" placeholder="Beskriv...">
</div>

<script>
document.addEventListener('change', (e) => {
  if (!e.target.matches('select[data-toggle]')) return;
  const target = document.getElementById(e.target.dataset.toggle);
  if (target) target.classList.toggle('hidden', e.target.value !== 'annat');
});
</script>
```

### Page Checklist (when creating new pages)

1. [ ] Copy nearest similar existing page as template
2. [ ] Update `<title>` and `<meta name="description">`
3. [ ] Use centralized classes (no custom one-off styles)
4. [ ] Add inline `<style>` fallback for file:// viewing
5. [ ] Test in browser (Chrome, Safari minimum)
6. [ ] Update `styles/src/README.md` with new file
7. [ ] Link from related pages (navigation, CTAs)

## Recommended Next Steps

### Priority 1: Complete Persona B flow
- Create `for-skolor.html` – Contact form for schools/municipalities
- Fields: Namn, Organisation, Roll, Telefon, Meddelande
- B2B tone, reference to demo/meeting booking

### Priority 2: Review remaining prototypes
- `login.html` – Verify alignment with design system
- `dashboard.html` – Teacher command center patterns
- `upload.html` – File upload UX

### Priority 3: Structural improvements
- Add watch mode: `fe-prototype-watch` for hot CSS reload
- Extract design tokens to `tokens/` directory
- Consider renaming `styles/src/` → `prototypes/` for clarity

### Priority 4: Vue migration prep
- Map prototype components to Vue component boundaries
- Set up Storybook for component documentation
- Automate OpenAPI → TypeScript type generation

## At the End of Your Session

When you are done, you MUST:

1. **Update documentation:**
   - Ensure `styles/src/README.md` reflects any new patterns or components
   - Update relevant task docs in `../TASKS/frontend/`

2. **Verify quality:**
   - Test all modified pages in browser (not just IDE preview)
   - Confirm WCAG AA compliance for new elements
   - Check responsive behavior (mobile, tablet, desktop)

3. **Update session context:**
   - Edit `frontend/.claude/work/session/handoff.md` with:
     - What was completed this session
     - What remains to be done
     - Key files touched
   - Produce updated instructions for the next developer in this file

## Frontend-Specific Success Criteria

- [ ] Visual consistency with established design system
- [ ] WCAG AA accessibility compliance (4.5:1 contrast minimum)
- [ ] Responsive design across mobile, tablet, and desktop
- [ ] Proper semantic HTML structure
- [ ] Clean, maintainable component organization
- [ ] Successful browser testing (not just IDE validation)
- [ ] Swedish UI text is idiomatic (not Swenglish)
- [ ] Documentation updated

---

## Cross-Reference

- **Backend context:** `/.claude/work/session/handoff.md`
- **Frontend handoff:** `frontend/.claude/work/session/handoff.md`
- **Monorepo rules:** `/.claude/rules/200-frontend-core-rules.md`
- **Design specs:** `frontend/docs/design/customer-flows.md`
