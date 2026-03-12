"""
Mesh Control - Windows-to-Windows Desktop Application

A Python application that allows one Windows laptop (server) to control 
another laptop (client) using a single keyboard, mouse, and shared clipboard 
over the local network.

Features:
- Manual client IP input (no auto-discovery)
- Smooth cursor edge switching between displays
- Keyboard and mouse control sharing
- Clipboard synchronization
- Modern Tkinter GUI with dark theme
- Low-latency UDP networking
- Windows native input injection
"""

import sys
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import socket
import json
import time
import ctypes
from ctypes import Structure, POINTER, c_int, c_uint, c_char_p, c_ulonglong, Union, wintypes
from pynput import mouse, keyboard
from pynput.keyboard import Key
import logging
import pyperclip
from collections import defaultdict
from datetime import datetime, timedelta
import os

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('mesh_control.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================================================
# GLOBAL CONFIGURATION
# ============================================================================

CONTROL_PORT = 6060          # UDP port for mouse/keyboard control
CLIPBOARD_PORT = 6061        # UDP port for clipboard sync
CURSOR_EDGE_THRESHOLD = 5    # pixels from edge to trigger cursor switch
CLIPBOARD_CHECK_INTERVAL = 0.5  # seconds

# ============================================================================
# WINDOWS API BINDINGS (CTYPES)
# ============================================================================

class POINT(Structure):
    _fields_ = [("x", c_int), ("y", c_int)]

class MOUSEINPUT(Structure):
    _fields_ = [("dx", c_int), ("dy", c_int), ("mouseData", c_uint),
                ("dwFlags", c_uint), ("time", c_uint), ("dwExtraInfo", c_uint)]

class KEYBDINPUT(Structure):
    _fields_ = [("wVk", c_uint), ("wScan", c_uint), ("dwFlags", c_uint),
                ("time", c_uint), ("dwExtraInfo", c_uint)]

class HARDWAREINPUT(Structure):
    _fields_ = [("uMsg", c_uint), ("wParamL", c_uint), ("wParamH", c_uint)]

class INPUT_UNION(Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

class INPUT(Structure):
    _fields_ = [("type", c_uint), ("ii", INPUT_UNION)]

# Windows API constants
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800

KEYEVENTF_KEYUP = 0x0002

# Virtual key codes
VK_CODES = {
    Key.enter: 0x0D,
    Key.backspace: 0x08,
    Key.tab: 0x09,
    Key.shift: 0x10,
    Key.ctrl: 0x11,
    Key.alt: 0x12,
    Key.space: 0x20,
    Key.esc: 0x1B,
    Key.left: 0x25,
    Key.right: 0x27,
    Key.up: 0x26,
    Key.down: 0x28,
    Key.delete: 0x2E,
}

# ============================================================================
# WINDOWS INPUT INJECTION
# ============================================================================

class WindowsInput:
    """Windows input injection via ctypes"""
    
    @staticmethod
    def get_cursor_position():
        """Get current cursor position"""
        pos = POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pos))
        return (pos.x, pos.y)
    
    @staticmethod
    def set_cursor_position(x, y):
        """Set cursor to absolute position"""
        ctypes.windll.user32.SetCursorPos(x, y)
    
    @staticmethod
    def send_input(input_obj):
        """Send input to Windows"""
        result = ctypes.windll.user32.SendInput(1, ctypes.byref(input_obj), ctypes.sizeof(INPUT))
        return result
    
    @staticmethod
    def move_mouse(dx, dy):
        """Move mouse by relative amount"""
        mouse_input = MOUSEINPUT(dx, dy, 0, MOUSEEVENTF_MOVE, 0, 0)
        input_union = INPUT_UNION()
        input_union.mi = mouse_input
        input_obj = INPUT(INPUT_MOUSE, input_union)
        WindowsInput.send_input(input_obj)
    
    @staticmethod
    def mouse_click(button='left', down=True):
        """Inject mouse click"""
        if button == 'left':
            flag = MOUSEEVENTF_LEFTDOWN if down else MOUSEEVENTF_LEFTUP
        elif button == 'right':
            flag = MOUSEEVENTF_RIGHTDOWN if down else MOUSEEVENTF_RIGHTUP
        elif button == 'middle':
            flag = MOUSEEVENTF_MIDDLEDOWN if down else MOUSEEVENTF_MIDDLEUP
        else:
            return
        
        mouse_input = MOUSEINPUT(0, 0, 0, flag, 0, 0)
        input_union = INPUT_UNION()
        input_union.mi = mouse_input
        input_obj = INPUT(INPUT_MOUSE, input_union)
        WindowsInput.send_input(input_obj)
    
    @staticmethod
    def get_vk_code(key):
        """Get virtual key code for keyboard key"""
        if key in VK_CODES:
            return VK_CODES[key]
        
        try:
            if isinstance(key, str):
                return ord(key.upper())
            elif hasattr(key, 'char'):
                char = key.char
                if char and len(char) == 1 and ord(char) < 256:
                    return ord(char.upper())
        except:
            pass
        
        return None
    
    @staticmethod
    def key_down(key):
        """Inject key down event"""
        vk = WindowsInput.get_vk_code(key)
        if vk is None:
            return
        
        kb_input = KEYBDINPUT(vk, 0, 0, 0, 0)
        input_union = INPUT_UNION()
        input_union.ki = kb_input
        input_obj = INPUT(INPUT_KEYBOARD, input_union)
        WindowsInput.send_input(input_obj)
    
    @staticmethod
    def key_up(key):
        """Inject key up event"""
        vk = WindowsInput.get_vk_code(key)
        if vk is None:
            return
        
        kb_input = KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP, 0, 0)
        input_union = INPUT_UNION()
        input_union.ki = kb_input
        input_obj = INPUT(INPUT_KEYBOARD, input_union)
        WindowsInput.send_input(input_obj)

    @staticmethod
    def show_cursor(show=True):
        """Show or hide cursor"""
        ctypes.windll.user32.ShowCursor(show)
    
    @staticmethod
    def get_screen_resolution():
        """Get screen resolution"""
        width = ctypes.windll.user32.GetSystemMetrics(0)
        height = ctypes.windll.user32.GetSystemMetrics(1)
        return (width, height)

# ============================================================================
# NETWORK UTILITIES
# ============================================================================

class NetworkUtils:
    """Network utilities"""
    
    @staticmethod
    def get_hostname():
        """Get computer hostname"""
        return socket.gethostname()

# ============================================================================
# CLIENT LOGIC
# ============================================================================

class ClientController:
    """Client mode - receives and applies input from server"""
    
    def __init__(self, config=None):
        self.config = config or {}
        self.running = False
        self.control_socket = None
        self.clipboard_socket = None
        self.last_clipboard = ""
        self.server_address = None
        
    def start(self):
        """Start client server"""
        self.running = True
        
        # Start control listener
        control_thread = threading.Thread(target=self._control_listen_loop, daemon=True)
        control_thread.start()
        
        # Start clipboard sync
        clipboard_thread = threading.Thread(target=self._clipboard_sync_loop, daemon=True)
        clipboard_thread.start()
        
        logger.info("Client started, listening for control...")
    
    def stop(self):
        """Stop client"""
        self.running = False
        if self.control_socket:
            try:
                self.control_socket.close()
            except:
                pass
        if self.clipboard_socket:
            try:
                self.clipboard_socket.close()
            except:
                pass
    
    def _control_listen_loop(self):
        """Listen for control packets"""
        try:
            self.control_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.control_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.control_socket.bind(('0.0.0.0', CONTROL_PORT))
            self.control_socket.settimeout(1.0)
            
            logger.info(f"Control listener on port {CONTROL_PORT}")
            
            while self.running:
                try:
                    data, addr = self.control_socket.recvfrom(1024)
                    self.server_address = addr
                    
                    # Skip empty or non-JSON packets
                    try:
                        packet = json.loads(data.decode('utf-8'))
                        self._handle_control_packet(packet)
                    except json.JSONDecodeError:
                        logger.debug(f"Received non-JSON packet from {addr}, ignoring")
                        continue
                except socket.timeout:
                    continue
                except Exception as e:
                    logger.error(f"Control receive error: {e}")
        except Exception as e:
            logger.error(f"Control listen error: {e}")
    
    def _handle_control_packet(self, packet):
        """Handle incoming control packet"""
        ptype = packet.get('type')
        
        # Skip handshake packets (just for connection verification)
        if ptype == 'handshake':
            return
        
        if ptype == 'mouse_move':
            dx, dy = packet.get('dx', 0), packet.get('dy', 0)
            if self.config.get('mouse_enabled', True):
                WindowsInput.move_mouse(dx, dy)
        
        elif ptype == 'mouse_click':
            button = packet.get('button', 'left')
            down = packet.get('down', True)
            if self.config.get('mouse_enabled', True):
                WindowsInput.mouse_click(button, down)
        
        elif ptype == 'key_press':
            key = packet.get('key')
            down = packet.get('down', True)
            if self.config.get('keyboard_enabled', True):
                if down:
                    WindowsInput.key_down(key)
                else:
                    WindowsInput.key_up(key)
        
        elif ptype == 'cursor_edge':
            # Client cursor hit edge, send return control signal
            self._send_return_control()
    
    def _send_return_control(self):
        """Send signal to server that cursor hit edge"""
        if not self.server_address:
            return
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            packet = json.dumps({"type": "return_control"})
            sock.sendto(packet.encode('utf-8'), self.server_address)
            sock.close()
        except Exception as e:
            logger.error(f"Return control error: {e}")
    
    def _clipboard_sync_loop(self):
        """Sync clipboard with server"""
        if not self.config.get('clipboard_enabled', False):
            return
        
        try:
            self.clipboard_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.clipboard_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.clipboard_socket.bind(('0.0.0.0', CLIPBOARD_PORT))
            self.clipboard_socket.settimeout(1.0)
            
            while self.running and self.config.get('clipboard_enabled', False):
                try:
                    data, addr = self.clipboard_socket.recvfrom(4096)
                    try:
                        packet = json.loads(data.decode('utf-8'))
                        if packet.get('type') == 'clipboard':
                            content = packet.get('text', '')
                            pyperclip.copy(content)
                            logger.debug(f"Clipboard synced: {len(content)} chars")
                    except json.JSONDecodeError:
                        logger.debug(f"Received non-JSON clipboard packet, ignoring")
                        continue
                except socket.timeout:
                    continue
        except Exception as e:
            logger.error(f"Clipboard sync error: {e}")

# ============================================================================
# SERVER LOGIC
# ============================================================================

class ServerController:
    """Server mode - captures input and sends to client"""
    
    def __init__(self, client_ip, config=None):
        self.client_ip = client_ip
        self.client_addr = (client_ip, CONTROL_PORT)
        self.clipboard_addr = (client_ip, CLIPBOARD_PORT)
        self.config = config or {}
        self.running = False
        self.cursor_in_control = True
        self.last_clipboard = ""
        self.control_socket = None
        self.clipboard_socket = None
        
        # Get screen dimensions
        self.screen_width, self.screen_height = WindowsInput.get_screen_resolution()
        logger.info(f"Screen resolution: {self.screen_width}x{self.screen_height}")
    
    def start(self):
        """Start server"""
        self.running = True
        
        # Start input capture
        input_thread = threading.Thread(target=self._input_capture_loop, daemon=True)
        input_thread.start()
        
        # Start clipboard sync
        clipboard_thread = threading.Thread(target=self._clipboard_sync_loop, daemon=True)
        clipboard_thread.start()
        
        logger.info(f"Server started, forwarding to {self.client_ip}")
    
    def stop(self):
        """Stop server"""
        self.running = False
        if self.control_socket:
            try:
                self.control_socket.close()
            except:
                pass
        if self.clipboard_socket:
            try:
                self.clipboard_socket.close()
            except:
                pass
    
    def _input_capture_loop(self):
        """Capture mouse and keyboard input"""
        try:
            self.control_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        except Exception as e:
            logger.error(f"Socket creation error: {e}")
            return
        
        last_pos = WindowsInput.get_cursor_position()
        
        def on_move(x, y):
            nonlocal last_pos
            
            if not self.running or not self.config.get('mouse_enabled', True):
                return
            
            # Check for cursor edge
            if self._should_transfer_control(x, y):
                self.cursor_in_control = False
                WindowsInput.show_cursor(False)  # Hide cursor
            
            if not self.cursor_in_control:
                return
            
            # Calculate relative movement
            dx = x - last_pos[0]
            dy = y - last_pos[1]
            last_pos = (x, y)
            
            if dx != 0 or dy != 0:
                packet = json.dumps({"type": "mouse_move", "dx": dx, "dy": dy})
                try:
                    self.control_socket.sendto(packet.encode('utf-8'), self.client_addr)
                except Exception as e:
                    logger.debug(f"Send error: {e}")
        
        def on_click(x, y, button, pressed):
            if not self.running or not self.config.get('mouse_enabled', True):
                return
            
            if not self.cursor_in_control:
                return
            
            button_name = {'left': 'left', 'right': 'right', 'middle': 'middle'}.get(str(button), 'left')
            packet = json.dumps({"type": "mouse_click", "button": button_name, "down": pressed})
            try:
                self.control_socket.sendto(packet.encode('utf-8'), self.client_addr)
            except Exception as e:
                logger.debug(f"Send error: {e}")
        
        def on_key(key, pressed):
            if not self.running or not self.config.get('keyboard_enabled', True):
                return
            
            if not self.cursor_in_control:
                return
            
            try:
                key_str = str(key).replace("'", "")
                packet = json.dumps({"type": "key_press", "key": key_str, "down": pressed})
                self.control_socket.sendto(packet.encode('utf-8'), self.client_addr)
            except Exception as e:
                logger.debug(f"Send error: {e}")
        
        with mouse.Listener(on_move=on_move, on_click=on_click) as m_listener:
            with keyboard.Listener(on_press=on_key, on_release=on_key) as k_listener:
                while self.running:
                    time.sleep(0.01)
    
    def _should_transfer_control(self, x, y):
        """Check if cursor hit edge and should transfer control"""
        client_pos = self.config.get('client_position', 'right')
        
        if client_pos == 'right':
            return x >= (self.screen_width - CURSOR_EDGE_THRESHOLD)
        else:  # left
            return x <= CURSOR_EDGE_THRESHOLD
    
    def _clipboard_sync_loop(self):
        """Sync clipboard to client"""
        if not self.config.get('clipboard_enabled', False):
            return
        
        try:
            self.clipboard_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        except Exception as e:
            logger.error(f"Clipboard socket error: {e}")
            return
        
        while self.running and self.config.get('clipboard_enabled', False):
            try:
                current = pyperclip.paste()
                if current != self.last_clipboard:
                    self.last_clipboard = current
                    packet = json.dumps({"type": "clipboard", "text": current})
                    self.clipboard_socket.sendto(packet.encode('utf-8'), self.clipboard_addr)
                    logger.debug(f"Clipboard sent: {len(current)} chars")
            except Exception as e:
                logger.debug(f"Clipboard error: {e}")
            
            time.sleep(CLIPBOARD_CHECK_INTERVAL)

# ============================================================================
# GUI
# ============================================================================

class MeshControlGUI:
    """Main GUI application"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("Mesh Control")
        self.root.geometry("500x600")
        
        self.server = None
        self.client = None
        self.running_mode = None
        self.connected = False
        
        self._setup_style()
        self._setup_ui()
    
    def _setup_style(self):
        """Configure ttk theme"""
        style = ttk.Style()
        style.theme_use('clam')
        
        # Dark theme colors
        bg_color = "#1e1e1e"
        fg_color = "#ffffff"
        accent1 = "#0066cc"  # Blue
        accent2 = "#9933cc"  # Purple
        
        self.root.configure(bg=bg_color)
        
        style.configure('TFrame', background=bg_color)
        style.configure('TLabel', background=bg_color, foreground=fg_color)
        style.configure('TButton', background=accent1, foreground=fg_color)
        style.configure('Header.TLabel', font=('Arial', 18, 'bold'), foreground=accent1)
        style.configure('Status.TLabel', font=('Arial', 12, 'bold'))
        style.configure('TCheckbutton', background=bg_color, foreground=fg_color)
    
    def _setup_ui(self):
        """Build UI"""
        # Header
        header_frame = ttk.Frame(self.root)
        header_frame.pack(fill=tk.X, padx=20, pady=20)
        
        title_label = ttk.Label(header_frame, text="Mesh Control", style='Header.TLabel')
        title_label.pack()
        
        # Status indicator
        self.status_frame = ttk.Frame(header_frame)
        self.status_frame.pack(pady=10)
        
        self.status_indicator = tk.Canvas(self.status_frame, width=20, height=20, bg="#1e1e1e", highlightthickness=0)
        self.status_indicator.pack(side=tk.LEFT, padx=5)
        self.status_indicator.create_oval(2, 2, 18, 18, fill="#ff4444", outline="#ff4444")
        
        self.status_label = ttk.Label(self.status_frame, text="Disconnected", style='Status.TLabel')
        self.status_label.pack(side=tk.LEFT)
        
        # Mode selection
        mode_frame = ttk.LabelFrame(self.root, text="Mode", padding=10)
        mode_frame.pack(fill=tk.X, padx=20, pady=10)
        
        self.mode_var = tk.StringVar(value="server")
        
        ttk.Radiobutton(mode_frame, text="Server (Control client)", variable=self.mode_var, 
                       value="server", command=self._on_mode_changed).pack(anchor=tk.W)
        ttk.Radiobutton(mode_frame, text="Client (Be controlled)", variable=self.mode_var,
                       value="client", command=self._on_mode_changed).pack(anchor=tk.W)
        
        # Connection section
        self.conn_frame = ttk.LabelFrame(self.root, text="Connection", padding=10)
        self.conn_frame.pack(fill=tk.X, padx=20, pady=10)
        
        ttk.Label(self.conn_frame, text="Client IP Address:").pack(anchor=tk.W)
        
        ip_entry_frame = ttk.Frame(self.conn_frame)
        ip_entry_frame.pack(fill=tk.X, pady=5)
        
        self.client_ip_var = tk.StringVar()
        self.client_ip_entry = ttk.Entry(ip_entry_frame, textvariable=self.client_ip_var, width=20)
        self.client_ip_entry.pack(side=tk.LEFT, padx=5)
        
        self.connect_btn = ttk.Button(ip_entry_frame, text="Connect", command=self._on_connect)
        self.connect_btn.pack(side=tk.LEFT)
        
        # Status display
        self.conn_status_label = ttk.Label(self.conn_frame, text="", foreground="blue")
        self.conn_status_label.pack(anchor=tk.W, pady=5)
        
        # Configuration section
        self.config_frame = ttk.LabelFrame(self.root, text="Configuration", padding=10)
        self.config_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        ttk.Label(self.config_frame, text="Client Position:").pack(anchor=tk.W, pady=5)
        
        position_frame = ttk.Frame(self.config_frame)
        position_frame.pack(anchor=tk.W, padx=20)
        
        self.client_position = tk.StringVar(value="right")
        ttk.Radiobutton(position_frame, text="Right", variable=self.client_position, 
                       value="right").pack(anchor=tk.W)
        ttk.Radiobutton(position_frame, text="Left", variable=self.client_position,
                       value="left").pack(anchor=tk.W)
        
        # Feature toggles
        ttk.Separator(self.config_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)
        
        self.keyboard_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.config_frame, text="Enable keyboard sharing", 
                       variable=self.keyboard_var).pack(anchor=tk.W, pady=3)
        
        self.clipboard_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.config_frame, text="Enable clipboard sharing",
                       variable=self.clipboard_var).pack(anchor=tk.W, pady=3)
        
        self.mouse_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.config_frame, text="Enable mouse sharing",
                       variable=self.mouse_var).pack(anchor=tk.W, pady=3)
        
        # Control buttons
        button_frame = ttk.Frame(self.root)
        button_frame.pack(fill=tk.X, padx=20, pady=10)
        
        self.start_btn = ttk.Button(button_frame, text="Start", command=self._on_start)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = ttk.Button(button_frame, text="Stop", command=self._on_stop, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        # Disable config initially
        self._set_config_enabled(False)
    
    def _on_mode_changed(self):
        """Handle mode change"""
        mode = self.mode_var.get()
        
        if mode == "server":
            self.conn_frame.config(text="Connection (Enter client IP)")
            self.client_ip_entry.config(state=tk.NORMAL)
            self.connect_btn.config(state=tk.NORMAL)
            self._set_config_enabled(False)
        else:
            self.conn_frame.config(text="Connection (Listen for server)")
            self.client_ip_entry.config(state=tk.DISABLED)
            self.connect_btn.config(state=tk.DISABLED)
            self._set_config_enabled(False)
    
    def _set_config_enabled(self, enabled):
        """Enable/disable config section"""
        state = tk.NORMAL if enabled else tk.DISABLED
        
        for child in self.config_frame.winfo_children():
            if isinstance(child, ttk.Checkbutton) or isinstance(child, ttk.Radiobutton):
                child.config(state=state)
    
    def _on_connect(self):
        """Connect to client (server mode)"""
        client_ip = self.client_ip_var.get().strip()
        
        if not client_ip:
            messagebox.showerror("Error", "Please enter client IP address")
            return
        
        # Verify we can reach the client
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(2)
            # Send handshake packet as JSON
            handshake = json.dumps({"type": "handshake"})
            sock.sendto(handshake.encode('utf-8'), (client_ip, CONTROL_PORT))
            sock.close()
            
            self.conn_status_label.config(
                text=f"Connected to: {client_ip}",
                foreground="green"
            )
            self.connected = True
            self._set_config_enabled(True)
            self.client_ip_entry.config(state=tk.DISABLED)
            self.connect_btn.config(state=tk.DISABLED)
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to connect to {client_ip}:\n{e}")
            self.connected = False
    
    def _on_start(self):
        """Start server or client"""
        mode = self.mode_var.get()
        
        if mode == "server":
            if not self.connected:
                messagebox.showerror("Error", "Please connect to a client first")
                return
            
            self._start_server()
        else:
            self._start_client()
    
    def _start_server(self):
        """Start server mode"""
        client_ip = self.client_ip_var.get()
        
        config = {
            'client_position': self.client_position.get(),
            'keyboard_enabled': self.keyboard_var.get(),
            'clipboard_enabled': self.clipboard_var.get(),
            'mouse_enabled': self.mouse_var.get(),
        }
        
        self.server = ServerController(client_ip, config)
        self.server.start()
        self.running_mode = "server"
        
        self._update_status("Server Running", True)
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.connect_btn.config(state=tk.DISABLED)
        self.mode_var_widget = tk.StringVar(value="server")
        
        logger.info(f"Server started, controlling {client_ip}")
    
    def _start_client(self):
        """Start client mode"""
        config = {
            'keyboard_enabled': self.keyboard_var.get(),
            'clipboard_enabled': self.clipboard_var.get(),
            'mouse_enabled': self.mouse_var.get(),
        }
        
        self.client = ClientController(config)
        self.client.start()
        self.running_mode = "client"
        
        self._update_status("Client Running", True)
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        
        logger.info("Client started, listening for control...")
    
    def _on_stop(self):
        """Stop server or client"""
        if self.server:
            self.server.stop()
            self.server = None
        
        if self.client:
            self.client.stop()
            self.client = None
        
        self.running_mode = None
        self.connected = False
        
        self._update_status("Disconnected", False)
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.connect_btn.config(state=tk.NORMAL)
        self.client_ip_entry.config(state=tk.NORMAL)
        self.conn_status_label.config(text="")
        
        self._set_config_enabled(False)
        logger.info("Stopped")
    
    def _update_status(self, text, connected):
        """Update status indicator"""
        self.status_label.config(text=text)
        color = "#44ff44" if connected else "#ff4444"
        self.status_indicator.delete("all")
        self.status_indicator.create_oval(2, 2, 18, 18, fill=color, outline=color)

# ============================================================================
# MAIN
# ============================================================================

def main():
    """Main entry point"""
    root = tk.Tk()
    app = MeshControlGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
