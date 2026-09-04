"""Always-on-top replica window and context menu."""

from __future__ import annotations

import logging
import os
from typing import Optional

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, Gio, GLib, Gtk

from .capture_pipeline import CapturePipeline
from .hypr_windows import hyprctl_available, list_windows, pin_window_by_title
from .portal_screencast import ScreenCastSession
from .region_select import RegionOverlay

logger = logging.getLogger(__name__)

REPLICA_TITLE = "OnTopReplica"


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, application: Gtk.Application) -> None:
        super().__init__(application=application, title=REPLICA_TITLE)
        self.set_default_size(480, 270)
        self.set_resizable(True)

        self._session: Optional[ScreenCastSession] = None
        self._capture = CapturePipeline()
        self._click_through = False
        self._lock_aspect = True
        self._aspect = 16 / 9
        self._selecting_region = False
        self._opacity = 1.0

        self._hint = Gtk.Label(label="Right-click to select a window")
        self._hint.set_halign(Gtk.Align.CENTER)
        self._hint.set_valign(Gtk.Align.CENTER)
        self._hint.add_css_class("hint-label")

        self._picture = Gtk.Picture()
        self._picture.set_content_fit(Gtk.ContentFit.CONTAIN)
        self._picture.set_hexpand(True)
        self._picture.set_vexpand(True)
        self._capture.set_picture(self._picture)
        self._capture.set_on_size(self._on_frame_size)
        self._capture.set_on_error(self._on_capture_error)

        self._stack = Gtk.Overlay()
        self._stack.set_child(self._picture)
        self._stack.add_overlay(self._hint)
        self._region_overlay: Optional[RegionOverlay] = None

        self.set_child(self._stack)

        css = Gtk.CssProvider()
        css.load_from_data(
            b"""
            window { background: #000000; }
            .hint-label {
                color: #cccccc;
                font-size: 14px;
                padding: 12px;
            }
            """
        )
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        # Right-click menu
        gesture = Gtk.GestureClick()
        gesture.set_button(3)
        gesture.connect("pressed", self._on_right_click)
        self.add_controller(gesture)

        # Also allow right-click on picture/hint
        for widget in (self._picture, self._hint, self._stack):
            g = Gtk.GestureClick()
            g.set_button(3)
            g.connect("pressed", self._on_right_click)
            widget.add_controller(g)

        self.connect("realize", self._on_realize)
        self.connect("map", self._on_map)
        self.connect("close-request", self._on_close)
        # Re-apply click-through when the window is resized
        self.connect("notify::default-width", lambda *_: self._apply_click_through())
        self.connect("notify::default-height", lambda *_: self._apply_click_through())

    def _on_realize(self, *_args) -> None:
        self.present()

    def _on_map(self, *_args) -> None:
        # GTK4 has no portable keep-above on Wayland; pin via Hyprland when available.
        GLib.timeout_add(200, self._hypr_elevate)

    def _hypr_elevate(self) -> bool:
        pin_window_by_title(REPLICA_TITLE)
        return False

    def _on_close(self, *_args) -> bool:
        self._teardown_capture()
        return False

    def _teardown_capture(self) -> None:
        self._capture.stop()
        if self._session is not None:
            self._session.close()
            self._session = None
        self._hint.set_visible(True)
        self._hint.set_label("Right-click to select a window")

    def _on_right_click(self, gesture: Gtk.GestureClick, _n: int, x: float, y: float) -> None:
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        widget = gesture.get_widget() or self
        self._popup_menu(widget, x, y)

    def _popup_menu(self, parent: Gtk.Widget, x: float, y: float) -> None:
        menu = GioMenuBuilder(self).build()
        popover = Gtk.PopoverMenu.new_from_model(menu)
        popover.set_parent(parent)
        rect = Gdk.Rectangle()
        rect.x = int(x)
        rect.y = int(y)
        rect.width = 1
        rect.height = 1
        popover.set_pointing_to(rect)
        popover.set_has_arrow(False)
        popover.popup()

    # --- actions invoked from menu ---

    def action_select_window(self, *_args) -> None:
        self._start_portal_capture()

    def action_stop(self, *_args) -> None:
        self._teardown_capture()

    def action_quit(self, *_args) -> None:
        self._teardown_capture()
        app = self.get_application()
        if app:
            app.quit()

    def action_toggle_click_through(self, *_args) -> None:
        self._click_through = not self._click_through
        self._apply_click_through()

    def action_toggle_aspect(self, *_args) -> None:
        self._lock_aspect = not self._lock_aspect

    def action_set_opacity(self, value: float) -> None:
        self._opacity = max(0.15, min(1.0, value))
        self.set_opacity(self._opacity)

    def action_select_region(self, *_args) -> None:
        if self._session is None:
            self._hint.set_label("Clone a window before selecting a region")
            self._hint.set_visible(True)
            return
        self._enter_region_mode()

    def action_clear_region(self, *_args) -> None:
        self._capture.set_crop(None)
        self._exit_region_mode()

    def _enter_region_mode(self) -> None:
        if self._region_overlay is not None:
            return
        self._selecting_region = True
        overlay = RegionOverlay(self._on_region_chosen)
        overlay.set_hexpand(True)
        overlay.set_vexpand(True)
        self._region_overlay = overlay
        self._stack.add_overlay(overlay)
        overlay.grab_focus()

    def _exit_region_mode(self) -> None:
        self._selecting_region = False
        if self._region_overlay is not None:
            self._stack.remove_overlay(self._region_overlay)
            self._region_overlay = None

    def _on_region_chosen(self, crop) -> None:
        self._capture.set_crop(crop)
        self._exit_region_mode()

    def _apply_click_through(self) -> None:
        surface = self.get_surface()
        if surface is None:
            return
        try:
            import cairo

            if self._click_through:
                region = cairo.Region()
            else:
                width = max(self.get_width(), 1)
                height = max(self.get_height(), 1)
                region = cairo.Region(cairo.RectangleInt(0, 0, width, height))
            surface.set_input_region(region)
        except Exception as exc:
            logger.warning("Could not set input region: %s", exc)

    def _start_portal_capture(self) -> None:
        self._teardown_capture()
        self._hint.set_label("Waiting for portal…")
        self._hint.set_visible(True)

        session = ScreenCastSession()
        self._session = session

        def on_ready(sess: ScreenCastSession) -> None:
            fd = sess.pipewire_fd
            node = sess.node_id
            if fd is None or node is None:
                self._on_capture_error("Portal did not provide a PipeWire stream")
                return
            gst_fd = os.dup(fd)
            self._capture.start(gst_fd, node)
            self._hint.set_visible(False)
            if sess.stream_size:
                w, h = sess.stream_size
                if w > 0 and h > 0:
                    self._aspect = w / h
                    self._maybe_resize_to_aspect()

        def on_error(message: str) -> None:
            self._on_capture_error(message)

        session.start(on_ready=on_ready, on_error=on_error, prefer_window=True)

    def _on_frame_size(self, width: int, height: int) -> None:
        if width > 0 and height > 0:
            self._aspect = width / height
            self._maybe_resize_to_aspect()

    def _maybe_resize_to_aspect(self) -> None:
        if not self._lock_aspect or self._aspect <= 0:
            return
        # Keep current width, adjust height
        width = self.get_width() or 480
        height = max(80, int(width / self._aspect))
        self.set_default_size(width, height)

    def _on_capture_error(self, message: str) -> None:
        logger.error(message)
        self._teardown_capture()
        self._hint.set_label(message)
        self._hint.set_visible(True)


class GioMenuBuilder:
    """Build a GMenu with window actions registered on the window."""

    def __init__(self, window: MainWindow) -> None:
        self.window = window

    def build(self) -> Gio.Menu:
        self._ensure_actions()
        menu = Gio.Menu()

        menu.append("Select window…", "win.select_window")

        windows = list_windows()
        self.window._hypr_menu_windows = windows
        if windows:
            submenu = Gio.Menu()
            # Portal cannot target a specific Hyprland address; entries start the same picker.
            for idx, win in enumerate(windows[:40]):
                action_name = f"win.pick_hypr_{idx}"
                if not self.window.lookup_action(f"pick_hypr_{idx}"):
                    act = Gio.SimpleAction.new(f"pick_hypr_{idx}", None)
                    act.connect("activate", self._make_hypr_picker(idx))
                    self.window.add_action(act)
                submenu.append(win.label[:80], action_name)
            menu.append_submenu("Windows (Hyprland)", submenu)
        elif hyprctl_available():
            menu.append("Windows (none found)", None)
        else:
            menu.append("Windows (hyprctl not found)", None)

        menu.append("Stop cloning", "win.stop")

        opacity = Gio.Menu()
        for label, value in (
            ("100%", 1.0),
            ("80%", 0.8),
            ("60%", 0.6),
            ("40%", 0.4),
            ("25%", 0.25),
        ):
            name = f"opacity_{int(value * 100)}"
            if not self.window.lookup_action(name):
                act = Gio.SimpleAction.new(name, None)
                act.connect("activate", lambda *_a, v=value: self.window.action_set_opacity(v))
                self.window.add_action(act)
            opacity.append(label, f"win.{name}")
        menu.append_submenu("Opacity", opacity)

        ct_label = "Disable click-through" if self.window._click_through else "Enable click-through"
        menu.append(ct_label, "win.click_through")

        aspect_label = "Unlock aspect ratio" if self.window._lock_aspect else "Lock aspect ratio"
        menu.append(aspect_label, "win.toggle_aspect")

        menu.append("Select region…", "win.select_region")
        menu.append("Clear region", "win.clear_region")
        menu.append("Quit", "win.quit")
        return menu

    def _make_hypr_picker(self, idx: int):
        def _activate(*_args) -> None:
            windows = getattr(self.window, "_hypr_menu_windows", []) or []
            if 0 <= idx < len(windows):
                self._pick_named(windows[idx].label)
            else:
                self.window._start_portal_capture()

        return _activate

    def _pick_named(self, label: str) -> None:
        self.window._hint.set_label(f"In the portal, select:\n{label}")
        self.window._hint.set_visible(True)
        self.window._start_portal_capture()

    def _ensure_actions(self) -> None:
        mapping = {
            "select_window": self.window.action_select_window,
            "stop": self.window.action_stop,
            "quit": self.window.action_quit,
            "click_through": self.window.action_toggle_click_through,
            "toggle_aspect": self.window.action_toggle_aspect,
            "select_region": self.window.action_select_region,
            "clear_region": self.window.action_clear_region,
        }
        for name, handler in mapping.items():
            if self.window.lookup_action(name):
                continue
            act = Gio.SimpleAction.new(name, None)
            act.connect("activate", handler)
            self.window.add_action(act)
