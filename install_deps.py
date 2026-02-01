#!/usr/bin/env python3
import subprocess
import sys

# --- pacman dependencies (Arch Linux) ---
pacman_packages = [
    "python-gobject",
    "gtk4",
    "libadwaita",
    "python-gobject",
    "python-pip"
    "python-psutil"
    "python-distro"
]

def install_pacman(pkgs):
    print("Installing...")
    cmd = ["sudo", "pacman", "-Syu", "--noconfirm"] + pkgs
    subprocess.run(cmd, check=True)

def main():
    try:
        install_pacman(pacman_packages)
        install_pip(pip_packages)
        print("All deps have been installed")
    except subprocess.CalledProcessError as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
