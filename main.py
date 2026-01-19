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

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, GLib

class LinuxUtilityApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id='com.example.LinuxUtility',
                         flags=Gio.ApplicationFlags.FLAGS_NONE)

    def do_activate(self):
        win = Adw.ApplicationWindow(application=self)
        win.set_title("Extreme System Utility & Config Master")
        win.set_default_size(580, 850)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        win.set_content(content)

        header = Adw.HeaderBar()
        content.append(header)

        self.view_stack = Adw.ViewStack()
        self.view_stack.set_vexpand(True)
        
        # TAB 1: TOOLS (Switches & Updates)
        tools_page = self.create_tools_page()
        self.view_stack.add_titled_with_icon(tools_page, "tools", "Tools", "emblem-system-symbolic")

        # TAB 2: DIAGNOSTICS (All 30+ Info Points)
        info_page = self.create_info_page()
        self.view_stack.add_titled_with_icon(info_page, "info", "Diagnostics", "dialog-information-symbolic")

        view_switcher = Adw.ViewSwitcher(stack=self.view_stack)
        header.set_title_widget(view_switcher)
        content.append(self.view_stack)

        view_switcher_bar = Adw.ViewSwitcherBar(stack=self.view_stack)
        view_switcher_bar.set_reveal(True)
        content.append(view_switcher_bar)
        
        win.present()

    def wrap_in_resizable_view(self, child_widget):
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        clamp = Adw.Clamp(maximum_size=520, child=child_widget)
        clamp.set_margin_top(20)
        clamp.set_margin_bottom(20)
        clamp.set_margin_start(15)
        clamp.set_margin_end(15)
        scrolled.set_child(clamp)
        return scrolled

    # --- TOOLS PAGE ---
    def create_tools_page(self):
        list_box = Gtk.ListBox(css_classes=["boxed-list"])
        list_box.set_selection_mode(Gtk.SelectionMode.NONE)

        # 1. System Update
        update_row = Adw.ActionRow(title="Smart System Update", subtitle=f"Detected: {distro.name(pretty=True)}")
        self.update_icon = Gtk.Image.new_from_icon_name("software-update-available-symbolic")
        update_btn = Gtk.Button(child=self.update_icon, valign=Gtk.Align.CENTER, css_classes=["suggested-action"])
        update_btn.connect("clicked", self.on_system_update)
        update_row.add_suffix(update_btn)
        
        # 2. MangoHud Switch (Swaps configs/MangoHud.conf.enabled/disabled)
        mango_row = Adw.ActionRow(title="MangoHud Toggle", subtitle="Swap local config to ~/.config/MangoHud/")
        mango_sw = Gtk.Switch(active=self.get_config_status("MangoHud.conf"), valign=Gtk.Align.CENTER)
        mango_sw.connect("state-set", self.on_config_toggle, "MangoHud.conf", "~/.config/MangoHud/MangoHud.conf")
        mango_row.add_suffix(mango_sw)

        # 3. Hyprland Pivot Switch (Swaps configs/general.conf.pivot/original)
        pivot_row = Adw.ActionRow(title="Monitor Pivot (DP-2)", subtitle="Swap Hyprland layout config")
        pivot_sw = Gtk.Switch(active=self.get_config_status("general.conf"), valign=Gtk.Align.CENTER)
        pivot_sw.connect("state-set", self.on_config_toggle, "general.conf", "~/.config/hypr/hyprland/general.conf")
        pivot_row.add_suffix(pivot_sw)

        list_box.append(update_row)
        list_box.append(mango_row)
        list_box.append(pivot_row)
        return self.wrap_in_resizable_view(list_box)

    # --- DIAGNOSTICS PAGE (COMPLETE) ---
    def create_info_page(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)

        # OS & Session
        vbox.append(self.create_spec_group("Software &amp; OS", [
            ("Distro", distro.name(pretty=True), "distributor-logo-linux-symbolic"),
            ("Kernel", platform.release(), "slint-symbolic"),
            ("Uptime", self.get_uptime(), "preferences-system-time-symbolic"),
            ("Desktop", os.environ.get('XDG_CURRENT_DESKTOP', 'N/A'), "window-new-symbolic"),
            ("Session", os.environ.get('XDG_SESSION_TYPE', 'N/A'), "window-restore-symbolic"),
            ("Shell", os.environ.get('SHELL', 'N/A').split('/')[-1], "utilities-terminal-symbolic")
        ]))

        # CPU & Load
        vbox.append(self.create_spec_group("Processor &amp; Performance", [
            ("CPU Model", self.get_cpu_info(), "processor-symbolic"),
            ("Cores", f"{psutil.cpu_count(logical=False)} Phys / {psutil.cpu_count()} Log", "processor-symbolic"),
            ("CPU Temp", self.get_temp(), "sensors-temperature-symbolic")
        ]))

        # Memory & Storage
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        vbox.append(self.create_spec_group("Memory &amp; Storage", [
            ("Total RAM", f"{round(mem.total / 1e9, 2)} GB", "ram-symbolic"),
            ("Available", f"{round(mem.available / 1e9, 2)} GB", "ram-symbolic"),
            ("Root Disk", f"{disk.percent}% Used", "drive-harddisk-symbolic"),
            ("Disk Free", f"{round(disk.free / 1e9, 1)} GB", "drive-harddisk-symbolic")
        ]))

        # Graphics
        vbox.append(self.create_spec_group("Graphics &amp; Display", [
            ("GPU Model", self.get_gpu_info(), "video-display-symbolic"),
            ("Vulkan API", self.get_vulkan_version(), "applications-games-symbolic"),
            ("OpenGL", self.get_opengl_version(), "video-display-symbolic")
        ]))

        # Networking & Health
        vbox.append(self.create_spec_group("Connectivity &amp; Health", [
            ("Local IP", self.get_ip(), "network-transmit-receive-symbolic"),
            ("Battery", self.get_battery(), "battery-full-symbolic"),
            ("Fan Speed", self.get_fans(), "sensors-fan-symbolic")
        ]))

        return self.wrap_in_resizable_view(vbox)

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

    # --- UNIVERSAL CONFIG SWAP LOGIC ---
    def get_config_status(self, filename):
        targets = {
            "general.conf": "~/.config/hypr/hyprland/general.conf",
            "MangoHud.conf": "~/.config/MangoHud/MangoHud.conf"
        }
        path = os.path.expanduser(targets.get(filename))
        if os.path.islink(path):
            link = os.readlink(path)
            return ".pivot" in link or ".enabled" in link
        return False

    def on_config_toggle(self, widget, state, filename, target_path):
        if filename == "general.conf":
            ext = "pivot" if state else "original"
        else: # MangoHud
            ext = "enabled" if state else "disabled"

        script_dir = os.path.dirname(os.path.abspath(__file__))
        source = os.path.join(script_dir, "configs", f"{filename}.{ext}")
        target = os.path.expanduser(target_path)

        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if os.path.exists(target) or os.path.islink(target):
                os.remove(target)
            os.symlink(source, target)
        except Exception as e:
            print(f"Error swapping {filename}: {e}")
        return False

    # --- UPDATER & PROBES ---
    def on_system_update(self, btn):
        managers = {"pacman": "sudo pacman -Syu", "apt": "sudo apt update && sudo apt upgrade -y", "dnf": "sudo dnf upgrade"}
        cmd = "echo 'Manager not found'"
        for exe, c in managers.items():
            if subprocess.run(f"command -v {exe}", shell=True, capture_output=True).returncode == 0:
                cmd = c; break
        subprocess.Popen(["gnome-terminal", "--", "bash", "-c", f"{cmd}; read"])

    def get_vulkan_version(self):
        try:
            out = subprocess.check_output("vulkaninfo --summary", shell=True, stderr=subprocess.DEVNULL).decode()
            return re.search(r'Vulkan Instance Version: (\d+\.\d+\.\d+)', out).group(1)
        except: return "N/A"

    def get_gpu_info(self):
        try:
            out = subprocess.check_output("glxinfo | grep 'Device:'", shell=True, stderr=subprocess.DEVNULL).decode()
            return out.split(":")[1].strip()
        except: return "Unknown"

    def get_temp(self):
            """High-accuracy sensor probe searching all hwmon nodes."""
            try:
                # 1. Try scanning /sys/class/hwmon directly (Most accurate for Linux)
                hwmon_path = '/sys/class/hwmon/'
                if os.path.exists(hwmon_path):
                    for folder in os.listdir(hwmon_path):
                        path = os.path.join(hwmon_path, folder)
                        try:
                            name = open(os.path.join(path, 'name')).read().strip()
                            # Look for CPU specific chips (Intel/AMD)
                            if name in ['coretemp', 'k10temp', 'zenpatch']:
                                # Search for the Package or Tdie sensor in this folder
                                for file in os.listdir(path):
                                    if file.endswith('_label'):
                                        label = open(os.path.join(path, file)).read().strip()
                                        if label in ['Package id 0', 'Tdie', 'Tctl']:
                                            temp_file = file.replace('_label', '_input')
                                            val = int(open(os.path.join(path, temp_file)).read())
                                            return f"{val // 1000}°C"
                        except:
                            continue

                # 2. Fallback to psutil but search for the maximum value
                temps = psutil.sensors_temperatures()
                highest = 0
                for chip, entries in temps.items():
                    for entry in entries:
                        # We want the 'Package' or 'Tctl' sensor as it's usually the highest/truest
                        if any(x in entry.label for x in ['Package', 'Tdie', 'Tctl']):
                            return f"{int(entry.current)}°C"
                        if entry.current > highest:
                            highest = int(entry.current)
                
                if highest > 0:
                    return f"{highest}°C"
            except:
                pass
            return "N/A"

    def get_fans(self):
            try:
                fans = psutil.sensors_fans()
                if not fans:
                    return "0 RPM"
                
                # Iterate through all fan sensors to find one spinning
                for chip, entries in fans.items():
                    for entry in entries:
                        if entry.current > 0:
                            return f"{entry.current} RPM"
                
                # If we find sensors but they all say 0, they might be PWM controlled/hidden
                return "0 RPM (Idle?)"
            except:
                pass
            return "N/A"

    def get_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except: return "127.0.0.1"

    def get_uptime(self):
        return str(datetime.timedelta(seconds=int(time.time() - psutil.boot_time())))

    def get_battery(self):
        batt = psutil.sensors_battery()
        return f"{int(batt.percent)}% ({'Plugged' if batt.power_plugged else 'Battery'})" if batt else "N/A"

    def get_opengl_version(self):
        try:
            out = subprocess.check_output("glxinfo | grep 'OpenGL version string'", shell=True, stderr=subprocess.DEVNULL).decode()
            return out.split(":")[1].strip()
        except: return "N/A"

    def get_cpu_info(self):
        try: return subprocess.check_output("grep -m 1 'model name' /proc/cpuinfo | cut -d: -f2", shell=True).decode().strip()
        except: return platform.processor()

if __name__ == "__main__":
    app = LinuxUtilityApp()
    app.run(None)