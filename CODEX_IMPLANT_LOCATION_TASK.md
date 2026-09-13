# Codex task — DrLinq implant location UI

Implement the UI request described in GitHub issue #15 on branch `codex/implant-location-ui-v2`.

Constraints:
- Edit the TEST implant intake only.
- Do not change live production or production data.
- Preserve the current 7-step green mobile-first flow and real dental sample assets.
- Make upper jaw and lower jaw independently selectable (including both at once), each with its own complete/right/left selection.
- Replace the rounded-rectangle tooth placeholders with an interactive SVG odontogram modeled on a standard FDI chart: 16 upper + 16 lower, human-tooth-like silhouettes, visible FDI numbers, red R/L labels, red center line, each tooth individually clickable and highlighted green when selected.
- Persist jaw/tooth selections and show them in summary.
- Validate against blank-page JS regression and run tests.
- Commit only the needed implementation changes on this branch.
