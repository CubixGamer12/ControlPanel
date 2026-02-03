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
import shutil

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, GLib, GObject, Gdk

# ==============================
# SYSTEM PROFILES CONFIG
# ==============================

SYSTEM_PROFILES = {
    "minimal": {
        "packages": [
            "git", "curl", "wget", "htop", "nano", "zen-browser-bin", "mpv",
            "flatpak", "cmake", "make", "python", "python-pip",
            "ark", "fuse", "snapper", "bitwarden", "smartmontools",
        ],
        "services_enable": [],
        "services_disable": [],
        "post_cmd": []
    },

    "gaming": {
        "packages": [
            "steam", "mangohud", "gamemode",
            "gamescope", "lutris", "heroic-games-launcher-bin",
            "git", "curl", "wget", "htop", "nano", "zen-browser-bin", "mpv",
            "flatpak", "cmake", "make", "python", "python-pip",
            "ark", "fuse", "snapper", "bitwarden", "smartmontools",
        ],
        "services_enable": ["gamemoded"],
        "services_disable": [],
        "post_cmd": []
    }
}


class LinuxUtilityApp(Adw.Application):
    
    def __init__(self):
        super().__init__(application_id='Control Panel',
                         flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.cpu_history = [0] * 50
        self.mem_history = [0] * 50
        self.freq_history = [0] * 50
        self.swap_history = [0] * 50

    def get_resource_path(self, relative_path):
        import sys
        base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base_path, relative_path)

    def do_activate(self):
        win = Adw.ApplicationWindow(application=self)
        win.set_title("Control Panel")
        win.set_default_size(650, 900)

        self.toast_overlay = Adw.ToastOverlay()
        win.set_content(self.toast_overlay)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.toast_overlay.set_child(content)

        header = Adw.HeaderBar()
        content.append(header)

        self.view_stack = Adw.ViewStack()
        self.view_stack.set_vexpand(True)
        
        # TAB 1: TOOLS
        self.view_stack.add_titled_with_icon(self.create_tools_page(), "tools", "Tools", "preferences-other-symbolic")

        # TAB 2: UTILITIES
        self.view_stack.add_titled_with_icon(
            self.create_utilities_page(),
            "utils",
            "Utilities",
            "applications-system-symbolic"
        )

        # TAB 3: DIAGNOSTICS
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
        graph_map = {
            "blue":   (self.cpu_history,  (0.2, 0.5, 0.9)),
            "green":  (self.mem_history,  (0.1, 0.8, 0.4)),
            "orange": (self.swap_history, (1.0, 0.5, 0.1)),
        }

        if color not in graph_map:
            return

        history, rgb = graph_map[color]

        cr.set_source_rgba(0.1, 0.1, 0.1, 0.2)
        cr.rectangle(0, 0, width, height)
        cr.fill()

        if len(history) < 2:
            return

        cr.set_source_rgb(*rgb)
        cr.set_line_width(2)

        step = width / (len(history) - 1)
        cr.move_to(0, height)

        for i, val in enumerate(history):
            val = max(0, min(val, 100))
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

        # CUPS Row
        cups_row = Adw.ActionRow(
            title="Install CUPS",
            subtitle="Install printer system and Printer drivers"
        )
        cups_btn = Gtk.Button(icon_name="printer-symbolic", valign=Gtk.Align.CENTER)
        cups_btn.connect("clicked", lambda x: self.install_cups_and_canon())
        cups_row.add_suffix(cups_btn)
        list_box.append(cups_row)

        # ---- Profiles Packages ----
        profile_row = Adw.ActionRow(
            title="System Profile",
            subtitle="Apply predefined system configuration"
        )

        self.profile_combo = Gtk.ComboBoxText()
        for profile in ["minimal", "gaming"]:
            self.profile_combo.append_text(profile)
        self.profile_combo.set_active(0)

        profile_row.add_suffix(self.profile_combo)

        apply_btn = Gtk.Button(icon_name="checkmark-symbolic", css_classes=["suggested-action"])
        apply_btn.set_valign(Gtk.Align.CENTER)
        apply_btn.connect("clicked", self.apply_profile)
        profile_row.add_suffix(apply_btn)

        list_box.append(profile_row)

        # ---- BTRFS SNAPSHOTS ----
        if self.is_btrfs() and self.has_snapper():
            snapshot_row = Adw.ActionRow(
                title="Create Btrfs Snapshot",
                subtitle="Create system snapshot (root)"
            )
            snapshot_btn = Gtk.Button.new_from_icon_name("camera-photo-symbolic")
            snapshot_btn.set_valign(Gtk.Align.CENTER)
            snapshot_btn.connect(
                "clicked",
                lambda x: self.open_terminal(
                    "sudo snapper -c root create --description 'Manual snapshot from Control Panel'; sleep 3"
                )
            )
            snapshot_row.add_suffix(snapshot_btn)
            list_box.append(snapshot_row)

            snap_list_row = Adw.ActionRow(
                title="View Btrfs Snapshots",
                subtitle="List available system snapshots"
            )
            snap_list_btn = Gtk.Button.new_from_icon_name("view-list-symbolic")
            snap_list_btn.set_valign(Gtk.Align.CENTER)
            snap_list_btn.connect(
                "clicked",
                lambda x: self.open_terminal("sudo snapper list; read")
            )
            snap_list_row.add_suffix(snap_list_btn)
            list_box.append(snap_list_row)

        else:
            snapshot_row = Adw.ActionRow(
                title="Create Btrfs Snapshot",
                subtitle="Btrfs snapshots not supported on this system",
                sensitive=False
            )
            list_box.append(snapshot_row)

            snap_list_row = Adw.ActionRow(
                title="View Btrfs Snapshots",
                subtitle="Btrfs snapshots not supported on this system",
                sensitive=False
            )
            list_box.append(snap_list_row)


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

        swap_g, self.swap_label, self.swap_area = self.create_graph("Swap Usage", "orange")
        vbox.append(swap_g)

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

    def create_utilities_page(self):
        list_box = Gtk.ListBox(css_classes=["boxed-list"])
        list_box.set_selection_mode(Gtk.SelectionMode.NONE)

        # Restart NetworkManager
        nm_row = Adw.ActionRow(
            title="Restart Network",
            subtitle="Restart NetworkManager service"
        )
        nm_btn = Gtk.Button(label="Restart", valign=Gtk.Align.CENTER)
        nm_btn.connect(
            "clicked",
            lambda x: self.open_terminal(
                "sudo systemctl restart NetworkManager && echo 'Done' && sleep 3"
            )
        )
        nm_row.add_suffix(nm_btn)
        list_box.append(nm_row)

        # Restart Audio (PipeWire)
        audio_row = Adw.ActionRow(
            title="Restart Audio",
            subtitle="Restart PipeWire / WirePlumber"
        )
        audio_btn = Gtk.Button(label="Restart", valign=Gtk.Align.CENTER)
        audio_btn.connect(
            "clicked",
            lambda x: self.open_terminal(
                "systemctl --user restart pipewire pipewire-pulse wireplumber && echo 'Done' && sleep 3"
            )
        )
        audio_row.add_suffix(audio_btn)
        list_box.append(audio_row)

        # Clear cache
        cache_row = Adw.ActionRow(
            title="Clear Cache",
            subtitle="Clear user cache (~/.cache)"
        )
        cache_btn = Gtk.Button(icon_name="edit-clear-symbolic", valign=Gtk.Align.CENTER)
        cache_btn.connect(
            "clicked",
            lambda x: self.open_terminal(
                "rm -rf ~/.cache/* && echo 'Cache cleared' && sleep 3"
            )
        )
        cache_row.add_suffix(cache_btn)
        list_box.append(cache_row)

        # Flatpak repair
        flatpak_fix_row = Adw.ActionRow(
            title="Flatpak Repair",
            subtitle="Fix broken Flatpak installations"
        )
        flatpak_fix_btn = Gtk.Button(
            icon_name="flatpak-symbolic",
            valign=Gtk.Align.CENTER
        )
        flatpak_fix_btn.connect(
            "clicked",
            lambda x: self.open_terminal(
                "flatpak repair -y && echo 'Done' && sleep 5"
            )
        )
        flatpak_fix_row.add_suffix(flatpak_fix_btn)
        list_box.append(flatpak_fix_row)

        # Open config folder
        cfg_row = Adw.ActionRow(
            title="Open Config Folder",
            subtitle="Open ~/.config in file manager"
        )
        cfg_btn = Gtk.Button(icon_name="folder-open-symbolic", valign=Gtk.Align.CENTER)
        cfg_btn.connect("clicked", lambda x: self.open_config_folder())
        cfg_row.add_suffix(cfg_btn)
        list_box.append(cfg_row)

        #GAME PREFIX
        game_prefix = (
            "mangohud gamemoderun gamescope "
            "-W 1920 -H 1080 -r 75 "
            "--force-grab-cursor -f -- %command%"
        )

        prefix_row = Adw.ActionRow(
            title="Game Prefix",
            subtitle=game_prefix
        )

        prefix_row.set_subtitle_selectable(True)

        copy_btn = Gtk.Button(
            icon_name="edit-copy-symbolic",
            valign=Gtk.Align.CENTER
        )

        copy_btn.connect(
            "clicked",
            lambda x: self.copy_to_clipboard(game_prefix)
        )

        prefix_row.add_suffix(copy_btn)
        list_box.append(prefix_row)


        # Logout
        logout_row = Adw.ActionRow(
            title="Logout",
            subtitle="End current session"
        )
        logout_btn = Gtk.Button(
            icon_name="system-log-out-symbolic",
            valign=Gtk.Align.CENTER,
            css_classes=["destructive-action"]
        )
        logout_btn.connect(
            "clicked",
            lambda x: self.open_terminal(
                "loginctl terminate-user $USER"
            )
        )
        logout_row.add_suffix(logout_btn)
        list_box.append(logout_row)

        return self.wrap_in_resizable_view(list_box)

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
        swap = psutil.swap_memory().percent
        self.swap_history.pop(0)
        self.swap_history.append(swap)

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
        backup_dir = os.path.join(os.path.dirname(target), "backup")
        
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if filename != "MangoHud.conf":
                os.makedirs(backup_dir, exist_ok=True)

            if not os.path.exists(target):
                open(target, "a").close()
                print(f"[INFO] Created missing config file: {target}")

            if os.path.exists(target) and filename != "MangoHud.conf":
                backup_file = os.path.join(backup_dir, os.path.basename(target))
                
                backup_file = backup_file.replace(".pivot", "").replace(".enabled", "")
                
                if os.path.exists(backup_file):
                    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
                    backup_file = f"{backup_file}.{timestamp}"
                
                shutil.move(target, backup_file)
                print(f"[INFO] Moved old config to backup: {backup_file}")
            
            shutil.copy2(source, target)
            print(f"[INFO] Copied {source} -> {target}")
            
            if filename != "MangoHud.conf":
                subprocess.run(["hyprctl", "reload"], check=False)
                print("[INFO] Hyprland reloaded")
            
        except Exception as e:
            print(f"[ERROR] Failed to toggle config: {e}")
        
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
            "lutris",
            "heroic-games-launcher-bin",
            "snapper",
        ]

        if not self.is_btrfs():
            packages = [p for p in packages if p != "snapper"]

        return packages

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
            "it.mijorus.gearlever",
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

    def install_cups_and_canon(self):
        import shutil
        import time

        required = ["cups", "gutenprint"]

        package_cmds = {
            "apt": "sudo apt update && sudo apt install -y {}",
            "pacman": "sudo pacman -S --needed {}",
            "dnf": "sudo dnf install -y {}",
            "zypper": "sudo zypper install -y {}",
            "xbps-install": "sudo xbps-install -S {}",
            "apk": "sudo apk add {}",
            "emerge": "sudo emerge {}",
            "nix-env": "nix-env -iA nixpkgs.{}"
        }

        pkg_manager = None
        for mgr in package_cmds.keys():
            if shutil.which(mgr):
                pkg_manager = mgr
                break

        if not pkg_manager:
            self.open_terminal("echo 'No supported package manager found!' && sleep 5")
            return

        missing = []
        for pkg in required:
            if pkg_manager in ["apt", "dnf", "zypper", "apk"]:
                check_cmd = f"dpkg -s {pkg}" if pkg_manager == "apt" else f"rpm -q {pkg}"
            elif pkg_manager == "pacman":
                check_cmd = f"pacman -Qi {pkg}"
            elif pkg_manager == "xbps-install":
                check_cmd = f"xbps-query -Rs {pkg}"
            elif pkg_manager == "emerge":
                check_cmd = f"equery list {pkg}"
            elif pkg_manager == "nix-env":
                check_cmd = f"nix-env -q {pkg}"
            else:
                check_cmd = ""

            if check_cmd:
                result = subprocess.run(check_cmd, shell=True, capture_output=True)
                if result.returncode != 0:
                    missing.append(pkg)

        if not missing:
            self.open_terminal("echo 'CUPS and Printer drivers are already installed!' && sleep 5")
            return

        pkg_str = " ".join(missing)
        install_cmd = package_cmds[pkg_manager].format(pkg_str)
        full_cmd = f"echo 'Installing missing packages: {pkg_str}'; {install_cmd}; echo 'Done.'; sleep 5"
        self.open_terminal(full_cmd)

    def open_config_folder(self):
        path = os.path.expanduser("~/.config")

        # Prefer file managers
        file_managers = [
            ("dolphin", ["dolphin", path]),
            ("nautilus", ["nautilus", path]),
            ("gio", ["gio", "open", path]),
        ]

        for binary, cmd in file_managers:
            if shutil.which(binary):
                subprocess.Popen(cmd)
                return

        # Fallback: terminal + cd
        terminal = None
        for t in ["kitty", "alacritty", "foot", "gnome-terminal", "konsole", "xterm"]:
            if shutil.which(t):
                terminal = t
                break

        if terminal == "gnome-terminal":
            subprocess.Popen(["gnome-terminal", "--", "bash", "-c", f"cd {path}; exec bash"])
        elif terminal:
            subprocess.Popen([terminal, "-e", f"bash -c 'cd {path}; exec bash'"])

    def copy_to_clipboard(self, text):
        clipboard = Gdk.Display.get_default().get_clipboard()
        clipboard.set(text)

        toast = Adw.Toast(title="Game prefix copied to clipboard")
        toast.set_timeout(2)

        self.toast_overlay.add_toast(toast)

    def is_btrfs(self):
        output = subprocess.getoutput("findmnt -n -o FSTYPE /")
        return "btrfs" in output

    def has_snapper(self):
        output = subprocess.getoutput("snapper list-configs")
        return "root" in output

    def apply_profile(self, btn):
        profile = self.profile_combo.get_active_text()
        cfg = SYSTEM_PROFILES[profile]

        pkg_str = " ".join(cfg["packages"])

        cmds = []

        if pkg_str:
            cmds.append(f"sudo pacman -S --needed {pkg_str}")

        for s in cfg["services_enable"]:
            cmds.append(f"sudo systemctl enable --now {s}")

        for s in cfg["services_disable"]:
            cmds.append(f"sudo systemctl disable --now {s}")

        cmds.extend(cfg["post_cmd"])

        full_cmd = " && ".join(cmds) + " ; echo 'Profile applied'; sleep 5"
        self.open_terminal(full_cmd)


if __name__ == "__main__":
    app = LinuxUtilityApp()
    app.run(None)