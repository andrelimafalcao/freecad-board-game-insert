"""
Board Game Insert Generator — FreeCAD Macro

New layout model:
  Box → layout tree → split nodes + tray-leaf nodes
  Tray → comp_layout tree → split nodes + comp-leaf nodes

JSON schema:
{
  "box_width": 300, "box_depth": 250, "box_height": 60,
  "margin": 2.0, "tolerance": 0.5,
  "defaults": {
    "wall_thickness": 2.0, "floor_thickness": 1.0, "div_thickness": 1.5,
    "finger_hole": false, "finger_hole_radius": 10.0,
    "finger_notch": "none", "finger_notch_width": 20.0,
    "fillet": { "external": 2.0, "internal": 1.0, "base": 1.5,
                "base_type": "fillet", "bottom_chamfer": 1.0 }
  },
  "layout": {
    "split": "V",
    "flex_weight": [1.0, 1.0],
    "children": [
      { "tray": { "name": "A", "comp_layout": { "comp": {} } } },
      { "tray": { "name": "B", "comp_layout": {
          "split": "V",
          "children": [
            { "comp": { "width": 80.0 } },
            { "comp": {} }
          ]
      } } }
    ]
  }
}

Tray sizing:
  Fixed: all comps in a direction have explicit width/depth
         tray size = sum(comp_sizes) + 2*wall_t + (n-1)*div_t + tolerance
  Flexible: any comp in that direction is null  →  tray fills its allocated share

Coordinate system:
  X = width (left → right),  Y = depth (front → back),  Z = height (bottom → top)
"""

import os
import json
import copy
from dataclasses import dataclass, field

import FreeCAD
import FreeCADGui
import Part
import MeshPart

from FreeCAD import Vector
from PySide2 import QtWidgets


# ── Data structures ────────────────────────────────────────────────────────────

@dataclass
class LayoutNode:
    x: float
    y: float
    w: float
    d: float
    tray:     object = None                      # tray dict if leaf
    comp:     object = None                      # comp dict if comp-level leaf
    split:    object = None                      # "V" | "H" | None
    children: list   = field(default_factory=list)
    overflow: bool   = False
    cfg_node: object = None                      # reference to config dict node


# ── File I/O ───────────────────────────────────────────────────────────────────

def pick_json_file():
    path, _ = QtWidgets.QFileDialog.getOpenFileName(
        None, "Select Board Game Insert Config", "", "JSON Files (*.json)"
    )
    return path


def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ── Box-level layout resolution ────────────────────────────────────────────────

def _comp_tree_fixed_size(comp_node, direction, div_t):
    """
    Return total fixed size of comp_node in `direction`, or None if any comp
    is flexible (no explicit width/depth).
    direction "V" → checks "width"; "H" → checks "depth".
    """
    if "comp" in comp_node:
        key = "width" if direction == "V" else "depth"
        return comp_node["comp"].get(key)          # float or None

    if "split" in comp_node:
        split    = comp_node["split"]
        children = comp_node.get("children") or []
        if not children:
            return None
        if split == direction:
            subs = [_comp_tree_fixed_size(c, direction, div_t) for c in children]
            if any(s is None for s in subs):
                return None
            return sum(subs) + max(len(subs) - 1, 0) * div_t
        else:
            # Cross-direction split: children share the same extent
            return _comp_tree_fixed_size(children[0], direction, div_t)

    return None


def _tray_slot_size(child_node, defs, direction):
    """
    Return the fixed size of a box-level child in `direction`, or None
    if the subtree contains a flexible tray in that direction.
    """
    if "tray" in child_node:
        tray   = child_node["tray"]
        wall_t = tray.get("wall_thickness") or defs.get("wall_thickness", 2.0)
        div_t  = tray.get("div_thickness")  or defs.get("div_thickness",  1.5)
        fixed  = _comp_tree_fixed_size(
            tray.get("comp_layout", {"comp": {}}), direction, div_t)
        if fixed is not None:
            return fixed + 2 * wall_t
        return None

    if "split" in child_node:
        split    = child_node["split"]
        children = child_node.get("children") or []
        if not children:
            return None
        if split == direction:
            parts = [_tray_slot_size(c, defs, direction) for c in children]
            return None if any(p is None for p in parts) else sum(parts)
        else:
            return _tray_slot_size(children[0], defs, direction)

    return None


def _distribute(parent_node, children, avail, defs, direction, gap=0.0):
    """
    Distribute `avail` mm among `children`. Fixed children get their computed
    size; flexible children share the remainder weighted by parent_node["flex_weight"].
    Returns list of float sizes, one per child.
    """
    n           = len(children)
    sizes       = [_tray_slot_size(c, defs, direction) for c in children]
    total_fixed = sum(s for s in sizes if s is not None)
    n_flex      = sum(1 for s in sizes if s is None)
    remaining   = max(avail - (n - 1) * gap - total_fixed, 0.0)

    if n_flex == 0:
        return sizes

    raw_weights  = parent_node.get("flex_weight") or []
    all_weights  = [(raw_weights[i] if i < len(raw_weights) else 1.0)
                    for i in range(len(children))]
    flex_weights = [all_weights[i] for i, s in enumerate(sizes) if s is None]
    total_w      = sum(flex_weights) or 1.0
    shares       = iter(w / total_w * remaining for w in flex_weights)
    return [next(shares) if s is None else s for s in sizes]


def _tray_size(tray, avail_w, avail_d, defs):
    """Return (outer_w, outer_d) for a tray given available slot space."""
    wall_t = tray.get("wall_thickness") or defs.get("wall_thickness", 2.0)
    div_t  = tray.get("div_thickness")  or defs.get("div_thickness",  1.5)
    layout = tray.get("comp_layout", {"comp": {}})
    fw = _comp_tree_fixed_size(layout, "V", div_t)
    fd = _comp_tree_fixed_size(layout, "H", div_t)
    w  = (fw + 2 * wall_t) if fw is not None else avail_w
    d  = (fd + 2 * wall_t) if fd is not None else avail_d
    return w, d


def _resolve_node(node, x, y, avail_w, avail_d, defs, max_x, max_y, gap=0.0):
    """Recursively resolve a layout node to a LayoutNode with absolute positions."""
    if "tray" in node:
        tray   = node["tray"]
        tw, td = _tray_size(tray, avail_w, avail_d, defs)
        ov     = (x + tw > max_x + 0.5) or (y + td > max_y + 0.5)
        return LayoutNode(x=x, y=y, w=tw, d=td, tray=tray, overflow=ov,
                          cfg_node=node)

    if "split" in node:
        split    = node["split"]
        children = node.get("children") or []
        n        = len(children)
        if n == 0:
            return LayoutNode(x=x, y=y, w=avail_w, d=avail_d,
                              split=split, cfg_node=node)

        if split == "V":
            sizes   = _distribute(node, children, avail_w, defs, "V", gap)
            cx      = x
            c_nodes = []
            for i, (child, cw) in enumerate(zip(children, sizes)):
                c_nodes.append(_resolve_node(
                    child, cx, y, cw, avail_d, defs, max_x, max_y, gap))
                cx += cw + (gap if i < n - 1 else 0.0)
            return LayoutNode(x=x, y=y, w=avail_w, d=avail_d,
                              split=split, children=c_nodes, cfg_node=node)

        elif split == "H":
            sizes   = _distribute(node, children, avail_d, defs, "H", gap)
            cy      = y
            c_nodes = []
            for i, (child, cd) in enumerate(zip(children, sizes)):
                c_nodes.append(_resolve_node(
                    child, x, cy, avail_w, cd, defs, max_x, max_y, gap))
                cy += cd + (gap if i < n - 1 else 0.0)
            return LayoutNode(x=x, y=y, w=avail_w, d=avail_d,
                              split=split, children=c_nodes, cfg_node=node)

    return LayoutNode(x=x, y=y, w=avail_w, d=avail_d, cfg_node=node)


def resolve_layout(config):
    """Pure function — returns a LayoutNode tree. Never mutates config."""
    bw     = config.get("box_width",  300.0)
    bd     = config.get("box_depth",  250.0)
    m      = config.get("margin",       0.0)
    gap    = config.get("tray_gap",     0.0)
    defs   = config.get("defaults")   or {}
    layout = config.get("layout",
                        {"tray": {"name": "Tray", "comp_layout": {"comp": {}}}})
    avail_w = max(bw - 2 * m, 1.0)
    avail_d = max(bd - 2 * m, 1.0)
    return _resolve_node(layout, m, m, avail_w, avail_d, defs, bw - m, bd - m, gap)


def collect_trays_from_layout(node):
    """Return list of (LayoutNode, tray_dict) for all tray leaves."""
    if node.tray is not None:
        return [(node, node.tray)]
    result = []
    for child in node.children:
        result.extend(collect_trays_from_layout(child))
    return result


# ── Tray-level comp layout resolution ─────────────────────────────────────────

def _distribute_comps(children, avail, div_t, direction):
    """
    Distribute inner tray space among comp children.
    avail already accounts for the full span in `direction`.
    Returns list of float sizes (one per child), dividers excluded.
    """
    n         = len(children)
    available = max(avail - max(n - 1, 0) * div_t, 0.0)
    fixed     = [_comp_tree_fixed_size(c, direction, div_t) for c in children]
    n_flex    = sum(1 for f in fixed if f is None)
    total_fix = sum(f for f in fixed if f is not None)
    remaining = max(available - total_fix, 0.0)
    flex_each = remaining / n_flex if n_flex > 0 else 0.0
    return [flex_each if f is None else f for f in fixed]


def _resolve_comp_node(node, x, y, avail_w, avail_d, div_t):
    """
    Resolve comp_layout node recursively.
    x, y are in outer tray coordinates (wall_t already applied).
    Returns flat list of dicts with _x, _y, _w, _d plus any comp properties.
    """
    if "comp" in node:
        result        = dict(node["comp"])
        result["_x"]  = x
        result["_y"]  = y
        result["_w"]  = avail_w
        result["_d"]  = avail_d
        result["_src"] = node["comp"]   # back-reference to config comp dict
        return [result]

    if "split" in node:
        split    = node["split"]
        children = node.get("children") or []
        result   = []
        if split == "V":
            widths = _distribute_comps(children, avail_w, div_t, "V")
            cx = x
            for child, cw in zip(children, widths):
                result.extend(_resolve_comp_node(child, cx, y, cw, avail_d, div_t))
                cx += cw + div_t
        elif split == "H":
            depths = _distribute_comps(children, avail_d, div_t, "H")
            cy = y
            for child, cd in zip(children, depths):
                result.extend(_resolve_comp_node(child, x, cy, avail_w, cd, div_t))
                cy += cd + div_t
        return result

    return []


def resolve_tray_layout(tray, inner_w, inner_d, defs):
    """
    Resolve comp_layout tree for a tray.
    inner_w, inner_d: inner tray dimensions (outer_w - 2*wall_t).
    Returns flat list of comp dicts with _x, _y, _w, _d in outer tray coords.
    (Coordinates include wall_t offset so _x >= wall_t.)
    """
    wall_t      = tray.get("wall_thickness") or defs.get("wall_thickness", 2.0)
    div_t       = tray.get("div_thickness")  or defs.get("div_thickness",  1.5)
    comp_layout = tray.get("comp_layout", {"comp": {}})
    return _resolve_comp_node(comp_layout, wall_t, wall_t, inner_w, inner_d, div_t)


# ── Defaults inheritance ───────────────────────────────────────────────────────

def merge_defaults(tray_cfg, defaults):
    """Fill missing tray fields from box-level defaults."""
    if not defaults:
        return
    for key in ("wall_thickness", "floor_thickness", "div_thickness"):
        if key not in tray_cfg and key in defaults:
            tray_cfg[key] = defaults[key]
    if "fillet" in defaults:
        tf = tray_cfg.setdefault("fillet", {})
        for k, v in defaults["fillet"].items():
            tf.setdefault(k, v)


def merge_comp_defaults(comp_cfg, defaults):
    """Fill missing comp fields from box-level defaults."""
    if not defaults:
        return
    for key in ("finger_hole", "finger_hole_radius", "finger_notch",
                "finger_notch_width", "floor_thickness"):
        if key not in comp_cfg and key in defaults:
            comp_cfg[key] = defaults[key]


# ── Finger features ────────────────────────────────────────────────────────────

def make_finger_hole(cx, cy, floor_t, radius):
    """Cylinder punched through the floor, centred at (cx, cy)."""
    return Part.makeCylinder(radius, floor_t + 1.0, Vector(cx, cy, -0.5))


def make_finger_notch(side, cx, cy, x0, y0, comp_w, comp_d, H, t, notch_w, floor_t=0.0):
    """
    Rectangular slot cut through a wall from floor_t to top of tray.
    side: 'south' | 'north' | 'east' | 'west'
    """
    r    = notch_w / 2.0
    eps  = 0.5
    slot = H - floor_t + eps

    if side == "south":
        return Part.makeBox(notch_w, t + 2 * eps, slot,
                            Vector(cx - r, y0 - t - eps, floor_t))
    elif side == "north":
        return Part.makeBox(notch_w, t + 2 * eps, slot,
                            Vector(cx - r, y0 + comp_d - eps, floor_t))
    elif side == "west":
        return Part.makeBox(t + 2 * eps, notch_w, slot,
                            Vector(x0 - t - eps, cy - r, floor_t))
    elif side == "east":
        return Part.makeBox(t + 2 * eps, notch_w, slot,
                            Vector(x0 + comp_w - eps, cy - r, floor_t))
    else:
        raise ValueError(f"Invalid finger_notch side '{side}'. Use: south|north|east|west.")


# ── Tray builder ───────────────────────────────────────────────────────────────

def build_tray(tray_cfg, resolved_comps, box_h, defs):
    """
    Build a Part.Shape for one tray using the resolved compartments list.

    tray_cfg      — tray dict (wall_thickness, floor_thickness, fillet, etc.)
    resolved_comps — list from resolve_tray_layout(); each has _x, _y, _w, _d
                     in outer tray coordinates.
    box_h         — default height if tray doesn't specify its own
    defs          — box-level defaults dict
    """
    t     = tray_cfg.get("wall_thickness") or defs.get("wall_thickness", 2.0)
    div_t = tray_cfg.get("div_thickness")  or defs.get("div_thickness",  1.5)
    ft    = tray_cfg.get("floor_thickness") or defs.get("floor_thickness", 1.0)
    H     = tray_cfg.get("height", box_h)
    name  = tray_cfg.get("name", "?")

    # Compute outer dims from resolved comp extents
    if resolved_comps:
        max_x = max(c["_x"] + c["_w"] for c in resolved_comps)
        max_y = max(c["_y"] + c["_d"] for c in resolved_comps)
        W = max_x + t    # right wall
        D = max_y + t    # back wall
    else:
        W = tray_cfg.get("width",  100.0)
        D = tray_cfg.get("depth",   80.0)

    # Write resolved dims back so apply_fillets can reference them
    tray_cfg["width"]  = W
    tray_cfg["depth"]  = D

    if W <= 2 * t or D <= 2 * t:
        raise ValueError(f"[{name}] Tray too small for wall_thickness={t}.")

    solid       = Part.makeBox(W, D, H)
    comp_cuts   = []
    finger_cuts = []

    for comp in resolved_comps:
        merge_comp_defaults(comp, defs)
        cx0     = comp["_x"]
        cy0_raw = comp["_y"]
        cw      = comp["_w"]
        cd      = comp["_d"]
        # Mirror Y: canvas Y increases down, FreeCAD top-view Y increases up
        cy0     = D - cy0_raw - cd
        cx      = cx0 + cw / 2.0
        cy      = cy0 + cd / 2.0
        comp_ft = comp.get("floor_thickness", ft)

        comp_cuts.append(Part.makeBox(cw, cd, H - comp_ft,
                                      Vector(cx0, cy0, comp_ft)))

        if comp.get("finger_hole"):
            raw_r  = comp.get("finger_hole_radius", min(cw, cd) * 0.25)
            safe_r = min(raw_r, cw / 2.0 - 1.0, cd / 2.0 - 1.0)
            if safe_r > 0.5:
                finger_cuts.append(make_finger_hole(cx, cy, comp_ft, safe_r))
            else:
                FreeCAD.Console.PrintWarning(
                    f"  Skipping finger_hole in '{name}': compartment too small.\n")

        notch_side = comp.get("finger_notch")
        if notch_side and notch_side not in ("None", "none"):
            notch_w = comp.get("finger_notch_width", min(cw, cd) * 0.4)
            # Use wall_t for outer-wall faces, div_t for inner divider faces
            _eps = 0.1
            if notch_side == "south":
                nt = t if cy0 <= t + _eps else div_t
            elif notch_side == "north":
                nt = t if (cy0 + cd) >= D - t - _eps else div_t
            elif notch_side == "west":
                nt = t if cx0 <= t + _eps else div_t
            elif notch_side == "east":
                nt = t if (cx0 + cw) >= W - t - _eps else div_t
            else:
                nt = t
            try:
                finger_cuts.append(make_finger_notch(
                    notch_side, cx, cy, cx0, cy0, cw, cd, H, nt, notch_w,
                    comp_ft + 0.5))
            except ValueError as e:
                FreeCAD.Console.PrintWarning(f"  {e}\n")

    # Step 1: cut compartments
    result = solid
    for cut in comp_cuts:
        result = result.cut(cut)

    # Step 2: base fillet/chamfer (before notch cuts for cleaner topology)
    fillet_cfg = tray_cfg.get("fillet") or {}
    r_base     = float(fillet_cfg.get("base", 0.0))
    base_type  = fillet_cfg.get("base_type", "fillet")
    if r_base > 0:
        base_edges = _compartment_base_edges(result, W, D, ft)
        if base_edges:
            try:
                result = (result.makeChamfer(r_base, base_edges)
                          if base_type == "chamfer"
                          else result.makeFillet(r_base, base_edges))
                FreeCAD.Console.PrintMessage(
                    f"  Base {base_type} r={r_base} on {len(base_edges)} edges.\n")
            except Exception as e:
                FreeCAD.Console.PrintWarning(f"  Base {base_type} failed: {e}\n")

    # Step 3: cut finger holes and notches
    for cut in finger_cuts:
        result = result.cut(cut)

    return result


# ── Fillets & chamfers ─────────────────────────────────────────────────────────

def _classify_vertical_edges(shape, W, D, tol=0.05):
    external, internal = [], []
    for edge in shape.Edges:
        verts = edge.Vertexes
        if not verts:
            continue
        xs = [v.X for v in verts]
        ys = [v.Y for v in verts]
        zs = [v.Z for v in verts]
        if max(xs) - min(xs) > tol or max(ys) - min(ys) > tol:
            continue
        if max(zs) - min(zs) < tol:
            continue
        x = xs[0]; y = ys[0]
        on_rim = (abs(x) < tol or abs(x - W) < tol or
                  abs(y) < tol or abs(y - D) < tol)
        if on_rim:
            if min(zs) < tol:
                external.append(edge)
        else:
            internal.append(edge)
    return external, internal


def _bottom_outer_edges(shape, W, D, tol=0.05):
    result = []
    for edge in shape.Edges:
        zvals = [v.Z for v in edge.Vertexes]
        if not all(abs(z) < tol for z in zvals):
            continue
        mid = edge.CenterOfMass
        if (mid.x < tol or abs(mid.x - W) < tol or
                mid.y < tol or abs(mid.y - D) < tol):
            result.append(edge)
    return result


def _compartment_base_edges(shape, W, D, ft, tol=0.05):
    result = []
    for edge in shape.Edges:
        zvals = [v.Z for v in edge.Vertexes]
        if not all(abs(z - ft) < tol for z in zvals):
            continue
        mid    = edge.CenterOfMass
        on_rim = (mid.x < tol or abs(mid.x - W) < tol or
                  mid.y < tol or abs(mid.y - D) < tol)
        if not on_rim:
            result.append(edge)
    return result


def _apply_vertical_progressive(shape, r, W, D, label):
    _, int_v = _classify_vertical_edges(shape, W, D)
    if not int_v:
        return shape
    try:
        shape = shape.makeFillet(r, int_v)
        FreeCAD.Console.PrintMessage(f"  {label} r={r} on {len(int_v)} edges.\n")
        return shape
    except Exception:
        pass
    total_ok = 0
    while True:
        _, int_v = _classify_vertical_edges(shape, W, D)
        if not int_v:
            break
        any_ok = False
        for edge in int_v:
            try:
                shape    = shape.makeFillet(r, [edge])
                total_ok += 1
                any_ok   = True
                break
            except Exception:
                continue
        if not any_ok:
            break
    if total_ok:
        FreeCAD.Console.PrintMessage(
            f"  {label} r={r}: {total_ok} edge(s) applied (edge-by-edge).\n")
    else:
        FreeCAD.Console.PrintWarning(f"  {label} skipped.\n")
    return shape


def apply_fillets(shape, tray_cfg):
    """
    Apply fillets/chamfers per tray's 'fillet' block:
      external       — outer vertical corner edges
      internal       — inner vertical edges (divider corners)
      base           — compartment floor edges (done in build_tray)
      base_type      — "fillet" or "chamfer"
      bottom_chamfer — outer bottom edges
    """
    fillet_cfg = tray_cfg.get("fillet")
    if not fillet_cfg:
        return shape

    W   = tray_cfg["width"]
    D   = tray_cfg["depth"]

    r_ext = float(fillet_cfg.get("external",       0.0))
    r_bot = float(fillet_cfg.get("bottom_chamfer", 0.0))
    r_int = float(fillet_cfg.get("internal",       0.0))

    if r_ext > 0:
        ext_v, _ = _classify_vertical_edges(shape, W, D)
        if ext_v:
            try:
                shape = shape.makeFillet(r_ext, ext_v)
                FreeCAD.Console.PrintMessage(
                    f"  External fillet r={r_ext} on {len(ext_v)} edges.\n")
            except Exception:
                ok = 0
                for edge in ext_v:
                    try:
                        shape = shape.makeFillet(r_ext, [edge])
                        ok += 1
                    except Exception:
                        pass
                if ok:
                    FreeCAD.Console.PrintMessage(
                        f"  External fillet r={r_ext}: {ok} edge(s) (fallback).\n")
                else:
                    FreeCAD.Console.PrintWarning("  External fillet skipped.\n")

    if r_bot > 0:
        ext_bot = _bottom_outer_edges(shape, W, D)
        if ext_bot:
            try:
                shape = shape.makeChamfer(r_bot, ext_bot)
                FreeCAD.Console.PrintMessage(
                    f"  Bottom chamfer r={r_bot} on {len(ext_bot)} edges.\n")
            except Exception:
                ok = 0
                for edge in ext_bot:
                    try:
                        shape = shape.makeChamfer(r_bot, [edge])
                        ok += 1
                    except Exception:
                        pass
                if ok:
                    FreeCAD.Console.PrintMessage(
                        f"  Bottom chamfer r={r_bot}: {ok} edge(s) (fallback).\n")
                else:
                    FreeCAD.Console.PrintWarning("  Bottom chamfer skipped.\n")

    if r_int > 0:
        shape = _apply_vertical_progressive(shape, r_int, W, D, "Internal fillet")

    return shape


# ── Export ─────────────────────────────────────────────────────────────────────

def export_stl(shape, filepath):
    mesh = MeshPart.meshFromShape(
        Shape=shape,
        LinearDeflection=0.1,
        AngularDeflection=0.0873,
        Relative=False,
    )
    mesh.write(filepath)


# ── View arrangement ───────────────────────────────────────────────────────────

def arrange_objects(doc, built_trays, gap=20.0):
    """
    Position trays side by side along X with the given gap between them.
    """
    x_offset = 0.0
    for name, tray_cfg in built_trays:
        obj = doc.getObject(name)
        if obj is None:
            continue
        obj.Placement = FreeCAD.Placement(
            FreeCAD.Vector(x_offset, 0.0, 0),
            FreeCAD.Rotation()
        )
        x_offset += tray_cfg["width"] + gap


# ── Main (standalone JSON mode) ────────────────────────────────────────────────

def main():
    json_path = pick_json_file()
    if not json_path:
        FreeCAD.Console.PrintMessage("No file selected — aborted.\n")
        return

    try:
        cfg = load_config(json_path)
    except Exception as e:
        FreeCAD.Console.PrintError(f"Failed to parse JSON: {e}\n")
        return

    out_dir  = cfg.get("output_dir", os.path.dirname(json_path))
    doc_name = cfg.get("document_name", "BoardGameInsert")
    defaults = cfg.get("defaults", {})
    box_h    = cfg.get("box_height", 60.0)

    os.makedirs(out_dir, exist_ok=True)
    doc         = FreeCAD.newDocument(doc_name)
    built_trays = []

    layout_root = resolve_layout(cfg)
    trays       = collect_trays_from_layout(layout_root)

    if not trays:
        FreeCAD.Console.PrintMessage("No trays found in layout.\n")
        return

    for node, tray_cfg in trays:
        name = tray_cfg.get("name", "Tray")
        FreeCAD.Console.PrintMessage(f"Building '{name}'...\n")
        merge_defaults(tray_cfg, defaults)

        wall_t  = tray_cfg.get("wall_thickness", defaults.get("wall_thickness", 2.0))
        inner_w = max(node.w - 2 * wall_t, 1.0)
        inner_d = max(node.d - 2 * wall_t, 1.0)
        resolved_comps = resolve_tray_layout(tray_cfg, inner_w, inner_d, defaults)

        try:
            shape = build_tray(tray_cfg, resolved_comps, box_h, defaults)
            shape = apply_fillets(shape, tray_cfg)
        except Exception as e:
            FreeCAD.Console.PrintError(f"  FAILED: {e}\n")
            continue

        obj       = doc.addObject("Part::Feature", name)
        obj.Shape = shape
        tray_cfg["x_pos"] = node.x
        tray_cfg["y_pos"] = node.y
        built_trays.append((obj.Name, tray_cfg))

        stl_path = os.path.join(out_dir, f"{name}.stl")
        export_stl(shape, stl_path)
        FreeCAD.Console.PrintMessage(f"  → STL: {stl_path}\n")

    arrange_objects(doc, built_trays, gap=0.0)

    fcstd_path = os.path.join(out_dir, f"{doc_name}.FCStd")
    doc.saveAs(fcstd_path)
    doc.recompute()
    FreeCADGui.ActiveDocument.ActiveView.fitAll()
    FreeCAD.Console.PrintMessage(f"Saved: {fcstd_path}\nDone!\n")


# Run only when executed directly as a macro
if __name__ not in ("board_game_insert", "builtins"):
    main()
