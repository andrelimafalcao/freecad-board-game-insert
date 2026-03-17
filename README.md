# FreeCAD Board Game Insert Generator

A FreeCAD macro that generates 3D-printable box inserts for board games from a JSON config file. Design your insert layout visually in a step-by-step GUI wizard, or write JSON directly and generate immediately.

## Features

- GUI wizard (`insert_designer.py`) for building and previewing insert layouts
- Recursive split layout engine — divide trays horizontally or vertically, nest as deep as needed
- Auto-fill: omit width/depth on one compartment per group and it fills the remaining space
- Finger holes (bottom) and finger notches (wall) per compartment
- Configurable fillets: external corners, internal dividers, base rounding, bottom chamfer
- Exports STL files ready for slicing
- Multiple trays auto-arranged in the FreeCAD viewport

## Requirements

- [FreeCAD](https://www.freecad.org/) 0.21 or later (uses Part and MeshPart workbenches)
- No additional Python packages required — uses FreeCAD's bundled Python

## Installation

1. Download `board_game_insert.py` and `insert_designer.py`
2. Place both files in the same folder (e.g. your FreeCAD macros folder)

To find your macros folder: **Macro → Macros → ...** (the folder path is shown at the top).

## Usage

### GUI Wizard (recommended)

1. Open FreeCAD
2. Go to **Macro → Macros**, select `insert_designer.py`, click **Execute**
3. Use the wizard to set box dimensions, add trays, and define compartments
4. Click **Generate** to build the shapes and export STL files

### Headless (JSON only)

1. Write a JSON config (see [examples/](examples/))
2. Open FreeCAD, go to **Macro → Macros**, select `board_game_insert.py`, click **Execute**
3. A file picker opens — select your JSON config
4. The insert is generated and STL files are written to the `output_dir` in your config

## JSON Config Reference

All dimensions are in **millimetres**.

```json
{
  "document_name": "MyInsert",
  "output_dir": "/path/to/output",
  "arrange_gap": 5,

  "box_width": 300,
  "box_depth": 200,
  "box_height": 60,

  "margin": 2.0,

  "defaults": {
    "wall_thickness": 2.0,
    "floor_thickness": 1.5,
    "div_thickness": 1.5,
    "finger_hole": false,
    "finger_hole_radius": 10.0,
    "finger_notch": "None",
    "finger_notch_width": 20.0,
    "fillet": {
      "external": 2.0,
      "internal": 1.0,
      "base": 1.0,
      "base_type": "fillet",
      "bottom_chamfer": 1.0
    }
  },

  "layout": { ... }
}
```

### Layout tree

The `layout` node (and `comp_layout` inside each tray) is a recursive tree of **splits**, **trays**, and **compartments**:

| Node | Keys | Description |
|------|------|-------------|
| Split | `split`, `children`, `flex_weight` | Divides space. `split: "H"` = side by side (along X). `split: "V"` = front to back (along Y). `flex_weight` optionally pins relative sizes of children. |
| Tray | `tray` → `name`, `comp_layout` | A physical tray. `comp_layout` is the root of its compartment tree. |
| Compartment | `comp` → see below | A single hollow cavity cut into the tray. |

**Compartment fields** (all optional — defaults are inherited from `defaults`):

| Field | Type | Description |
|-------|------|-------------|
| `width` | mm | Fixed width. Omit on exactly one sibling to auto-fill. |
| `depth` | mm | Fixed depth. Omit on exactly one sibling to auto-fill. |
| `label` | string | Label engraved in the floor (not yet implemented — reserved). |
| `finger_hole` | bool | Circular hole through the floor for pushing pieces up. |
| `finger_hole_radius` | mm | Radius of the finger hole. |
| `finger_notch` | `"north"` / `"south"` / `"east"` / `"west"` / `"None"` | Semicircular notch cut into the specified wall. |
| `finger_notch_width` | mm | Diameter of the finger notch. |

### Auto-fill rule

Within any split group, exactly one child may omit `width` (for H splits) or `depth` (for V splits). That child expands to fill whatever space remains after all fixed-size siblings and dividers are placed.

### Keys starting with `"_"` are comments

They are stripped before geometry generation and have no effect.

## Examples

See the [`examples/`](examples/) folder:

| File | Description |
|------|-------------|
| `example_config.json` | Simple 3-tray insert: tokens, cards, tiles |
| `futuropia.json` | 9-tray insert for a 365×265×17 mm box |
| `futuropia2.json` | 6-tray insert for a 365×265×30 mm box |

> **Note:** Update `output_dir` in each example to a folder on your machine before running.

## Project Structure

```
board_game_insert.py   # geometry engine (importable or standalone)
insert_designer.py     # PySide2 GUI wizard
examples/              # sample JSON configs
```

## Contributing

Issues and pull requests are welcome. Please open an issue before starting large changes.

## License

MIT
