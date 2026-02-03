#!/usr/bin/env python3
import os
import sys
import subprocess
from pathlib import Path

APP_NAME = "Control Panel"
DESKTOP_FILENAME = "ControlPanel.desktop"
ICON_NAME = "preferences-system" 

# Arch Linux system dependencies Yes i Use Arch BTW
PACMAN_PACKAGES = [
    "python-gobject",
    "gtk4",
    "libadwaita",
    "python-pip",
    "python-psutil",
    "python-distro"
]

def ask_yes_no(question: str) -> bool:
    answer = input(f"{question} [Y/n]: ").strip().lower()
    return answer in ("", "y", "yes")

def install_pacman(packages):
    print("Installing system dependencies using pacman...")
    cmd = ["sudo", "pacman", "-Syu", "--needed"] + packages
    subprocess.run(cmd, check=True)

def create_desktop_file(main_py: Path):
    desktop_dir = Path.home() / ".local/share/applications"
    desktop_dir.mkdir(parents=True, exist_ok=True)

    desktop_path = desktop_dir / DESKTOP_FILENAME

    desktop_content = f"""[Desktop Entry]
Name={APP_NAME}
Comment=Usefull control panel for hyprland
Exec=/usr/bin/env python3 "{main_py}"
Icon={ICON_NAME}
Terminal=false
Type=Application
Categories=Utility;Development;
StartupNotify=true
"""

    desktop_path.write_text(desktop_content)
    os.chmod(desktop_path, 0o755)

    return desktop_path

def main():
    print("=== Application Installer ===")

    project_dir = Path(__file__).resolve().parent
    main_py = project_dir / "main.py"

    if not main_py.exists():
        print("ERROR: main.py not found in the project directory")
        sys.exit(1)

    if ask_yes_no("Do you want to install required dependencies?"):
        try:
            install_pacman(PACMAN_PACKAGES)
            print("Dependencies installed successfully")
        except subprocess.CalledProcessError as e:
            print(f"ERROR: dependency installation failed: {e}")
            sys.exit(1)
    else:
        print("Skipping dependency installation")

    desktop_path = create_desktop_file(main_py)

    print("\nInstallation completed successfully")
    print(f"main.py path: {main_py}")
    print(f"Desktop file: {desktop_path}")
    print("If the app does not appear in the menu, log out and log in again")

if __name__ == "__main__":
    main()
