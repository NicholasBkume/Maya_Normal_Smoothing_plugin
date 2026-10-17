# Abnormal Maya 0.1.2

A Python 3 face-vertex normal editor targeting Autodesk Maya 2024+.
Ported from the supplied Abnormal Blender add-on 1.1.5 by Cody Winchester /
BlenderNPR, under the MIT license. This is a Maya implementation, not a Blender
add-on that can be loaded into Maya. The original Blender source is preserved
at the repository root.

**Validation:** the host-independent algorithms are tested with CPython. Maya
is not installed in the build environment: scene commands, Qt docking, normal
lock restoration, color storage, and viewport dragging require the supplied
integration checks on an actual Maya installation before production use.

## 0.1.2 Maya 2025 color API correction

Color import now uses `MFnMesh.getFaceVertexColors`, the supported bulk API,
rather than the nonexistent singular method. Signed RGB values are decoded in
polygon-corner order and invalid/missing color data is rejected before editing.
The user's Maya 2025 smoke run reached color import after the normal-write,
undo/redo, mask, transform, and JSON checks; the full smoke test still needs to
be rerun on this version.

## 0.1.1 normal-write correction

XYZ assignment now uses a single absolute Maya command, which already freezes
the normal. Redundant unlock/freeze commands were removed. Each operation reads
back its normals and raises an explicit error on mismatch. Smoke assertions
identify the failing stage and reject an old package loaded from another path.
This change still requires a Maya rerun; it is not a confirmed runtime fix.
Restart Maya before testing an updated package to avoid cached Python modules.
To replace an installation at another path, use
`install(new_root, replace_existing=True)` through the installer dictionary;
the previous module file is backed up first.

## Installation

[Download AbnormalMaya-0.1.2.zip](releases/AbnormalMaya-0.1.2.zip?raw=true).
On GitHub, use the download button if the ZIP preview opens.

1. Extract the distribution to a permanent location. Keep `install.py` and
   the `AbnormalMaya` directory beside one another.
2. In Maya's **Python** Script Editor run (substitute your actual path):

   ```python
   import runpy
   runpy.run_path(r"C:/tools/AbnormalMaya/install.py")["install"](
       r"C:/tools/AbnormalMaya"
   )
   ```

   Alternatively drag `install.py` into a Maya viewport. The installer writes
   `AbnormalMaya.mod` in your Maya user modules directory, preserves a different
   existing installation, and opens the panel without requiring a restart.
3. For future launches, or a Python shelf button:

   ```python
   import abnormal_maya
   abnormal_maya.show()
   ```

No pip installation, internet connection, NumPy, compiled plugin, or external
service is needed. Use Maya's bundled Qt bindings: PySide2 on 2024/2025, PySide6
on 2026+. Never install a replacement Qt binding into Maya.

For a temporary development launch without installation:

```python
import sys
sys.path.insert(0, r"C:/path/to/repository/maya/AbnormalMaya/scripts")
import abnormal_maya
abnormal_maya.show()
```

## Editing workflow

1. Select one polygon mesh or its components, then **Start session**.
2. Select vertices, edges, faces, or vertex-faces with Maya's normal component
   tools. Object selection means all corners. Maya native marquee, lasso,
   paint selection, isolate select, and viewport navigation remain available.
3. Leave **Edit individual face-vertex normals** off to group all corners at
   each touched vertex; enable it to preserve a partial corner selection.
4. Choose Object, World, or active View space and an axis. Rotate by increments
   or choose **Drag to rotate in viewport** (horizontal drag, 0.5 degrees/pixel;
   press Q to return to selection). Alignment, flatten, flip, averages,
   smoothing, normals from fully selected faces, inside, and outside operate
   through buttons. Explicit mirror and automatic symmetry always use mesh
   object axes, independently of the editing-space setting.
5. **Finish** keeps edits. **Cancel session** restores the session-start normal
   values and lock flags. Closing the panel keeps edits. **Reset selected**
   restores selected normals only and still respects the current weight mask.
6. Maya Undo/Redo operate on global history. Each button operation is one undo
   chunk; the native dragger groups a gesture using step undo mode. The gesture
   grouping and exception behavior must be verified in Maya, not inferred from
   the numerical tests. Leaving the drag tool keeps its latest edit. Escape
   is not a separate session rollback; use Undo or Cancel session.

Do not change topology during a session. The tool checks face connectivity and
vertex counts and rejects stale mappings. Deleted/replaced meshes and instances
are rejected. Renaming/reparenting the session mesh is supported through UUID
resolution. Symmetry maps rebuild after point positions change. The tool does
not disable deformers or modify construction-history connections. For a
predictable first workflow, use an editable non-instanced mesh with no incoming
construction history; validate your specific deformation stack separately.

## Features and precise behavior

- **Normals, not geometry:** edits never move vertices or reverse polygons.
  Updated normals are explicitly frozen; Maya's native commands own the undo
  records for previous normal values/locks. Hard/soft edge settings are not
  deliberately changed by the tool. Verify shared-normal assignments in Maya.
- **Flatten:** remove the component along the chosen axis. Zero-length results
  retain their original normal. Opposing averages also retain originals.
- **Smooth:** like Abnormal, average all corner normals on neighboring vertices,
  blend by `0.5 * strength` per iteration, and normalize afterward. This can
  update unselected sibling corners at selected vertices. It is not an
  area-weighted algorithm and does not automatically preserve hard seams.
- **From faces:** only fully selected faces contribute. Their normals are
  averaged per incident vertex. Individual mode restricts writes to those
  face corners; grouped mode includes other corners at the same vertices.
- **Inside/outside:** use geometric face normals, optionally averaged at a
  vertex using the separate face-direction checkbox (independent of individual
  corner selection). This changes direction calculation, not polygon shading. They do not detect closed-volume orientation. The source's flat-mode
  inside-sign omission is corrected here.
- **Mirror:** nearest reflected vertex plus matching geometric corner bisector;
  no UV dependency. Zero manual distance means unlimited nearest matching,
  matching the source. A positive distance limits manual matches. Auto mirror
  uses unlimited matching. Use clean symmetric meshes; centerline and
  overlapping-vertex ambiguities can require individual selection. Sequential
  axis processing matches the source; it is not all combinations of axes.
- **Clipboard:** select exactly one vertex or vertex-face and Store, then select
  destinations and Paste. A vertex source matches corner bisectors by dot
  product. Source corner references remain live, as in Abnormal. There is no
  cross-mesh clipboard. Geometric bisectors approximate BMesh corner tangents;
  verify concave/degenerate polygon correspondence.
- **Masks:** selection gives binary weights; soft-selected vertices give Maya
  rich-selection weights; a named component set gives binary membership.
  Weights are session-local. Clear means unrestricted editing. An empty mask
  protects everything, correcting the source's all-zero-mask behavior. Explicit
  mirror and automatic mirrored destinations bypass masks as in source symmetry.
  These masks are separate from Maya global selection undo.
- **Point/sphere:** target fields are world-space centimeters, independent of
  display units. Pick a locator/transform to sample its position, or set the
  target at the selected-corner centroid. Targets are sampled, not live scene
  connections. Point can align vectors from the selection centroid; sphere
  points away from the target. Displacement vectors are blended before
  normalization, retaining source distance-dependent strength behavior.
- **Spaces:** normals use inverse-transpose transforms and are normalized;
  targets use point transforms. Zero-scale transforms are rejected. No blanket
  Z-up to Y-up conversion is applied to native Maya meshes.
- **Persistent data:** Store/Load writes whole-mesh object-space vectors to the
  mesh's `abnormalNormals` JSON string attribute, including a topology signature.
  It survives scene saving. It stores normals, not weights or lock states.
- **Colors:** the `abnormalNormals` face-vertex color set stores signed XYZ
  directly, alpha 1, without clamping. This is data, not display color; do not
  apply color-space conversion. Negative values require an unclamped color set.
- **Display:** the panel toggles Maya's native face-vertex normal display and
  its size. Display changes are normal Maya undoable settings and are retained.

## What is not a one-to-one port yet

This release uses Maya native component selection and normal drawing. It does
not reproduce Blender's GPU corner wedges, selected/active normal colors,
weight heat map, per-normal hidden-state stack, custom rotation-ring gizmo,
custom shortest-path/loop selection heuristics, in-viewport floating panels, or
Blender hotkeys. It has no custom DG history node or compiled acceleration.
Qt controls replace the Blender custom UI. Maya native selection tools cover
basic selection but are not claimed to match all Blender selection algorithms.

Native per-corner commands prioritize Maya-managed undo over speed; very large
meshes and continuous drags can be slow and create substantial history. A
profiled API command with exact normal-assignment restoration is a future
optimization, not a requirement to install this script package. If a Maya
command fails halfway through, previous writes remain in a closed undo chunk;
use Maya Undo to revert them. Cancel restores values/locks, not necessarily
original internal normal-sharing IDs. Test on a copy of an asset first.

## Validation

Outside Maya, from the repository root:

```sh
python3 -m unittest discover -s maya/tests -v
python3 -m compileall -q maya/AbnormalMaya/scripts maya/tests maya/install.py
```

Inside Maya, after installation (creates and removes its own test cube; does
not reset or save the current scene):

```python
import runpy
runpy.run_path(r"C:/path/to/repository/maya/tests/maya_smoke.py")["run"]()
```

Or in Maya's Python interpreter, when available:

```sh
mayapy /path/to/repository/maya/tests/maya_smoke.py
```

The integration smoke checks corner isolation, native undo/redo and locks,
zero masks, nonuniform transforms, JSON/color round trips, session restoration,
and topology guards. It must print `PASS` and exit without an exception.

Manual GUI checks: launch and close/reopen docking; edit one cube face-corner;
undo/redo; drag rotation in object/world/view; try a soft-selection mask and
manual symmetry; cancel; save and reload stored data. Check Maya 2024 and your
newest supported release separately, including color storage and normal locks.
Tests have not been run under Maya in the cloud environment.

## Files

- `AbnormalMaya/scripts/abnormal_maya/core.py`: host-independent algorithms.
- `scene.py`: Maya selection, transforms, native undoable writes, storage.
- `ui.py`: Qt dockable panel and native selection/display controls.
- `tools.py`: native viewport dragger rotation context.
- `install.py`: user module registration and immediate launch.
- `tests/test_core.py`: executable numerical regression tests.
- `tests/maya_smoke.py`: actual Maya integration checks.

MIT license and original attribution are included in `AbnormalMaya/LICENSE`.

To build the distributable ZIP and SHA-256 file:

```sh
python3 maya/build.py
```

The generated `maya/dist/AbnormalMaya-0.1.2.zip` excludes caches and preserves
license attribution. It includes the standalone numerical and Maya integration
tests. The repository additionally contains `tests/blender_parity.py`, which
compares nine algorithms with the original source under Blender; those checks
passed on Blender 4.3.2. They replace only mesh-write/UI/undo callbacks and do
not establish Maya API or viewport compatibility.

## Extended automated and guided GUI checks

With the package installed, download `tests/run_all_maya.py` or the standalone
[`AbnormalMaya-tests.zip`](releases/AbnormalMaya-tests.zip). In Maya's **Python**
Script Editor:

```python
import runpy
report = runpy.run_path(r"C:/path/to/run_all_maya.py")["run"]()
```

This runner tests all operation adapters, normal undo/redo and locks,
object/world/view space, nonuniform/negative transforms, symmetry, clipboard,
weights and rich selection, signed colors/JSON, lifecycle guards, Qt docking,
panel controls, normal display, and rotation callbacks. It continues after a
failure and prints each case and traceback, followed by totals. Native pointer
coordinates are simulated for the callback test; this does **not** prove real
mouse dispatch or native gesture undo grouping.

A modeless checklist then offers a test cube and panel for actual pointer
rotation, per-gesture undo/redo, docking, and visual inspection. Mark each as
PASS/FAIL and click Print complete report. Closing the checklist removes its
own test geometry. Tests do not reset or save the scene, and restore selection,
current tool, and soft-selection settings. Like any Maya command test, they add
global undo-history entries; do not assume your prior undo queue is unchanged.
Use an otherwise idle Maya session; finish any active normal-editing gesture
before running. An existing rotation context is preserved and its creation
check is explicitly skipped. Restart Maya to test a fresh context.

To skip the manual checklist: `run(manual=False)`. To save the automated report,
pass `report_path=r"C:/path/to/report.json"`; the manual checklist prints its
updated results separately. No report files are written by default.

The extended GUI runner is syntax-checked here but has not been executed under
Maya in the cloud. The original 0.1.2 smoke suite passed in the user's Maya
2025 session; that does not imply these additional GUI checks have passed.
