"""GTK application entry point."""

from __future__ import annotations

import logging
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

from gi.repository import Gtk

from .main_window import MainWindow


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    app = Gtk.Application(application_id="io.github.ontopreplica.linux")

    def on_activate(application: Gtk.Application) -> None:
        win = application.get_active_window()
        if win is None:
            win = MainWindow(application)
        win.present()

    app.connect("activate", on_activate)
    return app.run(argv if argv is not None else sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
