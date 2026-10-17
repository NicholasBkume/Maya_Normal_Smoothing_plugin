# Abnormal Maya 0.9.1 — full feature candidate

A Python 3 face-corner normal editor for Maya 2024+, based on the supplied
MIT-licensed Abnormal 1.1.5 Blender add-on by Cody Winchester / BlenderNPR.
The original Blender source remains at the repository root.

[Download AbnormalMaya-0.9.1.zip](releases/AbnormalMaya-0.9.1.zip?raw=true).

The remaining feature milestones are implemented in this candidate. **Current
Maya validation is pending**: the previous 0.2.1 release passed all 16 automated
and six manual checks in the user's Maya 2025 session. Version 0.9.1 passes 57
local tests and expanded Blender comparisons. Its new 26-case Maya suite and
12 manual checks must run before a fully validated 1.0 claim. Maya 2024 and
2026 have not been verified here. See [PORT_STATUS.md](PORT_STATUS.md).

## Install or upgrade

1. Extract the ZIP to a permanent location. Close the old checklist/panel and
   **restart Maya** so the previous Python modules and draw plugin unload.
2. Drag `install.py` into a viewport, or use Maya's **Python** Script Editor:

   ```python
   import runpy
   runpy.run_path(r"C:/tools/AbnormalMaya-0.9.1/install.py")["install"](
       r"C:/tools/AbnormalMaya-0.9.1"
   )
   ```

   The installer writes a module entry to your Maya user `modules` directory.
   Known single-line older Abnormal entries upgrade with a backup. Custom
   entries require an explicit `replace_existing=True`; their contents are
   backed up too. An already-loaded package from a different folder is rejected
   with a restart message rather than silently running the old version.
3. Launch later, or create a **Python** shelf button:

   ```python
   import abnormal_maya
   abnormal_maya.show()
   ```

No pip packages, NumPy, compiled binaries, credentials or services are needed.
The UI selects PySide2 or PySide6 based on Maya's actual Qt version. It never
installs or replaces Maya's bundled Qt. For a temporary development launch,
put `AbnormalMaya/scripts` on `sys.path` before importing the package.

## Normal editing

Select one editable polygon mesh and **Start session**. Native vertex, edge,
face, and vertex-face component selection still works. Enable **Edit individual
face-vertex normals** to edit corners independently; otherwise touching a vertex
groups its incident corners. Object selection means all corners.

Controls include view/world/object rotation, axis flatten/alignment, flip,
reset, per-vertex or whole-selection averaging, iterative smoothing, normals
from fully selected faces, inside/outside, explicit/automatic symmetry,
active-to-selection copy, live-reference clipboard, binary/set/soft-selection
masks, and JSON/signed-color storage. Smooth/Flat shading changes edge flags
while preserving explicit normal directions; changed normals may need freezing.
Session restore also restores the original smoothing flags.

- **Finish** keeps changes and cleans up editing tools/overlays.
- **Cancel session** restores session-start normal values, lock flags and edge
  smoothing. It does not delete topology changes made outside the editor.
- **Reset selected** restores selected normal values, respecting weights.
- **Session undo/redo** restores normals, locks, edge flags, selection, active
  corner, hidden state, weights and clipboard together. Native Maya selection
  changes are captured before the next editor action.
- Maya's global Undo/Redo still works for native editing commands. Use session
  history when restoring filter/selection/display state. Do not alternate
  arbitrary external geometry edits with local history and expect a DAG snapshot.

Each normal editing action closes its native undo chunk even if a command
fails. Earlier writes in a failed operation remain natively undoable. There is
no long-lived undo chunk spanning the UI. Session history is bounded to 128
states and reduces the limit for large meshes (minimum four), targeting roughly
two million stored corner-normal entries. Complete immutable snapshots can
still consume substantial memory. Native internal normal-sharing IDs are not
promised to be byte-identical after restoring values/locks/edge state.

## Direct corner selection and traversal

Enable the custom overlay and click **Pick normals / corners**. This installs
an event filter only on the active viewport; it does not replace a global Maya
hotkey set. The overlay remains nonselectable to native Maya tools outside this
picker. The selector operates on displayed line segments and triangular corner
proxies, preserving split normals at shared vertices.

Choose **Click**, **Box**, **Circle**, or **Lasso**. Dragging previews the result;
release commits it. Escape cancels an unfinished region gesture. Circle mode
paints along the stroke; its radius is in physical viewport pixels. Projection
converts Qt logical coordinates to viewport pixels for HiDPI displays.

- No modifier: replace selection.
- Shift: add. Ctrl: subtract. Shift+Ctrl: toggle.
- **X-ray** ignores occlusion. Otherwise rays test the edited source mesh,
  including its evaluated geometry, with an intersection accelerator.
- Hidden corners and points behind the camera are excluded. With selected-only
  overlay enabled, undisplayed corners cannot be picked.
- Alt, middle button and right button remain available for native navigation.
  Alt navigation cancels an unfinished region gesture. Q exits the picker.

The topology buttons use mesh connectivity, not spatial proximity:

- **Linked** expands through connected visible vertices.
- **Vertex path** requires exactly two endpoint vertices.
- **Face path** requires corners on two endpoint faces (use individual mode).
- **Edge loop** requires one native Maya edge; it continues through valence-four
  vertices along edges not sharing adjacent faces, stopping at poles/boundaries.
- **Face ring** requires one native edge and crosses opposite edges of quads,
  stopping at non-quads and hidden faces.

Equal shortest paths and ambiguous overlapping picks use deterministic Maya-ID
ordering. Blender BMesh iteration can choose a different equally short path.
Source edge-loop/ring results were compared against all edges of a quad-grid
fixture; concave and non-manifold traversal still needs representative assets.

## Interactive rotation rings and targets

**Rotation rings** creates a temporary pivot at the selected-corner centroid
and uses Maya's native rotate manipulator. The pivot basis follows Object,
World or View mode. Normal vectors use the matrix delta from the initial pivot;
previews are absolute relative to captured normals, not compounded each tick.

**Live point target** and **Live sphere target** create a temporary locator at
the target fields and use Maya's move manipulator. Object/View mode aligns the
helper's local axes to the corresponding basis. World mode uses world axes.
Move the locator to preview normals. Point can align all vectors from the
selection centroid; sphere points away from the locator. Strength, masks,
selected corners and symmetry settings are captured for the operation.

**Confirm live tool** / Enter keeps the result. **Cancel live tool** / Escape
restores the captured full state. Ctrl+Z in the live viewport cancels the pending
preview rather than partially undoing its native commands. Closing the panel or
switching editor tools cancels an unconfirmed manipulation. Q can leave the
native manipulator, but an explicit Confirm/Cancel is still required.

The helper and its context are removed on completion, including failed previews.
Helpers are marked `doNotWrite` and do not serialize. No source vertices are
moved. Source renames resolve through UUIDs. Other editor actions are blocked
while a live manipulation is pending. Avoid external normal/topology edits
until confirming/cancelling. Helper creation/deletion and preview commands remain in native undo history;
native undo may temporarily restore a deleted nonsaving helper, as with normal
Maya node deletion. This keeps transform undo commands valid rather than deleting
their objects outside history. The confirmed result is a single step in
**session** history; use that history for the editor workflow. A failed preview
is cancelled when confirmed and reports its error.

## Viewport feedback

The optional Python Viewport 2.0 plugin supplies normal lines, vertex points,
corner wedges, normal/selected/active colors, positive-weight colors, X-ray,
selected-only display, length scaling, brightness, wedge size and mesh wireframe.
Colors and normal-length factors follow the source's HSV definitions. Weight
colors use 16 display bins; edit weights remain precise. Display lengths use
world centimeters, regardless of Maya display units; point sizes use pixels.

Hide selected/unselected and Reveal affect editor normals, **not mesh geometry**.
Hidden corners are protected from selected-normal edits, smoothing, clipboard
and mirrored destinations. Whole-mesh stored-data loads intentionally operate
on the whole mesh. Visibility has its own compatibility undo buttons as well
as unified session history. Native Maya normal display remains available as an
alternative but cannot individually hide corner normals.

The draw helper is a nonselectable, nonsaving shape below the source transform.
It is removed on disable, Finish, Cancel and panel close. Display helper changes
use scoped `stateWithoutFlush` to avoid splitting normal-edit history. Actual
API selection lists are preserved; transform/shape string aliases can change.
Render callback failures are recorded and reported by both UI and tests.
Refresh intervals adapt upward from 200 ms to avoid continuously queuing work
on slower/larger meshes. Disable the custom overlay for a lighter workflow.

The plugin uses local prototype node ID `0x0007F7F0`. Obtain a registered Autodesk
ID before studio-wide distribution. Node-ID collisions fail initialization.
Helpers may mark the scene modified, despite being excluded from serialization.

## Preferences and scoped shortcuts

**Save preferences** persists validated controls using a Maya `optionVar`.
**Reset controls** restores defaults without overwriting saved preferences until
Save is clicked. Font scaling, selection mode/radius, axis/space, normal settings,
overlay settings, strength, iterations and shortcut enablement persist. Session
meshes, selections, weights, clipboard, helper nodes and active tools do not.
Test-created panels do not automatically save preferences.

Panel-only shortcuts: Ctrl+Alt+Z / Ctrl+Alt+Shift+Z for session undo/redo; Alt+P
picker; Alt+R rotation rings; Alt+T point target; Alt+S sphere target. They use
`WidgetWithChildrenShortcut` and do not modify user hotkey sets.

While the viewport picker is active: B box, C circle, Shift+L lasso, L linked,
A select all, H hide selected, Shift+H hide unselected, Alt+H/F reveal, [ / ]
circle radius, Ctrl+Z / Ctrl+Shift+Z session history, Q exit. Non-cancel actions
are deferred during a region drag. Disable scoped shortcuts in the panel to
return ordinary key handling to Maya; Q/Escape still provide a safe tool exit.

## Data and transform semantics

Normals are stored per `(faceId, vertexId)` corner in object space. World/view
normal transforms use inverse transpose and normalization; points use ordinary
matrices. No automatic Blender Z-up conversion is applied to native Maya meshes.
Targets are world-space centimeters. Zero/near-singular transforms are rejected.

Smoothing matches the source's neighboring-corner average with an effective
iteration factor of `0.5 * strength`; it can change unselected siblings of touched
vertices, except hidden corners. It is not area-weighted or seam-preserving.
Outside/inside use geometric face directions, not a closed-volume test. Point
and sphere blend unnormalized displacements before normalization, retaining the
source's distance-dependent strength. Degenerate results keep previous normals.
The source's flat inside-sign and all-zero-mask omissions are corrected.

Mirroring finds the nearest reflected vertex and matches corner tangents.
Zero manual distance means unlimited nearest matching; automatic symmetry also
uses unlimited matching. Concave/straight corner tangents now match actual
`BMLoop.calc_tangent` fixtures. Clipboard source indices remain live and
mesh-local. Equal candidates use deterministic ID ordering.

Store/Load uses the mesh `abnormalNormals` JSON string attribute with topology
signature. The color-set path uses signed, unclamped face-vertex RGB values,
alpha one, also named `abnormalNormals`; no color-space conversion is applied.
Persistent storage contains vectors, not locks/history. Invalid storage data
is rejected before mesh edits.

## Verification and performance

Run in Maya's **Python** tab after restarting and extracting this package:

```python
import runpy
report = runpy.run_path(r"C:/path/to/AbnormalMaya-0.9.1/tests/run_all_maya.py")["run"]()
```

The runner has 26 automated cases, including all previous behavior, normal-ID
bulk capture ordering, grouped-command undo, full-state history, shading flags,
projection/occlusion, picker lifecycle, preferences and shortcut scopes, live
targets/rings, a representative construction-history/blendShape workflow, and
a 10,000-corner timing case. It uses a temporary camera for occlusion testing
and restores the previous viewport camera. Each case prints PASS/FAIL/SKIP and
its traceback. Render tests require successful native draw callbacks.

Complete the 12 checks in the modeless manual window for actual mouse input,
modifiers, HiDPI behavior, native navigation, live manipulation, history and
preferences. Synthetic callback tests do not establish physical gesture behavior.
Closing the checklist removes its own test geometry/panel.

Tests do not reset or save your scene. They restore selection, current tool,
soft-selection settings and the preference variable. They add global undo-history
entries. Run in an idle scene, with no active picker/live tool. An optional
`report_path` writes JSON; otherwise results are printed and returned. Use
`run(manual=False)` to omit the interactive checklist.

Outside Maya, from the repository root:

```sh
python3 -m unittest discover -s maya/tests -v
python3 -m compileall -q maya/AbnormalMaya/scripts maya/tests maya/install.py
python3 maya/tests/profile_algorithms.py
python3 maya/build.py
```

The repository-only `blender_parity.py` compares nine numerical operations,
actual BMesh corner tangents and source loop/ring traversal under Blender.
[PROFILE.json](PROFILE.json) records CPython CPU timings: for 10,000 vertices /
39,204 corners, approximately 0.32 s mesh-cache construction, 0.43 s overlay
geometry, 0.75 s for five smooth iterations and 0.05 s topology/path work on this
machine. These are **not Maya or GPU timings**. Actual host timings are recorded
by the integration runner. Bulk reads and grouping identical normal assignments
reduce Maya command overhead; arbitrary unique normals can still require many
native writes. No unverified custom API undo implementation replaces them.

## Boundaries of the full-port candidate

Qt controls and native Maya manipulators replace the Blender widget framework
and gizmo rendering. This is functional translation, not pixel-identical UI.
Tie-breaking, non-manifold traversal and modifier/deformer evaluation can differ
between hosts. The tool does not mute or rewrite Maya's construction graph.
Topology edits during a session invalidate mappings and are rejected; Finish
still cleans up the session. Instances are rejected; make a mesh unique first.

The 0.9.1 feature implementation is complete for the mapped workflows, but the
new Maya runtime tests, difficult production assets and 2024/2026 host coverage
remain necessary. Nothing in the local test results establishes those outcomes.

MIT license and original attribution are included in `AbnormalMaya/LICENSE`.
