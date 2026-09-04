"""xdg-desktop-portal ScreenCast session (PipeWire)."""

from __future__ import annotations

import logging
import os
import random
import string
from typing import Callable, Optional

import dbus
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

logger = logging.getLogger(__name__)

PORTAL_BUS = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
SCREENCAST_IFACE = "org.freedesktop.portal.ScreenCast"
REQUEST_IFACE = "org.freedesktop.portal.Request"
SESSION_IFACE = "org.freedesktop.portal.Session"

SOURCE_MONITOR = 1
SOURCE_WINDOW = 2
CURSOR_EMBEDDED = 2
CURSOR_HIDDEN = 1


def _token(prefix: str = "otr") -> str:
    suffix = "".join(random.choices(string.ascii_letters + string.digits, k=12))
    return f"{prefix}{suffix}"


def _request_path(bus: dbus.SessionBus, handle_token: str) -> str:
    unique = bus.get_unique_name()[1:].replace(".", "_")
    return f"/org/freedesktop/portal/desktop/request/{unique}/{handle_token}"


class ScreenCastSession:
    """Owns a portal ScreenCast session and the PipeWire remote fd."""

    def __init__(self) -> None:
        DBusGMainLoop(set_as_default=True)
        self._bus = dbus.SessionBus()
        portal = self._bus.get_object(PORTAL_BUS, PORTAL_PATH)
        self._screencast = dbus.Interface(portal, SCREENCAST_IFACE)
        self._session_path: Optional[str] = None
        self._pw_fd: Optional[int] = None
        self._node_id: Optional[int] = None
        self._stream_size: Optional[tuple[int, int]] = None
        self._closed = False

    @property
    def pipewire_fd(self) -> Optional[int]:
        return self._pw_fd

    @property
    def node_id(self) -> Optional[int]:
        return self._node_id

    @property
    def stream_size(self) -> Optional[tuple[int, int]]:
        return self._stream_size

    def start(
        self,
        on_ready: Callable[["ScreenCastSession"], None],
        on_error: Callable[[str], None],
        parent_window: str = "",
        prefer_window: bool = True,
    ) -> None:
        """Run CreateSession → SelectSources → Start → OpenPipeWireRemote."""
        if self._closed:
            on_error("Session already closed")
            return

        def fail(msg: str) -> None:
            logger.error(msg)
            self.close()
            on_error(msg)

        def after_start(response: int, results: dict) -> None:
            if response != 0:
                fail("Screen capture cancelled or failed")
                return
            streams = results.get("streams")
            if not streams:
                fail("No streams returned by portal")
                return
            node_id, props = streams[0]
            self._node_id = int(node_id)
            size = props.get("size")
            if size is not None:
                self._stream_size = (int(size[0]), int(size[1]))

            try:
                fd_obj = self._screencast.OpenPipeWireRemote(
                    dbus.ObjectPath(self._session_path),
                    dbus.Dictionary({}, signature="sv"),
                )
                # python-dbus returns a UnixFd
                if hasattr(fd_obj, "take"):
                    self._pw_fd = fd_obj.take()
                else:
                    self._pw_fd = int(fd_obj)
            except dbus.DBusException as exc:
                fail(f"OpenPipeWireRemote failed: {exc}")
                return

            if self._pw_fd is None or self._node_id is None:
                fail("Missing PipeWire fd or node id")
                return

            on_ready(self)

        def after_select(response: int, _results: dict) -> None:
            if response != 0:
                fail("Source selection failed")
                return
            self._call_request(
                lambda opts: self._screencast.Start(
                    dbus.ObjectPath(self._session_path),
                    parent_window,
                    opts,
                ),
                after_start,
                fail,
                extra_options={},
            )

        def after_create(response: int, results: dict) -> None:
            if response != 0:
                fail("Could not create screen cast session")
                return
            handle = results.get("session_handle")
            if not handle:
                fail("No session_handle in CreateSession response")
                return
            self._session_path = str(handle)

            props = dbus.Interface(
                self._bus.get_object(PORTAL_BUS, PORTAL_PATH),
                "org.freedesktop.DBus.Properties",
            )
            try:
                available = int(props.Get(SCREENCAST_IFACE, "AvailableSourceTypes"))
            except dbus.DBusException:
                available = SOURCE_MONITOR | SOURCE_WINDOW
            types = 0
            if prefer_window and (available & SOURCE_WINDOW):
                types |= SOURCE_WINDOW
            if available & SOURCE_MONITOR:
                types |= SOURCE_MONITOR
            if types == 0:
                types = SOURCE_MONITOR | SOURCE_WINDOW

            try:
                cursor_modes = int(props.Get(SCREENCAST_IFACE, "AvailableCursorModes"))
            except dbus.DBusException:
                cursor_modes = CURSOR_HIDDEN
            cursor = CURSOR_EMBEDDED if (cursor_modes & CURSOR_EMBEDDED) else CURSOR_HIDDEN

            select_opts = {
                "types": dbus.UInt32(types),
                "multiple": False,
                "cursor_mode": dbus.UInt32(cursor),
            }
            self._call_request(
                lambda opts: self._screencast.SelectSources(
                    dbus.ObjectPath(self._session_path),
                    opts,
                ),
                after_select,
                fail,
                extra_options=select_opts,
            )

        self._call_request(
            lambda opts: self._screencast.CreateSession(opts),
            after_create,
            fail,
            extra_options={"session_handle_token": _token("sess")},
        )

    def _call_request(
        self,
        invoker: Callable[[dbus.Dictionary], dbus.ObjectPath],
        on_response: Callable[[int, dict], None],
        on_error: Callable[[str], None],
        extra_options: Optional[dict] = None,
    ) -> None:
        handle_token = _token("req")
        options = {"handle_token": handle_token}
        if extra_options:
            options.update(extra_options)

        path = _request_path(self._bus, handle_token)
        request_obj = self._bus.get_object(PORTAL_BUS, path)
        request_iface = dbus.Interface(request_obj, REQUEST_IFACE)

        def handler(response: int, results: dbus.Dictionary) -> None:
            try:
                signal_match.remove()
            except Exception:
                pass
            # Ensure we run on the GLib main context
            GLib.idle_add(lambda: on_response(int(response), dict(results)) or False)

        signal_match = request_iface.connect_to_signal("Response", handler)

        try:
            invoker(dbus.Dictionary(options, signature="sv"))
        except dbus.DBusException as exc:
            try:
                signal_match.remove()
            except Exception:
                pass
            on_error(f"Portal call failed: {exc}")

    def close(self) -> None:
        self._closed = True
        if self._pw_fd is not None:
            try:
                os.close(self._pw_fd)
            except OSError:
                pass
            self._pw_fd = None

        if self._session_path:
            try:
                session = self._bus.get_object(PORTAL_BUS, self._session_path)
                dbus.Interface(session, SESSION_IFACE).Close()
            except dbus.DBusException:
                pass
            self._session_path = None
