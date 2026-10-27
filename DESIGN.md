---
name: Clinic Booking
description: A simple patient and clinic portal backed by the appointment API.
colors:
  ink: "#193350"
  muted: "#617087"
  accent: "#6056c8"
  accent-hover: "#4e45ac"
  accent-soft: "#eeecfb"
  green: "#247660"
  green-soft: "#eaf5ef"
  border: "#e3e7ef"
  bg: "#f7f8fb"
  white: "#fff"
  danger: "#b0394e"
typography:
  display:
    fontFamily: '"Nunito Sans", sans-serif'
    fontSize: "36px"
    fontWeight: 800
    lineHeight: 1.25
    letterSpacing: "-0.025em"
  title:
    fontFamily: '"Nunito Sans", sans-serif'
    fontSize: "18px"
    fontWeight: 800
    lineHeight: 1.4
  body:
    fontFamily: '"Nunito Sans", sans-serif'
    fontSize: "15px"
    lineHeight: 1.55
  label:
    fontFamily: '"Nunito Sans", sans-serif'
    fontSize: "12px"
    fontWeight: 800
rounded:
  panel: "16px"
  mobile-panel: "13px"
  control: "8px"
  time: "9px"
spacing:
  time-gap: "10px"
  field-gap: "20px"
  column-gap: "26px"
  page-inset: "32px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.white}"
    rounded: "{rounded.control}"
    padding: "12px 18px"
  button-primary-hover:
    backgroundColor: "{colors.accent-hover}"
  input:
    backgroundColor: "{colors.white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "12px 13px"
  panel:
    backgroundColor: "{colors.white}"
    rounded: "{rounded.panel}"
---

# Design System: Clinic Booking

## Overview

**Creative North Star: "A clear path to an appointment"**

The user requested simple patient and clinic workflows in place of the information-heavy homepage. The portal at `/` uses the Operate mode recorded in `.impeccable/surface-brief.md`: choose a time, enter details, and confirm. Navy text, violet actions, pale surfaces, Nunito Sans, and health icons retain the earlier approachable identity.

**Key Characteristics:** ordinary forms; visible selection and outcomes; restrained color; responsive task layouts.

These tokens describe `portal.css`. The earlier three-column API playground remains at `/guide` with `styles.css` and `app.js`; its code-heavy composition is not the portal template. Swagger remains at `/docs`.

## Colors

Violet identifies primary actions, the current navigation item, and selected times. Navy carries content; muted ink supports it. White panels sit on the cool page background. Green marks successful outcomes and availability; danger styling identifies cancellations and errors. Status words accompany color.

## Typography

The bundled Nunito Sans variable font covers weights 400–800 with `font-display: swap`. The portal uses ordinary prose and form labels, without visible JSON or UUIDs. Controls use 13–14px. Main headings step down from 36px to 32px, 29px, 26px, and 24px at the documented breakpoints.

## Layout

The header and application container cap at 1264px. Booking uses a `1.5fr / minmax(310px, 1fr)` grid, placing time selection before patient details. Lookup and clinic management use a 340px form column beside flexible results. Appointment times use a selectable grid.

| Width | Effective layout |
| --- | --- |
| At least 1440px | More top padding; booking column gap 30px. |
| At most 1100px | 25px page inset, tighter two-column layouts, two time columns. |
| At most 780px | Navigation wraps below the brand; all main layouts stack; three time columns. |
| At most 480px | 16px page inset, 13px panel radius, single-column lookup form, wrapping actions. |
| At most 350px | 12px page inset, two time columns, wrapped date controls. |

## Elevation & Depth

Panels use fine borders and tonal layering. The active navigation item alone uses a subtle `0 2px 5px #2330500c` shadow. Fields and selected time buttons express focus through outlines and border/background changes.

## Shapes

Panel, control, and time radii follow the tokens above; small status labels use 5px corners. The heart/pulse brand and line icons use inline SVG. The task does not require decorative photography or invented practitioner profiles.

## Components

- **Navigation:** Book a visit, My appointments, and Manage clinic switch visible views. The current item exposes `aria-current="page"`.
- **Booking:** selecting a time fills a human-readable summary. Name/email fields submit a real booking. Confirmation replaces the form; errors preserve patient entries and explain conflicts.
- **Lookup:** email finds matching appointments. Rows show dates, clinic information, and status; cancellation uses inline confirmation. Email lookup is not authentication.
- **Clinic workspace:** clinic creation and local date/time fields publish slots. Schedule and booking lists expose appropriate cancellations and prevent silently removing an occupied slot.
- **Feedback:** loading and empty states provide recovery; errors are announced; writes disable controls. Initial load reads data only. Local date/time input converts to UTC; display uses the browser timezone.

Controls have a 3px focus outline with 3px offset. State transitions last 0.16s and view changes 0.2s. Reduced-motion preferences disable animations and smooth scrolling. These notes describe implementation, not an accessibility certification. The portal remains an unauthenticated assessment demo using sample details.

## Do's and Don'ts

- **Do** keep booking, lookup, and schedule management understandable without API knowledge.
- **Do** show real availability, confirmations, errors, and cancellation state.
- **Do** preserve visible focus, local-time labels, and usable narrow-screen layouts.
- **Don't** move JSON examples or setup instructions back into the patient flow.
- **Don't** imply that email lookup or clinic navigation provides sign-in or access control.
- **Don't** invent doctors, ratings, availability counts, or security guarantees.
