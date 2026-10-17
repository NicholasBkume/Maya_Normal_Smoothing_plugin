# Full-port implementation and validation matrix — 0.9.2

Reference: supplied Abnormal 1.1.5 source. Original MIT attribution is retained.
"Implemented" below describes code, not an unrun Maya result.

| Milestone | Implementation | Validation evidence |
| --- | --- | --- |
| Per-corner normal editing, averages, smoothing, face directions, reset | `core.py`, `scene.py` | Previous Maya 2025 suites passed; numerical comparisons against Blender pass. Bulk-read/grouped-write changes have new Maya tests, pending. |
| World/object/view transforms | Inverse-transpose normals, unit-safe targets, degeneracy guards | Previous Maya 2025 tests passed; new projection/manipulator paths pending. |
| Symmetry and clipboard | Nearest reflected vertex, BMesh-compatible corner tangents, active-to-selected | Previous Maya tests passed. Convex/concave/collinear tangent comparisons against real BMesh pass. New active-copy integration pending. |
| Masks and persistent normal data | Selection, native sets, soft-selection weights, JSON and signed colors | Previous Maya 2025 tests passed. Unified-history changes pending. |
| Custom drawing and individual visibility | VP2 lines, points, wedges, state/weight colors, X-ray, wireframe, brightness, size, hide/reveal | 0.2.1: all 16 automated + six manual checks passed in the user's Maya 2025. New appearance controls tested locally; host rerun pending. |
| Direct normal/corner picking | Scoped Qt viewport filter, line/wedge hit tests, evaluated-mesh ray occlusion, HiDPI conversion | Pure geometric tests pass; new controlled-camera and lifecycle tests included, Maya/physical input pending. |
| Box/circle/lasso and selection modifiers | Region previews, stroke brush, additive/subtractive/toggle modes | Pure selection tests pass; Maya mouse tests pending. |
| Linked, vertex/face path, edge loop and face ring | BFS and source-style valence-four/opposite-quad traversal, hidden barriers | Pure tests pass; loop/ring outputs match supplied source across every edge of a quad-grid fixture. Adapter tests pending. |
| Rotation rings | Native rotate context on a transient pivot; absolute matrix delta | Implemented with Confirm/Cancel, masks and symmetry. New host and mouse tests pending. |
| Live point/sphere target | Transient locator, native move context and 100 ms preview | Implemented with unit-safe sampling and full-state rollback. New host and gesture tests pending. |
| Unified session history | Normals, locks, edge flags, selected/active corners, hidden state, weights, clipboard; bounded branching snapshots | Pure history tests pass. Full-state Maya tests pending. |
| Saved preferences and scoped shortcuts | Validated optionVar schema, panel and active-viewport scopes, actual host Qt selection | Pure schema tests pass. Host round-trip/scope/manual tests pending. |
| Performance and reversible scene writes | Bulk topology/normal reads, shape-resolution caching, equal-vector command grouping, adaptive overlay interval and history limit | CPU profiling saved in PROFILE.json. Maya 10,000-corner timing/undo test included, pending. |
| Save/reload and history/deformer workflows | Helpers do not serialize; stored data uses native attrs/colors; representative blendShape test | Previous storage and overlay serialization flags passed. Expanded representative history case pending; no general guarantee for every deformer stack. |
| Maya host matrix | Native Qt query chooses PySide2/6, shiboken follows the loaded binding | Maya 2025 user validation covers 0.2.1. New 0.9.2 and Maya 2024/2026 are pending. |

All requested feature milestones now have implementation and associated tests.
Release acceptance is blocked by the lack of an actual Maya runtime in the cloud,
not by a claim that numerical tests substitute for Maya. Run the packaged
26-case runner and 12-step manual checklist on the target host, then inspect
representative production assets. Use its version/Qt/Python metadata to record
host coverage; do not infer compatibility with untested releases.

Deliberate adaptations: native Maya manipulators instead of custom Blender rings,
Qt docking instead of the custom floating widget framework, deterministic Maya-ID
tie-breaking, source-mesh ray occlusion, and native undoable writes instead of an
unverified bulk API command. Normal values/locks/edge state are restored; internal
normal-sharing IDs are not promised to be byte-identical. Ambiguous/non-manifold
cases and arbitrary deformer stacks require asset-specific validation.
