# EMERS Design System Foundation

## 1. Purpose

Define the first design-system principles for EMERS Trade without finalizing visual identity.

## 2. Design-system goals

Consistency, clarity, accessibility, state visibility, broker-status precision, evidence linkage, and calm presentation.

## 3. Design tokens

Future tokens should describe color roles, typography scale, spacing, radius, elevation, motion, state, density, and data-visualization roles. No values are final.

## 4. Typography principles

Typography must be highly readable, suitable for financial data, strong in numerical alignment, clear in hierarchy, accessible at practical sizes, stable across web and mobile, and free of decorative display typography for operational content. No proprietary font is selected.

## 5. Color principles

Color communicates state, not excitement. Meaning must never rely on color alone. Profit and loss colors need text or symbols. Warnings require contrast. Muted states remain legible. Broker, data, and system states must be distinguishable. Paper and any future live mode must be visually unmistakable. No hexadecimal values are final.

## 6. Spacing

Spacing should create calm hierarchy and keep risk, status, and action relationships clear.

## 7. Layout

Layouts should separate summary, evidence, risk, and action areas while preserving context.

## 8. Elevation and hierarchy

Hierarchy should indicate importance and risk, not decorative drama.

## 9. Iconography

Icons should support labels, never replace critical text.

## 10. Data visualization

Charts must show axes, units, timeframes, stale data, uncertainty, and risk context.

## 11. Components

| Component family | Purpose | Information priority | Allowed states | Accessibility requirement | Prohibited behavior | Audit relevance | Scope |
|---|---|---|---|---|---|---|---|
| Application Shell | Present application shell information safely | Status/risk/action order | default, active, disabled, warning, error where relevant | Keyboard/screen-reader labels; no color-only meaning | Hide risk, imply certainty, or pre-approve action | High when tied to material action | Future |
| Navigation | Present navigation information safely | Status/risk/action order | default, active, disabled, warning, error where relevant | Keyboard/screen-reader labels; no color-only meaning | Hide risk, imply certainty, or pre-approve action | High when tied to material action | Future |
| Status Banner | Present status banner information safely | Status/risk/action order | default, active, disabled, warning, error where relevant | Keyboard/screen-reader labels; no color-only meaning | Hide risk, imply certainty, or pre-approve action | High when tied to material action | Future |
| Portfolio Summary | Present portfolio summary information safely | Status/risk/action order | default, active, disabled, warning, error where relevant | Keyboard/screen-reader labels; no color-only meaning | Hide risk, imply certainty, or pre-approve action | High when tied to material action | Future |
| Metric Card | Present metric card information safely | Status/risk/action order | default, active, disabled, warning, error where relevant | Keyboard/screen-reader labels; no color-only meaning | Hide risk, imply certainty, or pre-approve action | High when tied to material action | Future |
| Risk Card | Present risk card information safely | Status/risk/action order | default, active, disabled, warning, error where relevant | Keyboard/screen-reader labels; no color-only meaning | Hide risk, imply certainty, or pre-approve action | High when tied to material action | Current/future |
| Opportunity Card | Present opportunity card information safely | Status/risk/action order | default, active, disabled, warning, error where relevant | Keyboard/screen-reader labels; no color-only meaning | Hide risk, imply certainty, or pre-approve action | High when tied to material action | Future |
| Instrument Summary | Present instrument summary information safely | Status/risk/action order | default, active, disabled, warning, error where relevant | Keyboard/screen-reader labels; no color-only meaning | Hide risk, imply certainty, or pre-approve action | High when tied to material action | Future |
| Position Row | Present position row information safely | Status/risk/action order | default, active, disabled, warning, error where relevant | Keyboard/screen-reader labels; no color-only meaning | Hide risk, imply certainty, or pre-approve action | High when tied to material action | Future |
| Order Row | Present order row information safely | Status/risk/action order | default, active, disabled, warning, error where relevant | Keyboard/screen-reader labels; no color-only meaning | Hide risk, imply certainty, or pre-approve action | High when tied to material action | Current/future |
| Approval Panel | Present approval panel information safely | Status/risk/action order | default, active, disabled, warning, error where relevant | Keyboard/screen-reader labels; no color-only meaning | Hide risk, imply certainty, or pre-approve action | High when tied to material action | Current/future |
| Broker-State Panel | Present broker-state panel information safely | Status/risk/action order | default, active, disabled, warning, error where relevant | Keyboard/screen-reader labels; no color-only meaning | Hide risk, imply certainty, or pre-approve action | High when tied to material action | Current/future |
| Alert | Present alert information safely | Status/risk/action order | default, active, disabled, warning, error where relevant | Keyboard/screen-reader labels; no color-only meaning | Hide risk, imply certainty, or pre-approve action | High when tied to material action | Future |
| Warning | Present warning information safely | Status/risk/action order | default, active, disabled, warning, error where relevant | Keyboard/screen-reader labels; no color-only meaning | Hide risk, imply certainty, or pre-approve action | High when tied to material action | Future |
| Confirmation Dialog | Present confirmation dialog information safely | Status/risk/action order | default, active, disabled, warning, error where relevant | Keyboard/screen-reader labels; no color-only meaning | Hide risk, imply certainty, or pre-approve action | High when tied to material action | Future |
| Data-Freshness Indicator | Present data-freshness indicator information safely | Status/risk/action order | default, active, disabled, warning, error where relevant | Keyboard/screen-reader labels; no color-only meaning | Hide risk, imply certainty, or pre-approve action | High when tied to material action | Future |
| Uncertainty Indicator | Present uncertainty indicator information safely | Status/risk/action order | default, active, disabled, warning, error where relevant | Keyboard/screen-reader labels; no color-only meaning | Hide risk, imply certainty, or pre-approve action | High when tied to material action | Future |
| Evidence Link | Present evidence link information safely | Status/risk/action order | default, active, disabled, warning, error where relevant | Keyboard/screen-reader labels; no color-only meaning | Hide risk, imply certainty, or pre-approve action | High when tied to material action | Future |
| Audit Timeline | Present audit timeline information safely | Status/risk/action order | default, active, disabled, warning, error where relevant | Keyboard/screen-reader labels; no color-only meaning | Hide risk, imply certainty, or pre-approve action | High when tied to material action | Future |
| Filter Controls | Present filter controls information safely | Status/risk/action order | default, active, disabled, warning, error where relevant | Keyboard/screen-reader labels; no color-only meaning | Hide risk, imply certainty, or pre-approve action | High when tied to material action | Future |
| Table | Present table information safely | Status/risk/action order | default, active, disabled, warning, error where relevant | Keyboard/screen-reader labels; no color-only meaning | Hide risk, imply certainty, or pre-approve action | High when tied to material action | Future |
| Chart | Present chart information safely | Status/risk/action order | default, active, disabled, warning, error where relevant | Keyboard/screen-reader labels; no color-only meaning | Hide risk, imply certainty, or pre-approve action | High when tied to material action | Future |
| Empty State | Present empty state information safely | Status/risk/action order | default, active, disabled, warning, error where relevant | Keyboard/screen-reader labels; no color-only meaning | Hide risk, imply certainty, or pre-approve action | High when tied to material action | Future |
| Loading State | Present loading state information safely | Status/risk/action order | default, active, disabled, warning, error where relevant | Keyboard/screen-reader labels; no color-only meaning | Hide risk, imply certainty, or pre-approve action | High when tied to material action | Future |
| Degraded State | Present degraded state information safely | Status/risk/action order | default, active, disabled, warning, error where relevant | Keyboard/screen-reader labels; no color-only meaning | Hide risk, imply certainty, or pre-approve action | High when tied to material action | Future |
| Error State | Present error state information safely | Status/risk/action order | default, active, disabled, warning, error where relevant | Keyboard/screen-reader labels; no color-only meaning | Hide risk, imply certainty, or pre-approve action | High when tied to material action | Future |
| Emergency-Stop Control | Present emergency-stop control information safely | Status/risk/action order | default, active, disabled, warning, error where relevant | Keyboard/screen-reader labels; no color-only meaning | Hide risk, imply certainty, or pre-approve action | High when tied to material action | Future |

## 12. Interaction states

States should include default, hover/focus, selected, disabled, loading, warning, error, success, unresolved, and degraded.

## 13. Motion

Motion should be minimal, purposeful, and avoid urgency or celebration.

## 14. Responsive behavior

Responsive layouts must preserve risk and broker-state visibility.

## 15. Dark and light modes

Both are possible, but launch mode is undecided. Contrast and state meaning matter more than aesthetics.

## 16. Accessibility requirements

Future implementations should target an appropriate recognized accessibility standard and be independently tested before compliance claims.

## 17. Documentation and governance

Components need usage rules, prohibited patterns, examples, and evidence expectations.

## 18. Current working decisions

Risk-first hierarchy, explicit status labels, non-gamified design, and no final colors/fonts/logos.

## 19. Deferred visual decisions

Logo, typeface, color palette, illustration style, icon set, and motion system.

## 20. Open questions

Open questions include design tooling, token format, chart library, density settings, and accessibility target.
