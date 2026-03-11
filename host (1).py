"""
host.py - Remote Admin Host

Features:
  - Auto-installs ngrok if missing
  - Saves every successfully connected machine to computers.json
  - On launch shows a numbered list of known machines — connect by number
    or type "new" to connect to a new machine (adds it to the list)
  - Tracks hostname, last-seen time, and connection count per machine
  - Type "remove" at the menu to delete a saved entry
"""

import socket
import subprocess
import json
import sys
import os
import platform
import shutil
import urllib.request
import zipfile
import tarfile
import stat
import tempfile
import time
from datetime import datetime

SCRIPT_DIR    = os.path.dirname(os.path.abspath(__file__))
COMPUTERS_DB  = os.path.join(SCRIPT_DIR, "computers.json")
NGROK_BIN     = os.path.join(SCRIPT_DIR, "ngrok.exe" if platform.system() == "Windows" else "ngrok")
SYSTEM        = platform.system()

HELP_TEXT = """
─────────────────────────────────────────
  Available Commands
─────────────────────────────────────────
  Any shell command runs on the remote machine.

  Special:
    help        Show this message
    exit/quit   Disconnect and return to menu

  Windows examples:     Linux / Mac examples:
    whoami                whoami
    ipconfig              ip a / ifconfig
    tasklist              ps aux
    systeminfo            uname -a
    dir C:\\Users          ls -la
    netstat -an           netstat -an
─────────────────────────────────────────
"""


# ══════════════════════════════════════════════════════════════
#  COMPUTER DATABASE  (computers.json)
# ══════════════════════════════════════════════════════════════

def load_computers() -> list:
    if os.path.exists(COMPUTERS_DB):
        try:
            with open(COMPUTERS_DB) as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_computers(computers: list):
    with open(COMPUTERS_DB, "w") as f:
        json.dump(computers, f, indent=2)


def upsert_computer(computers: list, info: dict, host: str, port: int) -> list:
    """Add or update a computer record after a successful connection."""
    hostname = info.get("hostname", host)
    now      = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for entry in computers:
        if entry.get("hostname") == hostname:
            entry["last_address"] = host
            entry["last_port"]    = port
            entry["last_seen"]    = now
            entry["os"]           = info.get("os", entry.get("os", ""))
            entry["connections"]  = entry.get("connections", 0) + 1
            save_computers(computers)
            return computers

    # New machine
    computers.append({
        "hostname":     hostname,
        "last_address": host,
        "last_port":    port,
        "last_seen":    now,
        "os":           info.get("os", ""),
        "connections":  1,
    })
    save_computers(computers)
    return computers


def remove_computer(computers: list, index: int) -> list:
    computers.pop(index)
    save_computers(computers)
    return computers


def print_computer_list(computers: list):
    if not computers:
        print("  (no saved machines yet)\n")
        return
    print(f"  {'#':<4} {'Hostname':<22} {'OS':<10} {'Last Seen':<20} {'Address'}")
    print("  " + "─" * 75)
    for i, c in enumerate(computers):
        host_str = f"{c.get('last_address','')}:{c.get('last_port','')}"
        print(
            f"  {i+1:<4} {c.get('hostname','?'):<22} "
            f"{c.get('os','?'):<10} {c.get('last_seen','never'):<20} {host_str}"
        )
    print()


# ══════════════════════════════════════════════════════════════
#  NGROK — install (host doesn't need it to connect outbound,
#           but installs it anyway so admin can also run client)
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


def ensure_ngrok():
    if ngrok_binary():
        return
    print("[!] ngrok not found — installing automatically...")
    try:
        download_ngrok()
        print("[✓] ngrok installed.\n")
    except Exception as e:
        print(f"[!] Could not install ngrok: {e} (not required for host, continuing)\n")


# ══════════════════════════════════════════════════════════════
#  SOCKET HELPERS
# ══════════════════════════════════════════════════════════════

def recv_until(sock, marker: bytes) -> str:
    data = b""
    while not data.endswith(marker):
        chunk = sock.recv(4096)
        if not chunk:
            break
        data += chunk
    return data.decode()


def receive_response(sock) -> str:
    header = b""
    while not header.endswith(b"\n"):
        byte = sock.recv(1)
        if not byte:
            return "[ERROR] Connection closed."
        header += byte

    header_str = header.decode().strip()
    if not header_str.startswith("BEGIN "):
        return f"[ERROR] Unexpected response: {header_str}"

    length = int(header_str.split()[1])
    data   = b""
    while len(data) < length:
        chunk = sock.recv(min(4096, length - len(data)))
        if not chunk:
            break
        data += chunk

    sock.recv(5)  # consume \nEND\n
    return data.decode()


# ══════════════════════════════════════════════════════════════
#  CONNECTION — prompt, auth, session
# ══════════════════════════════════════════════════════════════

def prompt_new_connection() -> tuple[str, int, str]:
    """Ask the admin to enter ngrok address, port, and auth code."""
    print("\nEnter the details shown on the CLIENT machine:\n")
    target_host = input("  Ngrok Address (e.g. 0.tcp.ngrok.io): ").strip()
    target_port = int(input("  Ngrok Port    (e.g. 12345):          ").strip())
    code        = input("  Auth Code     (e.g. X7K2QR):          ").strip().upper()
    return target_host, target_port, code


def connect_and_run(target_host: str, target_port: int, code: str, computers: list) -> list:
    """Connect to a client, run command session, update computer list. Returns updated list."""
    print(f"\n[*] Connecting to {target_host}:{target_port}...")

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(15)
        sock.connect((target_host, target_port))
    except socket.timeout:
        print("[✗] Connection timed out. Is the client running?")
        return computers
    except (ConnectionRefusedError, OSError) as e:
        print(f"[✗] Could not connect: {e}")
        return computers

    sock.settimeout(None)

    # Auth
    prompt = recv_until(sock, b"\n")
    if "ENTER_CODE" not in prompt:
        print(f"[✗] Unexpected response: {prompt}")
        sock.close()
        return computers

    sock.sendall((code + "\n").encode())
    response = recv_until(sock, b"\n")

    if "AUTH_FAILED" in response:
        print("[✗] Authentication failed — wrong code.")
        sock.close()
        return computers

    if "AUTH_OK" not in response:
        print(f"[✗] Unexpected auth response: {response}")
        sock.close()
        return computers

    print("[+] Authenticated!\n")

    # System info
    sysinfo_line = recv_until(sock, b"\n").strip()
    info = {}
    if sysinfo_line.startswith("SYSINFO "):
        info = json.loads(sysinfo_line[8:])
        print("─" * 50)
        print("  Remote System")
        print("─" * 50)
        for k, v in info.items():
            print(f"  {k:<15} {v}")
        print("─" * 50)
        print(f"\n  Connected to : {info.get('hostname', target_host)}")
        print("  Type 'help' for commands. Type 'exit' to return to menu.\n")

    # Save / update this computer in the database
    computers = upsert_computer(computers, info, target_host, target_port)

    # Command loop
    while True:
        try:
            cmd = input("remote> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n[*] Disconnecting...")
            sock.sendall(b"exit\n")
            break

        if not cmd:
            continue
        if cmd.lower() == "help":
            print(HELP_TEXT)
            continue
        if cmd.lower() in ("exit", "quit", "disconnect"):
            sock.sendall(b"exit\n")
            print("[*] Disconnected.")
            break

        sock.sendall((cmd + "\n").encode())
        try:
            print(receive_response(sock))
        except Exception as e:
            print(f"[!] Error: {e}")
            break

    sock.close()
    return computers


# ══════════════════════════════════════════════════════════════
#  MAIN MENU
# ══════════════════════════════════════════════════════════════

def main():
    ensure_ngrok()

    computers = load_computers()

    while True:
        print()
        print("═" * 55)
        print("   Remote Admin Host  —  Saved Machines")
        print("═" * 55)
        print_computer_list(computers)

        if computers:
            print("  Enter a number to reconnect, 'new' to add a machine,")
            print("  'remove <#>' to delete an entry, or 'quit' to exit.")
        else:
            print("  Enter 'new' to connect to a machine, or 'quit' to exit.")

        print()
        try:
            choice = input("  Choice: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\n[*] Bye.")
            break

        # ── quit ──────────────────────────────────────────────
        if choice in ("quit", "exit", "q"):
            print("[*] Bye.")
            break

        # ── remove <n> ────────────────────────────────────────
        if choice.startswith("remove"):
            parts = choice.split()
            if len(parts) == 2 and parts[1].isdigit():
                idx = int(parts[1]) - 1
                if 0 <= idx < len(computers):
                    removed = computers[idx]["hostname"]
                    computers = remove_computer(computers, idx)
                    print(f"[✓] Removed '{removed}' from saved machines.")
                else:
                    print("[!] Invalid number.")
            else:
                print("[!] Usage: remove <number>")
            continue

        # ── new connection ────────────────────────────────────
        if choice == "new":
            target_host, target_port, code = prompt_new_connection()
            computers = connect_and_run(target_host, target_port, code, computers)
            continue

        # ── reconnect by number ───────────────────────────────
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(computers):
                entry = computers[idx]
                print(f"\n[*] Reconnecting to {entry['hostname']}...")
                print(f"    Last address: {entry['last_address']}:{entry['last_port']}")
                print()
                print("  The ngrok port changes on every reboot.")
                print("  Enter the current details from the client machine:\n")
                use_saved = input(
                    f"  Use saved address ({entry['last_address']}:{entry['last_port']})? [y/n]: "
                ).strip().lower()

                if use_saved == "y":
                    target_host = entry["last_address"]
                    target_port = entry["last_port"]
                else:
                    target_host = input("  New Ngrok Address: ").strip()
                    target_port = int(input("  New Ngrok Port:    ").strip())

                code = input("  Auth Code (from client): ").strip().upper()
                computers = connect_and_run(target_host, target_port, code, computers)
            else:
                print("[!] Invalid number.")
            continue

        print("[!] Unrecognized input. Enter a number, 'new', 'remove <#>', or 'quit'.")


if __name__ == "__main__":
    main()
