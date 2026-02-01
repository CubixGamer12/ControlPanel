import os
import subprocess
import gi
import distro
import platform
import psutil
import re
import datetime
import socket 
import time
import threading
import urllib.request

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, GLib, GObject, Gdk

class LinuxUtilityApp(Adw.Application):
    
    def __init__(self):
        super().__init__(application_id='com.example.LinuxUtility',
                         flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.cpu_history = [0] * 50
        self.mem_history = [0] * 50

    def get_resource_path(self, relative_path):
        import sys
        base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base_path, relative_path)

    def do_activate(self):
        win = Adw.ApplicationWindow(application=self)
        win.set_title("Control Panel")
        win.set_default_size(650, 900)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        win.set_content(content)

        header = Adw.HeaderBar()
        content.append(header)

        self.view_stack = Adw.ViewStack()
        self.view_stack.set_vexpand(True)
        
        # TAB 1: TOOLS
        self.view_stack.add_titled_with_icon(self.create_tools_page(), "tools", "Tools", "emblem-system-symbolic")

        # TAB 2: DIAGNOSTICS
        self.view_stack.add_titled_with_icon(self.create_info_page(), "info", "Diagnostics", "dialog-information-symbolic")

        view_switcher = Adw.ViewSwitcher(stack=self.view_stack)
        header.set_title_widget(view_switcher)
        content.append(self.view_stack)

        view_switcher_bar = Adw.ViewSwitcherBar(stack=self.view_stack)
        view_switcher_bar.set_reveal(True)
        content.append(view_switcher_bar)
        
        win.present()
        
        GLib.timeout_add(2000, self.refresh_data)

    # --- GRAPH LOGIC ---
    def create_graph(self, label_text, color):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        label = Gtk.Label(label=label_text, halign=Gtk.Align.START)
        vbox.append(label)
        area = Gtk.DrawingArea(content_height=80, vexpand=False)
        area.set_draw_func(self.draw_perf_graph, color)
        vbox.append(area)
        return vbox, label, area

    def draw_perf_graph(self, area, cr, width, height, color):
        history = self.cpu_history if color == "blue" else self.mem_history
        cr.set_source_rgba(0.1, 0.1, 0.1, 0.2)
        cr.rectangle(0, 0, width, height)
        cr.fill()
        if color == "blue": cr.set_source_rgb(0.2, 0.5, 0.9)
        else: cr.set_source_rgb(0.1, 0.8, 0.4)
        cr.set_line_width(2)
        step = width / (len(history) - 1) if len(history) > 1 else 0
        cr.move_to(0, height)
        for i, val in enumerate(history):
            cr.line_to(i * step, height - (val / 100.0 * height))
        cr.line_to(width, height)
        cr.fill_preserve()
        cr.stroke()

    # --- TOOLS PAGE ---
    def create_tools_page(self):
        list_box = Gtk.ListBox(css_classes=["boxed-list"])
        list_box.set_selection_mode(Gtk.SelectionMode.NONE)

        # Update Row
        update_row = Adw.ActionRow(title="System Update", subtitle=f"Detected: {distro.name(pretty=True)}")
        update_btn = Gtk.Button(icon_name="software-update-available-symbolic", valign=Gtk.Align.CENTER, css_classes=["suggested-action"])
        update_btn.connect("clicked", self.on_system_update)
        update_row.add_suffix(update_btn)
        list_box.append(update_row)

        # Install Packages Row
        install_row = Adw.ActionRow(
            title="Install Packages",
            subtitle="Install predefined packages via system package manager"
        )
        install_btn = Gtk.Button(
            icon_name="system-software-install-symbolic",
            valign=Gtk.Align.CENTER
        )
        install_btn.connect("clicked", self.on_install_packages)
        install_row.add_suffix(install_btn)
        list_box.append(install_row)

        # Flatpak Install row
        flatpak_row = Adw.ActionRow(
            title="Install Flatpaks",
            subtitle="Install predefined Flatpak applications"
        )
        flatpak_btn = Gtk.Button(
            icon_name="flatpak-symbolic",
            valign=Gtk.Align.CENTER)
        flatpak_btn.connect(
            "clicked",
            lambda x: self.open_terminal(self.install_flatpaks())
        )
        flatpak_row.add_suffix(flatpak_btn)
        list_box.append(flatpak_row)

        # Ping Row
        ping_row = Adw.ActionRow(title="Network Latency Test", subtitle="Ping Google DNS (8.8.8.8)")
        ping_btn = Gtk.Button(label="Run Ping", valign=Gtk.Align.CENTER)
        ping_btn.connect("clicked", lambda x: self.run_ping_test())
        ping_row.add_suffix(ping_btn)
        list_box.append(ping_row)
        
        # MangoHud Row
        if os.path.exists(os.path.expanduser("~/.config/MangoHud")):
            mango_row = Adw.ActionRow(title="MangoHud Toggle", subtitle="Swap local config to ~/.config/MangoHud/")
            mango_sw = Gtk.Switch(active=self.get_config_status("MangoHud.conf"), valign=Gtk.Align.CENTER)
            mango_sw.connect("state-set", self.on_config_toggle, "MangoHud.conf", "~/.config/MangoHud/MangoHud.conf")
            mango_row.add_suffix(mango_sw)
            list_box.append(mango_row)

        # Pivor Row
        if os.path.exists(os.path.expanduser("~/.config/hypr")):
            pivot_row = Adw.ActionRow(title="Monitor Pivot (DP-2)", subtitle="Swap Hyprland layout config")
            pivot_sw = Gtk.Switch(active=self.get_config_status("general.conf"), valign=Gtk.Align.CENTER)
            pivot_sw.connect("state-set", self.on_config_toggle, "general.conf", "~/.config/hypr/hyprland/general.conf")
            pivot_row.add_suffix(pivot_sw)
            list_box.append(pivot_row)

        return self.wrap_in_resizable_view(list_box)

    # --- DIAGNOSTICS PAGE ---
    def create_info_page(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)

        # Graphs
        cpu_g, self.cpu_label, self.cpu_draw_area = self.create_graph("CPU Graph: ...", "blue")
        mem_g, self.mem_label, self.mem_draw_area = self.create_graph("Memory Graph: ...", "green")
        vbox.append(cpu_g); vbox.append(mem_g)

        # 1. Software & OS
        vbox.append(self.create_spec_group("Software &amp; OS", [
            ("Distro", distro.name(pretty=True), "distributor-logo-linux-symbolic"),
            ("Kernel", platform.release(), "slint-symbolic"),
            ("Uptime", self.get_uptime(), "preferences-system-time-symbolic"),
            ("Desktop", os.environ.get('XDG_CURRENT_DESKTOP', 'N/A'), "window-new-symbolic"),
            ("Session", os.environ.get('XDG_SESSION_TYPE', 'N/A'), "window-restore-symbolic"),
            ("Shell", os.environ.get('SHELL', 'N/A').split('/')[-1], "utilities-terminal-symbolic")
        ]))

        # 2. Processor & Performance
        vbox.append(self.create_spec_group("Processor &amp; Performance", [
            ("CPU Model", self.get_cpu_info(), "processor-symbolic"),
            ("Cores", f"{psutil.cpu_count(logical=False)} Phys / {psutil.cpu_count()} Log", "processor-symbolic"),
            ("CPU Temp", self.get_temp(), "sensors-temperature-symbolic")
        ]))

        # 3. Memory & Storage Analysis
        storage_items = [
            ("Total RAM", f"{round(psutil.virtual_memory().total / 1e9, 2)} GB", "ram-symbolic"),
            ("Available", f"{round(psutil.virtual_memory().available / 1e9, 2)} GB", "ram-symbolic")
        ]
        for part in psutil.disk_partitions():
            if part.fstype in ['ext4', 'btrfs', 'xfs', 'ntfs', 'vfat']:
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    storage_items.append((f"Disk ({part.mountpoint})", f"{usage.percent}% Used of {round(usage.total/1e9, 1)} GB", "drive-harddisk-symbolic"))
                except: continue
        vbox.append(self.create_spec_group("Memory &amp; Storage Analysis", storage_items))

        # 4. Graphics & Display
        vbox.append(self.create_spec_group("Graphics &amp; Display", [
            ("GPU Model", self.get_gpu_info(), "video-display-symbolic"),
            ("Vulkan API", self.get_vulkan_version(), "applications-games-symbolic"),
            ("OpenGL", self.get_opengl_version(), "video-display-symbolic")
        ]))

        # 5. Connectivity & Health
        conn_items = [
            ("Local IP", self.get_ip(), "network-transmit-receive-symbolic"),
            ("Battery", self.get_battery(), "battery-full-symbolic"),
            ("Fan Speed", self.get_fans(), "sensors-fan-symbolic")
        ]
        
        conn_group = self.create_spec_group("Connectivity &amp; Health", conn_items)
        
        self.pub_ip_row = Adw.ActionRow(title="Public IP", subtitle="Click to check")
        self.pub_ip_row.add_prefix(Gtk.Image.new_from_icon_name("network-wired-symbolic"))
        pub_ip_btn = Gtk.Button(icon_name="view-refresh-symbolic", valign=Gtk.Align.CENTER)
        pub_ip_btn.connect("clicked", self.update_public_ip)
        self.pub_ip_row.add_suffix(pub_ip_btn)
        
        list_box = conn_group.get_last_child() 
        if isinstance(list_box, Gtk.ListBox):
            list_box.insert(self.pub_ip_row, 1)
        
        vbox.append(conn_group)

        return self.wrap_in_resizable_view(vbox)

    # --- LOGIC FUNCTIONS ---

    def update_public_ip(self, btn):
        self.pub_ip_row.set_subtitle("Fetching...")
        def fetch():
            try:
                with urllib.request.urlopen('https://api.ipify.org', timeout=5) as response:
                    ip = response.read().decode('utf-8')
                    GLib.idle_add(self.pub_ip_row.set_subtitle, ip)
            except:
                GLib.idle_add(self.pub_ip_row.set_subtitle, "Error/Timeout")
        threading.Thread(target=fetch, daemon=True).start()

    def run_ping_test(self):
        full_bash_cmd = "echo 'Testing connection to Google DNS...'; ping -c 4 8.8.8.8; echo -e '\nDone!'; sleep 3"
        self.open_terminal(full_bash_cmd)

    def open_terminal(self, cmd):
        terminal = "xterm"
        for t in ["gnome-terminal", "konsole", "xfce4-terminal", "alacritty", "kitty", "foot"]:
            if subprocess.run(f"command -v {t}", shell=True, capture_output=True).returncode == 0:
                terminal = t
                break
        if terminal == "gnome-terminal":
            subprocess.Popen(["gnome-terminal", "--", "bash", "-c", cmd])
        else:
            subprocess.Popen([terminal, "-e", f"bash -c \"{cmd}\""])

    def refresh_data(self):
        cpu_val = psutil.cpu_percent()
        mem_val = psutil.virtual_memory().percent
        self.cpu_history.pop(0); self.cpu_history.append(cpu_val)
        self.mem_history.pop(0); self.mem_history.append(mem_val)
        
        if hasattr(self, 'cpu_label'): self.cpu_label.set_text(f"CPU Graph: {cpu_val:.1f}%")
        if hasattr(self, 'mem_label'): self.mem_label.set_text(f"Memory Graph: {mem_val:.1f}%")
        if hasattr(self, 'cpu_draw_area'): self.cpu_draw_area.queue_draw()
        if hasattr(self, 'mem_draw_area'): self.mem_draw_area.queue_draw()

        return True

    # --- PROBES ---
    def get_vulkan_version(self):
        try:
            out = subprocess.check_output("vulkaninfo --summary", shell=True, stderr=subprocess.DEVNULL).decode()
            return re.search(r'Vulkan Instance Version: (\d+\.\d+\.\d+)', out).group(1)
        except: return "N/A"

    def get_opengl_version(self):
        try:
            out = subprocess.check_output("glxinfo | grep 'OpenGL version string'", shell=True, stderr=subprocess.DEVNULL).decode()
            return out.split(":")[1].strip()
        except: return "N/A"

    def get_temp(self):
        try:
            hwmon_path = '/sys/class/hwmon/'
            if os.path.exists(hwmon_path):
                for folder in os.listdir(hwmon_path):
                    path = os.path.join(hwmon_path, folder)
                    try:
                        name = open(os.path.join(path, 'name')).read().strip()
                        if name in ['coretemp', 'k10temp', 'zenpatch']:
                            for file in os.listdir(path):
                                if file.endswith('_label'):
                                    label = open(os.path.join(path, file)).read().strip()
                                    if label in ['Package id 0', 'Tdie', 'Tctl']:
                                        temp_file = file.replace('_label', '_input')
                                        val = int(open(os.path.join(path, temp_file)).read())
                                        return f"{val // 1000}°C"
                    except: continue
            return "N/A"
        except: return "N/A"

    def get_fans(self):
        try:
            fans = psutil.sensors_fans()
            for chip, entries in fans.items():
                for entry in entries:
                    if entry.current > 0: return f"{entry.current} RPM"
            return "0 RPM"
        except: return "N/A"

    def get_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80)); ip = s.getsockname()[0]; s.close(); return ip
        except: return "127.0.0.1"

    def get_battery(self):
        b = psutil.sensors_battery()
        return f"{int(b.percent)}% ({'Plugged' if b.power_plugged else 'Battery'})" if b else "N/A"

    def get_gpu_info(self):
        try:
            out = subprocess.check_output("glxinfo | grep 'Device:'", shell=True, stderr=subprocess.DEVNULL).decode()
            return out.split(":")[1].strip()
        except: return "Unknown"

    def get_cpu_info(self):
        try: return subprocess.check_output("grep -m 1 'model name' /proc/cpuinfo | cut -d: -f2", shell=True).decode().strip()
        except: return platform.processor()

    def get_uptime(self):
        return str(datetime.timedelta(seconds=int(time.time() - psutil.boot_time())))

    # --- UI HELPERS ---
    def create_spec_group(self, title, items):
        group = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        label = Gtk.Label(label=f"<b>{title}</b>", use_markup=True, halign=Gtk.Align.START)
        group.append(label)
        list_box = Gtk.ListBox(css_classes=["boxed-list"])
        list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        for name, val, icon in items:
            row = Adw.ActionRow(title=name, subtitle=str(val))
            row.add_prefix(Gtk.Image.new_from_icon_name(icon))
            list_box.append(row)
        group.append(list_box)
        return group

    def wrap_in_resizable_view(self, child):
        scrolled = Gtk.ScrolledWindow(vexpand=True)
        scrolled.set_propagate_natural_height(True)
        clamp = Adw.Clamp(maximum_size=520, child=child)
        clamp.set_margin_top(20); clamp.set_margin_bottom(20)
        clamp.set_margin_start(20); clamp.set_margin_end(20)
        scrolled.set_child(clamp)
        return scrolled

    def get_config_status(self, filename):
        targets = {"general.conf": "~/.config/hypr/hyprland/general.conf", "MangoHud.conf": "~/.config/MangoHud/MangoHud.conf"}
        path = os.path.expanduser(targets.get(filename))
        if not os.path.islink(path): return False
        try:
            link_target = os.readlink(path)
            return ".pivot" in link_target or ".enabled" in link_target
        except: return False

    def on_config_toggle(self, widget, state, filename, target_path):
        ext = ("pivot" if state else "original") if filename == "general.conf" else ("enabled" if state else "disabled")
        source = self.get_resource_path(os.path.join("configs", f"{filename}.{ext}"))
        target = os.path.expanduser(target_path)
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if os.path.exists(target) or os.path.islink(target): os.remove(target)
            os.symlink(source, target)
        except: pass
        return False

    def on_system_update(self, btn):
        package_managers = {
            "pacman": "sudo pacman -Syu",
            "apt": "sudo apt update && sudo apt upgrade -y",
            "dnf": "sudo dnf upgrade -y",
            "zypper": "sudo zypper dup",
            "eopkg": "sudo eopkg up",
            "xbps-install": "sudo xbps-install -Syu",
            "emerge": "sudo emerge --sync && sudo emerge -uDN @world",
            "apk": "sudo apk upgrade",
            "nix-env": "nix-env -u",
        }

        update_cmd = None
        for binary, cmd in package_managers.items():
            if subprocess.run(
                f"command -v {binary}",
                shell=True,
                capture_output=True
            ).returncode == 0:
                update_cmd = cmd
                break

        if not update_cmd:
            update_cmd = "echo 'No supported system package manager found!'"

        flatpak_update = self.update_flatpaks()

        full_cmd = (
            "echo '=== SYSTEM UPDATE ==='; "
            f"{update_cmd}; "
            "echo; echo '=== FLATPAK UPDATE ==='; "
            f"{flatpak_update}; "
            "echo; echo 'All updates completed.'; "
            "sleep 5"
        )

        self.open_terminal(full_cmd)


    def get_packages_to_install(self):
        return [
            "git",
            "curl",
            "wget",
            "mangohud",
            "cmake",
            "make",
            "mpv",
            "flatpak",
            "steam",
            "python",
            "python-pip",
            "gtk4",
            "gamemode",
            "gamescope",
            "ark",
            "bitwarden",
            "smartmontools",
            "fuse",
            "zen-browser-bin",
        ]

    def on_install_packages(self, btn):
        packages = self.get_packages_to_install()
        if not packages:
            self.open_terminal("echo 'No packages defined'; sleep 3")
            return

        pkg_str = " ".join(packages)

        managers = {
            "pacman": f"sudo pacman -S --needed {pkg_str}",
            "apt": f"sudo apt update && sudo apt install -y {pkg_str}",
            "dnf": f"sudo dnf install -y {pkg_str}",
            "zypper": f"sudo zypper install -y {pkg_str}",
            "xbps-install": f"sudo xbps-install -S {pkg_str}",
            "eopkg": f"sudo eopkg install -y {pkg_str}",
            "apk": f"sudo apk add {pkg_str}",
            "emerge": f"sudo emerge {pkg_str}",
            "nix-env": f"nix-env -i {pkg_str}",
        }

        install_cmd = None
        for binary, cmd in managers.items():
            if subprocess.run(
                f"command -v {binary}",
                shell=True,
                capture_output=True
            ).returncode == 0:
                install_cmd = cmd
                break

        if not install_cmd:
            install_cmd = "echo 'No supported package manager found!'"

        full_cmd = (
            f"echo 'Installing packages:'; echo '{pkg_str}'; echo; "
            f"{install_cmd}; "
            f"echo; echo 'Done.'; sleep 5"
        )

        self.open_terminal(full_cmd)

    def get_flatpaks_to_install(self):
        return [
            "com.dec05eba.gpu_screen_recorder",
            "com.github.taiko2k.tauonmb",
            "com.github.xournalpp.xournalpp",
            "com.vysp3r.ProtonPlus",
            "io.github.Faugus.faugus-launcher",
            "io.github.peazip.PeaZip",
            "io.github.ilya_zlobintsev.LACT",
            "net.nokyan.Resources",
            "org.equicord.equibop",
        ]

    def install_flatpaks(self):
        flatpaks = self.get_flatpaks_to_install()
        if not flatpaks:
            return "echo 'No Flatpaks defined'; sleep 3"

        flatpak_list = " ".join(flatpaks)

        script = (
            "#!/bin/bash\n"
            "command -v flatpak >/dev/null 2>&1 || {\n"
            "  echo \"Flatpak not installed!\";\n"
            "  sleep 5;\n"
            "  exit 1;\n"
            "}\n"
            "\n"
            "MISSING=\"\"\n"
            "\n"
            f"set -- {flatpak_list}\n"
            "\n"
            "for fp in \"$@\"; do\n"
            "  if ! flatpak info \"$fp\" >/dev/null 2>&1; then\n"
            "    MISSING=\"$MISSING $fp\"\n"
            "  fi\n"
            "done\n"
            "\n"
            "if [ -z \"$MISSING\" ]; then\n"
            "  echo \"All Flatpaks are already installed.\"\n"
            "  echo \"Closing in 5 seconds...\"\n"
            "  sleep 5\n"
            "  exit 0\n"
            "fi\n"
            "\n"
            "echo \"Installing missing Flatpaks:\"\n"
            "echo \"$MISSING\"\n"
            "echo\n"
            "\n"
            "if flatpak install -y flathub $MISSING; then\n"
            "  echo\n"
            "  echo \"SUCCESSFUL\"\n"
            "else\n"
            "  echo\n"
            "  echo \"ERROR during installation\"\n"
            "fi\n"
            "\n"
            "echo \"Closing in 5 seconds...\"\n"
            "sleep 5\n"
        )

        return script



    def update_flatpaks(self):
        return (
            "command -v flatpak >/dev/null || "
            "(echo 'Flatpak not installed!' && sleep 5 && exit); "
            "flatpak update -y"
        )


if __name__ == "__main__":
    app = LinuxUtilityApp()
    app.run(None)