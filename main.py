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
from gi.repository import Gtk, Adw, Gio, GLib, GObject, Gdk

# --- DATA MODEL FOR PROCESSES (WITH SORTING PROPERTIES) ---
class ProcessItem(GObject.Object):
    pid = GObject.Property(type=int)
    name = GObject.Property(type=str)
    cpu_val = GObject.Property(type=float)
    mem_val = GObject.Property(type=float)

    def __init__(self, pid, name, cpu, mem):
        super().__init__()
        self.pid = pid
        self.name = name
        self.cpu_val = cpu
        self.mem_val = mem
        self.cpu_text = f"{cpu:.1f}%"
        self.mem_text = f"{mem:.1f}%"

class LinuxUtilityApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id='com.example.LinuxUtility',
                         flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.cpu_history = [0] * 50
        self.mem_history = [0] * 50
        self.selected_pid = None

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

        # TAB 2: DIAGNOSTICS (ALL ORIGINAL INFO RESTORED)
        self.view_stack.add_titled_with_icon(self.create_info_page(), "info", "Diagnostics", "dialog-information-symbolic")

        # TAB 3: PROCESSES (SORTABLE)
        self.view_stack.add_titled_with_icon(self.create_task_manager_page(), "tasks", "Processes", "utilities-system-monitor-symbolic")

        view_switcher = Adw.ViewSwitcher(stack=self.view_stack)
        header.set_title_widget(view_switcher)
        content.append(self.view_stack)

        view_switcher_bar = Adw.ViewSwitcherBar(stack=self.view_stack)
        view_switcher_bar.set_reveal(True)
        content.append(view_switcher_bar)
        
        win.present()

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

        update_row = Adw.ActionRow(title="System Update", subtitle=f"Detected: {distro.name(pretty=True)}")
        update_btn = Gtk.Button(icon_name="software-update-available-symbolic", valign=Gtk.Align.CENTER, css_classes=["suggested-action"])
        update_btn.connect("clicked", self.on_system_update)
        update_row.add_suffix(update_btn)
        
        mango_row = Adw.ActionRow(title="MangoHud Toggle", subtitle="Swap local config to ~/.config/MangoHud/")
        mango_sw = Gtk.Switch(active=self.get_config_status("MangoHud.conf"), valign=Gtk.Align.CENTER)
        mango_sw.connect("state-set", self.on_config_toggle, "MangoHud.conf", "~/.config/MangoHud/MangoHud.conf")
        mango_row.add_suffix(mango_sw)

        pivot_row = Adw.ActionRow(title="Monitor Pivot (DP-2)", subtitle="Swap Hyprland layout config")
        pivot_sw = Gtk.Switch(active=self.get_config_status("general.conf"), valign=Gtk.Align.CENTER)
        pivot_sw.connect("state-set", self.on_config_toggle, "general.conf", "~/.config/hypr/hyprland/general.conf")
        pivot_row.add_suffix(pivot_sw)

        list_box.append(update_row); list_box.append(mango_row); list_box.append(pivot_row)
        return self.wrap_in_resizable_view(list_box)

    # --- DIAGNOSTICS PAGE (FULL 19+ INFO POINTS RESTORED) ---
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

        # 3. Memory & Storage
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        vbox.append(self.create_spec_group("Memory &amp; Storage", [
            ("Total RAM", f"{round(mem.total / 1e9, 2)} GB", "ram-symbolic"),
            ("Available", f"{round(mem.available / 1e9, 2)} GB", "ram-symbolic"),
            ("Root Disk", f"{disk.percent}% Used", "drive-harddisk-symbolic"),
            ("Disk Free", f"{round(disk.free / 1e9, 1)} GB", "drive-harddisk-symbolic")
        ]))

        # 4. Graphics & Display
        vbox.append(self.create_spec_group("Graphics &amp; Display", [
            ("GPU Model", self.get_gpu_info(), "video-display-symbolic"),
            ("Vulkan API", self.get_vulkan_version(), "applications-games-symbolic"),
            ("OpenGL", self.get_opengl_version(), "video-display-symbolic")
        ]))

        # 5. Connectivity & Health
        vbox.append(self.create_spec_group("Connectivity &amp; Health", [
            ("Local IP", self.get_ip(), "network-transmit-receive-symbolic"),
            ("Battery", self.get_battery(), "battery-full-symbolic"),
            ("Fan Speed", self.get_fans(), "sensors-fan-symbolic")
        ]))

        return self.wrap_in_resizable_view(vbox)

    # --- TASK MANAGER PAGE (SORTABLE) ---
    def create_task_manager_page(self):
        main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        clamp = Adw.Clamp(maximum_size=600)
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        vbox.set_margin_top(10); vbox.set_margin_bottom(10)

        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.proc_search = Gtk.SearchEntry(hexpand=True, placeholder_text="Filter processes...")
        kill_btn = Gtk.Button(label="Kill Process", css_classes=["destructive-action"])
        kill_btn.connect("clicked", self.on_kill_clicked)
        toolbar.append(self.proc_search); toolbar.append(kill_btn); vbox.append(toolbar)

        self.proc_store = Gio.ListStore(item_type=ProcessItem)
        self.sort_model = Gtk.SortListModel(model=self.proc_store)
        self.selection = Gtk.SingleSelection(model=self.sort_model)
        self.selection.connect("selection-changed", self.on_selection_changed)

        column_view = Gtk.ColumnView(model=self.selection, vexpand=True)
        self.sort_model.set_sorter(column_view.get_sorter())

        column_view.append_column(self.create_task_column("PID", "pid", 80, Gtk.NumericSorter.new(Gtk.PropertyExpression.new(ProcessItem, None, "pid"))))
        column_view.append_column(self.create_task_column("Name", "name", 220, Gtk.StringSorter.new(Gtk.PropertyExpression.new(ProcessItem, None, "name"))))
        column_view.append_column(self.create_task_column("CPU", "cpu_text", 85, Gtk.NumericSorter.new(Gtk.PropertyExpression.new(ProcessItem, None, "cpu_val"))))
        column_view.append_column(self.create_task_column("Mem", "mem_text", 85, Gtk.NumericSorter.new(Gtk.PropertyExpression.new(ProcessItem, None, "mem_val"))))

        scrolled = Gtk.ScrolledWindow(child=column_view, vexpand=True)
        scrolled.set_propagate_natural_height(True)
        scrolled.set_min_content_height(400)
        
        vbox.append(scrolled)
        clamp.set_child(vbox); main_vbox.append(clamp)
        
        GLib.timeout_add(2000, self.refresh_data)
        return main_vbox

    # --- CORE HELPERS & DATA REFRESH ---
    def refresh_data(self):
        cpu_val = psutil.cpu_percent()
        mem_val = psutil.virtual_memory().percent
        self.cpu_history.pop(0); self.cpu_history.append(cpu_val)
        self.mem_history.pop(0); self.mem_history.append(mem_val)
        
        if hasattr(self, 'cpu_label'): self.cpu_label.set_text(f"CPU Graph: {cpu_val:.1f}%")
        if hasattr(self, 'mem_label'): self.mem_label.set_text(f"Memory Graph: {mem_val:.1f}%")
        if hasattr(self, 'cpu_draw_area'): self.cpu_draw_area.queue_draw()
        if hasattr(self, 'mem_draw_area'): self.mem_draw_area.queue_draw()

        procs = []
        search = self.proc_search.get_text().lower()
        for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            try:
                if search in p.info['name'].lower() or search in str(p.info['pid']):
                    procs.append(ProcessItem(p.info['pid'], p.info['name'], p.info['cpu_percent'], p.info['memory_percent']))
            except: continue
        
        self.proc_store.splice(0, self.proc_store.get_n_items(), procs)

        if self.selected_pid:
            for i in range(self.sort_model.get_n_items()):
                if self.sort_model.get_item(i).pid == self.selected_pid:
                    self.selection.set_selected(i); break
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
    def create_task_column(self, title, prop, width, sorter):
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", lambda f, item: item.set_child(Gtk.Label(halign=Gtk.Align.START, margin_start=10)))
        factory.connect("bind", lambda f, item: item.get_child().set_label(str(getattr(item.get_item(), prop))))
        col = Gtk.ColumnViewColumn(title=title, factory=factory)
        col.set_fixed_width(width)
        col.set_sorter(sorter)
        return col

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
        return os.path.islink(path) and (".pivot" in os.readlink(path) or ".enabled" in os.readlink(path))

    def on_config_toggle(self, widget, state, filename, target_path):
        ext = ("pivot" if state else "original") if filename == "general.conf" else ("enabled" if state else "disabled")
        source = os.path.join(os.path.dirname(os.path.abspath(__file__)), "configs", f"{filename}.{ext}")
        target = os.path.expanduser(target_path)
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if os.path.exists(target) or os.path.islink(target): os.remove(target)
            os.symlink(source, target)
        except: pass
        return False

    def on_system_update(self, btn):
        subprocess.Popen(["gnome-terminal", "--", "bash", "-c", "sudo pacman -Syu; read"])

    def on_selection_changed(self, selection, position, n_items):
        item = selection.get_selected_item()
        if item: self.selected_pid = item.pid

    def on_kill_clicked(self, btn):
        item = self.selection.get_selected_item()
        if item:
            try: os.kill(item.pid, 9); self.selected_pid = None
            except: pass

if __name__ == "__main__":
    app = LinuxUtilityApp()
    app.run(None)