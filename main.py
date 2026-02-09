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
import configparser
import cairo
import shlex
import tempfile
import stat

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, GLib, GObject, Gdk

# ==============================
# SYSTEM PROFILES CONFIG
# ==============================

# Base packages included in all profiles
_BASE_PACKAGES = [
    "git", "curl", "wget", "htop", "nano", "flatpak", "fuse",
]

SYSTEM_PROFILES = {
    "minimal": {
        "description": "Essential tools only - lightweight setup",
        "packages": _BASE_PACKAGES + [
            "mpv", "ark", "smartmontools",
        ],
        "services_enable": [],
        "services_disable": [],
        "post_cmd": []
    },

    "developer": {
        "description": "Development environment with compilers and tools",
        "packages": _BASE_PACKAGES + [
            "cmake", "make", "gcc", "gdb", "python", "python-pip",
            "nodejs", "npm", "docker", "docker-compose",
            "neovim", "tmux", "ripgrep", "fd", "jq",
            "base-devel", "openssh", "vscodium",
        ],
        "services_enable": ["docker", "sshd"],
        "services_disable": [],
        "post_cmd": [
            "sudo usermod -aG docker $USER",
        ]
    },

    "gaming": {
        "description": "Optimized for gaming with Steam, Lutris, and performance tools",
        "packages": _BASE_PACKAGES + [
            "steam", "mangohud", "gamemode", "gamescope",
            "lutris", "heroic-games-launcher-bin",
            "wine", "wine-gecko", "wine-mono", "winetricks",
            "lib32-vulkan-icd-loader", "vulkan-tools",
            "mpv", "ark", "zen-browser-bin",
        ],
        "services_enable": [],
        "services_disable": [],
        "post_cmd": []
    },

    "workstation": {
        "description": "Full desktop with productivity and multimedia apps",
        "packages": _BASE_PACKAGES + [
            "python", "python-pip", "cmake", "make",
            "mpv", "ark", "bitwarden", "smartmontools",
            "zen-browser-bin", "snapper",
            "libreoffice-fresh", "gimp", "inkscape",
            "obs-studio", "kdenlive", "audacity",
            "thunderbird", "keepassxc",
        ],
        "services_enable": [],
        "services_disable": [],
        "post_cmd": []
    },

    "server": {
        "description": "Headless server with essential services",
        "packages": _BASE_PACKAGES + [
            "openssh", "fail2ban", "ufw",
            "docker", "docker-compose",
            "rsync", "cronie", "logrotate",
            "nginx", "certbot",
        ],
        "services_enable": [
            "sshd", "docker", "fail2ban", "ufw", "cronie", "nginx",
        ],
        "services_disable": [
            "bluetooth", "cups",
        ],
        "post_cmd": [
            "sudo ufw default deny incoming",
            "sudo ufw default allow outgoing",
            "sudo ufw allow ssh",
            "sudo ufw allow http",
            "sudo ufw allow https",
            "sudo ufw --force enable",
        ]
    },
}


class LinuxUtilityApp(Adw.Application):

    # Cached detection results
    _cached_pkg_manager = None
    _cached_terminal = None

    def __init__(self):
        super().__init__(
            application_id='org.cubixgamer.ControlPanel',
            flags=Gio.ApplicationFlags.FLAGS_NONE
        )
        self.cpu_history = [0] * 50
        self.mem_history = [0] * 50
        self.freq_history = [0] * 50
        self.swap_history = [0] * 50
        
        # I/O Tracking
        self.last_net_io = psutil.net_io_counters()
        self.last_disk_io = psutil.disk_io_counters()
        self.last_refresh_time = time.time()
        
        self.apply_custom_css()

    def apply_custom_css(self):
        css = """
        .sidebar-list {
            background-color: transparent;
        }
        .main-content {
            background-color: @window_bg_color;
        }
        .card {
            background-color: @card_bg_color;
            border-radius: 12px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .graph-label {
            font-weight: bold;
            font-size: 0.9em;
            color: @accent_color;
        }
        .accent-bg {
            background: linear-gradient(135deg, @accent_bg_color, @accent_color);
            color: white;
        }
        /* Sidebar styling */
        navigationrail, navigationsidbar {
            background-color: alpha(@window_bg_color, 0.8);
        }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    # ------------------------------
    # RESOURCE / ACTIVATION
    # ------------------------------

    def get_resource_path(self, relative_path):
        import sys
        base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base_path, relative_path)

    def do_activate(self):
        win = Adw.ApplicationWindow(application=self)
        win.set_title("Control Panel")
        win.set_default_size(950, 700)

        self.toast_overlay = Adw.ToastOverlay()
        win.set_content(self.toast_overlay)

        # Use NavigationSplitView for a modern sidebar look
        self.split_view = Adw.NavigationSplitView()
        self.split_view.set_collapsed(False)
        self.toast_overlay.set_child(self.split_view)

        # Sidebar Content
        sidebar_page = Adw.NavigationPage(title="Menu")
        sidebar_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        sidebar_header = Adw.HeaderBar(show_end_title_buttons=False)
        sidebar_vbox.append(sidebar_header)

        sidebar_list = Gtk.ListBox(css_classes=["navigation-sidebar", "sidebar-list"])
        sidebar_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        
        # Menu Items
        self.nav_items = [
            ("Diagnostics", "dialog-information-symbolic", "info"),
            ("Tools", "preferences-other-symbolic", "tools"),
            ("Utilities", "applications-system-symbolic", "utils"),
            ("Startup", "system-run-symbolic", "startup")
        ]

        for label, icon, tag in self.nav_items:
            row = Adw.ActionRow(title=label)
            row.add_prefix(Gtk.Image.new_from_icon_name(icon))
            sidebar_list.append(row)

        sidebar_list.connect("row-selected", self.on_nav_selected)
        sidebar_vbox.append(sidebar_list)
        sidebar_page.set_child(sidebar_vbox)
        self.split_view.set_sidebar(sidebar_page)

        # Content View
        self.content_stack = Adw.ViewStack()
        
        # Add pages to stack
        self.content_stack.add_titled(self.create_info_page(), "info", "Diagnostics")
        self.content_stack.add_titled(self.create_tools_page(), "tools", "Tools")
        self.content_stack.add_titled(self.create_utilities_page(), "utils", "Utilities")
        self.content_stack.add_titled(self.create_startup_page(), "startup", "Startup")

        content_page = Adw.NavigationPage(title="Control Panel")
        content_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content_header = Adw.HeaderBar()
        content_vbox.append(content_header)
        content_vbox.append(self.content_stack)
        content_page.set_child(content_vbox)
        
        self.split_view.set_content(content_page)

        win.present()
        sidebar_list.select_row(sidebar_list.get_row_at_index(0))
        GLib.timeout_add(2000, self.refresh_data)

    def on_nav_selected(self, listbox, row):
        if row:
            idx = row.get_index()
            tag = self.nav_items[idx][2]
            self.content_stack.set_visible_child_name(tag)
            # On mobile/small screens, show content
            self.split_view.set_show_content(True)

    # ------------------------------
    # GRAPH LOGIC
    # ------------------------------

    def create_graph(self, label_text, color):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        label = Gtk.Label(label=label_text, halign=Gtk.Align.START, css_classes=["caption-heading"])
        vbox.append(label)
        area = Gtk.DrawingArea(content_height=80, vexpand=True)
        area.set_draw_func(self.draw_perf_graph, color)
        area.set_margin_bottom(12)
        vbox.append(area)
        return vbox, label, area

    def draw_perf_graph(self, area, cr, width, height, color):
        graph_map = {
            "blue":   (self.cpu_history,  (0.2, 0.5, 0.9)),
            "green":  (self.mem_history,  (0.1, 0.8, 0.4)),
            "orange": (self.swap_history, (1.0, 0.5, 0.1)),
            "purple": (self.freq_history, (0.6, 0.3, 0.8)),
        }

        if color not in graph_map:
            return

        history, (r, g, b) = graph_map[color]

        # Background with subtle gradient
        pattern = cairo.LinearGradient(0, 0, 0, height)
        pattern.add_color_stop_rgba(0, r, g, b, 0.1)
        pattern.add_color_stop_rgba(1, r, g, b, 0.0)
        cr.set_source(pattern)
        cr.rectangle(0, 0, width, height)
        cr.fill()

        if len(history) < 2:
            return

        # Main Line and Fill
        cr.set_line_width(2.5)
        cr.set_line_join(cairo.LineJoin.ROUND)
        cr.set_line_cap(cairo.LineCap.ROUND)

        step = width / (len(history) - 1)
        
        # Create Path for fill
        cr.move_to(0, height)
        for i, val in enumerate(history):
            val = max(0, min(val, 100))
            y = height - (val / 100.0 * height)
            cr.line_to(i * step, y)
        cr.line_to(width, height)
        
        # Fill with gradient
        fill_pattern = cairo.LinearGradient(0, 0, 0, height)
        fill_pattern.add_color_stop_rgba(0, r, g, b, 0.4)
        fill_pattern.add_color_stop_rgba(1, r, g, b, 0.05)
        cr.set_source(fill_pattern)
        cr.fill_preserve()
        
        # Stroke the line
        cr.set_source_rgb(r, g, b)
        cr.stroke()

    # ------------------------------
    # TOOLS PAGE
    # ------------------------------

    def create_tools_page(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)

        # 1. Software Management
        software_group = Adw.PreferencesGroup(title="Software Management")
        
        # System Update
        software_group.add(self.create_utility_row(
            "System Update", f"Detected: {distro.name(pretty=True)}",
            "software-update-available-symbolic", self.on_system_update
        ))
        
        # Install Packages
        software_group.add(self.create_utility_row(
            "Install Packages", "Install predefined packages via system package manager",
            "system-software-install-symbolic", self.on_install_packages
        ))
        
        # Fastpak Install
        software_group.add(self.create_utility_row(
            "Install Flatpaks", "Install predefined Flatpak applications",
            "flatpak-symbolic", lambda: self.open_terminal(self.install_flatpaks())
        ))
        
        # CUPS Row
        software_group.add(self.create_utility_row(
            "Install CUPS", "Install printer system and Printer drivers",
            "printer-symbolic", self.install_cups_and_canon
        ))
        vbox.append(software_group)

        # 2. Hardware & Parameters
        hw_group = Adw.PreferencesGroup(title="Hardware & Parameters")
        hw_group.add(self.create_utility_row(
            "PCI/USB Devices", "List hardware components connected via PCI and USB",
            "computer-symbolic", self.probe_pci_devices
        ))
        hw_group.add(self.create_utility_row(
            "Microcode Status", "Check CPU vulnerabilities and microcode updates",
            "processor-symbolic", self.check_microcode
        ))
        hw_group.add(self.create_utility_row(
            "Kernel Params (sysctl)", "View active Linux kernel runtime parameters",
            "slint-symbolic", self.view_kernel_params
        ))
        vbox.append(hw_group)

        # 3. Snippet Vault
        snippet_group = Adw.PreferencesGroup(title="Snippet Vault")
        
        # Journal Health
        journal_cmd = "journalctl -p 3 -xb"
        journal_row = Adw.ActionRow(title="Check Critical Logs", subtitle=f"Filter: {journal_cmd}")
        journal_row.add_prefix(Gtk.Image.new_from_icon_name("utilities-terminal-symbolic"))
        copy_j = Gtk.Button(icon_name="edit-copy-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"])
        copy_j.connect("clicked", lambda x: self.copy_to_clipboard(journal_cmd))
        journal_row.add_suffix(copy_j)
        snippet_group.add(journal_row)

        # Pacman Orphans Snippet
        orphan_cmd = "pacman -Qtdq"
        orphan_row = Adw.ActionRow(title="List Orphans Command", subtitle=f"String: {orphan_cmd}")
        orphan_row.add_prefix(Gtk.Image.new_from_icon_name("edit-clear-all-symbolic"))
        copy_o = Gtk.Button(icon_name="edit-copy-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"])
        copy_o.connect("clicked", lambda x: self.copy_to_clipboard(orphan_cmd))
        orphan_row.add_suffix(copy_o)
        snippet_group.add(orphan_row)
        
        vbox.append(snippet_group)

        # 4. System Configuration
        config_group = Adw.PreferencesGroup(title="System Configuration")
        
        # Profiles
        self.profile_row = Adw.ComboRow(title="System Profile", subtitle="Apply predefined system configuration")
        self.profile_row.add_prefix(Gtk.Image.new_from_icon_name("preferences-system-symbolic"))
        
        # Modern Adw.ComboRow requires a model
        self.profile_model = Gtk.StringList.new(list(SYSTEM_PROFILES.keys()))
        self.profile_row.set_model(self.profile_model)
        
        apply_btn = Gtk.Button(icon_name="checkmark-symbolic", valign=Gtk.Align.CENTER, css_classes=["suggested-action", "flat"])
        apply_btn.connect("clicked", self.apply_profile)
        self.profile_row.add_suffix(apply_btn)
        config_group.add(self.profile_row)
        vbox.append(config_group)

        # 3. Backups & Snapshots
        snapshot_group = Adw.PreferencesGroup(title="Backups &amp; Snapshots")
        
        is_btrfs_root = self.is_btrfs()
        has_snapper_cfg = self.has_snapper()
        
        if is_btrfs_root and has_snapper_cfg:
            snapshot_group.add(self.create_utility_row(
                "Create Btrfs Snapshot", "Create manual system snapshot (root)",
                "camera-photo-symbolic", lambda: self.open_terminal("sudo snapper -c root create --description 'Manual snapshot from Control Panel'; sleep 3")
            ))
            snapshot_group.add(self.create_utility_row(
                "View Btrfs Snapshots", "List available system snapshots",
                "view-list-symbolic", lambda: self.open_terminal("sudo snapper list; read")
            ))
        else:
            status = "Btrfs snapshots not supported" if not is_btrfs_root else "Snapper not configured"
            snapshot_group.add(Adw.ActionRow(
                title="Btrfs Snapshots",
                subtitle=status,
                sensitive=False
            ))
        vbox.append(snapshot_group)

        # 4. Custom Toggles & Network
        advanced_group = Adw.PreferencesGroup(title="Custom Toggles &amp; Network")
        
        # Network Ping
        advanced_group.add(self.create_utility_row(
            "Network Latency Test", "Ping Google DNS (8.8.8.8)",
            "network-transmit-receive-symbolic", self.run_ping_test
        ))
        
        # MangoHud Toggle
        if os.path.exists(os.path.expanduser("~/.config/MangoHud")):
            mango_row = Adw.ActionRow(title="MangoHud Toggle", subtitle="Swap local config to ~/.config/MangoHud/")
            mango_row.add_prefix(Gtk.Image.new_from_icon_name("applications-games-symbolic"))
            mango_sw = Gtk.Switch(active=self.get_config_status("MangoHud.conf"), valign=Gtk.Align.CENTER)
            mango_sw.connect("state-set", self.on_config_toggle, "MangoHud.conf", "~/.config/MangoHud/MangoHud.conf")
            mango_row.add_suffix(mango_sw)
            advanced_group.add(mango_row)

        # Hyprland Pivot
        if os.path.exists(os.path.expanduser("~/.config/hypr")):
            pivot_row = Adw.ActionRow(title="Monitor Pivot (DP-2)", subtitle="Swap Hyprland layout config")
            pivot_row.add_prefix(Gtk.Image.new_from_icon_name("video-display-symbolic"))
            pivot_sw = Gtk.Switch(active=self.get_config_status("general.conf"), valign=Gtk.Align.CENTER)
            pivot_sw.connect("state-set", self.on_config_toggle, "general.conf", "~/.config/hypr/hyprland/general.conf")
            pivot_row.add_suffix(pivot_sw)
            advanced_group.add(pivot_row)
            
        vbox.append(advanced_group)

        return self.wrap_in_resizable_view(vbox)


    # --- DIAGNOSTICS PAGE ---
    def create_info_page(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)

        # 1. Performance Graphs (Side-by-Side)
        perf_group = Adw.PreferencesGroup(title="Real-time Performance")
        graph_grid = Gtk.Grid(column_spacing=12, row_spacing=12, column_homogeneous=True)
        
        cpu_g, self.cpu_label, self.cpu_draw_area = self.create_graph("CPU Load", "blue")
        mem_g, self.mem_label, self.mem_draw_area = self.create_graph("Memory Load", "green")
        swap_g, self.swap_label, self.swap_area = self.create_graph("Swap Usage", "orange")
        freq_g, self.freq_label, self.freq_draw_area = self.create_graph("CPU Frequency", "purple")

        graph_grid.attach(cpu_g, 0, 0, 1, 1)
        graph_grid.attach(mem_g, 1, 0, 1, 1)
        graph_grid.attach(swap_g, 0, 1, 1, 1)
        graph_grid.attach(freq_g, 1, 1, 1, 1)

        perf_group.add(graph_grid)
        vbox.append(perf_group)

        # 2. System Overview
        sw_group = Adw.PreferencesGroup(title="System Overview")
        sw_group.add(self.create_action_row("Distribution", distro.name(pretty=True), "distributor-logo-linux-symbolic"))
        sw_group.add(self.create_action_row("Kernel", platform.release(), "slint-symbolic"))
        self.uptime_row = self.create_action_row("Uptime", self.get_uptime(), "preferences-system-time-symbolic")
        sw_group.add(self.uptime_row)
        sw_group.add(self.create_action_row("CPU Features", self.get_cpu_features(), "processor-symbolic"))
        sw_group.add(self.create_action_row("Virtualization", self.get_virt_info(), "slint-symbolic"))
        vbox.append(sw_group)

        # 3. CPU & Motherboard
        cpu_mb_group = Adw.PreferencesGroup(title="CPU &amp; Motherboard")
        cpu_row = Adw.ExpanderRow(title="Processor", subtitle=self.get_cpu_info())
        cpu_row.add_prefix(Gtk.Image.new_from_icon_name("processor-symbolic"))
        cpu_row.add_row(self.create_action_row("Cores", f"{psutil.cpu_count(logical=False)} Physical / {psutil.cpu_count()} Logical", "processor-symbolic"))
        self.temp_row = self.create_action_row("Temperature", self.get_temp(), "sensors-temperature-symbolic")
        cpu_row.add_row(self.temp_row)
        # Added Microcode/Sec Info
        cpu_row.add_row(self.create_action_row("Microcode", "Click 'Microcode Status' in Tools for details", "security-high-symbolic"))
        cpu_mb_group.add(cpu_row)

        mb_row = Adw.ExpanderRow(title="Motherboard &amp; BIOS", subtitle="Hardware Identification")
        mb_row.add_prefix(Gtk.Image.new_from_icon_name("computer-symbolic"))
        mb_row.add_row(self.create_action_row("Model", self.get_motherboard_info(), "computer-symbolic"))
        mb_row.add_row(self.create_action_row("BIOS Version", self.get_bios_version(), "preferences-system-visibility-symbolic"))
        cpu_mb_group.add(mb_row)
        vbox.append(cpu_mb_group)

        # 4. Graphics
        gpu_group = Adw.PreferencesGroup(title="Graphics")
        gpu_row = Adw.ExpanderRow(title="GPU Information", subtitle=self.get_gpu_info())
        gpu_row.add_prefix(Gtk.Image.new_from_icon_name("video-display-symbolic"))
        gpu_row.add_row(self.create_action_row("Vulkan API", self.get_vulkan_version(), "applications-games-symbolic"))
        gpu_row.add_row(self.create_action_row("OpenGL", self.get_opengl_version(), "video-display-symbolic"))
        gpu_group.add(gpu_row)
        vbox.append(gpu_group)

        # 5. Storage &amp; Memory
        storage_group = Adw.PreferencesGroup(title="Storage &amp; Memory")
        mem_row = Adw.ExpanderRow(title="Memory (RAM)", subtitle=f"{round(psutil.virtual_memory().total / 1e9, 2)} GB Total")
        mem_row.add_prefix(Gtk.Image.new_from_icon_name("ram-symbolic"))
        self.mem_avail_row = self.create_action_row("Available", f"{round(psutil.virtual_memory().available / 1e9, 2)} GB", "ram-symbolic")
        mem_row.add_row(self.mem_avail_row)
        storage_group.add(mem_row)

        for part in psutil.disk_partitions():
            if part.fstype in ['ext4', 'btrfs', 'xfs', 'ntfs', 'vfat']:
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    disk_row = Adw.ExpanderRow(title=f"Disk ({part.mountpoint})", subtitle=f"{usage.percent}% Used")
                    disk_row.add_prefix(Gtk.Image.new_from_icon_name("drive-harddisk-symbolic"))
                    disk_row.add_row(self.create_action_row("Total Space", f"{round(usage.total/1e9, 1)} GB", "drive-harddisk-symbolic"))
                    disk_row.add_row(self.create_action_row("Used", f"{round(usage.used/1e9, 1)} GB", "drive-harddisk-symbolic"))
                    disk_row.add_row(self.create_action_row("Free", f"{round(usage.free/1e9, 1)} GB", "drive-harddisk-symbolic"))
                    storage_group.add(disk_row)
                except: continue
        vbox.append(storage_group)

        # 6. Connectivity
        conn_group = Adw.PreferencesGroup(title="Connectivity")
        conn_group.add(self.create_action_row("Local IP", self.get_ip(), "network-transmit-receive-symbolic"))
        self.net_io_row = self.create_action_row("Network Speed", "Calculating...", "network-transmit-receive-symbolic")
        conn_group.add(self.net_io_row)
        self.disk_io_row = self.create_action_row("Disk Throughput", "Calculating...", "drive-harddisk-symbolic")
        conn_group.add(self.disk_io_row)
        
        self.pub_ip_row = Adw.ActionRow(title="Public IP", subtitle="Click to check")
        self.pub_ip_row.add_prefix(Gtk.Image.new_from_icon_name("network-wired-symbolic"))
        pub_ip_btn = Gtk.Button(icon_name="view-refresh-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"])
        pub_ip_btn.connect("clicked", self.update_public_ip)
        self.pub_ip_row.add_suffix(pub_ip_btn)
        conn_group.add(self.pub_ip_row)
        vbox.append(conn_group)

        # 7. Health &amp; Resources
        health_group = Adw.PreferencesGroup(title="Health &amp; Resources")
        self.top_proc_row = self.create_action_row("Top Resource Consumer", "Identifying...", "process-stop-symbolic")
        health_group.add(self.top_proc_row)

        self.battery_row = self.create_action_row("Battery", self.get_battery(), "battery-full-symbolic")
        health_group.add(self.battery_row)
        self.fans_row = self.create_action_row("Fan Speed", self.get_fans(), "sensors-fan-symbolic")
        health_group.add(self.fans_row)
        vbox.append(health_group)

        return self.wrap_in_resizable_view(vbox)

    def create_action_row(self, title, subtitle, icon):
        row = Adw.ActionRow(title=title, subtitle=str(subtitle))
        row.add_prefix(Gtk.Image.new_from_icon_name(icon))
        return row

    def create_utility_row(self, title, subtitle, icon_name, callback, css=None):
        row = Adw.ActionRow(title=title, subtitle=subtitle)
        row.add_prefix(Gtk.Image.new_from_icon_name(icon_name))
        
        btn = Gtk.Button(valign=Gtk.Align.CENTER)
        if css:
            btn.add_css_class(css)
        
        # Determine button icon/label based on action
        if "Restart" in title or "Reload" in title or "Sync" in title:
            btn.set_icon_name("view-refresh-symbolic")
        elif "Clean" in title or "Remove" in title or "Clear" in title:
            btn.set_icon_name("edit-clear-symbolic")
        elif "Open" in title or "Check" in title or "Install" in title:
            btn.set_icon_name("go-next-symbolic")
        elif "Reboot" in title or "Shutdown" in title or "Logout" in title:
            btn.set_icon_name(icon_name) # Use the main icon for power actions
        else:
            btn.set_icon_name("go-next-symbolic") # Default

        btn.connect("clicked", lambda x: callback())
        row.add_suffix(btn)
        return row

    def create_utilities_page(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)

        # 1. Maintenance & Cleanup
        maintenance_group = Adw.PreferencesGroup(title="Maintenance &amp; Cleanup")
        maintenance_group.add(self.create_utility_row(
            "Clean Package Cache", "Clear distro-specific package manager caches", 
            "user-trash-symbolic", self.clean_package_cache
        ))
        maintenance_group.add(self.create_utility_row(
            "Remove Orphan Packages", "Uninstall unused dependencies and leftover packages", 
            "edit-clear-all-symbolic", self.remove_orphans
        ))
        maintenance_group.add(self.create_utility_row(
            "Sync System Clock", "Synchronize time with NTP servers", 
            "preferences-system-time-symbolic", self.sync_system_clock
        ))
        maintenance_group.add(self.create_utility_row(
            "Flush DNS Cache", "Clear system DNS resolver cache", 
            "network-transmit-receive-symbolic", self.flush_dns_cache
        ))
        maintenance_group.add(self.create_utility_row(
            "Clear Home Cache", "Remove files from ~/.cache", 
            "edit-clear-symbolic", lambda: self.open_terminal("rm -rf ~/.cache/* && echo 'Cache cleared' && sleep 3")
        ))
        maintenance_group.add(self.create_utility_row(
            "Log Rotation (Manual)", "Force system logs to rotate immediately", 
            "view-refresh-symbolic", self.trigger_logrotate
        ))

        # System Monitoring & Logs (Consolidated)
        maintenance_group.add(self.create_utility_row(
            "View System Logs", "Open journalctl viewer to inspect system activity",
            "utilities-terminal-symbolic", self.view_system_logs
        ))
        maintenance_group.add(self.create_utility_row(
            "Battery Health Probe", "Analyze battery wear, capacity, and charge status",
            "battery-level-100-symbolic", self.probe_battery_health
        ))
        vbox.append(maintenance_group)


        # 3. Service Management
        services_adm_group = Adw.PreferencesGroup(title="Service Management")
        for svc in ["NetworkManager", "docker", "bluetooth", "cups"]:
            row = Adw.ActionRow(title=f"Service: {svc}")
            row.add_prefix(Gtk.Image.new_from_icon_name("system-run-symbolic"))
            
            # Status btn
            status_btn = Gtk.Button(icon_name="dialog-information-symbolic", css_classes=["flat"])
            status_btn.connect("clicked", lambda x, s=svc: self.on_service_action(s, "status"))
            
            # Restart btn
            restart_btn = Gtk.Button(icon_name="view-refresh-symbolic", css_classes=["flat", "warning"])
            restart_btn.connect("clicked", lambda x, s=svc: self.on_service_action(s, "restart"))
            
            row.add_suffix(status_btn)
            row.add_suffix(restart_btn)
            services_adm_group.add(row)
        vbox.append(services_adm_group)

        # 4. System Services
        services_group = Adw.PreferencesGroup(title="System Services")
        services_group.add(self.create_utility_row(
            "Restart Network", "Restart NetworkManager service", 
            "network-wired-symbolic", lambda: self.open_terminal("sudo systemctl restart NetworkManager && echo 'Done' && sleep 3")
        ))
        services_group.add(self.create_utility_row(
            "Restart Audio", "Restart PipeWire and WirePlumber", 
            "audio-volume-high-symbolic", lambda: self.open_terminal("systemctl --user restart pipewire pipewire-pulse wireplumber && echo 'Done' && sleep 3")
        ))
        services_group.add(self.create_utility_row(
            "Restart Bluetooth", "Reset the Bluetooth stack and service", 
            "bluetooth-active-symbolic", self.restart_bluetooth
        ))
        services_group.add(self.create_utility_row(
            "Reload systemd", "Reload daemon configuration (daemon-reload)", 
            "view-refresh-symbolic", self.on_systemd_reload
        ))
        services_group.add(self.create_utility_row(
            "Install Printers (CUPS)", "Setup CUPS and Canon imaging drivers", 
            "printer-symbolic", self.install_cups_and_canon
        ))
        services_group.add(self.create_utility_row(
            "Flatpak Repair", "Fix broken Flatpak installations", 
            "flatpak-symbolic", lambda: self.open_terminal("flatpak repair -y && echo 'Done' && sleep 5")
        ))
        vbox.append(services_group)

        # 3. Files & System Tools
        files_group = Adw.PreferencesGroup(title="Files &amp; System Tools")
        files_group.add(self.create_utility_row(
            "Open Config Folder", "Browse ~/.config in your file manager", 
            "folder-remote-symbolic", self.open_config_folder
        ))
        files_group.add(self.create_utility_row(
            "Check Disk Health (SMART)", "Run quick SMART diagnostics on available disks", 
            "drive-harddisk-symbolic", self.check_disk_health
        ))
        files_group.add(self.create_utility_row(
            "Kill GPU Processes", "Force stop all processes currently using the GPU", 
            "process-stop-symbolic", self.kill_gpu_procs
        ))

        # Game Prefix Row
        game_prefix = "mangohud gamemoderun gamescope -W 1920 -H 1080 -r 75 --force-grab-cursor -f -- %command%"
        prefix_row = Adw.ActionRow(title="Game Prefix", subtitle=game_prefix)
        prefix_row.set_subtitle_selectable(True)
        prefix_row.add_prefix(Gtk.Image.new_from_icon_name("applications-games-symbolic"))
        copy_btn = Gtk.Button(icon_name="edit-copy-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"])
        copy_btn.connect("clicked", lambda x: self.copy_to_clipboard(game_prefix))
        prefix_row.add_suffix(copy_btn)
        
        files_group.add(prefix_row)
        vbox.append(files_group)

        # 4. Power Management
        power_group = Adw.PreferencesGroup(title="Power Management")
        power_group.add(self.create_utility_row(
            "Reboot System", "Safely restart the computer", 
            "system-reboot-symbolic", lambda: subprocess.Popen(["systemctl", "reboot"]), css="warning"
        ))
        power_group.add(self.create_utility_row(
            "Shutdown System", "Power off the computer immediately", 
            "system-shutdown-symbolic", lambda: subprocess.Popen(["systemctl", "poweroff"]), css="destructive"
        ))
        power_group.add(self.create_utility_row(
            "Logout Session", "End the current user session", 
            "system-log-out-symbolic", self.logout, css="destructive"
        ))
        vbox.append(power_group)

        return self.wrap_in_resizable_view(vbox)

    def create_startup_page(self):
        self.startup_list_box = Gtk.ListBox(css_classes=["boxed-list"])
        self.startup_list_box.set_selection_mode(Gtk.SelectionMode.NONE)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        
        info_banner = Adw.Bin(css_classes=["card"])
        info_label = Gtk.Label(
            label="Manage applications that start automatically when you log in.",
            margin_top=12, margin_bottom=12, margin_start=12, margin_end=12,
            wrap=True
        )
        info_banner.set_child(info_label)
        vbox.append(info_banner)

        self.refresh_startup_list()
        vbox.append(self.startup_list_box)

        add_btn = Gtk.Button(
            label="Add Startup Application",
            icon_name="list-add-symbolic",
            halign=Gtk.Align.CENTER,
            css_classes=["suggested-action", "pill"]
        )
        add_btn.connect("clicked", self.on_add_startup_click)
        vbox.append(add_btn)

        return self.wrap_in_resizable_view(vbox)

    def refresh_startup_list(self):
        # Clear existing rows
        while (child := self.startup_list_box.get_first_child()):
            self.startup_list_box.remove(child)

        autostart_dir = os.path.expanduser("~/.config/autostart")
        if not os.path.exists(autostart_dir):
            return

        for filename in sorted(os.listdir(autostart_dir)):
            if filename.endswith(".desktop"):
                path = os.path.join(autostart_dir, filename)
                config = configparser.ConfigParser(interpolation=None)
                try:
                    config.read(path)
                    if "Desktop Entry" in config:
                        name = config["Desktop Entry"].get("Name", filename)
                        comment = config["Desktop Entry"].get("Comment", "No description")
                        
                        row = Adw.ActionRow(title=name, subtitle=comment)
                        
                        del_btn = Gtk.Button(
                            icon_name="user-trash-symbolic",
                            valign=Gtk.Align.CENTER,
                            css_classes=["destructive-action", "flat"]
                        )
                        del_btn.connect("clicked", lambda b, p=path: self.on_delete_startup(p))
                        row.add_suffix(del_btn)
                        
                        self.startup_list_box.append(row)
                except Exception as e:
                    print(f"[ERROR] Failed to read desktop file {path}: {e}")

    def on_delete_startup(self, path):
        try:
            os.remove(path)
            self.refresh_startup_list()
            toast = Adw.Toast(title="Startup application removed")
            self.toast_overlay.add_toast(toast)
        except Exception as e:
            print(f"[ERROR] Failed to delete {path}: {e}")

    def on_add_startup_click(self, btn):
        dialog = Gtk.Dialog(title="Add Startup Application", transient_for=btn.get_root())
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Add", Gtk.ResponseType.OK)

        content = dialog.get_content_area()
        content.set_spacing(12)
        content.set_margin_top(12)
        content.set_margin_bottom(12)
        content.set_margin_start(12)
        content.set_margin_end(12)

        name_entry = Gtk.Entry(placeholder_text="Name (e.g. Discord)")
        cmd_entry = Gtk.Entry(placeholder_text="Command (e.g. discord)")
        desc_entry = Gtk.Entry(placeholder_text="Description (Optional)")

        content.append(Gtk.Label(label="Name:", halign=Gtk.Align.START))
        content.append(name_entry)
        content.append(Gtk.Label(label="Command:", halign=Gtk.Align.START))
        content.append(cmd_entry)
        content.append(Gtk.Label(label="Description:", halign=Gtk.Align.START))
        content.append(desc_entry)

        def on_response(dialog, response_id):
            if response_id == Gtk.ResponseType.OK:
                name = name_entry.get_text().strip()
                cmd = cmd_entry.get_text().strip()
                desc = desc_entry.get_text().strip()
                if name and cmd:
                    self.add_startup_file(name, cmd, desc)
            dialog.destroy()

        dialog.connect("response", on_response)
        dialog.present()

    def add_startup_file(self, name, cmd, desc):
        autostart_dir = os.path.expanduser("~/.config/autostart")
        os.makedirs(autostart_dir, exist_ok=True)
        
        safe_name = "".join([c for c in name if c.isalnum()]).lower()
        if not safe_name: safe_name = "startup_app"
        path = os.path.join(autostart_dir, f"{safe_name}.desktop")

        content = f"[Desktop Entry]\nType=Application\nName={name}\nExec={cmd}\nComment={desc}\nX-GNOME-Autostart-enabled=true\n"
        
        try:
            with open(path, "w") as f:
                f.write(content)
            self.refresh_startup_list()
            toast = Adw.Toast(title=f"Added {name} to startup")
            self.toast_overlay.add_toast(toast)
        except Exception as e:
            print(f"[ERROR] Failed to create startup file: {e}")

    # --- LOGIC FUNCTIONS ---

    def update_public_ip(self, btn=None):
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

    def view_system_logs(self):
        """Open system journal in a pager."""
        self.open_terminal("echo '=== SYSTEM LOGS (Journalctl) ==='; sudo journalctl -xe; echo 'Logs closed'; sleep 2")

    def probe_battery_health(self):
        """Show detailed battery wear and health info."""
        cmd = (
            "echo '=== BATTERY HEALTH PROBE ==='; "
            "upower -i $(upower -e | grep 'BAT') | grep -E 'state|to full|percentage|capacity|energy-full|energy-design'; "
            "echo -e '\nPress Enter to close...'; read"
        )
        self.open_terminal(cmd)

    def trigger_logrotate(self):
        """Manually trigger log rotation."""
        self.open_terminal("echo 'Force rotating logs...'; sudo logrotate -f /etc/logrotate.conf && echo 'Success' || echo 'Failed'; sleep 3")

    def probe_pci_devices(self):
        """List PCI devices with verbose info."""
        self.open_terminal("echo '=== PCI DEVICE LIST ==='; lspci -vmm; echo -e '\nPress Enter to close...'; read")

    def probe_usb_devices(self):
        """List USB devices."""
        self.open_terminal("echo '=== USB DEVICE LIST ==='; lsusb; echo -e '\nPress Enter to close...'; read")

    def check_microcode(self):
        """Check CPU microcode status."""
        self.open_terminal("echo '=== CPU MICROCODE STATUS ==='; grep . /sys/devices/system/cpu/vulnerabilities/*; echo; journalctl -k | grep -i microcode | tail -n 5; echo -e '\nPress Enter to close...'; read")

    def view_kernel_params(self):
        """List active sysctl parameters."""
        self.open_terminal("echo '=== KERNEL PARAMETERS (sysctl) ==='; sysctl -a | head -n 50; echo '... (truncated, use sysctl -a for full list)'; echo -e '\nPress Enter to close...'; read")

    def on_service_action(self, service, action):
        """Handle service management actions (status, restart)."""
        if action == "status":
            self.open_terminal(f"systemctl status {service}; echo -e '\nPress Enter to close...'; read")
        elif action == "restart":
            self.open_terminal(f"echo 'Restarting {service}...'; sudo systemctl restart {service} && echo 'Done' || echo 'Failed'; sleep 3")

    def _detect_terminal(self):
        """Detect and cache available terminal emulator."""
        if LinuxUtilityApp._cached_terminal is not None:
            return LinuxUtilityApp._cached_terminal

        terminal = "xterm"
        for t in ["gnome-terminal", "konsole", "xfce4-terminal", "alacritty", "kitty", "foot"]:
            if shutil.which(t):
                terminal = t
                break
        LinuxUtilityApp._cached_terminal = terminal
        return terminal

    def _detect_package_manager(self):
        """Detect and cache available package manager with its commands."""
        if LinuxUtilityApp._cached_pkg_manager is not None:
            return LinuxUtilityApp._cached_pkg_manager

        managers = {
            "pacman": {
                "update": "sudo pacman -Syu",
                "install": "sudo pacman -S --needed {}",
                "check": "pacman -Qi {}",
                "cleanup": "sudo pacman -Sc --noconfirm",
                "orphans": "sudo pacman -Rns $(pacman -Qtdq) 2>/dev/null || echo 'No orphans found'"
            },
            "apt": {
                "update": "sudo apt update && sudo apt upgrade -y",
                "install": "sudo apt update && sudo apt install -y {}",
                "check": "dpkg -s {}",
                "cleanup": "sudo apt clean && sudo apt autoclean",
                "orphans": "sudo apt autoremove -y"
            },
            "dnf": {
                "update": "sudo dnf upgrade -y",
                "install": "sudo dnf install -y {}",
                "check": "rpm -q {}",
                "cleanup": "sudo dnf clean all",
                "orphans": "sudo dnf autoremove -y"
            },
            "zypper": {
                "update": "sudo zypper dup",
                "install": "sudo zypper install -y {}",
                "check": "rpm -q {}",
                "cleanup": "sudo zypper clean --all",
                "orphans": "sudo zypper rm -u"
            },
            "xbps-install": {
                "update": "sudo xbps-install -Su",
                "install": "sudo xbps-install -S {}",
                "check": "xbps-query -W {}",
                "cleanup": "sudo xbps-remove -O",
                "orphans": "sudo xbps-remove -o"
            },
            "apk": {
                "update": "sudo apk update && sudo apk upgrade",
                "install": "sudo apk add {}",
                "check": "apk info -e {}",
                "cleanup": "sudo apk cache clean",
                "orphans": "sudo apk del $(apk info -n --orphans)"
            },
            "emerge": {
                "update": "sudo emerge --sync && sudo emerge -auDN @world",
                "install": "sudo emerge -a {}",
                "check": "qlist -I {}",
                "cleanup": "sudo eclean-dist -d",
                "orphans": "sudo emerge --depclean"
            },
            "nix-env": {
                "update": "nix-channel --update && nix-env -iA nixpkgs.nix nixpkgs.cacert",
                "install": "nix-env -iA nixpkgs.{}",
                "check": "nix-env -q {}",
                "cleanup": "nix-collect-garbage -d",
                "orphans": "nix-collect-garbage"
            }
        }

        for name, cmds in managers.items():
            if shutil.which(name):
                LinuxUtilityApp._cached_pkg_manager = (name, cmds)
                return LinuxUtilityApp._cached_pkg_manager

        LinuxUtilityApp._cached_pkg_manager = (None, None)
        return LinuxUtilityApp._cached_pkg_manager

    def open_terminal(self, cmd):
        terminal = self._detect_terminal()
        
        # If the command is complex (multi-line or has special chars), use a temp script
        is_complex = "\n" in cmd or any(c in cmd for c in "`$|#")
        
        if is_complex:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
                f.write("#!/bin/bash\n" + cmd)
                temp_path = f.name
            
            # Make it executable
            os.chmod(temp_path, os.stat(temp_path).st_mode | stat.S_IEXEC)
            
            exec_cmd = temp_path
            # Cleanup script after some time (optional, but good practice)
            GLib.timeout_add_seconds(30, lambda: os.unlink(temp_path) if os.path.exists(temp_path) else None)
        else:
            exec_cmd = f"bash -c {shlex.quote(cmd)}"

        if terminal == "gnome-terminal":
            subprocess.Popen(["gnome-terminal", "--", "bash", "-c", exec_cmd if not is_complex else f"bash {exec_cmd}"])
        else:
            # Most other terminals use -e
            if is_complex:
                subprocess.Popen([terminal, "-e", f"bash {exec_cmd}"])
            else:
                subprocess.Popen([terminal, "-e", exec_cmd])

    def refresh_data(self):
        now = time.time()
        dt = now - self.last_refresh_time
        if dt <= 0: dt = 1 # Avoid division by zero
        
        cpu_val = psutil.cpu_percent()
        mem_val = psutil.virtual_memory().percent
        swap_val = psutil.swap_memory().percent
        freq_list = psutil.cpu_freq(percpu=False)
        freq_val = (freq_list.current / freq_list.max * 100.0) if freq_list and freq_list.max else 0

        # Network I/O Speed
        net_now = psutil.net_io_counters()
        sent_speed = (net_now.bytes_sent - self.last_net_io.bytes_sent) / dt
        recv_speed = (net_now.bytes_recv - self.last_net_io.bytes_recv) / dt
        self.last_net_io = net_now
        
        # Disk I/O Speed
        disk_now = psutil.disk_io_counters()
        read_speed = (disk_now.read_bytes - self.last_disk_io.read_bytes) / dt
        write_speed = (disk_now.write_bytes - self.last_disk_io.write_bytes) / dt
        self.last_disk_io = disk_now
        
        self.last_refresh_time = now

        self.cpu_history.pop(0); self.cpu_history.append(cpu_val)
        self.mem_history.pop(0); self.mem_history.append(mem_val)
        self.swap_history.pop(0); self.swap_history.append(swap_val)
        self.freq_history.pop(0); self.freq_history.append(freq_val)

        # Update labels (now subtitles/text)
        if hasattr(self, 'cpu_label'): self.cpu_label.set_text(f"CPU Load: {cpu_val:.1f}%")
        if hasattr(self, 'mem_label'): self.mem_label.set_text(f"Memory Load: {mem_val:.1f}%")
        if hasattr(self, 'swap_label'): self.swap_label.set_text(f"Swap Usage: {swap_val:.1f}%")
        if hasattr(self, 'freq_label'): self.freq_label.set_text(f"CPU Freq: {int(freq_list.current if freq_list else 0)} MHz")

        # Update rows
        if hasattr(self, 'uptime_row'): self.uptime_row.set_subtitle(self.get_uptime())
        if hasattr(self, 'temp_row'): self.temp_row.set_subtitle(self.get_temp())
        if hasattr(self, 'mem_avail_row'): self.mem_avail_row.set_subtitle(f"{round(psutil.virtual_memory().available / 1e9, 2)} GB")
        if hasattr(self, 'battery_row'): self.battery_row.set_subtitle(self.get_battery())
        if hasattr(self, 'fans_row'): self.fans_row.set_subtitle(self.get_fans())
        
        # New monitoring rows
        if hasattr(self, 'net_io_row'):
            self.net_io_row.set_subtitle(f"↑ {self.format_bytes(sent_speed)}/s | ↓ {self.format_bytes(recv_speed)}/s")
        if hasattr(self, 'disk_io_row'):
            self.disk_io_row.set_subtitle(f"Read: {self.format_bytes(read_speed)}/s | Write: {self.format_bytes(write_speed)}/s")
        if hasattr(self, 'top_proc_row'):
            self.top_proc_row.set_subtitle(self.get_top_process())

        # Redraw areas
        if hasattr(self, 'cpu_draw_area'): self.cpu_draw_area.queue_draw()
        if hasattr(self, 'mem_draw_area'): self.mem_draw_area.queue_draw()
        if hasattr(self, 'swap_area'): self.swap_area.queue_draw()
        if hasattr(self, 'freq_draw_area'): self.freq_draw_area.queue_draw()

        return True

    def get_top_process(self):
        try:
            procs = [(p.info['name'], p.info['cpu_percent']) for p in psutil.process_iter(['name', 'cpu_percent'])]
            top = sorted(procs, key=lambda x: x[1], reverse=True)[0]
            return f"{top[0]} ({top[1]:.1f}% CPU)"
        except: return "N/A"

    def format_bytes(self, n):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if n < 1024: return f"{n:.1f} {unit}"
            n /= 1024
        return f"{n:.1f} TB"

    def get_cpu_features(self):
        try:
            with open('/proc/cpuinfo') as f:
                for line in f:
                    if line.startswith('flags'):
                        all_flags = line.split(':')[1].strip().split()
                        essential = [f for f in all_flags if f in ['sse4_1', 'sse4_2', 'avx', 'avx2', 'aes']]
                        return ", ".join(essential).upper() or "Standard x86_64"
            return "N/A"
        except: return "N/A"

    def get_virt_info(self):
        try:
            with open('/proc/cpuinfo') as f:
                content = f.read()
                if 'vmx' in content: return "Intel VT-x (Enabled)"
                if 'svm' in content: return "AMD-V (Enabled)"
            return "Disabled / Not supported"
        except: return "N/A"

    def get_motherboard_info(self):
        try:
            return subprocess.check_output("cat /sys/class/dmi/id/board_name", shell=True, stderr=subprocess.DEVNULL).decode().strip() or "N/A"
        except: return "N/A"

    def get_bios_version(self):
        try:
            return subprocess.check_output("cat /sys/class/dmi/id/bios_version", shell=True, stderr=subprocess.DEVNULL).decode().strip() or "N/A"
        except: return "N/A"

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
            glx_out = subprocess.check_output("glxinfo | grep 'Device:'", shell=True, stderr=subprocess.DEVNULL).decode()
            device = glx_out.split(":")[1].strip()
            # Try to get vendor info from lspci
            vendor_out = subprocess.getoutput("lspci | grep -i vga").split(":")[2].strip() if shutil.which("lspci") else ""
            if vendor_out:
                return f"{vendor_out} ({device})"
            return device
        except: return "Unknown"

    def get_cpu_info(self):
        try: return subprocess.check_output("grep -m 1 'model name' /proc/cpuinfo | cut -d: -f2", shell=True).decode().strip()
        except: return platform.processor()

    def get_uptime(self):
        return str(datetime.timedelta(seconds=int(time.time() - psutil.boot_time())))

    def create_action_row(self, title, subtitle, icon):
        row = Adw.ActionRow(title=title, subtitle=str(subtitle))
        row.add_prefix(Gtk.Image.new_from_icon_name(icon))
        return row

    def wrap_in_resizable_view(self, child):
        scrolled = Gtk.ScrolledWindow(vexpand=True)
        scrolled.set_propagate_natural_height(True)
        # 1000px maximum size for professional tiling support
        clamp = Adw.Clamp(maximum_size=1000, child=child)
        clamp.set_margin_top(24); clamp.set_margin_bottom(24)
        clamp.set_margin_start(12); clamp.set_margin_end(12)
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

    def on_system_update(self, btn=None):
        pkg_name, pkg_cmds = self._detect_package_manager()

        if pkg_cmds:
            update_cmd = pkg_cmds["update"]
        else:
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
        packages = [
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

    def on_install_packages(self, btn=None):
        packages = self.get_packages_to_install()
        if not packages:
            self.open_terminal("echo 'No packages defined'; sleep 3")
            return

        pkg_str = " ".join(packages)
        pkg_name, pkg_cmds = self._detect_package_manager()

        if pkg_cmds:
            install_cmd = pkg_cmds["install"].format(pkg_str)
        else:
            install_cmd = "echo 'No supported package manager found!'"

        full_cmd = (
            f"echo 'Installing packages:'; echo '{pkg_str}'; echo; "
            f"{install_cmd}; "
            f"echo; echo 'Done.'; sleep 5"
        )

        self.open_terminal(full_cmd)

    def clean_package_cache(self):
        """Clean package manager cache based on detected package manager."""
        pkg_name, pkg_cmds = self._detect_package_manager()

        if pkg_cmds and "cleanup" in pkg_cmds:
            cmd = pkg_cmds["cleanup"]
        else:
            cmd = "echo 'Cleanup not supported for this package manager'"

        self.open_terminal(f"{cmd} && echo 'Cache cleaned' && sleep 3")

    def remove_orphans(self):
        """Remove orphan packages based on detected package manager."""
        pkg_name, pkg_cmds = self._detect_package_manager()

        if pkg_cmds and "orphans" in pkg_cmds:
            cmd = pkg_cmds["orphans"]
        else:
            cmd = "echo 'Orphan removal not supported for this package manager'"

        self.open_terminal(f"{cmd} && echo 'Orphans removed' && sleep 3")

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
            "# Ensure Flathub remote exists\n"
            "flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo\n"
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
            "echo \"========================================\"\n"
            "echo \"   FLATPAK INSTALLATION SERVICE\"\n"
            "echo \"========================================\"\n"
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

    def install_cups_and_canon(self, btn=None):
        required = ["cups", "gutenprint"]
        pkg_name, pkg_cmds = self._detect_package_manager()

        if not pkg_cmds:
            self.open_terminal("echo 'No supported package manager found!' && sleep 5")
            return

        missing = []
        for pkg in required:
            check_cmd = pkg_cmds["check"].format(pkg)
            result = subprocess.run(check_cmd, shell=True, capture_output=True)
            if result.returncode != 0:
                missing.append(pkg)

        if not missing:
            self.open_terminal("echo 'CUPS and Printer drivers are already installed!' && sleep 5")
            return

        pkg_str = " ".join(missing)
        install_cmd = pkg_cmds["install"].format(pkg_str)
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
        terminal = self._detect_terminal()
        if terminal == "gnome-terminal":
            subprocess.Popen(["gnome-terminal", "--", "bash", "-c", f"cd {path}; exec bash"])
        else:
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

    def restart_bluetooth(self):
        """Restart the bluetooth service."""
        cmd = "sudo systemctl restart bluetooth && echo 'Bluetooth service restarted' && sleep 3"
        self.open_terminal(cmd)

    def kill_gpu_procs(self):
        """Forcefully kill processes using the GPU."""
        cmd = (
            "echo 'Killing GPU processes...'; "
            "sudo fuser -kv /dev/nvidia* /dev/dri/* 2>/dev/null; "
            "echo 'Done'; sleep 3"
        )
        self.open_terminal(cmd)

    def sync_system_clock(self):
        """Sync system clock with NTP."""
        cmd = (
            "sudo timedatectl set-ntp true && sudo hwclock --systohc && "
            "echo 'System clock synchronized' && sleep 3"
        )
        self.open_terminal(cmd)

    def flush_dns_cache(self):
        """Flush system DNS cache."""
        cmd = (
            "sudo systemd-resolve --flush-caches 2>/dev/null || "
            "sudo resolvectl flush-caches 2>/dev/null || "
            "sudo killall -HUP nscd 2>/dev/null; "
            "echo 'DNS cache flushed' && sleep 3"
        )
        self.open_terminal(cmd)

    def on_systemd_reload(self, btn=None):
        """Reload systemd configuration."""
        self.open_terminal("sudo systemctl daemon-reload && echo 'systemd reloaded' && sleep 3")

    def check_disk_health(self):
        """Run SMART disk diagnostics."""
        cmd = (
            "echo '=== DISK HEALTH ===' && "
            "for disk in $(lsblk -d -o NAME | tail -n +2); do "
            "echo \"\\n--- /dev/$disk ---\"; "
            "sudo smartctl -H /dev/$disk 2>/dev/null || echo 'SMART not supported'; "
            "done; echo; read -p 'Press Enter to close...'"
        )
        self.open_terminal(cmd)

    def create_utility_row(self, title, subtitle, icon, callback, css=None):
        row = Adw.ActionRow(title=title, subtitle=subtitle)
        row.add_prefix(Gtk.Image.new_from_icon_name(icon))
        
        btn = Gtk.Button(icon_name="go-next-symbolic", valign=Gtk.Align.CENTER, css_classes=["flat"])
        if css == "warning":
            btn.add_css_class("warning-action")
        elif css == "destructive":
            btn.add_css_class("destructive-action")
            
        btn.connect("clicked", lambda b: callback())
        row.add_suffix(btn)
        
        row.set_activatable(True)
        row.connect("activated", lambda r: callback())
        
        return row

    def logout(self):
        """Logout the current user session."""
        self.open_terminal("loginctl terminate-user $USER")

    def apply_profile(self, btn=None):
        selected_idx = self.profile_row.get_selected()
        profile = list(SYSTEM_PROFILES.keys())[selected_idx]
        cfg = SYSTEM_PROFILES[profile]

        pkg_str = " ".join(cfg["packages"])
        pkg_name, pkg_cmds = self._detect_package_manager()

        cmds = []

        if pkg_str and pkg_cmds:
            cmds.append(pkg_cmds["install"].format(pkg_str))
        elif pkg_str:
            cmds.append("echo 'No supported package manager found!'")

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