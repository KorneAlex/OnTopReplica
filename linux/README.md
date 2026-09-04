# OnTopReplica for Linux (Hyprland MVP)

Always-on-top live window replica for Wayland, aimed at Hyprland. Uses the
xdg-desktop-portal ScreenCast API and PipeWire (same stack as screen sharing).

## Dependencies

Arch / CachyOS:

```bash
sudo pacman -S python-gobject gtk4 python-dbus pipewire \
  xdg-desktop-portal xdg-desktop-portal-hyprland \
  gst-plugin-pipewire gstreamer gst-plugins-base
```

Optional (smoother display path):

```bash
sudo pacman -S gst-plugin-gtk4
```

## Run

```bash
cd linux
python3 -m ontopreplica
```

## Usage

1. A dark always-on-top window appears.
2. Right-click → **Select window…** (or pick a title under **Windows**).
3. Confirm the Hyprland / portal capture dialog.
4. Right-click for opacity, region crop, click-through, or stop.

## Notes

- Wayland cannot silently attach to an arbitrary window; the portal picker is required.
- Click forwarding into the source window is not supported in this MVP.
- The Hyprland window menu lists clients via `hyprctl`; capture still goes through the portal.
- Always-on-top uses Hyprland `pin` / `alterzorder` (GTK4 has no portable keep-above on Wayland). Add this to `~/.config/hypr/config/windowrules.lua` so the replica stays detached (floating + pinned):

```lua
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
