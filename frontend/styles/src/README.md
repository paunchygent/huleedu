# Prototyper – HTML/CSS

> **Syfte:** Self-contained HTML-prototyper för design-iteration och stakeholder-review.
> **Status:** Pre-produktion – dessa migreras till Vue 3-komponenter när designen är låst.
> **Språk:** Svenska (UI-text och dokumentation) – målgrupp är svenska lärare och skolledare.

## Relation till Vue-appen

```
frontend/
├── src/                    ← Vue 3 produktionskod (TypeScript)
├── styles/src/             ← HTML-prototyper (denna katalog)
│   ├── *.html              ← Statiska prototyper
│   ├── input.css           ← Tailwind CSS källa
│   └── tailwind.css        ← Kompilerad CSS
└── docs/                   ← Teknisk dokumentation (engelska)
```

**Arbetsflöde:**
1. Designa och iterera i HTML-prototyper (snabbt, stakeholder-vänligt)
2. När design är godkänd → migrera till Vue 3-komponenter i `src/`
3. Prototyperna arkiveras men behålls som referens

## Bygga CSS

```bash
# Från monorepo-root (PDM hanterar working_dir)
pdm run fe-prototype-build    # Kompilerar input.css → tailwind.css
```

## Struktur

```text
styles/src/
├── README.md                    ← Du är här
├── tailwind.css                 ← Kompilerad CSS (ändra ej manuellt)
├── HuleEduLogo.svg              ← Logotyp
│
├── huleedu-landing-final.html   ← Landing page (publik)
├── anmal-intresse.html          ← Väntlisteformulär (Persona A)
├── for-skolor.html              ← Kontaktformulär (Persona B) [PLANERAD]
│
├── login.html                   ← Inloggning (autentiserad)
├── dashboard.html               ← Översikt (autentiserad)
└── upload.html                  ← Filuppladdning (autentiserad)
```

## Sidkategorier

| Kategori | Filer | Målgrupp |
|----------|-------|----------|
| **Publik** | `huleedu-landing-final.html` | Alla besökare |
| **Konvertering** | `anmal-intresse.html`, `for-skolor.html` | Leads |
| **Autentiserad** | `login.html`, `dashboard.html`, `upload.html` | Inloggade lärare |

## Designmönster

Alla prototyper följer samma mönster. Kopiera från befintlig fil – **skapa inga nya klasser**.

### Dokumentstruktur

```html
<!DOCTYPE html>
<html lang="sv">
<head>
    <!-- Meta, title, fonts, tailwind.css -->
    <!-- Lokala stilar ENDAST om Tailwind-klasser saknas -->
</head>
<body class="font-sans">
    <div class="ledger-frame flex flex-col">
        <header>...</header>
        <main>...</main>
        <footer>...</footer>
    </div>
</body>
</html>
```

### Header-mönster

Tre standardiserade header-varianter. Välj baserat på sidtyp.

#### 1. Minimal (auth-sidor)

Centrerad logotyp, inget annat. Fokus på formuläret.

```html
<header class="h-16 border-b border-navy shrink-0 flex items-center justify-center">
    <a href="/" aria-label="HuleEdu startsida">
        <img src="HuleEduLogo.svg" alt="HuleEdu" class="h-8 w-auto">
    </a>
</header>
```

**Användning:** `login.html`

#### 2. App-header (autentiserade sidor)

Logotyp vänster, navigation höger. Logotyp fungerar som "hem"-länk.

```html
<header class="h-16 border-b border-navy shrink-0 flex items-center justify-between px-6">
    <a href="/" aria-label="HuleEdu startsida">
        <img src="HuleEduLogo.svg" alt="HuleEdu" class="h-8 w-auto">
    </a>
    <a href="..." class="text-xs font-semibold uppercase tracking-label text-navy/60 hover:text-navy transition-colors">
        ← Tillbaka
    </a>
</header>
```

**Användning:** `dashboard.html`, `upload.html`, `anmal-intresse.html`

#### 3. Landing-header (brutalist grid)

Logotyp i avgränsad cell, navigation i egen sektion.

```html
<header class="sticky top-0 z-50 bg-canvas border-b border-navy h-16">
    <div class="h-full flex">
        <div class="h-full border-r border-navy px-5 flex items-center">
            <a href="/" aria-label="HuleEdu startsida">
                <img src="HuleEduLogo.svg" alt="HuleEdu" class="h-8 w-auto">
            </a>
        </div>
        <!-- Fler celler för nav... -->
    </div>
</header>
```

**Användning:** `huleedu-landing-final.html`

### Formulärkomponenter (från `input.css`)

Dessa klasser definieras i `input.css` och kompileras till `tailwind.css`.

#### Formulärkort

```html
<form class="form-card">
    <!-- eller med Tailwind utilities: -->
    <form class="border border-navy bg-white p-8 shadow-brutal">
</form>
```

#### Etikett

```html
<label class="form-label">E-post *</label>
```

#### Textfält

```html
<input type="email" class="form-input" placeholder="namn@skola.se">
```

#### Select (dropdown)

```html
<select class="form-select">
    <option value="" disabled selected>Välj...</option>
    <option value="a">Alternativ A</option>
</select>
```

**Notera:** På iOS visas alltid native picker vid öppning – detta är avsiktligt för bättre touch-UX. `form-select` stylar endast closed state konsekvent.

#### Textarea

```html
<textarea class="form-textarea" rows="3" placeholder="..."></textarea>
```

#### Primär knapp

```html
<button class="btn-primary">Skicka</button>
<a href="..." class="btn-primary">Länk som knapp</a>
```

#### Sekundär länk

```html
<a href="#" class="link-secondary">
    För skolor och kommuner <span class="arrow">→</span>
</a>
```

### Färger (CSS-variabler)

| Variabel | Användning |
|----------|------------|
| `--color-canvas` | Bakgrund (#F7F5F0) |
| `--color-navy` | Text, borders (#1C2E4A) |
| `--color-burgundy` | Accent, CTA (#7B2D3B) |

### Status-färger (Tailwind)

| Färg | Semantik | Användning |
|------|----------|------------|
| `burgundy` | Kräver åtgärd | Section headers, action borders |
| `amber-500/600` | Pågående | Progress bars, section headers |
| `emerald-700` | Klart | Checkmarks, success states |

> **Val av grön:** `emerald-700` (#047857) valdes över `green-700` för dess blå undertoner som harmoniserar bättre med navy och den dämpade paletten.

### Text-opacity (WCAG AA)

| Klass | Kontrast | Användning |
|-------|----------|------------|
| `text-navy` | 100% – 12:1 | Primärtext, rubriker |
| `text-navy/70` | 70% – 6:1 | Sekundärtext, beskrivningar |
| `text-navy/60` | 60% – 4.5:1 | Tertiär (labels, metadata, timestamps) |
| `text-navy/50` | 50% – 3.5:1 | ⚠️ Endast ikoner |
| `text-navy/40` | 40% – 2.5:1 | ⚠️ Endast dekorativa element |
| `text-navy/30` | 30% – 2:1 | ⚠️ Endast pilar |

**Regel:** Aldrig under `/60` för text som ska läsas. Ikoner kan vara `/50`.

### Typografi

| Klass | Användning |
|-------|------------|
| `font-sans` | Brödtext (IBM Plex Sans) |
| `font-serif` | Elevtext/citat (IBM Plex Serif) |
| `tracking-tightest` | Rubriker |
| `tracking-label` | Etiketter, knappar |

## Bygga CSS (två alternativ)

### Alt 1: PDM från monorepo-root (rekommenderat)

```bash
pdm run fe-prototype-build    # pytailwindcss: input.css → tailwind.css
```

### Alt 2: Vite dev server

```bash
pdm run fe-dev                # Hot reload, CSS kompileras automatiskt
```

**För file:// protokoll:** Prototypfilerna inkluderar inline `<style>` fallback så de fungerar utan server.

## Checklista vid ny sida

1. [ ] Kopiera närmast liknande befintlig sida
2. [ ] Uppdatera `<title>` och `<meta name="description">`
3. [ ] Använd centraliserade klasser (`form-input`, `form-select`, `btn-primary`, etc.)
4. [ ] Lägg till inline `<style>` fallback för file:// viewing (kopiera från `anmal-intresse.html`)
5. [ ] Testa i webbläsare (inte bara IDE-preview)
6. [ ] Uppdatera denna README med ny fil

## Länkning mellan prototyper

Använd relativa sökvägar utan `/`:

```html
<a href="login.html">Logga in</a>
<a href="huleedu-landing-final.html">Tillbaka till startsidan</a>
```

## Uppgiftshantering (Task System)

Frontend har sitt eget uppgiftssystem i `frontend/TASKS/`:

- **Uppgifter:** `frontend/TASKS/` (från frontend-root)
- **Frontend-ADR:er:** `frontend/docs/decisions/`
- **Session-kontext:** `frontend/.claude/work/session/handoff.md`

> **Obs:** Backend-uppgifter finns i monorepo `TASKS/` (assessment/, infrastructure/, etc.).
> Cross-cutting ADR:er (som påverkar både frontend OCH backend) placeras i `docs/decisions/`.

## Relaterad dokumentation

- [Kundflöden och designmotivering](../docs/design/customer-flows.md)
- [Teacher Dashboard Epic](../docs/product/epics/teacher-dashboard-epic.md)
- [Frontend-uppgifter](../../TASKS/) (frontend task system)
