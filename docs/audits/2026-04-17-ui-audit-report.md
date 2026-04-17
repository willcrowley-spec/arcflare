# Arcflare UI Audit Report

**Date**: April 17, 2026
**Auditor**: Impeccable Design Audit (v2.1.1)
**Scope**: All frontend pages and components (`frontend/src/pages/`, `frontend/src/components/`)

---

## Audit Health Score

| # | Dimension | Score | Key Finding |
|---|-----------|-------|-------------|
| 1 | Accessibility | 1 | SearchBar has **no visible focus indicator** (`focus:outline-none focus:ring-0`); DataTable sort headers not keyboard-operable; ConnectPlatformModal missing `role="dialog"` |
| 2 | Performance | 3 | Mostly sound; some missing memoization opportunities; Recharts re-renders on every parent render |
| 3 | Responsive Design | 2 | Mobile nav exists but touch targets consistently under 44px; pagination buttons 32px; no container queries |
| 4 | Theming | 2 | Custom navy tokens exist but many hardcoded hex values in Recharts; no dark mode; Inter is the sole font (on the banned list) |
| 5 | Anti-Patterns | 2 | Landing page has gradient text (`bg-clip-text`); landing cards use `backdrop-blur-sm` (glassmorphism); card-grid pattern repeated heavily |
| **Total** | | **10/20** | **Acceptable — significant work needed** |

**Rating bands**: 18–20 Excellent · 14–17 Good · 10–13 Acceptable · 6–9 Poor · 0–5 Critical

---

## Anti-Patterns Verdict

**Would someone say "AI made this"?** Borderline. The authenticated app pages are clean and professional — good information density, consistent card patterns, sensible color usage. But the **landing page** has two glaring AI tells: gradient text on "Transform." and glassmorphism on feature cards. The `ConnectPlatformModal` overlay also uses `backdrop-blur-sm`. The reliance on identical `rounded-xl + shadow-sm + ring-1` card wrappers everywhere creates a template feel. Inter as the sole font is the #1 most common AI-generated choice.

**Specific tells found:**
- Gradient text on landing hero (absolute ban from design system)
- `backdrop-blur-sm` on landing cards + modal overlay (glassmorphism)
- Identical card grid on landing (3 cards, icon + heading + text)
- Inter font exclusively

---

## Detailed Findings

### P0 — Blocking

#### SearchBar has no visible focus indicator
- **Location**: `components/SearchBar.tsx`
- **Category**: Accessibility
- **Impact**: Keyboard users cannot see which element is focused. The input explicitly removes focus styles with `focus:outline-none focus:ring-0`.
- **WCAG**: 2.4.7 Focus Visible (AA)
- **Recommendation**: Add `focus-visible:ring-2 focus-visible:ring-navy-200` to the input, remove `focus:ring-0`

#### SearchBar input has no accessible label
- **Location**: `components/SearchBar.tsx`
- **Category**: Accessibility
- **Impact**: Screen readers announce it as an unlabeled text field. Placeholder text is not an accessible name.
- **WCAG**: 1.3.1 Info and Relationships (A), 4.1.2 Name, Role, Value (A)
- **Recommendation**: Add `aria-label="Search"` to the input

#### DataTable sort headers not keyboard-accessible
- **Location**: `components/DataTable.tsx`
- **Category**: Accessibility
- **Impact**: Sortable columns use `onClick` on `<th>` with no `tabIndex`, `role`, `aria-sort`, or keyboard handler. Keyboard-only users cannot sort tables.
- **WCAG**: 2.1.1 Keyboard (A)
- **Recommendation**: Add `tabIndex={0}`, `role="button"`, `aria-sort`, and `onKeyDown` (Enter/Space) handler

#### ConnectPlatformModal missing dialog semantics
- **Location**: `components/ConnectPlatformModal.tsx`
- **Category**: Accessibility
- **Impact**: No `role="dialog"`, `aria-modal="true"`, `aria-labelledby`, or focus trap. Screen readers don't announce it as a modal. Focus can escape behind the overlay.
- **WCAG**: 4.1.2 Name, Role, Value (A)
- **Recommendation**: Add dialog role/aria attributes, implement focus trap, add `aria-label="Close"` to X button

---

### P1 — Major

#### Landing page gradient text
- **Location**: `components/AppLayout.tsx` (landing hero section)
- **Category**: Anti-Pattern
- **Impact**: `bg-gradient-to-r from-orange-400 to-amber-300 bg-clip-text text-transparent` on "Transform." — top AI design tell.
- **Recommendation**: Replace with solid `text-orange-400` or use font weight/size for emphasis instead

#### Landing page glassmorphism
- **Location**: `components/AppLayout.tsx` (feature cards)
- **Category**: Anti-Pattern
- **Impact**: Feature cards use `backdrop-blur-sm` + `bg-white/5` — textbook glassmorphism. Decorative, not functional.
- **Recommendation**: Replace with solid `bg-navy-800` or `bg-white/10` without blur

#### Inter font exclusively
- **Location**: `frontend/src/index.css`
- **Category**: Theming / Anti-Pattern
- **Impact**: Inter is the single most overused AI-generated font. Using it as the only font with no display pairing creates immediate "template" recognition.
- **Recommendation**: Keep Inter for body or replace; add a distinctive display face for headings

#### Pagination buttons under 44px touch targets
- **Location**: `components/DataTable.tsx` — `h-8 w-8` (32px)
- **Category**: Responsive / Accessibility
- **Impact**: Mobile users will mis-tap. WCAG 2.5.8 Target Size (AA) requires 24px minimum (44px recommended).
- **Recommendation**: Increase to `h-10 w-10` minimum

#### Non-functional CTA buttons
- **Location**: `pages/Agents/index.tsx` (Configure), `pages/Recommendations/index.tsx` (Initialize Deployment, Analysis Details, Implement, Review)
- **Category**: Interaction
- **Impact**: Buttons with hover states but no onClick handlers. Users click them expecting something to happen.
- **Recommendation**: Either wire them up, add `disabled` + styling, or remove them

---

### P2 — Minor

#### Hardcoded hex in Recharts
- **Location**: `pages/Agents/index.tsx`, `pages/Organization/index.tsx`
- **Category**: Theming
- **Impact**: Chart colors like `#cbd5e1`, `#0f1736`, `#0d9488` aren't connected to the navy/slate token system. Theme changes won't propagate.
- **Recommendation**: Define chart color CSS variables that reference the token system

#### Processes accordion missing aria-expanded
- **Location**: `pages/Processes/index.tsx`
- **Category**: Accessibility
- **Impact**: Screen reader users can't tell if an accordion section is open or closed.
- **Recommendation**: Add `aria-expanded={isOpen}` and `aria-controls` with matching panel `id`

#### SyncProgressPanel lacks progressbar semantics
- **Location**: `components/SyncProgressPanel.tsx`
- **Category**: Accessibility
- **Impact**: Progress bar is visual-only; screen reader users don't get sync percentage.
- **Recommendation**: Add `role="progressbar"`, `aria-valuenow`, `aria-valuemin`, `aria-valuemax`

#### Organization licensing tabs missing tablist pattern
- **Location**: `pages/Organization/index.tsx`
- **Category**: Accessibility
- **Recommendation**: Add `role="tablist"` on container, `role="tab"` + `aria-selected` on buttons, `role="tabpanel"` + `aria-labelledby` on content

#### Footer links are `href="#"` placeholders
- **Location**: `components/AppLayout.tsx`
- **Category**: Interaction
- **Recommendation**: Either link to real pages, remove them, or mark as `aria-disabled`

---

### P3 — Polish

#### Card pattern uniformity
- **Location**: Every page
- **Category**: Anti-Pattern
- **Impact**: `rounded-xl + shadow-sm + ring-1` repeated identically on nearly every container. Creates template feel.
- **Recommendation**: Vary container treatments — some sections could use no border, some flat backgrounds, some full-bleed

#### backdrop-blur on ConnectPlatformModal overlay
- **Location**: `components/ConnectPlatformModal.tsx`
- **Category**: Anti-Pattern / Performance
- **Recommendation**: Replace with solid `bg-black/50` — blur is decorative and costs GPU

#### Small action buttons across pages
- **Location**: Analysis connection cards, Processes sub-process links, Recommendations pagination
- **Category**: Responsive
- **Impact**: `px-2.5 py-1.5 text-xs` buttons are ~30px tall
- **Recommendation**: Minimum `py-2` for interactive elements

---

## Positive Findings

- **Information density** is genuinely good — the Analysis page packs a lot of useful data without feeling cluttered
- **Consistent status badges** (`StatusBadge`) with semantic color mapping are well-executed
- **Navy-800 header** with orange active indicator is a strong, distinctive brand element
- **DataTable pagination** has proper `aria-label` and `aria-current` on page buttons
- **Salesforce connected banner** correctly uses `role="status"`
- **Responsive mobile nav** exists with proper breakpoint handling
- **No unnecessary animations** — the UI is fast and doesn't waste time on entrance effects

---

## Recommended Actions (Priority Order)

| Priority | Action | Description |
|----------|--------|-------------|
| P0 | Fix accessibility blockers | SearchBar focus + label, DataTable keyboard sort, ConnectPlatformModal dialog semantics |
| P1 | Remove anti-patterns | Gradient text on landing, glassmorphism, establish chart color tokens |
| P1 | Typography upgrade | Replace or supplement Inter with a distinctive display font for headings |
| P1 | Fix touch targets | Pagination, action buttons, header icons — all under 44px |
| P1 | Remove dead buttons | Disable or remove non-functional CTA buttons (Agents, Recommendations) |
| P2 | Add missing ARIA | Accordion expanded state, progressbar, tablist pattern |
| P3 | Vary card treatments | Reduce template uniformity in container styling |
| P3 | Final sweep | Polish pass after all fixes applied |

---

## Issue Summary

| Severity | Count |
|----------|-------|
| P0 Blocking | 4 |
| P1 Major | 5 |
| P2 Minor | 5 |
| P3 Polish | 3 |
| **Total** | **17** |
