# TraceDrive design notes

TraceDrive is a local robotics measurement workbench. The saved-run rail and dominant time-series plot support inspection; the measurement table and textual threshold list keep results readable outside the chart. Styles live in `web/styles.css`, with SVG encoding and keyboard probing in `web/app.js`.

## Palette and type

| Role | Value |
| --- | --- |
| Canvas / surface / rail | `#f4f6f5` / `#fff` / `#eef2f0` |
| Ink / supporting text / divider | `#1c2929` / `#596463` / `#dce3e0` |
| Action, focus, primary measured / selected control | `#185e4c` / `#e4f1ea` |
| Comparison measured | `#bb622c` |
| Primary target / comparison target | `#707d83` / `#6d76a3` |
| Plot grid / axis / probe | `#e2e8e4` / `#374943` / `#7b8a82` |

Use the final TraceDrive root overrides, not the earlier inherited blue declarations. The bundled typeface is Noto Sans, aliased as `Instrument` in CSS; regular and bold TTF files and the OFL license live in `web/assets`. Body text is 15px/1.55, page headings 30px/1.25 (27px on phones), panel headings 17px, and supporting text and chart labels 12px. Numeric columns use tabular numerals.

## Layout and controls

The rail is 235px and the workspace is capped at 1700px. Two run selectors sit above a full-width plot; measurement and threshold panels share two columns. At 1200px, the rail becomes 205px, lower panels stack, and measurement controls move below the chart heading. At 760px, the rail becomes a top region, saved runs scroll horizontally, selectors stack, and workspace padding becomes 20px 16px 30px.

Panels have a white fill, 1px divider border, and 12px corners. Buttons use 7px corners and a 39px minimum height; inputs use 6px corners and a 41px minimum height. Saved runs use native pressed buttons with white selected surfaces and accented names. Measurement buttons form a labeled group with `aria-pressed`, not an ARIA tablist. There are no shadows.

## Plot, tables, and keyboard

- The SVG has a title, description, explicit units, time axis, and labeled legend. Measured traces are solid; targets are dashed. Threshold crossings are a textual segment list, not chart overlays.
- Runs align at elapsed time zero. Long drawn traces retain bucket extrema; metrics and sample inspection retain the full dataset. The comparison trace uses its own timestamps.
- Pointer movement inspects the nearest primary sample. Focus the plot and use Left/Right for one sample, Shift+Left/Right for ten, and Home/End for first/last. The text readout reports time, units, target velocity, and the nearest comparison sample when available.
- The measurement table supplies exact summary values, units, and signed comparison-minus-primary changes. Names may wrap; numbers and units stay together. The table is a named, keyboard-focusable scroll region with a phone-width scroll hint.
- Focus uses a 3px forest outline and 3px offset; table outlines are inset. Rebuilding the run list preserves focus. A skip link enters the workspace. Import CSV opens the native disclosure and focuses the run name.

## States and provenance

Pending work disables buttons and selectors and marks the import form `aria-busy`. Errors preserve input and use alert notices; successful results use status. Empty states offer examples or CSV import. Existing runs prevent sample seeding. Notices alone reveal over 0.25s when reduced motion is not requested.

Saved runs and the current data-origin label distinguish “Synthetic example” from “Imported CSV.” Generated examples do not establish observed robot performance. Thresholds are illustrative; crossings do not confirm hardware faults. A signed delta is arithmetic, not a claim of improvement. Keep those qualifications adjacent to measurements.
