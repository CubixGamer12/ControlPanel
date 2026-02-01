# ControlPanel

ControlPanel is a Python GTK4–based desktop application that provides a simple graphical control panel for managing application workflows and system-related actions.

> ⚠️ Personal project / experimental code. Use at your own risk.

---

## 🚀 Features

- GTK4 + libadwaita graphical interface
- Linux desktop integration via `.desktop` file
- One-click installer script
- Arch Linux–friendly dependency handling
- Simple and hackable Python codebase

---

## 📦 Requirements

- **Linux** (tested on Arch Linux)
- **Python 3.10+**
- GTK4 and libadwaita
- `pacman` package manager

---

## 🛠 Installation

Clone the repository:

```bash
git clone https://github.com/CubixGamer12/ControlPanel.git
cd ControlPanel
```

Run the installer:

```bash
python install.py
```

The installer will:
1. Ask whether you want to install required dependencies  
2. Install missing system packages using `pacman`  
3. Create a `.desktop` launcher for the application

---

## ▶️ Running the Application

After installation, launch **Control Panel** from your desktop application menu.

You can also run it manually:

```bash
/usr/bin/env python3 main.py
```

---

## 🧩 Dependencies

Installed automatically (Arch Linux):

- `python-gobject`
- `gtk4`
- `libadwaita`
- `python-pip`
- `python-psutil`
- `python-distro`

---

## 📁 Project Structure

```
ControlPanel/
├── install.py        # Installer (dependencies + desktop entry)
├── main.py           # Main application entry point
├── ControlPanel.desktop (generated)
└── configs/          # Configuration files (if present)
```

---

## 🧪 Status

This project is under active development and may change frequently.  
Expect rough edges and experimental code.

---

## 🧑‍💻 Contributing

Contributions are welcome!

1. Fork the repository  
2. Create a feature branch  
3. Commit your changes  
4. Open a Pull Request

---

## 📜 License

No license specified yet.  
You are free to use and modify this project for personal purposes.

---

## 👤 Author

**CubixGamer12**

GitHub: https://github.com/CubixGamer12
