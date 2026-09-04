"""GStreamer PipeWire capture → GTK display."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

import gi

gi.require_version("Gst", "1.0")
gi.require_version("GstApp", "1.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")

from gi.repository import Gdk, GLib, Gst, GstApp, Gtk

logger = logging.getLogger(__name__)

Gst.init(None)

# Normalized crop: fractions of source frame (left, top, right, bottom) in 0..1
CropRect = Tuple[float, float, float, float]


@dataclass
class CaptureState:
    width: int = 0
    height: int = 0


class CapturePipeline:
    """pipewiresrc → videoconvert → appsink (or gtk4paintablesink)."""

    def __init__(self) -> None:
        self._pipeline: Optional[Gst.Pipeline] = None
        self._appsink: Optional[GstApp.AppSink] = None
        self._picture: Optional[Gtk.Picture] = None
        self._use_gtk4_sink = False
        self._crop: Optional[CropRect] = None
        self._state = CaptureState()
        self._on_size: Optional[Callable[[int, int], None]] = None
        self._on_error: Optional[Callable[[str], None]] = None
        self._bus_watch_id: Optional[int] = None

    @property
    def frame_size(self) -> Tuple[int, int]:
        return self._state.width, self._state.height

    def set_picture(self, picture: Gtk.Picture) -> None:
        self._picture = picture

    def set_on_size(self, callback: Callable[[int, int], None]) -> None:
        self._on_size = callback

    def set_on_error(self, callback: Callable[[str], None]) -> None:
        self._on_error = callback

    def set_crop(self, crop: Optional[CropRect]) -> None:
        """Set normalized crop rectangle (left, top, right, bottom)."""
        self._crop = crop

    def start(self, pipewire_fd: int, node_id: int) -> None:
        self.stop()

        factory = Gst.ElementFactory.find("gtk4paintablesink")
        # Prefer appsink so software crop works without gst-plugins-good videocrop
        self._use_gtk4_sink = bool(factory)
        logger.info(
            "Display path: appsink (gtk4paintablesink %s)",
            "available" if self._use_gtk4_sink else "missing",
        )

        desc = (
            f"pipewiresrc fd={pipewire_fd} path={node_id} do-timestamp=true ! "
            f"videoconvert ! video/x-raw,format=RGBA ! "
            f"appsink name=sink emit-signals=true max-buffers=2 drop=true sync=false"
        )
        logger.info("Starting pipeline: %s", desc.replace(str(pipewire_fd), "<fd>"))

        pipeline = Gst.parse_launch(desc)
        assert isinstance(pipeline, Gst.Pipeline)
        self._pipeline = pipeline
        sink = pipeline.get_by_name("sink")
        assert isinstance(sink, GstApp.AppSink)
        self._appsink = sink
        sink.connect("new-sample", self._on_new_sample)

        bus = pipeline.get_bus()
        bus.add_signal_watch()
        self._bus_watch_id = bus.connect("message", self._on_bus_message)

        ret = pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            self._emit_error("Failed to start capture pipeline")
            self.stop()

    def stop(self) -> None:
        if self._pipeline is not None:
            bus = self._pipeline.get_bus()
            if self._bus_watch_id is not None:
                try:
                    bus.disconnect(self._bus_watch_id)
                except Exception:
                    pass
                self._bus_watch_id = None
            try:
                bus.remove_signal_watch()
            except Exception:
                pass
            self._pipeline.set_state(Gst.State.NULL)
            self._pipeline = None
        self._appsink = None
        if self._picture is not None:
            self._picture.set_paintable(None)

    def _emit_error(self, message: str) -> None:
        logger.error(message)
        if self._on_error:
            GLib.idle_add(lambda: self._on_error(message) or False)

    def _on_bus_message(self, _bus: Gst.Bus, message: Gst.Message) -> None:
        if message.type == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            self._emit_error(f"GStreamer error: {err} ({debug})")
        elif message.type == Gst.MessageType.EOS:
            self._emit_error("Capture stream ended")

    def _on_new_sample(self, sink: GstApp.AppSink) -> Gst.FlowReturn:
        sample = sink.emit("pull-sample")
        if sample is None:
            return Gst.FlowReturn.ERROR

        buffer = sample.get_buffer()
        caps = sample.get_caps()
        if buffer is None or caps is None:
            return Gst.FlowReturn.ERROR

        structure = caps.get_structure(0)
        width = structure.get_value("width")
        height = structure.get_value("height")
        if not width or not height:
            return Gst.FlowReturn.ERROR

        success, map_info = buffer.map(Gst.MapFlags.READ)
        if not success:
            return Gst.FlowReturn.ERROR

        try:
            data = bytes(map_info.data)
        finally:
            buffer.unmap(map_info)

        # Optional software crop (normalized → pixels)
        crop = self._crop
        src_w, src_h = int(width), int(height)
        if crop is not None:
            left, top, right, bottom = crop
            x0 = max(0, min(src_w - 1, int(left * src_w)))
            y0 = max(0, min(src_h - 1, int(top * src_h)))
            x1 = max(x0 + 1, min(src_w, int(right * src_w)))
            y1 = max(y0 + 1, min(src_h, int(bottom * src_h)))
            out_w = x1 - x0
            out_h = y1 - y0
            stride = src_w * 4
            rows = []
            for y in range(y0, y1):
                start = y * stride + x0 * 4
                rows.append(data[start : start + out_w * 4])
            data = b"".join(rows)
            out_width, out_height = out_w, out_h
        else:
            out_width, out_height = src_w, src_h

        # Copy into a GBytes-backed MemoryTexture on the main thread
        frame_bytes = data
        fw, fh = out_width, out_height

        def apply_frame() -> bool:
            if self._picture is None:
                return False
            try:
                bytes_obj = GLib.Bytes.new(frame_bytes)
                texture = Gdk.MemoryTexture.new(
                    fw,
                    fh,
                    Gdk.MemoryFormat.R8G8B8A8,
                    bytes_obj,
                    fw * 4,
                )
                self._picture.set_paintable(texture)
            except Exception as exc:
                logger.exception("Failed to create texture: %s", exc)
                return False

            if fw != self._state.width or fh != self._state.height:
                self._state.width = fw
                self._state.height = fh
                if self._on_size:
                    self._on_size(fw, fh)
            return False

        GLib.idle_add(apply_frame)
        return Gst.FlowReturn.OK
