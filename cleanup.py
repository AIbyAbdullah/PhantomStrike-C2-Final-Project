import os
import sys
import subprocess
import ctypes

# ======================================================
# ADMIN CHECK
# ======================================================
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def run_as_admin():
    if not is_admin():
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
        sys.exit()

run_as_admin()

# ======================================================
# RESTORE WEBCAM PERMISSIONS
# ======================================================
print("="*50)
print("    🔥 RESTORE WEBCAM PERMISSIONS")
print("="*50)

print("\n[*] Removing ALLOW permissions...")

# Remove ALLOW from registry
keys = [
    "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore\\webcam",
    "HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore\\webcam",
    "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore\\webcam\\NonPackaged"
]

for key in keys:
    try:
        subprocess.run(f'reg delete "{key}" /v Value /f', shell=True, capture_output=True)
        print(f"  [+] Removed ALLOW from: {key}")
    except:
        print(f"  [!] Key not found: {key}")

print("\n[*] Setting permissions to DEFAULT (ASK)...")

# Set to ASK (default)
commands = [
    'reg add "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore\\webcam" /v Value /t REG_SZ /d ASK /f',
    'reg add "HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore\\webcam" /v Value /t REG_SZ /d ASK /f',
    'reg add "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore\\webcam\\NonPackaged" /v Value /t REG_SZ /d ASK /f'
]

for cmd in commands:
    try:
        subprocess.run(cmd, shell=True, capture_output=True)
    except:
        pass

print("\n[+] Webcam permissions restored to DEFAULT!")
print("[+] System will now ASK before allowing webcam access.")

print("\n" + "="*50)
print("[+] Done!")
input("\nPress Enter to exit...")