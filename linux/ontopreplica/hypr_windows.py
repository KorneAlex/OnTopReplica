"""Enumerate visible clients via hyprctl (Hyprland)."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class HyprWindow:
    address: str
    title: str
    class_name: str
    workspace: str

    @property
    def label(self) -> str:
        title = self.title.strip() or "(no title)"
        cls = self.class_name.strip()
        if cls:
            return f"{title}  [{cls}]"
        return title


def hyprctl_available() -> bool:
    return shutil.which("hyprctl") is not None


def pin_window_by_title(title: str) -> bool:
    """Float, pin, and raise a Hyprland window matching title (best-effort).

    Supports Hyprland 0.55+ Lua dispatchers; falls back to legacy dispatch names.
    """
    if not hyprctl_available():
        return False

    safe = title.replace("\\", "\\\\").replace("'", "\\'").replace('"', "")
    selector = f"title:^{safe}$"

    # Hyprland 0.55+ Lua API (preferred)
    lua_cmds = [
        f'hl.dsp.window.float({{action = "set", window = "{selector}"}})()',
        f'hl.dsp.window.pin({{action = "set", window = "{selector}"}})()',
        f'hl.dsp.window.alter_zorder({{mode = "top", window = "{selector}"}})()',
    ]
    lua_ok = True
    for code in lua_cmds:
        try:
            proc = subprocess.run(
                ["hyprctl", "eval", code],
                check=False,
                capture_output=True,
                text=True,
                timeout=2,
            )
            if proc.returncode != 0 or "error" in (proc.stdout + proc.stderr).lower():
                lua_ok = False
                break
        except (OSError, subprocess.SubprocessError):
            lua_ok = False
            break

    if lua_ok:
        return True

    # Legacy (pre-0.55) dispatchers
    legacy = [
        ["hyprctl", "dispatch", "focuswindow", selector],
        ["hyprctl", "dispatch", "setfloating", "1"],
        ["hyprctl", "dispatch", "pin"],
        ["hyprctl", "dispatch", "alterzorder", "top"],
    ]
    ok = True
    for cmd in legacy:
        try:
            subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=2)
        except (OSError, subprocess.SubprocessError):
            ok = False
    return ok



def list_windows() -> list[HyprWindow]:
    """Return mapped clients from `hyprctl clients -j`, or [] if unavailable."""
    if not hyprctl_available():
        return []

    try:
        proc = subprocess.run(
            ["hyprctl", "clients", "-j"],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    try:
        clients = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return []

    windows: list[HyprWindow] = []
    for client in clients:
        if not isinstance(client, dict):
            continue
        if client.get("mapped") is False:
            continue
        # Skip special / empty shells that are not useful to clone
        title = str(client.get("title") or "")
        class_name = str(client.get("class") or "")
        if not title and not class_name:
            continue
        workspace = client.get("workspace") or {}
        ws_name = ""
        if isinstance(workspace, dict):
            ws_name = str(workspace.get("name") or workspace.get("id") or "")
        windows.append(
            HyprWindow(
                address=str(client.get("address") or ""),
                title=title,
                class_name=class_name,
                workspace=ws_name,
            )
        )

    windows.sort(key=lambda w: (w.workspace, w.title.lower()))
    return windows
