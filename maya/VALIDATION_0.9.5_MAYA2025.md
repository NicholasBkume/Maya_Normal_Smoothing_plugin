# Abnormal Maya 0.9.5 — Maya 2025 automated validation

**Host-reported result (supplied by tester, 2026-10-17): 26 passed, 0 failed, 0 skipped.**

This is a record of the tester's output from Maya 2025, not a rerun by the GitHub automation environment. Loaded package version: `0.9.5`. Validated file was from the extracted 0.9.5 ZIP's `tests/run_all_maya.py`; the adapter loaded from the same archive's `AbnormalMaya/scripts/abnormal_maya/scene.py`.

## Automated checks — all PASS

1. All normal operation buttons: object-space results
2. Normal undo, redo, corner isolation and lock restoration
3. World-space normals under rotated, nonuniform and negative transforms
4. View-space rotation against active camera matrix
5. Manual symmetry, auto symmetry and distance rejection
6. Live corner clipboard and vertex clipboard
7. Binary, empty and fractional weight masks
8. Native Maya soft-selection weight extraction
9. Signed color data and JSON storage round trips
10. Rename, deletion, instance and topology guards
11. Qt dock creation, close and fresh reopen
12. Panel selection, set mask, targets, display and finish/cancel
13. Session normal visibility, hidden edit protection and visibility history
14. Viewport 2.0 plugin, display payload, rename and cleanup
15. Panel custom overlay toggles, hiding and lifecycle cleanup
16. Bulk normal capture order and grouped native assignment undo
17. Unified session history: selection, active, masks, visibility and normals
18. Native edge shading parity, native/session undo and exact restoration
19. Direct projection, occlusion and topology selection adapters
20. Picker installation, scoped key events and teardown
21. Preferences round trip, native Qt binding and shortcut scope
22. Live point/sphere targets: preview, cancel, confirm and helper cleanup
23. Native rotation rings: quaternion preview and full-state cancel
24. Editable construction history and blendShape representative workflow
25. Representative 10,000-corner mesh: capture, grouped edit and overlay timing
26. Native rotate-context creation and callback math (synthetic pointer input)

The runner printed `Maya-native undo/redo produced unrecorded session fields: selected`. This was an expected diagnostic from the history regression and did not cause failure.

## Performance observed in Maya 2025

- Vertices: 2,601; face corners: 10,000
- Session capture: 0.21489419999124948 seconds
- Grouped edit: 0.647148100004415 seconds
- Overlay: 0.3106312000018079 seconds

These are one host run, not a cross-device benchmark.

## Manual interactive checklist — 12 PENDING

1. Physical mouse press/drag/release rotates the intended selected normal
2. One native Undo/Redo reverses/restores one complete mouse gesture
3. Dock/undock and normal lines work at physical display scale
4. VP2 overlay shows selected/active colors, wedges and positive mask colors
5. Overlay X-ray and selected-only controls visibly work
6. Hide/reveal and visibility undo/redo do not hide mesh geometry
7. Picker click/box/circle/lasso and Shift/Ctrl modifiers work on HiDPI viewport
8. Picker X-ray versus occlusion, and Alt navigation, behave correctly
9. Rotation ring Confirm/Cancel behavior works with physical native manipulator
10. Live point/sphere tools follow native movement; Enter/Escape work
11. Session history restores normals, selection, active corner, weights and hidden state
12. Saved preferences reopen; shortcuts remain scoped to the editor

**Status:** automated integration checks passed in Maya 2025. Manual physical interaction/visual checks are not yet verified. Do not generalize this evidence to Maya 2024/2026 or arbitrary production meshes.

Release artifact: `maya/releases/AbnormalMaya-0.9.5.zip` on `fix/abnormal-maya-0.9.5`.
