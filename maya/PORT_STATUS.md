# Abnormal full-port status

Primary reference: the original Abnormal 1.1.5 source in the repository root.
The original MIT license and author attribution are retained.

| Area | Maya implementation | Evidence / remaining gap |
| --- | --- | --- |
| Corner normals and bulk editing operations | `core.py`, `scene.py` | 0.1.3: Maya 2025 automated tests passed. Native commands preserve undo. |
| Object/world/view transforms | inverse-transpose normal transforms and transform guards | Maya 2025 tests passed, including nonuniform/negative scale. |
| Smoothing, averaging, face-derived directions | Source-derived corner/adjacency math | Nine numerical comparisons against Blender source passed. |
| Symmetry and clipboard | Nearest reflected vertex, geometric corner bisectors | Maya tests passed; concave/degenerate BMesh tangent equivalence still needs fixtures. |
| Weights and storage | Binary/set/rich-selection masks, JSON and signed color data | Maya 2025 tests passed. |
| Rotation tool and Qt docking | Native dragger context, dockable panel | Maya 2025 automated and manual gesture/undo/docking tests passed in 0.1.3. |
| Normal lines, points, wedges, state colors, weights, X-ray | Optional VP2 plugin in 0.2.0 | Pure display tests pass. New plugin and GPU appearance checks pending Maya rerun. |
| Hide/reveal individual normals | Session visibility plus bounded visibility undo | Pure tests pass; Maya edit-protection tests added, pending rerun. |
| Direct normal/corner picking | Native component selection only | Next: custom screen-space picking context and geometric occlusion tests. |
| Box/circle/lasso selection | Native Maya selection only | Port Blender corner-based selection and additive/subtractive modes. |
| Linked/loop/shortest-path selection | Native Maya equivalents only | Port exact adjacency traversal and selection boundaries. |
| Rotation rings and target manipulation | Incremental rotation + horizontal drag; sampled target fields | Next: interactive rotation rings and live point/sphere target tool with cancel. |
| Session undo/redo | Maya normal undo + separate visibility history | Port unified selection, active element, hidden, normal and filter history. |
| Preferences and shortcuts | Qt settings currently transient | Port saved preferences and context-scoped hotkeys without replacing user bindings. |
| Performance | Native per-corner command writes | Profile; API command optimization needs exact assignment/lock restoration and equivalent undo tests. |
| Host coverage | User validated Maya 2025 / PySide2 | Maya 2024 and Maya 2026 / PySide6 remain unverified. |

## Next sequence

1. Validate the 0.2.0 overlay and visibility milestone in Maya.
2. Add direct corner/normal picking and source-style selection tools on that
   display foundation, including X-ray and occlusion semantics.
3. Add rotation-ring manipulation and movable target modes with explicit
   confirm/cancel behavior.
4. Integrate session history, saved preferences, and scoped shortcuts.
5. Profile and validate larger assets, history/deformer stacks, difficult
   topology, save/reload, and the supported Maya/Qt versions before a 1.0 claim.

An implemented checkbox or passing pure-Python test does not establish a Maya
rendering result. Pending checks above stay pending until actually exercised.
