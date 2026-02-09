#!/usr/bin/env python3
import os
import sys
import subprocess
import threading
import shutil
from pathlib import Path

# Modern Uninstaller for Control Panel
# Mirroring the installer's look and feel for a consistent experience

try:
    import gi
    gi.require_version('Gtk', '4.0')
    gi.require_version('Adw', '1')
    from gi.repository import Gtk, Adw, Gio, GLib, Gdk
except ImportError:
    print("Modern Uninstaller requires 'python-gobject', 'gtk4', and 'libadwaita'.")
    print("Please install these dependencies manually first.")
    sys.exit(1)

APP_NAME = "Control Panel"
DESKTOP_FILENAME = "ControlPanel.desktop"

class ControlPanelUninstaller(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id='org.cubixgamer.ControlPanelUninstaller',
            flags=Gio.ApplicationFlags.FLAGS_NONE
        )
        self.desktop_path = Path.home() / ".local/share/applications" / DESKTOP_FILENAME

    def apply_custom_css(self):
        css = """
        window {
            background-color: @window_bg_color;
        }
        statuspage {
            margin: 24px;
        }
        .welcome-title {
            font-size: 2.2em;
            font-weight: 800;
            background-image: linear-gradient(135deg, @accent_color, @accent_bg_color);
            color: @accent_color;
        }
        .pill {
            padding: 12px 32px;
            font-weight: bold;
        }
        .destructive-btn {
            background-color: @destructive_bg_color;
            color: @destructive_fg_color;
        }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def do_activate(self):
        self.apply_custom_css()

        self.win = Adw.ApplicationWindow(application=self, title="Control Panel Uninstaller")
        self.win.set_default_size(500, 600)

        self.stack = Adw.ViewStack()
        clamp = Adw.Clamp(maximum_size=1000)
        clamp.set_child(self.stack)
        self.win.set_content(clamp)

        # --- Welcome Page ---
        welcome_page = Adw.StatusPage(
            title="Uninstall Control Panel?",
            description="All shortcuts and application registration will be removed.",
            icon_name="user-trash-full-symbolic"
        )
        
        btns_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12, halign=Gtk.Align.CENTER)
        
        cancel_btn = Gtk.Button(label="Keep It", css_classes=["pill"])
        cancel_btn.connect("clicked", lambda x: self.quit())
        
        uninst_btn = Gtk.Button(
            label="Remove Application", 
            css_classes=["destructive-action", "pill"]
        )
        uninst_btn.connect("clicked", self.on_start_uninstall)
        
        btns_box.set_margin_top(24)
        btns_box.append(cancel_btn)
        btns_box.append(uninst_btn)
        
        welcome_page.set_child(btns_box)
        self.stack.add_titled(welcome_page, "welcome", "Welcome")

        # --- Removal Page ---
        self.removal_page = Adw.StatusPage(
            title="Removing Files",
            description="Cleaning up system shortcuts...",
            icon_name="process-working-symbolic"
        )
        self.stack.add_titled(self.removal_page, "removal", "Removal")

        # --- Success Page ---
        success_page = Adw.StatusPage(
            title="Successfully Removed",
            description="Control Panel has been uninstalled from your system.\n\nNote: System dependencies (Gtk, psutil, etc.) were skipped to keep other apps stable.",
            icon_name="emblem-ok-symbolic"
        )
        close_btn = Gtk.Button(
            label="Close Uninstaller", 
            halign=Gtk.Align.CENTER, 
            css_classes=["suggested-action", "pill"]
        )
        close_btn.set_margin_top(24)
        close_btn.connect("clicked", lambda x: self.quit())
        success_page.set_child(close_btn)
        self.stack.add_titled(success_page, "success", "Success")

        self.win.present()

    def on_start_uninstall(self, btn):
        self.stack.set_visible_child_name("removal")
        
        def run_removal():
            try:
                # 1. Remove Desktop File
                if self.desktop_path.exists():
                    os.remove(self.desktop_path)
                
                # Use idle_add for UI updates
                GLib.idle_add(lambda: self.stack.set_visible_child_name("success"))
            except Exception as e:
                GLib.idle_add(lambda: self.removal_page.set_description(f"Error: {e}"))

        threading.Thread(target=run_removal, daemon=True).start()

if __name__ == "__main__":
    app = ControlPanelUninstaller()
    app.run(sys.argv)
