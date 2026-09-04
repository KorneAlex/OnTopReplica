# OnTopReplica for Linux

Always-on-top live window replica for **Wayland**, aimed at **Hyprland**.

The Windows app cannot run here: it depends on DWM Thumbnails. This is a separate Python/GTK4 app that mirrors the same idea via **xdg-desktop-portal ScreenCast** and **PipeWire**.

## Quick start

```bash
cd linux
python3 -m ontopreplica
# or: ./run.sh
```

1. A dark floating window appears (“Right-click to select a window”).
2. **Right-click** → **Select window…** (or a title under **Windows (Hyprland)**).
3. Confirm the compositor / portal share dialog and pick the source window (or monitor).
4. The replica shows a live clone. Right-click again for opacity, region, click-through, stop, quit.

Wayland does not allow silent capture of another window: the portal picker is required every time you start a clone (unless the portal restores a previous grant).

## Dependencies

Arch Linux and derivatives:

```bash
sudo pacman -S python-gobject gtk4 python-dbus pipewire \
  xdg-desktop-portal xdg-desktop-portal-hyprland \
  gst-plugin-pipewire gstreamer gst-plugins-base
```

Optional:

```bash
sudo pacman -S gst-plugin-gtk4   # gtk4paintablesink (display still works via appsink without it)
```

On other distros, install the equivalent packages (PyGObject, GTK 4, PipeWire, xdg-desktop-portal with a Hyprland or wlroots backend, GStreamer + pipewiresrc).

## Hyprland: keep the replica detached

GTK4 has no portable “always on top” on Wayland. Add a window rule so OnTopReplica floats and stays pinned across workspaces.

Example for Hyprland’s Lua config (`windowrules` / similar):

```lua
-- OnTopReplica — detach from tiling: float + pin across workspaces
hl.window_rule({
    name              = "ontopreplica-detached",
    match             = {
        class = "^(io\\.github\\.ontopreplica\\.linux)$",
        title = "^(OnTopReplica)$",
    },
    float             = true,
    pin               = true,
    keep_aspect_ratio = true,
    size              = { "max(monitor_w, monitor_h)*0.30", "min(monitor_w, monitor_h)*0.30" },
})
```

Then reload Hyprland (e.g. `hyprctl reload`).

The app also best-effort calls Hyprland pin/float APIs on map; the window rule is the reliable path.

## What’s supported (MVP)

| Feature | Status |
| --- | --- |
| Live clone of a window or monitor | Yes (via portal + PipeWire) |
| Always-on-top / detached floating | Yes (Hyprland float + pin rule) |
| Opacity | Yes (context menu: 100% / 80% / 60% / 40% / 25%) |
| Region crop | Yes (drag rectangle on the replica; clear via menu) |
| Click-through | Yes (empty input region — overlay mode) |
| Aspect ratio lock | Yes (menu toggle; default on) |
| Free resize | Yes |
| Hyprland window list in menu | Yes (`hyprctl clients`) — still opens the portal to capture |
| Stop cloning / quit | Yes |
| Portal cancel / stream end | Handled without crashing (shows a hint) |

## Not supported yet

| Feature (from Windows OnTopReplica) | Status |
| --- | --- |
| Click forwarding into the source window | No (Wayland input injection is unreliable / compositor-specific) |
| Stored regions / restore last region | No |
| Position lock to screen corners | No (drag/place manually; pin keeps it visible) |
| Fit half / quarter / fullscreen presets | No (resize manually) |
| Group switch mode | No |
| Hotkeys | No |
| Silent attach by HWND / title without portal | No (Wayland security model) |
| Non-Hyprland polish | Partial — portal capture can work elsewhere; `hyprctl` menu and pin rules are Hyprland-oriented |

Known rough edges: portal UX, pin timing, and stream teardown can vary by compositor and portal version.

## How it works

```
Right-click menu
    → (optional) hyprctl window list for labels
    → xdg-desktop-portal ScreenCast (WINDOW / MONITOR)
    → PipeWire node
    → GStreamer (pipewiresrc → videoconvert → appsink)
    → GTK4 window (Gtk.Picture)
```

Package layout:

```
linux/
  README.md                 ← this file
  run.sh
  ontopreplica/
    app.py                  # Gtk.Application
    main_window.py          # UI + context menu
    portal_screencast.py    # D-Bus ScreenCast session
    capture_pipeline.py     # GStreamer pipeline
    hypr_windows.py         # hyprctl helpers
    region_select.py        # drag-to-crop overlay
```

## License

Same as the main project: [MS-RL](../LICENSE).
