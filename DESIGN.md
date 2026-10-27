---
name: Clinic Appointment Booking API
description: A reference-led visual guide with live appointment API examples.
colors:
  ink: "#102d58"
  muted: "#4f6582"
  border: "#dfebfb"
  blue: "#255cb3"
  green: "#087353"
  purple: "#8150bb"
  action: "#5962d7"
  action-hover: "#414bbf"
  surface: "#fff"
  hero-bg: "#f4f4ff"
  examples-bg: "#f0f7ff"
  code-bg: "#f5f8fd"
  terminal-bg: "#243242"
  terminal-text: "#eff6ff"
  focus: "#5965df"
  success-text: "#0b6749"
  success-bg: "#dff3e9"
  error-text: "#a3223f"
  error-bg: "#ffebee"
  warning-text: "#894514"
  warning-bg: "#fff0db"
  loading-text: "#5443ad"
  loading-bg: "#eee8ff"
  post-method: "#087a53"
typography:
  display:
    fontFamily: '"Nunito Sans", sans-serif'
    fontSize: "clamp(28px, 2.48vw, 43px)"
    fontWeight: 800
    lineHeight: 1.15
    letterSpacing: "-0.025em"
  title:
    fontFamily: '"Nunito Sans", sans-serif'
    fontSize: "16px"
    fontWeight: 800
    lineHeight: 1.3
  body:
    fontFamily: '"Nunito Sans", sans-serif'
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.55
  code:
    fontFamily: 'ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace'
    fontSize: "10px"
    lineHeight: 1.6
  label:
    fontFamily: '"Nunito Sans", sans-serif'
    fontSize: "10px"
    fontWeight: 800
rounded:
  panel: "12px"
  request-card: "9px"
  primary: "7px"
  control: "5px"
  label: "4px"
spacing:
  compact-gap: "8px"
  code-inset: "9px"
  inline-gap: "10px"
  panel-gap: "14px"
  column-gap: "15px"
  page-inset: "18px"
components:
  button-primary:
    backgroundColor: "{colors.action}"
    textColor: "{colors.surface}"
    rounded: "{rounded.primary}"
    padding: "9px 17px"
  button-primary-hover:
    backgroundColor: "{colors.action-hover}"
  panel:
    rounded: "{rounded.panel}"
  request-card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.request-card}"
    padding: "11px 11px 8px"
  request-input:
    backgroundColor: "{colors.code-bg}"
    rounded: "{rounded.control}"
    padding: "{spacing.code-inset}"
    typography: "{typography.code}"
  result-success:
    backgroundColor: "{colors.success-bg}"
    textColor: "{colors.success-text}"
    rounded: "{rounded.label}"
    padding: "2px 5px"
  terminal:
    backgroundColor: "{colors.terminal-bg}"
    textColor: "{colors.terminal-text}"
    rounded: "{rounded.panel}"
    padding: "14px 16px"
---

# Design System: Clinic Appointment Booking API

## Overview

**Creative North Star: "Clinic Appointment Booking API reference image"**

The user's supplied image is the visual authority: a light, compact clinic API guide with navy lettering, pastel panels, health-themed vector icons, sequential examples, and a database diagram. Preserve that recognizable identity. The actual API contract governs endpoint names, UUIDs, UTC timestamps, cancellation responses, and concurrency explanations.

This document records the implemented system in `clinic_api/static/index.html`, `styles.css`, and `app.js`. Product commitments live in `PRODUCT.md`; the page-specific composition and interaction purpose live in `.impeccable/surface-brief.md`. It records code evidence, not a visual audit or a claim that browser scenarios passed.

**Key Characteristics:**

- Rounded pastel panels with fine borders and navy typography.
- A local variable font for prose and system monospace for editable JSON and responses.
- Compact information density that reflows into readable mobile sections.
- Actual HTTP status, response body, and timing for every executed example.

## Colors

The palette uses cool lavender and blue surfaces, with green, amber, and red reserved for meaningful operations and outcomes.

- **Primary:** Action violet identifies the introductory action; blue identifies links and supporting controls.
- **Secondary:** Green and purple organize method badges, schema entities, and explanatory accents.
- **Neutral:** Ink carries headings and prose; muted ink carries support copy. White request cards sit inside pale blue example panels. The dark terminal isolates the live race result.
- **Status:** Success, error, warning, and loading use distinct text/background pairs from the tokens above. A label and response accompany color; color alone never communicates the result.

## Typography

Nunito Sans is bundled as a variable WOFF2 font covering weights 400–800, loaded with `font-display: swap`; its SIL license is bundled beside it. JSON, commands, endpoints, and timings use the system monospace stack with tabular numerals.

The display token describes the default hero; section titles use the title token, and request headings use 13px at weight 800. Code defaults to the code token; it grows to 11px on wide screens and in the final mobile rules. The interface uses a compact, observed size hierarchy, not a mathematical type scale.

## Layout

The page container is centered with a maximum width of 1760px. Default desktop layout uses three columns (`1.04fr 1.13fr 0.74fr`), the page-inset and column-gap tokens, and independently stacked panels. Request/response pairs share two equal columns where space permits. Every grid child permits shrinking; code wraps and scrolls inside its panel.

| Viewport | Implemented behavior |
| --- | --- |
| At least 1600px | Three columns; hero title 43px, more panel padding, code 11px. |
| 1251–1599px | Default three columns and paired request/response editors. |
| 1001–1250px | Three compact columns (`1fr 1.15fr .75fr`); 12px outer padding/gap; request/response pairs stack. |
| 681–1000px | Two main columns (`1fr 1.12fr`); assurance panels occupy a full-width, two-column row; request/response pairs stack. |
| At most 680px | One main column; examples follow overview, then assurance. Detail cards and request/response pairs stack. Stack entries remain a two-column list; code uses 11px. |
| At most 380px | Additional hero, icon, and diagram reductions; hero title 24px. |

The final `max-width: 680px` block deliberately overrides earlier mobile rules: detail cards and request/response editors are single-column. Keep the effective cascade when adapting this page. Code/output panels have internal scroll limits; the race console caps at 270px.

## Elevation & Depth

Depth comes from background tone, thin borders, and white inset request cards. The stylesheet declares no box shadows. The hero has a pale decorative ring behind its content; it is noninteractive. Dark terminal contrast marks a different kind of content without an elevated modal treatment.

## Shapes

Outer panels use the panel radius; inset request cards, primary buttons, fields, and status labels step down through the documented radius tokens. Icon discs and small connection indicators are circular. Inline SVG supplies the heart/pulse emblem and line icons; preserve the established rounded stroke treatment.

## Components

- **Primary action:** White text on action violet, weight 800, with a darker hover state. It scrolls to the API examples and focuses the first action. Run buttons use a lighter blue treatment; destructive text actions remain explicitly labelled.
- **Request card:** A heading and run action sit above the method/endpoint bar. An editable, vertically resizable JSON field and response area sit below. On narrow layouts the response follows the request.
- **Status label:** Idle guidance changes only after a request starts or finishes. HTTP 409 receives warning styling; unsuccessful requests show the actual error. Successful DELETE 204 explains that no response body is returned.
- **Live race console:** A separate synthetic clinic and slot receive two concurrent booking requests. Its result uses both HTTP responses and a follow-up confirmed-booking count. An incomplete result is labelled incomplete; it is not presented as a passing test suite.
- **Data browser and reset:** Listing uses the current clinic context where applicable. Cancelling retains history. Reset clears the page's example context and drafts; it does not delete persisted API records.
- **Documentation links:** Swagger remains at `/docs`, and repository/setup links use normal anchors. The keyboard skip link leads directly to the examples.

Interactions use same-origin API paths. Initial page load checks `/health`; data changes happen on explicit actions. While an action is active, buttons/selects are disabled and drafts become read-only. Status elements use polite live announcements, and output areas expose busy state. API output is inserted as text, not interpreted HTML.

All interactive controls share a visible 3px focus outline with a 3px offset. Button backgrounds transition over 0.15s. Reduced-motion preferences disable CSS transitions/animations and replace smooth programmatic scrolling with immediate scrolling. This documentation describes the implementation; it does not certify accessibility conformance.

## Do's and Don'ts

### Do:

- **Do** preserve the supplied reference's navy typography, pastel panels, and health-themed vector identity.
- **Do** keep examples consistent with the live API and show real status codes, response bodies, and timings.
- **Do** preserve the final mobile stacking rules, wrapped code, keyboard focus, and reduced-motion behavior.
- **Do** keep synthetic patient details and persistent-data effects explicit.

### Don't:

- **Don't** replace the chosen reference with a new visual identity during routine changes.
- **Don't** show illustrative responses or a live demonstration as a completed automated test run.
- **Don't** imply that resetting examples deletes clinics, slots, or bookings.
- **Don't** introduce shadows or external font dependencies into this existing flat, bundled system without an intentional design change.
