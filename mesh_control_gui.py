import socket
import json
import ctypes
import threading
import time
from pynput import mouse, keyboard

PORT = 6060
BUFFER_SIZE = 1024

user32 = ctypes.windll.user32

# Get system metrics
SCREEN_WIDTH = user32.GetSystemMetrics(0)
SCREEN_HEIGHT = user32.GetSystemMetrics(1)
MONITOR_WIDTH = user32.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
MONITOR_HEIGHT = user32.GetSystemMetrics(79)  # SM_CYVIRTUALSCREEN

# Border threshold (pixels from edge to trigger transition)
BORDER_THRESHOLD = 2

# Virtual key codes for special keys
SPECIAL_KEYS = {
    'shift': 0x10,
    'ctrl': 0x11,
    'alt': 0x12,
    'enter': 0x0D,
    'tab': 0x09,
    'backspace': 0x08,
    'delete': 0x2E,
    'up': 0x26,
    'down': 0x28,
    'left': 0x25,
    'right': 0x27,
    'home': 0x24,
    'end': 0x23,
    'pageup': 0x21,
    'pagedown': 0x22,
    'esc': 0x1B,
}

# ---------------- Windows Input ----------------

def move_mouse(dx, dy):
    """Move mouse by relative offset"""
    user32.mouse_event(0x0001, int(dx), int(dy), 0, 0)

def mouse_click(button="left", double=False):
    """Click mouse button"""
    if button == "left":
        if double:
            user32.mouse_event(0x0002, 0, 0, 0, 0)
            user32.mouse_event(0x0004, 0, 0, 0, 0)
            time.sleep(0.05)
            user32.mouse_event(0x0002, 0, 0, 0, 0)
            user32.mouse_event(0x0004, 0, 0, 0, 0)
        else:
            user32.mouse_event(0x0002, 0, 0, 0, 0)
            user32.mouse_event(0x0004, 0, 0, 0, 0)
    elif button == "right":
        user32.mouse_event(0x0008, 0, 0, 0, 0)
        user32.mouse_event(0x0010, 0, 0, 0, 0)
    elif button == "middle":
        user32.mouse_event(0x0020, 0, 0, 0, 0)
        user32.mouse_event(0x0040, 0, 0, 0, 0)

def mouse_scroll(delta):
    """Scroll mouse wheel"""
    user32.mouse_event(0x0800, 0, 0, delta, 0)

def key_event(key_char, down=True):
    """Send keyboard input"""
    key_lower = str(key_char).lower()
    
    # Handle special keys
    if key_lower in SPECIAL_KEYS:
        vk = SPECIAL_KEYS[key_lower]
    else:
        # Handle regular character
        result = user32.VkKeyScanA(ord(key_char))
        vk = result & 0xFF
        shift = (result >> 8) & 0x01
        
        if shift and down:
            user32.keybd_event(0x10, 0, 0, 0)  # Press shift
        
        if down:
            user32.keybd_event(vk, 0, 0, 0)
        else:
            user32.keybd_event(vk, 0, 2, 0)
        
        if shift and not down:
            user32.keybd_event(0x10, 0, 2, 0)  # Release shift
        return
    
    if down:
        user32.keybd_event(vk, 0, 0, 0)
    else:
        user32.keybd_event(vk, 0, 2, 0)

def get_cursor_position():
    """Get current cursor position"""
    class Point(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    
    pt = Point()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y

def set_cursor_position(x, y):
    """Set cursor to absolute position"""
    user32.SetCursorPos(int(x), int(y))

# ---------------- CLIENT ----------------

def run_client():
    """Run client - receives and executes remote input"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", PORT))
    sock.settimeout(None)

    print(f"[CLIENT] Listening on port {PORT}...")
    print(f"[CLIENT] Screen resolution: {SCREEN_WIDTH}x{SCREEN_HEIGHT}")
    
    client_active = False
    last_update_time = time.time()

    try:
        while True:
            try:
                data, addr = sock.recvfrom(BUFFER_SIZE)
                if not data:
                    continue

                msg = json.loads(data.decode())
                msg_type = msg[0]

                # Smooth input processing
                if msg_type == "m":  # Mouse move
                    dx, dy = msg[1], msg[2]
                    move_mouse(dx, dy)
                    client_active = True

                elif msg_type == "c":  # Mouse click
                    button = msg[1] if len(msg) > 1 else "left"
                    double = msg[2] if len(msg) > 2 else False
                    mouse_click(button, double)
                    client_active = True

                elif msg_type == "s":  # Mouse scroll
                    delta = msg[1] if len(msg) > 1 else 0
                    mouse_scroll(delta)
                    client_active = True

                elif msg_type == "k":  # Keyboard input
                    key_char = msg[1]
                    is_down = msg[2] if len(msg) > 2 else True
                    key_event(key_char, is_down)
                    client_active = True

                elif msg_type == "show_cursor":  # Show cursor
                    user32.ShowCursor(True)

                elif msg_type == "hide_cursor":  # Hide cursor
                    user32.ShowCursor(False)

                last_update_time = time.time()

            except json.JSONDecodeError:
                continue
            except Exception as e:
                print(f"[CLIENT] Error processing input: {e}")
                continue

    except KeyboardInterrupt:
        print("[CLIENT] Shutdown...")
    finally:
        user32.ShowCursor(True)
        sock.close()

# ---------------- SERVER ----------------

def run_server():
    """Run server - captures local input and sends to client"""
    client_ip = input("[SERVER] Enter client IP: ").strip()
    if not client_ip:
        print("[SERVER] No IP provided. Exiting...")
        return

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(1.0)

    print(f"[SERVER] Server running at {client_ip}:{PORT}")
    print(f"[SERVER] Screen resolution: {SCREEN_WIDTH}x{SCREEN_HEIGHT}")
    print(f"[SERVER] Move cursor to RIGHT edge to switch control to client")

    control = False
    last_x, last_y = 0, 0
    mouse_controller = mouse.Controller()

    def send(msg):
        """Send message to client"""
        try:
            sock.sendto(json.dumps(msg).encode(), (client_ip, PORT))
        except Exception as e:
            print(f"[SERVER] Send error: {e}")

    def on_move(x, y):
        """Handle mouse movement"""
        nonlocal control, last_x, last_y

        # Calculate delta for smooth movement
        dx = x - last_x
        dy = y - last_y

        last_x = x
        last_y = y

        if not control:
            # Check if cursor moved to right edge (border transition)
            if x >= SCREEN_WIDTH - BORDER_THRESHOLD:
                control = True
                user32.ShowCursor(False)
                print("[SERVER] ✓ Control switched to CLIENT - Cursor hidden")
                send(["show_cursor"])

            # Prevent sending movement when in server control
            return

        else:
            # Check if cursor came back from left edge (return to server)
            if x <= BORDER_THRESHOLD:
                control = False
                user32.ShowCursor(True)
                print("[SERVER] ✓ Control returned to SERVER - Cursor shown")
                send(["hide_cursor"])
                
                # Reset position to safe area
                last_x = 50
                last_y = y
                mouse_controller.position = (50, y)
                return

            # Send smooth movement to client
            send(["m", dx, dy])

    def on_click(x, y, button, pressed):
        """Handle mouse clicks"""
        if control and pressed:
            button_name = "left"
            if button == mouse.Button.right:
                button_name = "right"
            elif button == mouse.Button.middle:
                button_name = "middle"
            
            send(["c", button_name, False])

    def on_scroll(x, y, dx, dy):
        """Handle mouse scroll"""
        if control:
            send(["s", int(dy) * 120])  # Normalize scroll delta

    def on_press(key):
        """Handle key press"""
        if control:
            try:
                if hasattr(key, 'char') and key.char:
                    send(["k", key.char, True])
                else:
                    # Handle special keys
                    key_name = str(key).lower()
                    if 'shift' in key_name:
                        send(["k", "shift", True])
                    elif 'ctrl' in key_name:
                        send(["k", "ctrl", True])
                    elif 'alt' in key_name:
                        send(["k", "alt", True])
                    elif 'enter' in key_name:
                        send(["k", "enter", True])
                    elif 'backspace' in key_name:
                        send(["k", "backspace", True])
                    elif 'delete' in key_name:
                        send(["k", "delete", True])
                    elif 'tab' in key_name:
                        send(["k", "tab", True])
            except Exception as e:
                pass

    def on_release(key):
        """Handle key release"""
        if control:
            try:
                if hasattr(key, 'char') and key.char:
                    send(["k", key.char, False])
                else:
                    key_name = str(key).lower()
                    if 'shift' in key_name:
                        send(["k", "shift", False])
                    elif 'ctrl' in key_name:
                        send(["k", "ctrl", False])
                    elif 'alt' in key_name:
                        send(["k", "alt", False])
                    elif 'enter' in key_name:
                        send(["k", "enter", False])
                    elif 'backspace' in key_name:
                        send(["k", "backspace", False])
                    elif 'delete' in key_name:
                        send(["k", "delete", False])
                    elif 'tab' in key_name:
                        send(["k", "tab", False])
            except Exception as e:
                pass

    # Start listeners
    mouse.Listener(on_move=on_move, on_click=on_click, on_scroll=on_scroll).start()
    keyboard.Listener(on_press=on_press, on_release=on_release).start()

    try:
        print("[SERVER] Input listeners active. Press Ctrl+C to exit.")
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("[SERVER] Shutdown...")
    finally:
        user32.ShowCursor(True)
        sock.close()

# ---------------- MAIN ----------------

if __name__ == "__main__":
    print("\n" + "="*50)
    print("          MESH CONTROL - Multi-Machine Input")
    print("="*50)
    print("\n1. Server (Monitor & Send)")
    print("2. Client (Receive & Execute)")
    print()

    mode = input("Select mode [1/2]: ").strip()

    if mode == "1":
        run_server()
    elif mode == "2":
        run_client()
    else:
        print("Invalid selection.")