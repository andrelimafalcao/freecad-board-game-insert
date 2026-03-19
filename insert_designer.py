"""
Board Game Insert Designer — FreeCAD Macro
Canvas-first GUI for creating board game insert configurations.

New model: layout tree with split nodes and tray-leaf nodes.
  No "areas" — tray leaf nodes ARE the layout leaves.
  Tray sizes derived from comp_layout trees.

Layout:
  Top    — toolbar
  Left   — canvas (box + trays + compartments)
  Right  — Properties panel

Run from FreeCAD: Macro > Macros > Execute
Requires board_game_insert.py in the same folder.
"""

import os
import sys
import json
import copy

import FreeCAD
import FreeCADGui

from PySide2 import QtWidgets, QtCore, QtGui
from PySide2.QtCore import Qt


# ── Icons ─────────────────────────────────────────────────────────────────────

try:
    _ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
except NameError:
    _ICON_DIR = None

def _load_icon(name):
    if _ICON_DIR is None:
        return QtGui.QIcon()
    path = os.path.join(_ICON_DIR, name + ".svg")
    return QtGui.QIcon(path) if os.path.isfile(path) else QtGui.QIcon()


# ── Import core generator ─────────────────────────────────────────────────────

def _import_generator():
    macro_dir = ""
    if "__file__" in dir():
        macro_dir = os.path.dirname(os.path.abspath(__file__))
    if not macro_dir:
        macro_dir = FreeCAD.getUserMacroDir(True)
    if macro_dir and macro_dir not in sys.path:
        sys.path.insert(0, macro_dir)
    try:
        import importlib
        import board_game_insert as gen
        importlib.reload(gen)
        return gen
    except ImportError as e:
        FreeCAD.Console.PrintWarning(f"Cannot import board_game_insert: {e}\n")
        return None


# ── Selection type constants ──────────────────────────────────────────────────

SEL_BOX  = "box"
SEL_TRAY = "tray"
SEL_COMP = "comp"

PANEL = {SEL_BOX: 0, SEL_TRAY: 1, SEL_COMP: 2}


# ── Colour palette for trays ──────────────────────────────────────────────────

_TRAY_PALETTE = [
    QtGui.QColor(100, 149, 237),
    QtGui.QColor( 80, 200, 120),
    QtGui.QColor(255, 165,   0),
    QtGui.QColor(200, 130, 220),
    QtGui.QColor( 70, 200, 210),
    QtGui.QColor(240, 180,  60),
    QtGui.QColor(230, 100, 130),
    QtGui.QColor(140, 200,  90),
]


# ── Helper widgets ────────────────────────────────────────────────────────────

def _dspin(min_=0.0, max_=9999.0, decimals=1, suffix=" mm", step=1.0):
    w = QtWidgets.QDoubleSpinBox()
    w.setRange(min_, max_)
    w.setDecimals(decimals)
    w.setSuffix(suffix)
    w.setSingleStep(step)
    return w


def _hbox(*widgets):
    w = QtWidgets.QWidget()
    lay = QtWidgets.QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(4)
    for wgt in widgets:
        lay.addWidget(wgt)
    lay.addStretch()
    return w


def _section_label(text):
    lbl = QtWidgets.QLabel(f"  {text}")
    lbl.setStyleSheet(
        "color: #888; font-size: 10px; font-weight: bold; "
        "border-bottom: 1px solid #ccc; padding-bottom: 2px; margin-top: 6px;"
    )
    return lbl


def _scroll_form():
    inner  = QtWidgets.QWidget()
    form   = QtWidgets.QFormLayout(inner)
    form.setLabelAlignment(Qt.AlignRight)
    form.setFieldGrowthPolicy(QtWidgets.QFormLayout.ExpandingFieldsGrow)
    form.setContentsMargins(12, 8, 12, 8)
    form.setSpacing(6)
    scroll = QtWidgets.QScrollArea()
    scroll.setWidget(inner)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
    return scroll, form


# ── Layout tree helpers ───────────────────────────────────────────────────────

def _find_tray_parent(layout_node, target_tray):
    """
    Walk config layout tree. Return (parent_node, child_index) for the child
    containing `target_tray`, or None if not found.
    parent_node is the split node in config (dict with "split"/"children").
    """
    children = layout_node.get("children") or []
    for i, child in enumerate(children):
        if "tray" in child and child["tray"] is target_tray:
            return layout_node, i
        if "split" in child:
            result = _find_tray_parent(child, target_tray)
            if result:
                return result
    return None


def _find_comp_parent(comp_node, target_comp):
    """
    Walk comp_layout tree. Return (parent_node, child_index) or None.
    parent_node is a split node in comp_layout.
    """
    children = comp_node.get("children") or []
    for i, child in enumerate(children):
        if "comp" in child and child["comp"] is target_comp:
            return comp_node, i
        if "split" in child:
            result = _find_comp_parent(child, target_comp)
            if result:
                return result
    return None


def _find_tray_for_comp(layout_node, target_comp):
    """Find the tray dict that owns target_comp somewhere in its comp_layout."""
    if "tray" in layout_node:
        tray = layout_node["tray"]
        cl   = tray.get("comp_layout", {})
        if _comp_tree_contains(cl, target_comp):
            return tray
    for child in (layout_node.get("children") or []):
        result = _find_tray_for_comp(child, target_comp)
        if result:
            return result
    return None


def _comp_tree_contains(comp_node, target_comp):
    if "comp" in comp_node and comp_node["comp"] is target_comp:
        return True
    for child in (comp_node.get("children") or []):
        if _comp_tree_contains(child, target_comp):
            return True
    return False


def _collect_layout_trays(layout_node):
    """Return list of tray dicts from the config layout tree (leaves only)."""
    if "tray" in layout_node:
        return [layout_node["tray"]]
    result = []
    for child in (layout_node.get("children") or []):
        result.extend(_collect_layout_trays(child))
    return result


def _collect_comps(comp_node, result=None):
    """Return list of comp dicts (leaves only)."""
    if result is None:
        result = []
    if "comp" in comp_node:
        result.append(comp_node["comp"])
    for child in (comp_node.get("children") or []):
        _collect_comps(child, result)
    return result


def _tray_is_flexible(tray, defs, gen=None):
    """
    Return True if tray has at least one flexible comp in V or H direction.
    Flexible means tray fills its allocated slot.
    """
    if gen is None:
        try:
            import board_game_insert as gen
        except ImportError:
            return True   # assume flexible if backend unavailable
    div_t = tray.get("div_thickness") or defs.get("div_thickness", 1.5)
    cl    = tray.get("comp_layout", {"comp": {}})
    fw    = gen._comp_tree_fixed_size(cl, "V", div_t)
    fd    = gen._comp_tree_fixed_size(cl, "H", div_t)
    return fw is None or fd is None


# ── Layout Canvas ─────────────────────────────────────────────────────────────

class LayoutCanvas(QtWidgets.QWidget):
    """
    Unified 2D top-down view: box → trays (from layout tree) → compartments.
    Click to select. Drag box-level dividers to adjust flex_weight.
    """
    selection_changed = QtCore.Signal(str, object)  # (sel_type, data_dict)
    divider_released  = QtCore.Signal()

    _MARGIN       = 28
    _DIVIDER_GRAB = 5

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config         = {}
        self._gen           = None      # set by owner after import
        self._selection     = None      # (sel_type, data_dict)
        self._hit_list      = []
        self._comp_tray_map = {}        # id(src_comp) -> tray dict
        self._dividers      = []        # [(config_split_node, child_idx, "V"|"H", split_mm)]
        self._drag_div  = None      # (config_split_node, child_idx, "V"|"H")
        self._drag_start_mm = 0.0
        self._tray_index    = 0

        self.setMinimumSize(300, 200)
        self.setMouseTracking(True)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Expanding,
        )

    # ── coordinate helpers ────────────────────────────────────────────────────

    def _transform(self):
        bw = max(self.config.get("box_width",  300), 1)
        bd = max(self.config.get("box_depth",  250), 1)
        m  = self._MARGIN
        aw = self.width()  - 2 * m
        ah = self.height() - 2 * m
        scale = min(aw / bw, ah / bd)
        ox = m + (aw - bw * scale) / 2
        oy = m + (ah - bd * scale) / 2
        return scale, ox, oy

    def _mm_rect(self, x, y, w, d, scale, ox, oy):
        return QtCore.QRectF(ox + x * scale, oy + y * scale,
                             w * scale, d * scale)

    def _draw_rounded_rect(self, p, rect, r_px, fill, pen):
        r = max(0.0, min(r_px, rect.width() / 2.0, rect.height() / 2.0))
        path = QtGui.QPainterPath()
        path.addRoundedRect(rect, r, r)
        if fill is not None:
            p.fillPath(path, fill)
        if pen is not None:
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)

    def _fillet(self, tray, key):
        tf = (tray or {}).get("fillet") or {}
        if key in tf:
            return float(tf[key])
        df = (self.config.get("defaults") or {}).get("fillet") or {}
        return float(df.get(key, 0.0))

    # ── paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, _event):
        bw    = self.config.get("box_width",  300)
        bd    = self.config.get("box_depth",  250)
        scale, ox, oy = self._transform()

        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.fillRect(self.rect(), QtGui.QColor(45, 45, 48))

        # Box outline
        box_px = QtCore.QRectF(ox, oy, bw * scale, bd * scale)
        p.fillRect(box_px, QtGui.QColor(65, 65, 70))
        sel_box = self._selection and self._selection[0] == SEL_BOX
        p.setPen(QtGui.QPen(
            QtGui.QColor(255, 230, 0) if sel_box else QtGui.QColor(180, 180, 180),
            2.0 if sel_box else 1.5,
        ))
        p.drawRect(box_px)

        # Dimension labels
        p.setPen(QtGui.QColor(130, 130, 130))
        p.setFont(QtGui.QFont("Arial", 8))
        p.drawText(QtCore.QRectF(ox, oy + bd * scale + 4, bw * scale, 14),
                   Qt.AlignHCenter | Qt.AlignTop, f"{bw:.0f} mm")
        p.save()
        p.translate(ox - 16, oy + bd * scale)
        p.rotate(-90)
        p.drawText(QtCore.QRectF(0, 0, bd * scale, 14),
                   Qt.AlignHCenter | Qt.AlignTop, f"{bd:.0f} mm")
        p.restore()

        # Margin guide
        m = self.config.get("margin", 0.0)
        if m > 0.5:
            margin_px = QtCore.QRectF(
                ox + m * scale, oy + m * scale,
                (bw - 2*m) * scale, (bd - 2*m) * scale)
            pen_m = QtGui.QPen(QtGui.QColor(100, 100, 80), 1)
            pen_m.setStyle(Qt.DashLine)
            p.setPen(pen_m)
            p.drawRect(margin_px)

        # Reset hit/divider lists
        self._hit_list      = [(SEL_BOX, self.config, box_px)]
        self._dividers      = []
        self._comp_tray_map = {}
        self._tray_index    = 0

        if self._gen and self.config.get("layout"):
            try:
                layout_node = self._gen.resolve_layout(self.config)
                self._draw_layout_node(p, layout_node,
                                       self.config.get("layout"), scale, ox, oy)
            except Exception as e:
                p.setPen(QtGui.QColor(255, 80, 80))
                p.drawText(box_px, Qt.AlignCenter,
                           f"Layout error:\n{e}")

        p.end()

    def _draw_layout_node(self, p, node, config_node, scale, ox, oy):
        """Recursively draw a LayoutNode. config_node is the corresponding config dict."""
        if node.tray is not None:
            self._draw_tray(p, node, scale, ox, oy)
            return

        if node.split and node.children:
            children_cfg = (config_node.get("children") or []) if config_node else []
            for i, child_node in enumerate(node.children):
                child_cfg = children_cfg[i] if i < len(children_cfg) else {}
                self._draw_layout_node(p, child_node, child_cfg, scale, ox, oy)

            # Draw divider lines between children
            pen = QtGui.QPen(QtGui.QColor(120, 120, 120), 1)
            pen.setStyle(Qt.DashLine)
            p.setPen(pen)
            if node.split == "V":
                for i, child in enumerate(node.children[:-1]):
                    px = ox + (child.x + child.w) * scale
                    p.drawLine(QtCore.QPointF(px, oy + node.y * scale),
                               QtCore.QPointF(px, oy + (node.y + node.d) * scale))
                    cn = children_cfg[i] if i < len(children_cfg) else {}
                    # We store the *parent* config_node for drag updates
                    self._dividers.append(
                        (config_node, i, "V", child.x + child.w))
            else:
                for i, child in enumerate(node.children[:-1]):
                    py = oy + (child.y + child.d) * scale
                    p.drawLine(QtCore.QPointF(ox + node.x * scale, py),
                               QtCore.QPointF(ox + (node.x + node.w) * scale, py))
                    self._dividers.append(
                        (config_node, i, "H", child.y + child.d))

    def _draw_tray(self, p, node, scale, ox, oy):
        tray   = node.tray
        defs   = self.config.get("defaults") or {}

        # Tray drawn rect
        tray_px = QtCore.QRectF(
            ox + node.x * scale,
            oy + node.y * scale,
            max(node.w * scale, 1),
            max(node.d * scale, 1),
        )

        sel      = (self._selection and
                    self._selection[0] == SEL_TRAY and
                    self._selection[1] is tray)
        color    = _TRAY_PALETTE[self._tray_index % len(_TRAY_PALETTE)]
        self._tray_index += 1

        # Overflow: red tint
        if node.overflow:
            fill_color  = QtGui.QColor(200, 60, 60, 180)
            border_pen  = QtGui.QPen(QtGui.QColor(255, 80, 80), 1.5)
            border_pen.setStyle(Qt.DashLine)
        elif sel:
            fill_color  = color.lighter(140)
            border_pen  = QtGui.QPen(QtGui.QColor(255, 230, 0), 2)
        else:
            fill_color  = color
            border_pen  = QtGui.QPen(QtGui.QColor(0, 0, 0, 160), 1)

        r_ext_px = self._fillet(tray, "external") * scale
        self._draw_rounded_rect(p, tray_px, r_ext_px, fill_color, border_pen)

        # Tray label
        min_side = min(tray_px.width(), tray_px.height())
        if min_side > 12:
            fs   = max(7, min(10, int(min_side / 5)))
            name = tray.get("name", "Tray")
            dims = f"{node.w:.0f}x{node.d:.0f}"
            text = name if min_side < 30 else f"{name}\n{dims}"
            p.setFont(QtGui.QFont("Arial", fs))
            p.setPen(QtGui.QColor(255, 255, 255))
            p.drawText(tray_px, Qt.AlignCenter | Qt.TextWordWrap, text)

        self._hit_list.append((SEL_TRAY, tray, tray_px))

        # Draw compartments
        wall_t  = tray.get("wall_thickness") or defs.get("wall_thickness", 2.0)
        inner_w = max(node.w - 2 * wall_t, 0.0)
        inner_d = max(node.d - 2 * wall_t, 0.0)
        if inner_w > 0 and inner_d > 0 and self._gen:
            try:
                comps = self._gen.resolve_tray_layout(tray, inner_w, inner_d, defs)
                tray_ox = node.x   # tray outer origin in mm
                tray_oy = node.y
                self._draw_comps(p, comps, tray, tray_ox, tray_oy, scale, ox, oy)
            except Exception:
                pass

    def _draw_comps(self, p, comps, tray, tray_ox, tray_oy, scale, ox, oy):
        """Draw all resolved compartments for a tray."""
        defs    = self.config.get("defaults") or {}
        div_t   = tray.get("div_thickness") or defs.get("div_thickness", 1.5)
        half_dv = div_t / 2.0
        r_int   = self._fillet(tray, "internal") * scale

        for comp in comps:
            # Comp is in outer tray coords; shift to canvas mm
            x_mm = tray_ox + comp["_x"] + half_dv
            y_mm = tray_oy + comp["_y"] + half_dv
            w_mm = max(comp["_w"] - div_t, 0.0)
            d_mm = max(comp["_d"] - div_t, 0.0)
            rect_px = QtCore.QRectF(
                ox + x_mm * scale, oy + y_mm * scale,
                w_mm * scale, d_mm * scale,
            )

            # _src points back to the original comp dict in config
            src_comp = comp.get("_src", comp)
            sel = (self._selection and
                   self._selection[0] == SEL_COMP and
                   self._selection[1] is src_comp)

            if sel:
                fill = QtGui.QColor(255, 230, 0, 80)
                pen  = QtGui.QPen(QtGui.QColor(255, 230, 0), 1.5)
            else:
                fill = QtGui.QColor(255, 255, 255, 20)
                pen  = QtGui.QPen(QtGui.QColor(0, 0, 0, 60), 0.5)
            self._draw_rounded_rect(p, rect_px, r_int, fill, pen)

            # Notch indicator
            notch = comp.get("finger_notch")
            if notch is None:
                notch = defs.get("finger_notch", "None")
            if notch and notch not in ("None", "none"):
                nw_px = min(
                    comp.get("finger_notch_width",
                             defs.get("finger_notch_width", min(w_mm, d_mm) * 0.4)) * scale,
                    rect_px.width() * 0.8, rect_px.height() * 0.8,
                )
                bar = max(5.0, min(10.0, rect_px.width() * 0.15,
                                   rect_px.height() * 0.15))
                nc  = QtGui.QColor(90, 90, 90, 220)
                p.save()
                p.setPen(Qt.NoPen)
                p.setBrush(nc)
                cx_px = rect_px.center().x()
                cy_px = rect_px.center().y()
                if notch == "south":
                    p.drawRect(QtCore.QRectF(cx_px - nw_px/2, rect_px.bottom(), nw_px, bar))
                elif notch == "north":
                    p.drawRect(QtCore.QRectF(cx_px - nw_px/2, rect_px.top() - bar, nw_px, bar))
                elif notch == "west":
                    p.drawRect(QtCore.QRectF(rect_px.left() - bar, cy_px - nw_px/2, bar, nw_px))
                elif notch == "east":
                    p.drawRect(QtCore.QRectF(rect_px.right(), cy_px - nw_px/2, bar, nw_px))
                p.restore()

            # Finger hole indicator
            hole = comp.get("finger_hole")
            if hole is None:
                hole = defs.get("finger_hole", False)
            if hole:
                raw_r  = comp.get("finger_hole_radius",
                                  defs.get("finger_hole_radius", 10.0))
                safe_r = min(raw_r, w_mm / 2.0 - 1.0, d_mm / 2.0 - 1.0)
                if safe_r > 0.5:
                    r_px = safe_r * scale
                    p.save()
                    p.setPen(QtGui.QPen(QtGui.QColor(120, 120, 120, 200), 1.0))
                    p.setBrush(QtGui.QColor(150, 150, 150, 80))
                    p.drawEllipse(rect_px.center(), r_px, r_px)
                    p.restore()

            label = comp.get("label", "")
            if label and rect_px.width() > 20 and rect_px.height() > 10:
                p.setPen(QtGui.QColor(0, 0, 0, 160))
                p.setFont(QtGui.QFont("Arial", 7))
                p.drawText(rect_px, Qt.AlignCenter | Qt.TextWordWrap, label)

            self._comp_tray_map[id(src_comp)] = tray
            self._hit_list.append((SEL_COMP, src_comp, rect_px))

    # ── mouse ─────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        scale, ox, oy = self._transform()
        px, py = event.pos().x(), event.pos().y()

        # Divider grab
        for config_node, child_idx, orient, split_mm in self._dividers:
            if orient == "V":
                spx = ox + split_mm * scale
                if abs(px - spx) <= self._DIVIDER_GRAB:
                    self._drag_div = (config_node, child_idx, orient)
                    self._drag_start_mm = split_mm
                    self.setCursor(Qt.SizeHorCursor)
                    return
            else:
                spy = oy + split_mm * scale
                if abs(py - spy) <= self._DIVIDER_GRAB:
                    self._drag_div = (config_node, child_idx, orient)
                    self._drag_start_mm = split_mm
                    self.setCursor(Qt.SizeVerCursor)
                    return
        self._drag_div = None

        # Hit test (reverse = topmost first)
        for sel_type, data, rect in reversed(self._hit_list):
            if rect.contains(QtCore.QPointF(px, py)):
                self._selection = (sel_type, data)
                self.update()
                self.selection_changed.emit(sel_type, data)
                return

        self._selection = (SEL_BOX, self.config)
        self.update()
        self.selection_changed.emit(SEL_BOX, self.config)

    def mouseMoveEvent(self, event):
        scale, ox, oy = self._transform()
        px, py = event.pos().x(), event.pos().y()

        if self._drag_div is not None:
            config_node, child_idx, orient = self._drag_div
            children = config_node.get("children", [])
            n = len(children)

            # Get current resolved sizes for this split from the layout tree
            if self._gen:
                try:
                    layout = self._gen.resolve_layout(self.config)
                    # Find the matching split node in the resolved tree
                    res_node = self._find_resolved_node(layout, config_node)
                except Exception:
                    res_node = None
            else:
                res_node = None

            if res_node and res_node.children and orient == "V":
                mm_x   = (px - ox) / scale
                avail  = res_node.w
                parent_x = res_node.x
                # Clamp
                mm_x = max(parent_x + 5, min(parent_x + avail - 5, mm_x))
                # Compute new weights: split child_idx and child_idx+1
                # All other children keep current resolved sizes
                sizes = [c.w for c in res_node.children]
                prev_x = parent_x
                for j in range(child_idx):
                    prev_x += sizes[j]
                left_w  = mm_x - prev_x
                right_w = sizes[child_idx] + sizes[child_idx + 1] - left_w
                if left_w > 2 and right_w > 2:
                    new_weights = list(config_node.get("flex_weight")
                                       or [1.0] * n)
                    while len(new_weights) < n:
                        new_weights.append(1.0)
                    new_weights[child_idx]     = round(left_w,  2)
                    new_weights[child_idx + 1] = round(right_w, 2)
                    config_node["flex_weight"] = new_weights

            elif res_node and res_node.children and orient == "H":
                mm_y   = (py - oy) / scale
                avail  = res_node.d
                parent_y = res_node.y
                mm_y = max(parent_y + 5, min(parent_y + avail - 5, mm_y))
                sizes = [c.d for c in res_node.children]
                prev_y = parent_y
                for j in range(child_idx):
                    prev_y += sizes[j]
                top_d    = mm_y - prev_y
                bottom_d = sizes[child_idx] + sizes[child_idx + 1] - top_d
                if top_d > 2 and bottom_d > 2:
                    new_weights = list(config_node.get("flex_weight")
                                       or [1.0] * n)
                    while len(new_weights) < n:
                        new_weights.append(1.0)
                    new_weights[child_idx]     = round(top_d,    2)
                    new_weights[child_idx + 1] = round(bottom_d, 2)
                    config_node["flex_weight"] = new_weights

            self.update()
            return

        # Cursor hints near dividers
        for _, _, orient, split_mm in self._dividers:
            if orient == "V" and abs(px - (ox + split_mm * scale)) <= self._DIVIDER_GRAB:
                self.setCursor(Qt.SizeHorCursor)
                return
            if orient == "H" and abs(py - (oy + split_mm * scale)) <= self._DIVIDER_GRAB:
                self.setCursor(Qt.SizeVerCursor)
                return
        self.setCursor(Qt.ArrowCursor)

    def mouseReleaseEvent(self, event):
        if self._drag_div is not None:
            self.divider_released.emit()
        self._drag_div = None
        self.setCursor(Qt.ArrowCursor)

    def resizeEvent(self, _event):
        self.update()

    # ── helpers ───────────────────────────────────────────────────────────────

    def _find_resolved_node(self, resolved_node, config_node):
        """Find the LayoutNode whose cfg_node is config_node (by identity)."""
        if resolved_node.cfg_node is config_node:
            return resolved_node
        for child_rn in resolved_node.children:
            result = self._find_resolved_node(child_rn, config_node)
            if result:
                return result
        return None

    def refresh(self):
        self.update()

    def set_selection(self, sel_type, data):
        self._selection = (sel_type, data)
        self.update()


# ── Main Dialog ───────────────────────────────────────────────────────────────

class InsertDesigner(QtWidgets.QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Board Game Insert Designer")
        self.setWindowIcon(_load_icon("insert_designer"))
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowMinimizeButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.WindowCloseButtonHint
        )
        self.resize(1100, 750)
        self._loading        = False
        self._gen            = _import_generator()
        self._comp_clipboard = None

        self.config = {
            "document_name": "BoardGameInsert",
            "output_dir":    "",
            "box_width":    300.0,
            "box_depth":    250.0,
            "box_height":    70.0,
            "margin":      2.0,
            "tray_gap": 2.0,
            "defaults": {
                "wall_thickness":     2.0,
                "floor_thickness":    1.0,
                "div_thickness":      1.5,
                "finger_hole":        False,
                "finger_hole_radius": 10.0,
                "finger_notch":       "None",
                "finger_notch_width": 20.0,
                "fillet": {
                    "external":       2.0,
                    "internal":       1.0,
                    "base":           1.5,
                    "base_type":      "fillet",
                    "bottom_chamfer": 1.0,
                },
            },
            "layout": {
                "tray": {
                    "name":        "Tray 1",
                    "comp_layout": {"comp": {}},
                }
            },
        }

        self._selection       = (SEL_BOX, self.config)
        self._undo_stack      = []
        self._redo_stack      = []
        self._edit_snap_taken = False

        self._build_ui()
        self.canvas.set_selection(SEL_BOX, self.config)
        self.stack.setCurrentIndex(PANEL[SEL_BOX])
        self._load_box_panel()
        self._refresh_tree()

    # ── Event overrides ───────────────────────────────────────────────────────

    def keyPressEvent(self, event):
        # Prevent QDialog from activating its default button on Enter/Return,
        # which would reset fields by triggering an unintended button click.
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            return
        super().keyPressEvent(event)

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        root = QtWidgets.QVBoxLayout(self)
        root.setSpacing(4)

        # Toolbar
        tb = QtWidgets.QHBoxLayout()
        tb.setSpacing(2)

        def _icon_btn(icon_name, tooltip, fixed=True):
            b = QtWidgets.QPushButton()
            b.setIcon(_load_icon(icon_name))
            b.setIconSize(QtCore.QSize(16, 16))
            b.setToolTip(tooltip)
            if fixed:
                b.setFixedSize(26, 26)
            return b

        def _tb_sep():
            sep = QtWidgets.QFrame()
            sep.setFrameShape(QtWidgets.QFrame.VLine)
            sep.setFrameShadow(QtWidgets.QFrame.Sunken)
            sep.setFixedWidth(10)
            return sep

        _disabled_style = (
            "QPushButton:disabled { color: #777; border: 1px solid #555; "
            "background-color: #2a2a2a; opacity: 0.4; }"
        )

        # History group
        self.btn_undo = _icon_btn("undo", "Undo  Ctrl+Z")
        self.btn_redo = _icon_btn("redo", "Redo  Ctrl+Y")
        self.btn_undo.setEnabled(False)
        self.btn_redo.setEnabled(False)

        # Split tray group
        self.btn_split_tray_v = _icon_btn("split_tray_v", "Split Tray Vertically")
        self.btn_split_tray_h = _icon_btn("split_tray_h", "Split Tray Horizontally")

        # Split comp / navigate group
        self.btn_split_comp_v = _icon_btn("split_comp_v", "Split Compartment Vertically")
        self.btn_split_comp_h = _icon_btn("split_comp_h", "Split Compartment Horizontally")
        self.btn_select_tray  = _icon_btn("select_tray",  "Select Parent Tray")
        self.btn_select_tray.setEnabled(False)

        # Comp clipboard group
        self.btn_copy_comp  = _icon_btn("copy_comp",  "Copy Compartment Properties")
        self.btn_paste_comp = _icon_btn("paste_comp", "Paste Compartment Properties")
        self.btn_copy_comp.setEnabled(False)
        self.btn_paste_comp.setEnabled(False)

        # Delete group
        self.btn_delete = _icon_btn("delete", "Delete Selected")

        # File / generate group (right side)
        btn_load = _icon_btn("load_json", "Load JSON")
        btn_save = _icon_btn("save_json", "Save JSON")
        btn_gen  = _icon_btn("generate",  "Generate Insert", fixed=False)
        btn_gen.setFixedHeight(26)
        btn_gen.setMinimumWidth(36)

        for _b in [self.btn_undo, self.btn_redo,
                   self.btn_split_tray_v, self.btn_split_tray_h,
                   self.btn_split_comp_v, self.btn_split_comp_h,
                   self.btn_select_tray, self.btn_copy_comp,
                   self.btn_paste_comp, self.btn_delete]:
            _b.setStyleSheet(_disabled_style)

        # Layout: [history] | [split tray] | [split comp | select tray] | [copy/paste] | [delete] <stretch> [load | save] | [gen]
        for w in [self.btn_undo, self.btn_redo, _tb_sep(),
                  self.btn_split_tray_v, self.btn_split_tray_h, _tb_sep(),
                  self.btn_split_comp_v, self.btn_split_comp_h, self.btn_select_tray, _tb_sep(),
                  self.btn_copy_comp, self.btn_paste_comp, _tb_sep(),
                  self.btn_delete]:
            tb.addWidget(w)
        tb.addStretch()
        for w in [btn_load, btn_save, _tb_sep(), btn_gen]:
            tb.addWidget(w)

        self.btn_undo.clicked.connect(self._undo)
        self.btn_redo.clicked.connect(self._redo)
        self.btn_split_tray_v.clicked.connect(lambda: self._split_tray("V"))
        self.btn_split_tray_h.clicked.connect(lambda: self._split_tray("H"))
        self.btn_split_comp_v.clicked.connect(lambda: self._split_comp("V"))
        self.btn_split_comp_h.clicked.connect(lambda: self._split_comp("H"))
        self.btn_select_tray.clicked.connect(self._comp_select_tray)
        self.btn_copy_comp.clicked.connect(self._copy_comp)
        self.btn_paste_comp.clicked.connect(self._paste_comp)
        self.btn_delete.clicked.connect(self._delete_selected)
        btn_load.clicked.connect(self._load_json)
        btn_save.clicked.connect(self._save_json)
        btn_gen.clicked.connect(self._generate)

        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+Z"), self).activated.connect(self._undo)
        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+Y"), self).activated.connect(self._redo)
        QtWidgets.QShortcut(
            QtGui.QKeySequence("Ctrl+Shift+Z"), self).activated.connect(self._redo)

        root.addLayout(tb)

        # Main splitter
        splitter = QtWidgets.QSplitter(Qt.Horizontal)
        root.addWidget(splitter, stretch=1)

        self.canvas = LayoutCanvas()
        self.canvas.config = self.config
        self.canvas._gen   = self._gen
        self.canvas.selection_changed.connect(self._on_selection)
        self.canvas.divider_released.connect(self._snapshot)
        splitter.addWidget(self.canvas)

        # Right side
        right_panel = QtWidgets.QWidget()
        right_panel.setMinimumWidth(280)
        right_panel.setMaximumWidth(420)
        right_layout = QtWidgets.QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.stack = QtWidgets.QStackedWidget()
        self.stack.addWidget(self._panel_box())    # 0
        self.stack.addWidget(self._panel_tray())   # 1
        self.stack.addWidget(self._panel_comp())   # 2
        placeholder = QtWidgets.QLabel("Click something on the canvas.")
        placeholder.setAlignment(Qt.AlignCenter)
        self.stack.addWidget(placeholder)          # 3
        right_layout.addWidget(self.stack)

        # Keep tree widget alive (hidden) so _refresh_tree() calls don't crash
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setAnimated(True)
        self.tree.itemClicked.connect(self._on_tree_click)

        splitter.addWidget(right_panel)
        splitter.setSizes([720, 340])

    # ── Property panels ───────────────────────────────────────────────────────

    def _panel_box(self):
        scroll, f = _scroll_form()

        self.box_doc    = QtWidgets.QLineEdit()
        self.box_dir    = QtWidgets.QLineEdit()
        btn_browse      = QtWidgets.QPushButton("Browse...")
        self.box_w      = _dspin(10, 9999, step=5)
        self.box_d      = _dspin(10, 9999, step=5)
        self.box_h      = _dspin(5,  9999, step=5)
        self.box_margin = _dspin(0, 50, step=0.5)
        self.box_gap    = _dspin(0, 50, step=0.5)

        self.box_def_wall   = _dspin(0.5, 20, step=0.5)
        self.box_def_floor  = _dspin(0.5, 20, step=0.5)
        self.box_def_div    = _dspin(0, 20, step=0.5)
        self.box_def_hole   = QtWidgets.QCheckBox("Enabled by default")
        self.box_def_hole_r = _dspin(1, 100, step=0.5)
        self.box_def_notch  = QtWidgets.QComboBox()
        self.box_def_notch.addItems(["None", "south", "north", "east", "west"])
        self.box_def_notch_w = _dspin(5, 200, step=1)
        self.box_def_f_ext   = _dspin(0, 20, step=0.5)
        self.box_def_f_int   = _dspin(0, 20, step=0.5)
        self.box_def_f_base  = _dspin(0, 20, step=0.5)
        self.box_def_f_base_type = QtWidgets.QComboBox()
        self.box_def_f_base_type.addItems(["fillet", "chamfer"])
        self.box_def_f_bot = _dspin(0, 20, step=0.5)

        dir_row = QtWidgets.QHBoxLayout()
        dir_row.addWidget(self.box_dir)
        dir_row.addWidget(btn_browse)

        f.addRow(_section_label("Document"))
        f.addRow("Name:", self.box_doc)
        f.addRow(_section_label("Box inner space"))
        f.addRow("Width (X):",    self.box_w)
        f.addRow("Depth (Y):",    self.box_d)
        f.addRow("Height (Z):",   self.box_h)
        f.addRow("Margin:",       self.box_margin)
        f.addRow("Tray spacing:", self.box_gap)
        f.addRow(_section_label("Defaults"))
        f.addRow("Wall thickness:",  self.box_def_wall)
        f.addRow("Floor thickness:", self.box_def_floor)
        f.addRow("Div thickness:",   self.box_def_div)
        f.addRow(_section_label("Default finger features"))
        f.addRow("Finger hole:",   self.box_def_hole)
        f.addRow("Hole radius:",   self.box_def_hole_r)
        f.addRow("Finger notch:",  self.box_def_notch)
        f.addRow("Notch width:",   self.box_def_notch_w)
        f.addRow(_section_label("Default fillets  (0 = off)"))
        f.addRow("External:",      self.box_def_f_ext)
        f.addRow("Internal:",      self.box_def_f_int)
        f.addRow("Base:",          self.box_def_f_base)
        f.addRow("Base type:",     self.box_def_f_base_type)
        f.addRow("Bottom chamfer:", self.box_def_f_bot)
        f.addRow(_section_label("Output"))
        f.addRow("Directory:",    dir_row)

        btn_browse.clicked.connect(self._browse_dir)
        self.box_doc.textChanged.connect(lambda v: self._cfg("document_name", v))
        self.box_dir.textChanged.connect(lambda v: self._cfg("output_dir", v))
        self.box_w.valueChanged.connect(
            lambda v: (self._cfg("box_width",  v), self.canvas.refresh()))
        self.box_d.valueChanged.connect(
            lambda v: (self._cfg("box_depth",  v), self.canvas.refresh()))
        self.box_h.valueChanged.connect(lambda v: self._cfg("box_height", v))
        self.box_margin.valueChanged.connect(
            lambda v: (self._cfg("margin", v), self.canvas.refresh()))
        self.box_gap.valueChanged.connect(
            lambda v: (self._cfg("tray_gap", v), self.canvas.refresh()))
        self.box_def_wall.valueChanged.connect(lambda v: self._def("wall_thickness", v))
        self.box_def_floor.valueChanged.connect(lambda v: self._def("floor_thickness", v))
        self.box_def_div.valueChanged.connect(lambda v: self._def("div_thickness", v))
        self.box_def_hole.toggled.connect(lambda v: self._def("finger_hole", v))
        self.box_def_hole_r.valueChanged.connect(lambda v: self._def("finger_hole_radius", v))
        self.box_def_notch.currentTextChanged.connect(lambda v: self._def("finger_notch", v))
        self.box_def_notch_w.valueChanged.connect(lambda v: self._def("finger_notch_width", v))
        self.box_def_f_ext.valueChanged.connect(lambda v: self._def_fillet("external", v))
        self.box_def_f_int.valueChanged.connect(lambda v: self._def_fillet("internal", v))
        self.box_def_f_base.valueChanged.connect(lambda v: self._def_fillet("base", v))
        self.box_def_f_base_type.currentTextChanged.connect(
            lambda v: self._def_fillet("base_type", v))
        self.box_def_f_bot.valueChanged.connect(
            lambda v: self._def_fillet("bottom_chamfer", v))
        return scroll

    def _panel_tray(self):
        scroll, f = _scroll_form()

        self.tr_name       = QtWidgets.QLineEdit()
        self.tr_h          = _dspin(5, 9999)
        self.tr_size_lbl   = QtWidgets.QLabel()
        self.tr_size_lbl.setStyleSheet("color: #666; font-style: italic;")
        self.tr_wall       = _dspin(0.5, 20, step=0.5)
        self.tr_wall_dflt  = QtWidgets.QCheckBox("Use box default")
        self.tr_floor      = _dspin(0.5, 20, step=0.5)
        self.tr_floor_dflt = QtWidgets.QCheckBox("Use box default")
        self.tr_div        = _dspin(0, 20, step=0.5)
        self.tr_div_dflt   = QtWidgets.QCheckBox("Use box default")
        self.tr_f_ext          = _dspin(0, 20, step=0.5)
        self.tr_f_ext_dflt     = QtWidgets.QCheckBox("Use box default")
        self.tr_f_int          = _dspin(0, 20, step=0.5)
        self.tr_f_int_dflt     = QtWidgets.QCheckBox("Use box default")
        self.tr_f_base         = _dspin(0, 20, step=0.5)
        self.tr_f_base_dflt    = QtWidgets.QCheckBox("Use box default")
        self.tr_f_base_type    = QtWidgets.QComboBox()
        self.tr_f_base_type.addItems(["fillet", "chamfer"])
        self.tr_f_base_type_dflt = QtWidgets.QCheckBox("Use box default")
        self.tr_f_bot          = _dspin(0, 20, step=0.5)
        self.tr_f_bot_dflt     = QtWidgets.QCheckBox("Use box default")

        f.addRow(_section_label("Identity"))
        f.addRow("Name:",          self.tr_name)
        f.addRow(_section_label("Dimensions"))
        f.addRow("Height (Z):",    self.tr_h)
        f.addRow("Computed size:", self.tr_size_lbl)
        f.addRow(_section_label("Wall, floor & dividers"))
        f.addRow("Wall thickness:", _hbox(self.tr_wall, self.tr_wall_dflt))
        f.addRow("Floor thickness:", _hbox(self.tr_floor, self.tr_floor_dflt))
        f.addRow("Div thickness:",   _hbox(self.tr_div,   self.tr_div_dflt))
        f.addRow(_section_label("Fillets / chamfers"))
        f.addRow("External:", _hbox(self.tr_f_ext,  self.tr_f_ext_dflt))
        f.addRow("Internal:", _hbox(self.tr_f_int,  self.tr_f_int_dflt))
        f.addRow("Base:",     _hbox(self.tr_f_base, self.tr_f_base_dflt))
        f.addRow("Base type:", _hbox(self.tr_f_base_type, self.tr_f_base_type_dflt))
        f.addRow("Bottom chamfer:", _hbox(self.tr_f_bot, self.tr_f_bot_dflt))

        self.tr_name.textChanged.connect(lambda v: self._tr("name", v))
        self.tr_h.valueChanged.connect(lambda v: self._tr("height", v))
        self.tr_wall.valueChanged.connect(lambda v: self._tr("wall_thickness", v))
        self.tr_wall_dflt.toggled.connect(
            lambda c: self._tr_use_default("wall_thickness", c, self.tr_wall))
        self.tr_floor.valueChanged.connect(lambda v: self._tr("floor_thickness", v))
        self.tr_floor_dflt.toggled.connect(
            lambda c: self._tr_use_default("floor_thickness", c, self.tr_floor))
        self.tr_div.valueChanged.connect(lambda v: self._tr("div_thickness", v))
        self.tr_div_dflt.toggled.connect(
            lambda c: self._tr_use_default("div_thickness", c, self.tr_div))
        self.tr_f_ext.valueChanged.connect(lambda v: self._tr_fillet("external", v))
        self.tr_f_ext_dflt.toggled.connect(
            lambda c: self._tr_use_default("external", c, self.tr_f_ext, fillet_key="external"))
        self.tr_f_int.valueChanged.connect(lambda v: self._tr_fillet("internal", v))
        self.tr_f_int_dflt.toggled.connect(
            lambda c: self._tr_use_default("internal", c, self.tr_f_int, fillet_key="internal"))
        self.tr_f_base.valueChanged.connect(lambda v: self._tr_fillet("base", v))
        self.tr_f_base_dflt.toggled.connect(
            lambda c: self._tr_use_default("base", c, self.tr_f_base, fillet_key="base"))
        self.tr_f_base_type.currentTextChanged.connect(
            lambda v: self._tr_fillet("base_type", v))
        self.tr_f_base_type_dflt.toggled.connect(
            lambda c: self._tr_use_default_combo(
                "base_type", c, self.tr_f_base_type, fillet_key="base_type"))
        self.tr_f_bot.valueChanged.connect(lambda v: self._tr_fillet("bottom_chamfer", v))
        self.tr_f_bot_dflt.toggled.connect(
            lambda c: self._tr_use_default(
                "bottom_chamfer", c, self.tr_f_bot, fillet_key="bottom_chamfer"))
        return scroll

    def _panel_comp(self):
        scroll, f = _scroll_form()

        self.comp_label    = QtWidgets.QLineEdit()
        self.comp_size_lbl = QtWidgets.QLabel()
        self.comp_size_lbl.setStyleSheet("color: #666; font-style: italic;")

        self.comp_cw      = _dspin(1, 9999)
        self.comp_cw_auto = QtWidgets.QCheckBox("Flexible (fill available width)")
        self.comp_cd      = _dspin(1, 9999)
        self.comp_cd_auto = QtWidgets.QCheckBox("Flexible (fill available depth)")

        self.comp_floor      = _dspin(0.1, 50, step=0.5)
        self.comp_floor_auto = QtWidgets.QCheckBox("Use tray default")

        self.comp_hole       = QtWidgets.QCheckBox("Finger hole through floor")
        self.comp_hole_dflt  = QtWidgets.QCheckBox("Use box default")
        self.comp_hole_r     = _dspin(1, 100, step=0.5)
        self.comp_hole_r_dflt = QtWidgets.QCheckBox("Use box default")
        self.comp_notch      = QtWidgets.QComboBox()
        self.comp_notch.addItems(["None", "south", "north", "east", "west"])
        self.comp_notch_dflt  = QtWidgets.QCheckBox("Use box default")
        self.comp_notch_w     = _dspin(5, 200, step=1)
        self.comp_notch_w_dflt = QtWidgets.QCheckBox("Use box default")

        f.addRow(_section_label("Identity"))
        f.addRow("Label:",        self.comp_label)
        f.addRow("Resolved size:", self.comp_size_lbl)
        f.addRow(_section_label("Size  (drives tray size when fixed)"))
        f.addRow("Width:",  self.comp_cw)
        f.addRow("",        self.comp_cw_auto)
        f.addRow("Depth:",  self.comp_cd)
        f.addRow("",        self.comp_cd_auto)
        f.addRow(_section_label("Floor"))
        f.addRow("Floor thickness:", self.comp_floor)
        f.addRow("",                 self.comp_floor_auto)
        f.addRow(_section_label("Finger hole"))
        f.addRow("", _hbox(self.comp_hole, self.comp_hole_dflt))
        f.addRow("Hole radius:", _hbox(self.comp_hole_r, self.comp_hole_r_dflt))
        f.addRow(_section_label("Finger notch  (wall cutout at top)"))
        f.addRow("Notch side:",  _hbox(self.comp_notch, self.comp_notch_dflt))
        f.addRow("Notch width:", _hbox(self.comp_notch_w, self.comp_notch_w_dflt))
        hint = QtWidgets.QLabel(
            "south = front  north = back\nwest = left   east = right")
        hint.setStyleSheet("color: #888; font-size: 10px;")
        f.addRow("", hint)

        self.comp_label.textChanged.connect(lambda v: self._comp("label", v))
        self.comp_cw.valueChanged.connect(
            lambda v: self._comp_size("width", v))
        self.comp_cw_auto.toggled.connect(
            lambda c: self._comp_size_auto("width", c, self.comp_cw))
        self.comp_cd.valueChanged.connect(
            lambda v: self._comp_size("depth", v))
        self.comp_cd_auto.toggled.connect(
            lambda c: self._comp_size_auto("depth", c, self.comp_cd))
        self.comp_floor.valueChanged.connect(lambda v: self._comp("floor_thickness", v))
        self.comp_floor_auto.toggled.connect(self._comp_floor_auto_toggle)
        self.comp_hole.toggled.connect(self._comp_hole_toggle)
        self.comp_hole_dflt.toggled.connect(self._comp_hole_dflt_toggle)
        self.comp_hole_r.valueChanged.connect(lambda v: self._comp("finger_hole_radius", v))
        self.comp_hole_r_dflt.toggled.connect(
            lambda c: self._comp_use_default("finger_hole_radius", c, self.comp_hole_r))
        self.comp_notch.currentTextChanged.connect(self._comp_notch_change)
        self.comp_notch_dflt.toggled.connect(self._comp_notch_dflt_toggle)
        self.comp_notch_w.valueChanged.connect(lambda v: self._comp("finger_notch_width", v))
        self.comp_notch_w_dflt.toggled.connect(
            lambda c: self._comp_use_default("finger_notch_width", c, self.comp_notch_w))
        return scroll

    # ── Selection handler ─────────────────────────────────────────────────────

    def _on_selection(self, sel_type, data):
        self._selection       = (sel_type, data)
        self._edit_snap_taken = False
        self._update_toolbar(sel_type, data)
        idx = PANEL.get(sel_type, 3)
        self.stack.setCurrentIndex(idx)
        self._loading = True
        try:
            if sel_type == SEL_BOX:
                self._load_box_panel()
            elif sel_type == SEL_TRAY:
                self._load_tray_panel(data)
            elif sel_type == SEL_COMP:
                self._load_comp_panel(data)
        finally:
            self._loading = False
        self._sync_tree_selection()

    def _update_toolbar(self, sel_type, data=None):
        defs = self.config.get("defaults") or {}
        is_tray = sel_type == SEL_TRAY
        is_comp = sel_type == SEL_COMP

        # Split Tray: enabled on flexible trays, and on comps (splits the parent tray)
        if is_tray:
            tray_data = data
        elif is_comp and data is not None:
            tray_data = self.canvas._comp_tray_map.get(id(data))
        else:
            tray_data = None
        if tray_data:
            try:
                flexible = _tray_is_flexible(tray_data, defs, self._gen)
            except Exception:
                flexible = False
        else:
            flexible = False
        self.btn_split_tray_v.setEnabled(flexible)
        self.btn_split_tray_h.setEnabled(flexible)
        self.btn_split_comp_v.setEnabled(is_comp)
        self.btn_split_comp_h.setEnabled(is_comp)
        self.btn_select_tray.setEnabled(is_comp)
        self.btn_copy_comp.setEnabled(is_comp)
        self.btn_paste_comp.setEnabled(is_comp and self._comp_clipboard is not None)
        self.btn_delete.setEnabled(is_tray or is_comp)

    # ── Undo / redo ───────────────────────────────────────────────────────────

    def _snapshot(self):
        self._undo_stack.append(copy.deepcopy(self.config))
        self._redo_stack.clear()
        if len(self._undo_stack) > 100:
            self._undo_stack.pop(0)
        self._edit_snap_taken = True
        self._update_undo_redo_btns()

    def _snapshot_if_new_edit(self):
        if not self._edit_snap_taken and not self._loading:
            self._snapshot()

    def _restore_config(self, cfg):
        self.config.clear()
        self.config.update(cfg)
        self.canvas.config = self.config
        self.canvas.set_selection(SEL_BOX, self.config)
        self._on_selection(SEL_BOX, self.config)
        self.canvas.refresh()
        self._refresh_tree()

    def _undo(self):
        if not self._undo_stack:
            return
        self._redo_stack.append(copy.deepcopy(self.config))
        self._restore_config(self._undo_stack.pop())
        self._update_undo_redo_btns()

    def _redo(self):
        if not self._redo_stack:
            return
        self._undo_stack.append(copy.deepcopy(self.config))
        self._restore_config(self._redo_stack.pop())
        self._update_undo_redo_btns()

    def _update_undo_redo_btns(self):
        self.btn_undo.setEnabled(bool(self._undo_stack))
        self.btn_redo.setEnabled(bool(self._redo_stack))
        n_u = len(self._undo_stack)
        n_r = len(self._redo_stack)
        self.btn_undo.setToolTip(f"Undo  Ctrl+Z  ({n_u} step{'s' if n_u != 1 else ''})")
        self.btn_redo.setToolTip(f"Redo  Ctrl+Y  ({n_r} step{'s' if n_r != 1 else ''})")

    # ── Tree view ─────────────────────────────────────────────────────────────

    def _refresh_tree(self):
        self.tree.clear()
        root_item = QtWidgets.QTreeWidgetItem(self.tree, ["Box"])
        root_item.setData(0, Qt.UserRole, (SEL_BOX, self.config))
        root_item.setExpanded(True)
        layout = self.config.get("layout")
        if layout:
            self._mk_layout_item(root_item, layout)
        self.tree.expandAll()
        self._sync_tree_selection()

    def _mk_layout_item(self, parent_item, node):
        """Recursively build tree items for the layout tree."""
        if "tray" in node:
            tray = node["tray"]
            name = tray.get("name", "Tray")
            item = QtWidgets.QTreeWidgetItem(parent_item, [f"Tray: {name}"])
            item.setData(0, Qt.UserRole, (SEL_TRAY, tray))
            item.setExpanded(True)
            cl = tray.get("comp_layout")
            if cl:
                self._mk_comp_item(item, cl)
            return

        if "split" in node:
            split    = node["split"]
            children = node.get("children") or []
            label    = f"[{split} split, {len(children)} parts]"
            item     = QtWidgets.QTreeWidgetItem(parent_item, [label])
            item.setData(0, Qt.UserRole, (SEL_BOX, self.config))  # split nodes → select box
            item.setExpanded(True)
            for child in children:
                self._mk_layout_item(item, child)

    def _mk_comp_item(self, parent_item, comp_node):
        """Recursively build tree items for a comp_layout tree."""
        if "comp" in comp_node:
            comp  = comp_node["comp"]
            label = comp.get("label", "(compartment)")
            item  = QtWidgets.QTreeWidgetItem(parent_item, [label])
            item.setData(0, Qt.UserRole, (SEL_COMP, comp))
            return

        if "split" in comp_node:
            split    = comp_node["split"]
            children = comp_node.get("children") or []
            label    = f"[{split} split]"
            item     = QtWidgets.QTreeWidgetItem(parent_item, [label])
            item.setExpanded(True)
            for child in children:
                self._mk_comp_item(item, child)

    def _sync_tree_selection(self):
        if not self._selection:
            return
        sel_type, sel_data = self._selection

        def find_item(item):
            d = item.data(0, Qt.UserRole)
            if d and d[0] == sel_type and d[1] is sel_data:
                return item
            for i in range(item.childCount()):
                result = find_item(item.child(i))
                if result:
                    return result
            return None

        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            found = find_item(root.child(i))
            if found:
                self.tree.blockSignals(True)
                self.tree.setCurrentItem(found)
                self.tree.blockSignals(False)
                return

    def _on_tree_click(self, item, _col):
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        sel_type, sel_data = data
        self.canvas.set_selection(sel_type, sel_data)
        self._on_selection(sel_type, sel_data)

    # ── Panel loaders ─────────────────────────────────────────────────────────

    def _load_box_panel(self):
        cfg = self.config
        self.box_doc.setText(cfg.get("document_name", ""))
        self.box_dir.setText(cfg.get("output_dir", ""))
        self.box_w.setValue(cfg.get("box_width",  300.0))
        self.box_d.setValue(cfg.get("box_depth",  250.0))
        self.box_h.setValue(cfg.get("box_height",  70.0))
        self.box_margin.setValue(cfg.get("margin", 2.0))
        self.box_gap.setValue(cfg.get("tray_gap", 2.0))
        defs = cfg.get("defaults", {})
        self.box_def_wall.setValue(defs.get("wall_thickness", 2.0))
        self.box_def_floor.setValue(defs.get("floor_thickness", 1.0))
        self.box_def_div.setValue(defs.get("div_thickness", 1.5))
        self.box_def_hole.setChecked(bool(defs.get("finger_hole", False)))
        self.box_def_hole_r.setValue(defs.get("finger_hole_radius", 10.0))
        self.box_def_notch.setCurrentText(defs.get("finger_notch", "None"))
        self.box_def_notch_w.setValue(defs.get("finger_notch_width", 20.0))
        df = defs.get("fillet", {})
        self.box_def_f_ext.setValue(df.get("external", 2.0))
        self.box_def_f_int.setValue(df.get("internal", 1.0))
        self.box_def_f_base.setValue(df.get("base", 1.5))
        self.box_def_f_base_type.setCurrentText(df.get("base_type", "fillet"))
        self.box_def_f_bot.setValue(df.get("bottom_chamfer", 1.0))

    def _load_tray_panel(self, tray):
        defs   = self.config.get("defaults", {})
        fillet = tray.get("fillet", {})
        df     = defs.get("fillet", {})

        self.tr_name.setText(tray.get("name", ""))
        self.tr_h.setValue(tray.get("height", self.config.get("box_height", 70.0)))

        # Computed size
        if self._gen:
            try:
                layout = self._gen.resolve_layout(self.config)
                trays  = self._gen.collect_trays_from_layout(layout)
                node   = next((n for n, t in trays if t is tray), None)
                if node:
                    self.tr_size_lbl.setText(
                        f"{node.w:.1f} × {node.d:.1f} mm"
                        + (" ⚠ overflow" if node.overflow else ""))
                else:
                    self.tr_size_lbl.setText("—")
            except Exception:
                self.tr_size_lbl.setText("—")
        else:
            self.tr_size_lbl.setText("—")

        def _load_spinbox_default(spin, dflt_cb, key, default_val):
            use_dflt = key not in tray
            dflt_cb.setChecked(use_dflt)
            spin.setEnabled(not use_dflt)
            spin.setValue(float(tray.get(key, default_val)))

        _load_spinbox_default(self.tr_wall,  self.tr_wall_dflt,  "wall_thickness",
                               defs.get("wall_thickness", 2.0))
        _load_spinbox_default(self.tr_floor, self.tr_floor_dflt, "floor_thickness",
                               defs.get("floor_thickness", 1.0))
        _load_spinbox_default(self.tr_div,   self.tr_div_dflt,   "div_thickness",
                               defs.get("div_thickness", 1.5))

        def _load_fillet_default(spin, dflt_cb, key, default_val):
            use_dflt = key not in fillet
            dflt_cb.setChecked(use_dflt)
            spin.setEnabled(not use_dflt)
            spin.setValue(float(fillet.get(key, default_val)))

        _load_fillet_default(self.tr_f_ext,  self.tr_f_ext_dflt,  "external",
                              df.get("external", 2.0))
        _load_fillet_default(self.tr_f_int,  self.tr_f_int_dflt,  "internal",
                              df.get("internal", 1.0))
        _load_fillet_default(self.tr_f_base, self.tr_f_base_dflt, "base",
                              df.get("base", 1.5))
        _load_fillet_default(self.tr_f_bot,  self.tr_f_bot_dflt,  "bottom_chamfer",
                              df.get("bottom_chamfer", 1.0))

        use_base_type_dflt = "base_type" not in fillet
        self.tr_f_base_type_dflt.setChecked(use_base_type_dflt)
        self.tr_f_base_type.setEnabled(not use_base_type_dflt)
        self.tr_f_base_type.setCurrentText(
            fillet.get("base_type", df.get("base_type", "fillet")))

    def _load_comp_panel(self, comp):
        self.comp_label.setText(comp.get("label", ""))

        cw = comp.get("width")
        self.comp_cw_auto.setChecked(cw is None)
        self.comp_cw.setEnabled(cw is not None)
        self.comp_cw.setValue(cw if cw is not None else 10.0)

        cd = comp.get("depth")
        self.comp_cd_auto.setChecked(cd is None)
        self.comp_cd.setEnabled(cd is not None)
        self.comp_cd.setValue(cd if cd is not None else 10.0)

        cf = comp.get("floor_thickness")
        self.comp_floor_auto.setChecked(cf is None)
        self.comp_floor.setEnabled(cf is not None)
        self.comp_floor.setValue(cf if cf is not None else 1.0)

        defs = self.config.get("defaults", {})

        hole_dflt = "finger_hole" not in comp
        self.comp_hole_dflt.setChecked(hole_dflt)
        self.comp_hole.setEnabled(not hole_dflt)
        self.comp_hole.setChecked(bool(comp.get("finger_hole",
                                                 defs.get("finger_hole", False))))

        hole_r_dflt = "finger_hole_radius" not in comp
        self.comp_hole_r_dflt.setChecked(hole_r_dflt)
        self.comp_hole_r.setEnabled(not hole_r_dflt)
        self.comp_hole_r.setValue(comp.get("finger_hole_radius",
                                           defs.get("finger_hole_radius", 10.0)))

        notch_dflt = "finger_notch" not in comp
        self.comp_notch_dflt.setChecked(notch_dflt)
        self.comp_notch.setEnabled(not notch_dflt)
        notch = comp.get("finger_notch") or defs.get("finger_notch") or "None"
        self.comp_notch.setCurrentText(notch)

        notch_w_dflt = "finger_notch_width" not in comp
        self.comp_notch_w_dflt.setChecked(notch_w_dflt)
        self.comp_notch_w.setEnabled(not notch_w_dflt)
        self.comp_notch_w.setValue(comp.get("finger_notch_width",
                                            defs.get("finger_notch_width", 20.0)))
        self.comp_size_lbl.setText("—")

    # ── Config write helpers ──────────────────────────────────────────────────

    def _cfg(self, key, val):
        if not self._loading:
            self._snapshot_if_new_edit()
            self.config[key] = val

    def _def(self, key, val):
        if not self._loading:
            self._snapshot_if_new_edit()
            self.config.setdefault("defaults", {})[key] = val
            self.canvas.refresh()

    def _def_fillet(self, key, val):
        if not self._loading:
            self._snapshot_if_new_edit()
            self.config.setdefault("defaults", {}).setdefault("fillet", {})[key] = val
            self.canvas.refresh()

    def _current_tray(self):
        if self._selection and self._selection[0] == SEL_TRAY:
            return self._selection[1]
        return None

    def _current_comp(self):
        if self._selection and self._selection[0] == SEL_COMP:
            return self._selection[1]
        return None

    def _comp_select_tray(self):
        comp = self._current_comp()
        if comp is None:
            return
        tray = self.canvas._comp_tray_map.get(id(comp))
        if tray is None:
            return
        self.canvas.set_selection(SEL_TRAY, tray)
        self._on_selection(SEL_TRAY, tray)

    _COMP_COPY_KEYS = (
        "width", "depth", "floor_thickness",
        "finger_hole", "finger_hole_radius",
        "finger_notch", "finger_notch_width",
    )

    def _copy_comp(self):
        comp = self._current_comp()
        if comp is None:
            return
        self._comp_clipboard = {k: comp[k] for k in self._COMP_COPY_KEYS if k in comp}
        self._update_toolbar(SEL_COMP, comp)   # refresh Paste enable state

    def _paste_comp(self):
        comp = self._current_comp()
        if comp is None or not self._comp_clipboard:
            return
        self._snapshot()
        for k in self._COMP_COPY_KEYS:
            comp.pop(k, None)
        comp.update({k: v for k, v in self._comp_clipboard.items()
                     if k != "label"})
        self._on_selection(SEL_COMP, comp)
        self.canvas.refresh()

    def _tr(self, key, val):
        if self._loading:
            return
        tray = self._current_tray()
        if tray is not None:
            self._snapshot_if_new_edit()
            tray[key] = val
            self.canvas.refresh()

    def _tr_fillet(self, key, val):
        if self._loading:
            return
        tray = self._current_tray()
        if tray is not None:
            self._snapshot_if_new_edit()
            tray.setdefault("fillet", {})[key] = val

    def _tr_use_default(self, key, checked, spin, fillet_key=None):
        if self._loading:
            return
        tray = self._current_tray()
        if tray is None:
            return
        defs = self.config.get("defaults", {})
        self._snapshot_if_new_edit()
        if checked:
            if fillet_key:
                tray.get("fillet", {}).pop(fillet_key, None)
                default_val = defs.get("fillet", {}).get(fillet_key)
            else:
                tray.pop(key, None)
                default_val = defs.get(key)
            if default_val is not None and not isinstance(default_val, str):
                self._loading = True
                try:
                    spin.setValue(float(default_val))
                finally:
                    self._loading = False
            spin.setEnabled(False)
        else:
            spin.setEnabled(True)
            if fillet_key:
                tray.setdefault("fillet", {})[fillet_key] = spin.value()
            else:
                tray[key] = spin.value()
        self.canvas.refresh()

    def _tr_use_default_combo(self, key, checked, combo, fillet_key=None):
        if self._loading:
            return
        tray = self._current_tray()
        if tray is None:
            return
        defs = self.config.get("defaults", {})
        self._snapshot_if_new_edit()
        if checked:
            if fillet_key:
                tray.get("fillet", {}).pop(fillet_key, None)
                default_val = defs.get("fillet", {}).get(fillet_key)
            else:
                tray.pop(key, None)
                default_val = defs.get(key)
            if default_val is not None:
                self._loading = True
                try:
                    combo.setCurrentText(str(default_val))
                finally:
                    self._loading = False
            combo.setEnabled(False)
        else:
            combo.setEnabled(True)
            if fillet_key:
                tray.setdefault("fillet", {})[fillet_key] = combo.currentText()
            else:
                tray[key] = combo.currentText()

    def _comp(self, key, val):
        if self._loading:
            return
        comp = self._current_comp()
        if comp is not None:
            self._snapshot_if_new_edit()
            if val == "" or val is None:
                comp.pop(key, None)
            else:
                comp[key] = val
            self.canvas.refresh()

    def _comp_size(self, key, val):
        """Write width or depth only when not in auto mode."""
        if self._loading:
            return
        comp = self._current_comp()
        if comp is not None and comp.get(key) is not None:
            self._snapshot_if_new_edit()
            comp[key] = val
            self.canvas.refresh()

    def _comp_size_auto(self, key, checked, spin):
        if self._loading:
            return
        comp = self._current_comp()
        if comp is None:
            return
        self._snapshot_if_new_edit()
        if checked:
            comp.pop(key, None)
            spin.setEnabled(False)
        else:
            val = spin.value() or 10.0
            comp[key] = val
            spin.setEnabled(True)
        self.canvas.refresh()

    def _comp_floor_auto_toggle(self, checked):
        if self._loading:
            return
        comp = self._current_comp()
        if comp is None:
            return
        self._snapshot_if_new_edit()
        if checked:
            comp.pop("floor_thickness", None)
            self.comp_floor.setEnabled(False)
        else:
            comp["floor_thickness"] = self.comp_floor.value()
            self.comp_floor.setEnabled(True)
        self.canvas.refresh()

    def _comp_hole_toggle(self, checked):
        if self._loading:
            return
        comp = self._current_comp()
        if comp is not None:
            self._snapshot_if_new_edit()
            comp["finger_hole"] = checked
            self.canvas.refresh()

    def _comp_hole_dflt_toggle(self, checked):
        if self._loading:
            return
        comp = self._current_comp()
        if comp is None:
            return
        defs = self.config.get("defaults", {})
        self._snapshot_if_new_edit()
        if checked:
            comp.pop("finger_hole", None)
            self._loading = True
            try:
                self.comp_hole.setChecked(bool(defs.get("finger_hole", False)))
            finally:
                self._loading = False
            self.comp_hole.setEnabled(False)
        else:
            self.comp_hole.setEnabled(True)
            comp["finger_hole"] = self.comp_hole.isChecked()
        self.canvas.refresh()

    def _comp_notch_change(self, text):
        if self._loading:
            return
        comp = self._current_comp()
        if comp is not None:
            self._snapshot_if_new_edit()
            comp["finger_notch"] = text
            self.canvas.refresh()

    def _comp_notch_dflt_toggle(self, checked):
        if self._loading:
            return
        comp = self._current_comp()
        if comp is None:
            return
        defs = self.config.get("defaults", {})
        self._snapshot_if_new_edit()
        if checked:
            comp.pop("finger_notch", None)
            self._loading = True
            try:
                self.comp_notch.setCurrentText(
                    str(defs.get("finger_notch", "None")))
            finally:
                self._loading = False
            self.comp_notch.setEnabled(False)
        else:
            self.comp_notch.setEnabled(True)
            text = self.comp_notch.currentText()
            if text and text != "None":
                comp["finger_notch"] = text
            else:
                comp.pop("finger_notch", None)
        self.canvas.refresh()

    def _comp_use_default(self, key, checked, spin):
        if self._loading:
            return
        comp = self._current_comp()
        if comp is None:
            return
        defs = self.config.get("defaults", {})
        self._snapshot_if_new_edit()
        if checked:
            comp.pop(key, None)
            default_val = defs.get(key)
            if default_val is not None:
                self._loading = True
                try:
                    spin.setValue(float(default_val))
                finally:
                    self._loading = False
            spin.setEnabled(False)
        else:
            spin.setEnabled(True)
            comp[key] = spin.value()
        self.canvas.refresh()

    # ── Toolbar actions ───────────────────────────────────────────────────────

    def _split_tray(self, direction):
        """
        Split the currently selected tray's slot into N equal sibling trays.
        Also works when a comp is selected — splits the comp's parent tray.
        Only valid on flexible trays.
        """
        tray = self._current_tray()
        if tray is None:
            comp = self._current_comp()
            if comp is not None:
                tray = _find_tray_for_comp(self.config.get("layout", {}), comp)
        if tray is None:
            return

        n, ok = QtWidgets.QInputDialog.getInt(
            self, f"Split Tray {direction}", "Number of parts:", 2, 2, 20)
        if not ok:
            return

        layout = self.config.get("layout", {})
        result = _find_tray_parent(layout, tray)
        self._snapshot()

        # Build n tray children: original tray first, then n-1 new ones
        new_trays = [{"name": f"Tray {self._next_tray_num() + i}",
                      "comp_layout": {"comp": {}}} for i in range(n - 1)]
        children = [{"tray": tray}] + [{"tray": t} for t in new_trays]
        split_node = {"split": direction, "children": children}

        if result is None:
            # The tray IS the root layout node — wrap it
            self.config["layout"] = split_node
        else:
            parent_node, child_idx = result
            parent_node["children"][child_idx] = split_node
            # Preserve parent flex_weight slot (unchanged weight for sub-split)

        sel_tray = new_trays[-1] if new_trays else tray
        self.canvas.set_selection(SEL_TRAY, sel_tray)
        self._on_selection(SEL_TRAY, sel_tray)
        self.canvas.refresh()
        self._refresh_tree()

    def _next_tray_num(self):
        trays = _collect_layout_trays(self.config.get("layout", {}))
        return len(trays) + 1

    def _split_comp(self, direction):
        """Split the selected compartment into N equal sub-compartments."""
        comp = self._current_comp()
        if comp is None:
            return

        n, ok = QtWidgets.QInputDialog.getInt(
            self, f"Split Comp {direction}", "Number of parts:", 2, 2, 20)
        if not ok:
            return

        tray = _find_tray_for_comp(self.config.get("layout", {}), comp)
        if tray is None:
            return

        # Build n comp children: original comp first, then n-1 new empty ones
        new_comps  = [{} for _ in range(n - 1)]
        children   = [{"comp": comp}] + [{"comp": c} for c in new_comps]
        split_node = {"split": direction, "children": children}

        comp_layout = tray.get("comp_layout", {})
        if "comp" in comp_layout and comp_layout["comp"] is comp:
            # This comp IS the root comp node
            self._snapshot()
            tray["comp_layout"] = split_node
            new_comp = new_comps[-1]
            self.canvas.set_selection(SEL_COMP, new_comp)
            self._on_selection(SEL_COMP, new_comp)
        else:
            result = _find_comp_parent(comp_layout, comp)
            if result is None:
                return
            parent_comp_node, child_idx = result
            self._snapshot()
            new_comp = new_comps[-1]
            parent_comp_node["children"][child_idx] = split_node
            self.canvas.set_selection(SEL_COMP, new_comp)
            self._on_selection(SEL_COMP, new_comp)

        self.canvas.refresh()
        self._refresh_tree()

    def _delete_selected(self):
        if not self._selection:
            return
        sel_type, data = self._selection
        self._snapshot()

        if sel_type == SEL_TRAY:
            layout = self.config.get("layout", {})
            result = _find_tray_parent(layout, data)
            if result is None:
                # Tray is the root — replace with empty flexible tray
                self.config["layout"] = {
                    "tray": {"name": "Tray 1", "comp_layout": {"comp": {}}}
                }
            else:
                parent_node, child_idx = result
                siblings = parent_node["children"]
                sibling_idx = 1 - child_idx if len(siblings) == 2 else None
                if sibling_idx is not None:
                    # Collapse: replace parent with sibling
                    sibling = siblings[sibling_idx]
                    grandparent = _find_tray_parent(layout, data)
                    # Replace the parent split with the sibling
                    self._replace_node_in_layout(
                        self.config["layout"], parent_node, sibling)
                else:
                    # 3+ siblings: just remove this one
                    siblings.pop(child_idx)
                    fw = parent_node.get("flex_weight")
                    if fw and child_idx < len(fw):
                        fw.pop(child_idx)
            self.canvas.set_selection(SEL_BOX, self.config)
            self._on_selection(SEL_BOX, self.config)

        elif sel_type == SEL_COMP:
            tray = _find_tray_for_comp(self.config.get("layout", {}), data)
            if tray is None:
                return
            comp_layout = tray.get("comp_layout", {})
            if "comp" in comp_layout and comp_layout["comp"] is data:
                # Root comp — nothing to delete (reset it)
                comp_layout["comp"] = {}
                new_comp = comp_layout["comp"]
            else:
                result = _find_comp_parent(comp_layout, data)
                if result is None:
                    return
                parent_comp_node, child_idx = result
                siblings = parent_comp_node["children"]
                if len(siblings) == 2:
                    sibling = siblings[1 - child_idx]
                    self._replace_comp_node_in_tray(tray, parent_comp_node, sibling)
                    new_comp = _collect_comps(tray.get("comp_layout", {}))[0]
                else:
                    siblings.pop(child_idx)
                    new_comp = _collect_comps(tray.get("comp_layout", {}))[0]
            self.canvas.set_selection(SEL_COMP, new_comp)
            self._on_selection(SEL_COMP, new_comp)

        self.canvas.refresh()
        self._refresh_tree()

    def _replace_node_in_layout(self, layout_root, target_node, replacement):
        """Replace target_node (a split node) in the layout tree with replacement."""
        # Check if target is immediate child of current node
        children = layout_root.get("children") or []
        for i, child in enumerate(children):
            if child is target_node:
                children[i] = replacement
                return True
            if self._replace_node_in_layout(child, target_node, replacement):
                return True
        # If target_node IS the root, replace config["layout"]
        if layout_root is target_node:
            self.config["layout"] = replacement
            return True
        return False

    def _replace_comp_node_in_tray(self, tray, target_node, replacement):
        """Replace target_node in tray's comp_layout tree with replacement."""
        comp_layout = tray.get("comp_layout", {})
        if comp_layout is target_node:
            tray["comp_layout"] = replacement
            return True
        return self._replace_comp_node_recursive(comp_layout, target_node, replacement)

    def _replace_comp_node_recursive(self, node, target, replacement):
        children = node.get("children") or []
        for i, child in enumerate(children):
            if child is target:
                children[i] = replacement
                return True
            if self._replace_comp_node_recursive(child, target, replacement):
                return True
        return False

    # ── File I/O ──────────────────────────────────────────────────────────────

    def _browse_dir(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select Output Directory", self.config.get("output_dir", ""))
        if d:
            self.config["output_dir"] = d
            self._loading = True
            self.box_dir.setText(d)
            self._loading = False

    def _load_json(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Load Config", "", "JSON Files (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Load Error", str(e))
            return
        self._snapshot()

        def strip_comments(obj):
            if isinstance(obj, dict):
                return {k: strip_comments(v) for k, v in obj.items()
                        if not k.startswith("_")}
            if isinstance(obj, list):
                return [strip_comments(i) for i in obj]
            return obj

        self.config.clear()
        self.config.update(strip_comments(data))
        self.canvas.config = self.config
        self.canvas.set_selection(SEL_BOX, self.config)
        self._on_selection(SEL_BOX, self.config)
        self.canvas.refresh()
        self._refresh_tree()

    def _save_json(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Config",
            self.config.get("output_dir", ""), "JSON Files (*.json)")
        if not path:
            return

        def clean(obj):
            if isinstance(obj, dict):
                return {k: clean(v) for k, v in obj.items()
                        if not k.startswith("_")}
            if isinstance(obj, list):
                return [clean(i) for i in obj]
            return obj
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(clean(self.config), f, indent=2)
            FreeCAD.Console.PrintMessage(f"Saved: {path}\n")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Save Error", str(e))

    # ── Generate ──────────────────────────────────────────────────────────────

    def _generate(self):
        if not self._gen:
            QtWidgets.QMessageBox.critical(
                self, "Error", "board_game_insert.py not loaded.")
            return

        cfg      = copy.deepcopy(self.config)
        defaults = cfg.get("defaults", {})
        out_dir  = cfg.get("output_dir", "")
        doc_name = cfg.get("document_name", "BoardGameInsert")
        box_h    = cfg.get("box_height", 70.0)

        if not out_dir:
            QtWidgets.QMessageBox.warning(
                self, "Generate", "Set an output directory in the Box panel first.")
            return

        os.makedirs(out_dir, exist_ok=True)

        layout_root = self._gen.resolve_layout(cfg)
        trays       = self._gen.collect_trays_from_layout(layout_root)

        if not trays:
            QtWidgets.QMessageBox.information(
                self, "Generate", "No trays found in layout.")
            return

        doc    = FreeCAD.newDocument(doc_name)
        errors = []

        for node, tray_cfg in trays:
            name = tray_cfg.get("name", "Tray")
            FreeCAD.Console.PrintMessage(f"Building '{name}'...\n")
            self._gen.merge_defaults(tray_cfg, defaults)

            wall_t  = tray_cfg.get("wall_thickness",
                                    defaults.get("wall_thickness", 2.0))
            inner_w = max(node.w - 2 * wall_t, 1.0)
            inner_d = max(node.d - 2 * wall_t, 1.0)
            resolved_comps = self._gen.resolve_tray_layout(
                tray_cfg, inner_w, inner_d, defaults)

            try:
                shape = self._gen.build_tray(tray_cfg, resolved_comps, box_h, defaults)
                shape = self._gen.apply_fillets(shape, tray_cfg)
            except Exception as e:
                msg = f"'{name}' failed: {e}"
                FreeCAD.Console.PrintError(f"  {msg}\n")
                errors.append(msg)
                continue

            obj       = doc.addObject("Part::Feature", name)
            obj.Shape = shape
            # Place tray to match canvas layout; flip Y so FreeCAD top view = canvas
            box_d = cfg.get("box_depth", 250.0)
            fx = node.x
            fy = box_d - node.y - node.d
            obj.Placement = FreeCAD.Placement(
                FreeCAD.Vector(fx, fy, 0), FreeCAD.Rotation())

            stl_path = os.path.join(out_dir, f"{name}.stl")
            self._gen.export_stl(shape, stl_path)
            FreeCAD.Console.PrintMessage(f"  → STL: {stl_path}\n")

        fcstd_path = os.path.join(out_dir, f"{doc_name}.FCStd")
        doc.saveAs(fcstd_path)
        doc.recompute()
        FreeCADGui.ActiveDocument.ActiveView.fitAll()

        msg = f"Done! Saved: {fcstd_path}"
        if errors:
            msg += "\n\nErrors:\n" + "\n".join(errors)
        QtWidgets.QMessageBox.information(self, "Generate Complete", msg)


# ── Launch ────────────────────────────────────────────────────────────────────

def main():
    dlg = InsertDesigner(FreeCADGui.getMainWindow())
    dlg.show()


if __name__ == "__main__":
    main()
