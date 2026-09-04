"""Drag-to-select a normalized crop region over the replica."""

from __future__ import annotations

from typing import Callable, Tuple

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, Gtk

CropRect = Tuple[float, float, float, float]


class RegionOverlay(Gtk.DrawingArea):
    """Transparent overlay: drag a rectangle, report normalized crop on release."""

    def __init__(self, on_region: Callable[[CropRect], None]) -> None:
        super().__init__()
        self._on_region = on_region
        self._dragging = False
        self._start_x = 0.0
        self._start_y = 0.0
        self._cur_x = 0.0
        self._cur_y = 0.0
        self.set_draw_func(self._draw)
        self.set_can_target(True)
        self.set_focusable(True)

        click = Gtk.GestureClick()
        click.set_button(1)
        click.connect("pressed", self._on_pressed)
        click.connect("released", self._on_released)
        self.add_controller(click)

        drag = Gtk.EventControllerMotion()
        drag.connect("motion", self._on_motion)
        self.add_controller(drag)

        key = Gtk.EventControllerKey()
        key.connect("key-pressed", self._on_key)
        self.add_controller(key)

    def _on_pressed(self, _gesture: Gtk.GestureClick, _n: int, x: float, y: float) -> None:
        self._dragging = True
        self._start_x = self._cur_x = x
        self._start_y = self._cur_y = y
        self.queue_draw()

    def _on_motion(self, _controller: Gtk.EventControllerMotion, x: float, y: float) -> None:
        if not self._dragging:
            return
        self._cur_x = x
        self._cur_y = y
        self.queue_draw()

    def _on_released(self, _gesture: Gtk.GestureClick, _n: int, x: float, y: float) -> None:
        if not self._dragging:
            return
        self._dragging = False
        self._cur_x = x
        self._cur_y = y
        self.queue_draw()

        width = max(self.get_width(), 1)
        height = max(self.get_height(), 1)
        x0 = min(self._start_x, self._cur_x) / width
        y0 = min(self._start_y, self._cur_y) / height
        x1 = max(self._start_x, self._cur_x) / width
        y1 = max(self._start_y, self._cur_y) / height

        # Ignore tiny drags
        if (x1 - x0) * width < 8 or (y1 - y0) * height < 8:
            return

        x0 = max(0.0, min(1.0, x0))
        y0 = max(0.0, min(1.0, y0))
        x1 = max(0.0, min(1.0, x1))
        y1 = max(0.0, min(1.0, y1))
        if x1 <= x0 or y1 <= y0:
            return
        self._on_region((x0, y0, x1, y1))

    def _on_key(self, _controller: Gtk.EventControllerKey, keyval: int, _code: int, _state: Gdk.ModifierType) -> bool:
        if keyval == Gdk.KEY_Escape:
            self._dragging = False
            self.queue_draw()
            return True
        return False

    def _draw(self, _area: Gtk.DrawingArea, cr, width: int, height: int) -> None:
        import cairo as cairo_mod

        # Dim overlay while selecting
        cr.set_source_rgba(0, 0, 0, 0.35)
        cr.rectangle(0, 0, width, height)
        cr.fill()

        if not self._dragging:
            cr.set_source_rgba(1, 1, 1, 0.9)
            cr.select_font_face("Sans", 0, 0)
            cr.set_font_size(14)
            text = "Drag to select region  (Esc to cancel)"
            extents = cr.text_extents(text)
            cr.move_to((width - extents.width) / 2, height / 2)
            cr.show_text(text)
            return

        x = min(self._start_x, self._cur_x)
        y = min(self._start_y, self._cur_y)
        w = abs(self._cur_x - self._start_x)
        h = abs(self._cur_y - self._start_y)

        # Punch a hole in the dim overlay for the selection
        cr.set_operator(cairo_mod.OPERATOR_CLEAR)
        cr.rectangle(x, y, w, h)
        cr.fill()
        cr.set_operator(cairo_mod.OPERATOR_OVER)

        cr.set_source_rgba(0.2, 0.7, 1.0, 0.9)
        cr.set_line_width(2)
        cr.rectangle(x, y, w, h)
        cr.stroke()
