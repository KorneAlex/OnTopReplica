# OnTopReplica (Linux branch)

Real-time always-on-top replica of another window — originally for Windows, with a **Linux (Hyprland / Wayland) MVP** on this branch.

| Platform | Status | Location |
| --- | --- | --- |
| **Linux (Hyprland)** | MVP — usable, some gaps | [`linux/`](linux/) |
| Windows | Original app (unchanged) | [`src/`](src/) |

Capture on Linux uses the desktop portal and PipeWire, not Windows DWM thumbnails.

**→ Full Linux usage, deps, Hyprland rules, and feature support: [linux/README.md](linux/README.md)**

```bash
cd linux
python3 -m ontopreplica
```

---

## Original Windows app

**A real-time always-on-top “replica” of a window of your choice, for Windows Vista, 7, 8, or 10.**

Shows a blank always-on-top window by default. Pick any other window to keep a live clone on top — useful for monitoring background processes, multi-window games/tools, watching video while working, and so on.

**Windows features:**

* Clone any window and keep it always-on-top
* Select a subregion (storable; relative border coordinates)
* Auto-resizing (fit, half, quarter, fullscreen)
* Position lock on screen corners
* Adjustable opacity
* Click forwarding into the cloned window
* Click-through (overlay with partial opacity)
* Group switch mode

### Windows requirements

* Windows Vista or greater (DWM Thumbnails)
* .NET Framework 4.7
* Desktop Composition (Aero) enabled

### Windows installation

Get the [latest release](https://github.com/LorenzCK/OnTopReplica/releases) MSI from upstream, or build from [`src/`](src/).

## License

**OnTopReplica** is licensed under the [MS-RL (Microsoft Reciprocal License)](LICENSE).
