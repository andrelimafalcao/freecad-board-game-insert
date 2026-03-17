# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A FreeCAD macro system that generates 3D-printable board game box inserts from JSON configuration files. There are two entry points:

- **`insert_designer.py`** — the primary macro to run. Opens a PySide2 GUI wizard inside FreeCAD for building configs and generating inserts.
- **`board_game_insert.py`** — the backend engine, imported by the designer. Can also be run standalone (shows a file picker, reads a JSON, generates immediately).

## How to run

Both files are **FreeCAD macros**. Execute them from inside FreeCAD:
> Macro → Macros → select file → Execute

`insert_designer.py` imports `board_game_insert.py` at runtime by inserting the macro directory into `sys.path`. Both files must be in the same folder.

There is no build step, no package manager, no test suite.

## Architecture

### Data model

Everything flows through a plain Python `dict` that mirrors the JSON schema:

```
config {
  box_width / box_depth / box_height  ← inner space of the physical game box
  document_name, output_dir, arrange_gap
  trays: [
    tray {
      name, width, depth, height
      wall_thickness, floor_thickness
      fillet: { external, internal }
      sections: [
        section {
          depth  (omit one per tray for auto-fill)
          columns: [
            column {
              width  (omit one per section for auto-fill)
              label, finger_hole, finger_hole_radius
              finger_notch, finger_notch_width
            }
          ]
        }
      ]
    }
  ]
}
```

### Coordinate system

- X = width (left → right)
- Y = depth (front → back)
- Z = height (bottom → top)

Tray origin is at (0, 0, 0). Inner space starts at (wall_t, wall_t, floor_t).

### board_game_insert.py — key functions

| Function | Role |
|---|---|
| `resolve_layout(tray)` | Validates dimensions; auto-fills one missing `depth` per tray and one missing `width` per section. Mutates the config dict in-place. |
| `build_tray(tray_cfg)` | Creates the Part shape: starts with a solid box, cuts out each compartment, cuts finger holes and notches. Returns a `Part.Shape`. |
| `apply_fillets(shape, tray_cfg)` | Classifies edges as external (outer rim + base) or internal (divider tops), applies separate fillet radii via `shape.makeFillet()`. Failures are caught as warnings. |
| `export_stl(shape, filepath)` | Meshes the shape with `MeshPart.meshFromShape` and writes STL. |
| `arrange_objects(doc, built_trays, gap)` | Sets `Placement` on each `Part::Feature` to lay trays side by side along X. |

### insert_designer.py — key classes/methods

The single class `InsertDesigner(QDialog)` owns `self.config` (the live dict) and the tree. Tree items store `(node_type, data_dict, parent_list)` in `Qt.UserRole`. Editing a field immediately mutates the dict.

| Method | Role |
|---|---|
| `_populate_tree()` | Rebuilds the entire tree from `self.config`. |
| `_on_select()` | Loads the selected node's data into the right property panel; sets `self._loading = True` to suppress dict writes during load. |
| `_rebuild_subtree(item)` | Used by move-up/down to re-render children of a tree node after reordering `parent_list`. |
| `_update_usage()` | Recomputes the Insert panel's "Tray usage" label (width/depth/height vs. box dimensions). |
| `_generate()` | Deep-copies config, strips `_comment` keys, calls `gen.build_tray` / `gen.apply_fillets` / `gen.export_stl` / `gen.arrange_objects` from the imported backend. |

### Auto-fill rule

`resolve_layout` allows exactly one `section` per tray to omit `"depth"` and exactly one `column` per section to omit `"width"`. The missing value is computed as the remaining inner space after summing the others and the dividers. Exceeding this limit raises `ValueError` with a descriptive message.

### FreeCAD geometry strategy

`build_tray` uses **subtraction-only CSG**:
1. Solid box (outer dimensions)
2. Cut each compartment volume → walls, floor, and dividers are what remains
3. Cut finger holes (vertical cylinders through the floor)
4. Cut finger notches (horizontal cylinders through the wall at `z = H`, producing a semicircle opening upward)

Dividers are never explicitly created — they are the solid left between adjacent compartment cuts.

## JSON config

See `example_config.json` for a working three-tray example. Keys starting with `"_"` are treated as comments and stripped before generation.

The `"box_width"` / `"box_depth"` / `"box_height"` fields on the root object represent the board game box's inner space and are used only for the designer's usage indicator — they do not affect geometry generation.
