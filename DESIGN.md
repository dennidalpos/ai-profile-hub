---
name: AI Profile Hub
description: A compact native workspace for client-specific AI profiles.
colors:
  light-canvas: "#F5F6F8"
  light-surface: "#FFFFFF"
  light-text: "#202631"
  light-muted: "#596474"
  light-border: "#D7DDE5"
  light-accent: "#2458B8"
  light-selected: "#E2EBFC"
  dark-canvas: "#15191F"
  dark-surface: "#1D232C"
  dark-text: "#EEF1F6"
  dark-muted: "#B0BAC8"
  dark-border: "#394352"
  dark-accent: "#8DB7FF"
  dark-selected: "#2C4264"
typography:
  heading:
    fontSize: "28px"
    fontWeight: 600
  section:
    fontSize: "18px"
    fontWeight: 600
  body:
    fontSize: "14px"
rounded:
  field: "4px"
  control: "6px"
spacing:
  control-y: "2px"
  field: "6px"
  small: "8px"
  control-x: "10px"
  compact: "12px"
  regular: "16px"
  panel: "20px"
  page: "24px"
  form-top: "28px"
  wide: "32px"
components:
  button-light:
    backgroundColor: "{colors.light-surface}"
    textColor: "{colors.light-text}"
    rounded: "{rounded.control}"
    padding: "2px 10px"
  button-primary-light:
    backgroundColor: "{colors.light-accent}"
    textColor: "{colors.light-surface}"
    rounded: "{rounded.control}"
    padding: "2px 10px"
  button-hover-light:
    backgroundColor: "{colors.light-selected}"
  button-dark:
    backgroundColor: "{colors.dark-surface}"
    textColor: "{colors.dark-text}"
    rounded: "{rounded.control}"
    padding: "2px 10px"
  button-primary-dark:
    backgroundColor: "{colors.dark-accent}"
    textColor: "{colors.dark-canvas}"
    rounded: "{rounded.control}"
    padding: "2px 10px"
  button-hover-dark:
    backgroundColor: "{colors.dark-selected}"
---

# Design System: AI Profile Hub

## Overview

The approved direction is a quiet, compact native workspace in **Operate** mode. System typography, familiar controls and a shared profile list support finding and opening the intended client quickly. English interface copy distinguishes managed profiles from linked sessions and describes launch requests without implying authenticated identity.

This records the implemented PySide6 / Qt Widgets system with the Fusion widget style. Windows, macOS and Linux are targets; visual verification currently covers Windows only. The approved list-and-details composition takes precedence over the evaluated direction seed `seed:c7e30520d8a497ca`.

**Key Characteristics:**

- Compact task-focused pages with persistent navigation.
- System appearance with explicit Light and Dark overrides.
- Flat surfaces, restrained blue emphasis and visible keyboard focus.
- Contextual details and recoverable feedback without routine modal interruption.

## Colors

Blue accents sit against cool neutral surfaces. The frontmatter records both implemented palettes; `profile_switch/qt_support.py` is the runtime source.

### Primary

Accents identify primary actions and focus borders. Primary button text uses the light surface in Light mode and the dark canvas in Dark mode. Selection colors support table selection, ordinary button hover and checked navigation; selected text keeps the normal text color.

### Neutral

Canvas colors cover the workspace and alternate base; surface colors cover the rail, inspector, controls and table. Text colors carry content, muted colors carry secondary labels and placeholders, and border colors delineate surfaces. Disabled buttons use muted text on the canvas. Feedback includes words rather than relying on color.

System mode follows Qt's color-scheme hint and responds to changes. The stored override selects the complete Light or Dark palette.

## Typography

Use the platform system font inherited by Qt; no named or bundled family is imposed. Body text is 14 logical pixels, page headings are 28 pixels at weight 600, and section headings are 18 pixels at weight 600. Checked navigation, table headers and primary buttons use weight 600. Other weight, line-height and letter spacing remain platform defaults. These implemented pixel values replace the provisional point-based scale.

## Layout

The initial window is 1220 × 760 logical pixels with a 760 × 560 minimum. A fixed 166-pixel navigation rail sits beside a flexible stacked workspace. The rail uses 16-pixel horizontal margins, a 24-pixel top margin and 20-pixel bottom margin.

Profiles uses 24-pixel top/side margins, a 20-pixel bottom margin and 16-pixel vertical gaps. Title and New profile precede search and two filters. The main area combines a sortable table and contextual inspector; count, contextual Clear filters and the open action sit below. Launch results occupy a scrollable region capped at 115 pixels.

Rows are 42 pixels high. Initial column widths are 170, 130, 220 and 90 pixels for Profile, Product, Client and Source; the last section stretches and columns are resizable. The splitter starts at 650/300 with a 280–350-pixel inspector. Inspector content has 20-pixel margins and 12-pixel gaps; actions remain in a separate footer.

Below a window width of 1060 pixels, an explicit Details action opens a dedicated page with Back to profiles; the inline inspector and Source column are hidden. This is a desktop adaptation. Settings and editor margins are 32/28/32/24 pixels; settings gaps are 20 pixels and editor gaps are 16 pixels.

## Elevation & Depth

No custom shadows or decorative motion are implemented. Tonal surfaces, single-pixel borders and the rail separator establish structure. Platform-managed dialogs retain Qt behavior.

## Shapes

Controls, the table and inspector use 6-pixel corners. The read-only path field uses 4-pixel corners. Borders are one pixel at rest; supported focused controls use a two-pixel accent border.

## Components

### Buttons and navigation

Text-labelled Qt buttons use 2/10-pixel vertical/horizontal padding and a stylesheet minimum height of 32 pixels. Ordinary hover uses the selection surface. Primary buttons use accent fill and weight 600; their primary styling remains authoritative on hover. Checked rail buttons use the selection surface and weight 600. Profiles and Settings are the destinations.

### Fields and filters

Search, combo boxes and editor fields share button geometry, normal surface and text colors. Search includes Qt's clear affordance. Inputs and combo boxes receive an accent focus border. Editor validation remains in the page and preserves entered values. Advanced executable and working-directory fields appear for applicable client types.

### Profile table and inspector

The non-editable table supports sorting, extended row selection and double-click launch. Headers use muted text, canvas fill, 12/8-pixel padding and a bottom separator; cells use 8-pixel padding without a visible grid. The inspector shows availability, paths, refresh, sign-in, edit and removal actions. Its read-only path field wraps and supports keyboard traversal; scrollable details accommodate long content.

### Empty states and feedback

An empty collection offers New profile. Empty filtered results also offer Clear filters; a clear action remains available with nonempty filtered results. Operation errors appear in a persistent dismissible banner, editor errors stay in the form, and launch results provide Retry failed when applicable. The status bar supplies supporting feedback. Removal uses a confirmation with No as default; file selection uses Qt dialogs.

### Keyboard and operation state

Use platform New, Find and Refresh shortcuts. Return opens the selection when focus is in the table or search. Controls use text labels or accessible names. Disabled actions track selection and operation state; slow operations run outside the UI thread. Account verification stays in the external client.

## Do's and Don'ts

### Do:

- **Do** use implemented theme roles, inherited system typography and compact spacing.
- **Do** preserve visible focus, readable state words and recoverable feedback.
- **Do** qualify all three native platforms before claiming visual parity.

### Don't:

- **Don't** add marketing headers, dashboard statistics or decorative cards to the approved Profiles workspace.
- **Don't** infer successful sign-in or identity from a launch request.
- **Don't** introduce custom fonts, icon systems, shadows or motion absent from the implementation.
