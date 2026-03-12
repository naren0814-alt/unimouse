"""
Mesh Control - Windows-to-Windows Multi-Computer Control Application

A Python application that allows one computer (server) to control up to two other 
computers (clients) using a single keyboard and mouse over a local network.

Features:
- Automatic client discovery via UDP broadcast
- Smooth cursor edge switching between computers
- Low-latency UDP networking
- Windows native input injection
- Tkinter-based GUI
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
from collections import defaultdict
from datetime import datetime, timedelta
import os
import subprocess

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

DISCOVERY_PORT = 15050  # Changed from 5050 to avoid privilege requirements
CONTROL_PORT = 16060    # Changed from 6060 to avoid privilege requirements
DISCOVERY_INTERVAL = 2.0  # seconds
CLIENT_HEARTBEAT_TIMEOUT = 10.0  # seconds
CURSOR_EDGE_THRESHOLD = 5  # pixels from edge to trigger switch
BROADCAST_ADDRESS = '255.255.255.255'

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
INPUT_HARDWARE = 2

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_WHEEL = 0x0800

KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

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

class WindowsInput:
    """Windows input injection via ctypes"""
    
    @staticmethod
    def get_cursor_position():
        """Get current cursor position"""
        pos = POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pos))
        return (pos.x, pos.y)
    
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
        
        # Try to extract character
        try:
            if isinstance(key, str):
                return ord(key.upper())
            elif hasattr(key, 'char'):
                char = key.char
                if char and len(char) == 1 and ord(char) < 256:
                    return ord(char.upper())
            elif hasattr(key, 'vk'):
                # Some pynput keys have vk attribute
                return key.vk
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

# ============================================================================
# NETWORK UTILITIES
# ============================================================================

class NetworkUtils:
    """Network utilities for discovery and communication"""
    
    @staticmethod
    def get_local_ip():
        """Get local IP address"""
        try:
            # Connect to external host to determine local IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"
    
    @staticmethod
    def get_hostname():
        """Get computer hostname"""
        return socket.gethostname()

# ============================================================================
# DISCOVERY SYSTEM
# ============================================================================

class DiscoveryManager:
    """Manages client discovery via UDP broadcast"""
    
    def __init__(self, mode='server'):
        self.mode = mode
        self.discovered_clients = {}  # {client_id: {hostname, ip, last_seen}}
        self.running = False
        self.socket = None
        self.thread = None
    
    def start(self):
        """Start discovery"""
        self.running = True
        self.thread = threading.Thread(target=self._discovery_loop, daemon=True)
        self.thread.start()
        logger.info("Discovery manager started")
    
    def stop(self):
        """Stop discovery"""
        self.running = False
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
    
    def _discovery_loop(self):
        """Main discovery loop"""
        if self.mode == 'server':
            self._server_discovery_loop()
        else:
            self._client_discovery_loop()
    
    def _server_discovery_loop(self):
        """Server listening for client broadcasts"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                # Try to set SO_EXCLUSIVEADDRUSE on Windows to avoid conflicts
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            except (AttributeError, OSError):
                pass  # Not available on all systems
            
            try:
                self.socket.bind(('', DISCOVERY_PORT))
            except OSError as e:
                logger.error(f"Failed to bind to port {DISCOVERY_PORT}: {e}")
                logger.info("NOTE: You may need to run the application as Administrator")
                return
            
            self.socket.settimeout(1.0)
            
            server_ip = NetworkUtils.get_local_ip()
            logger.info(f"Server discovery listening on port {DISCOVERY_PORT}")
            logger.info(f"Server IP: {server_ip}")
            
            while self.running:
                try:
                    data, addr = self.socket.recvfrom(1024)
                    packet = json.loads(data.decode('utf-8'))
                    
                    if packet.get('type') == 'mesh_client':
                        client_id = f"{packet['hostname']}@{packet['ip']}"
                        self.discovered_clients[client_id] = {
                            'hostname': packet['hostname'],
                            'ip': packet['ip'],
                            'last_seen': datetime.now()
                        }
                        logger.info(f"✓ Discovered client: {client_id} from {addr[0]}")
                except socket.timeout:
                    pass
                except json.JSONDecodeError as e:
                    logger.debug(f"Invalid discovery packet: {e}")
                except Exception as e:
                    logger.warning(f"Error in discovery: {e}")
                
                # Clean up stale clients
                self._cleanup_stale_clients()
        
        except Exception as e:
            logger.error(f"Server discovery error: {e}")
    
    def _client_discovery_loop(self):
        """Client broadcasting presence"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            
            hostname = NetworkUtils.get_hostname()
            local_ip = NetworkUtils.get_local_ip()
            
            logger.info(f"Client broadcasting presence: {hostname} at {local_ip}")
            logger.info(f"Broadcasting to 255.255.255.255:{DISCOVERY_PORT} every {DISCOVERY_INTERVAL}s")
            
            broadcast_count = 0
            while self.running:
                try:
                    packet = {
                        'type': 'mesh_client',
                        'hostname': hostname,
                        'ip': local_ip
                    }
                    data = json.dumps(packet).encode('utf-8')
                    self.socket.sendto(data, (BROADCAST_ADDRESS, DISCOVERY_PORT))
                    broadcast_count += 1
                    logger.debug(f"Broadcast #{broadcast_count} sent to {BROADCAST_ADDRESS}:{DISCOVERY_PORT}")
                    time.sleep(DISCOVERY_INTERVAL)
                except Exception as e:
                    logger.warning(f"Error broadcasting: {e}")
                    time.sleep(DISCOVERY_INTERVAL)
        
        except Exception as e:
            logger.error(f"Client discovery error: {e}")
    
    def _cleanup_stale_clients(self):
        """Remove clients that haven't been seen recently"""
        now = datetime.now()
        stale = []
        for client_id, info in self.discovered_clients.items():
            if (now - info['last_seen']).total_seconds() > CLIENT_HEARTBEAT_TIMEOUT:
                stale.append(client_id)
        
        for client_id in stale:
            del self.discovered_clients[client_id]
            logger.debug(f"Removed stale client: {client_id}")
    
    def get_discovered_clients(self):
        """Get list of discovered clients"""
        self._cleanup_stale_clients()
        return list(self.discovered_clients.keys())

# ============================================================================
# CONTROL NETWORKING
# ============================================================================

class ControlNetwork:
    """UDP control channel for input forwarding"""
    
    def __init__(self, client_ip, role='server'):
        self.client_ip = client_ip
        self.role = role
        self.socket = None
        self.running = False
        self.listen_thread = None
        self.callbacks = {}  # Event type -> callback
        self.server_ip = None  # For client mode - IP of the server
    
    def start(self):
        """Start control network"""
        self.running = True
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        if self.role == 'client':
            # Client listens for control packets from server
            try:
                self.socket.bind(('', CONTROL_PORT))
                self.socket.settimeout(1.0)
                self.listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
                self.listen_thread.start()
                logger.info(f"Client listening on port {CONTROL_PORT} for incoming control packets")
            except OSError as e:
                logger.error(f"Failed to bind client to port {CONTROL_PORT}: {e}")
        else:
            # Server only sends to clients, doesn't need to bind
            # It will send return_control packets via a separate mechanism
            logger.info(f"Server control network ready to send packets to {self.client_ip}")
    
    def stop(self):
        """Stop control network"""
        self.running = False
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
    
    def send_control_packet(self, packet):
        """Send control packet to client"""
        if not self.socket or self.role != 'server':
            return
        
        try:
            data = json.dumps(packet).encode('utf-8')
            self.socket.sendto(data, (self.client_ip, CONTROL_PORT))
        except Exception as e:
            logger.warning(f"Error sending control packet: {e}")
    
    def send_mouse_move(self, dx, dy):
        """Send mouse move packet"""
        self.send_control_packet(['m', dx, dy])
    
    def send_mouse_click(self, button='left'):
        """Send mouse click packet"""
        self.send_control_packet(['c', button])
    
    def send_key_event(self, key, down):
        """Send keyboard event"""
        # Serialize the key
        try:
            if hasattr(key, 'char'):
                key_str = key.char or str(key)
            else:
                key_str = str(key)
        except:
            key_str = str(key)
        
        self.send_control_packet(['k', key_str, down])
    
    def send_return_control(self):
        """Send return control packet"""
        if not self.socket or self.role != 'client':
            return
        
        try:
            # Send to the server IP if known, otherwise send to host that sent control
            if self.server_ip:
                data = json.dumps({'type': 'return_control'}).encode('utf-8')
                self.socket.sendto(data, (self.server_ip, CONTROL_PORT + 1000))
            else:
                # Broadcast as fallback
                data = json.dumps({'type': 'return_control'}).encode('utf-8')
                self.socket.sendto(data, (BROADCAST_ADDRESS, CONTROL_PORT + 1000))
        except Exception as e:
            logger.debug(f"Error sending return control: {e}")
    
    def register_callback(self, event_type, callback):
        """Register callback for event"""
        self.callbacks[event_type] = callback
    
    def _listen_loop(self):
        """Listen for incoming control packets"""
        while self.running:
            try:
                data, addr = self.socket.recvfrom(1024)
                # Track server IP on client side
                if self.role == 'client' and not self.server_ip:
                    self.server_ip = addr[0]
                
                packet = json.loads(data.decode('utf-8'))
                self._handle_packet(packet)
            except socket.timeout:
                pass
            except Exception as e:
                logger.warning(f"Error in listen loop: {e}")
    
    def _handle_packet(self, packet):
        """Handle incoming control packet"""
        try:
            if isinstance(packet, list):
                if packet[0] == 'm':  # Mouse move
                    dx, dy = packet[1], packet[2]
                    WindowsInput.move_mouse(int(dx), int(dy))
                elif packet[0] == 'c':  # Mouse click
                    button = packet[1] if len(packet) > 1 else 'left'
                    # Simulate click with down and up
                    WindowsInput.mouse_click(button, True)
                    time.sleep(0.05)
                    WindowsInput.mouse_click(button, False)
                elif packet[0] == 'k':  # Keyboard
                    if len(packet) >= 3:
                        key = packet[1]
                        down = packet[2]
                        try:
                            # Try to convert key to integer (VK code)
                            vk = int(key) if isinstance(key, int) else ord(key[0].upper()) if key else None
                            if vk:
                                if down:
                                    ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
                                else:
                                    ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
                        except:
                            pass
            elif isinstance(packet, dict):
                if packet.get('type') == 'return_control':
                    callback = self.callbacks.get('return_control')
                    if callback:
                        callback()
        except Exception as e:
            logger.warning(f"Error handling packet: {e}")

# ============================================================================
# INPUT CAPTURE SYSTEM
# ============================================================================

class InputCapture:
    """Captures mouse and keyboard input"""
    
    def __init__(self):
        self.listeners = []
        self.running = False
        self.callbacks = {}
        self.last_mouse_pos = WindowsInput.get_cursor_position()
    
    def start(self):
        """Start capturing input"""
        self.running = True
        
        # Mouse listener
        mouse_listener = mouse.Listener(
            on_move=self._on_mouse_move,
            on_click=self._on_mouse_click,
            on_scroll=self._on_scroll
        )
        mouse_listener.start()
        self.listeners.append(mouse_listener)
        
        # Keyboard listener
        keyboard_listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release
        )
        keyboard_listener.start()
        self.listeners.append(keyboard_listener)
        
        logger.info("Input capture started")
    
    def stop(self):
        """Stop capturing input"""
        self.running = False
        for listener in self.listeners:
            try:
                listener.stop()
            except:
                pass
        self.listeners.clear()
    
    def on_mouse_move(self, callback):
        """Register mouse move callback"""
        self.callbacks['mouse_move'] = callback
    
    def on_mouse_click(self, callback):
        """Register mouse click callback"""
        self.callbacks['mouse_click'] = callback
    
    def on_key_press(self, callback):
        """Register key press callback"""
        self.callbacks['key_press'] = callback
    
    def on_key_release(self, callback):
        """Register key release callback"""
        self.callbacks['key_release'] = callback
    
    def _on_mouse_move(self, x, y):
        """Internal mouse move handler"""
        if not self.running:
            return
        
        dx = x - self.last_mouse_pos[0]
        dy = y - self.last_mouse_pos[1]
        self.last_mouse_pos = (x, y)
        
        callback = self.callbacks.get('mouse_move')
        if callback:
            callback(x, y, dx, dy)
    
    def _on_mouse_click(self, x, y, button, pressed):
        """Internal mouse click handler"""
        if not self.running:
            return
        
        callback = self.callbacks.get('mouse_click')
        if callback:
            button_name = str(button).split('.')[-1]
            callback(x, y, button_name, pressed)
    
    def _on_scroll(self, x, y, dx, dy):
        """Internal scroll handler"""
        pass
    
    def _on_key_press(self, key):
        """Internal key press handler"""
        if not self.running:
            return
        
        callback = self.callbacks.get('key_press')
        if callback:
            callback(key)
    
    def _on_key_release(self, key):
        """Internal key release handler"""
        if not self.running:
            return
        
        callback = self.callbacks.get('key_release')
        if callback:
            callback(key)

# ============================================================================
# SERVER LOGIC
# ============================================================================

class ServerController:
    """Server-side control logic"""
    
    def __init__(self, gui):
        self.gui = gui
        self.discovery = DiscoveryManager(mode='server')
        self.input_capture = InputCapture()
        self.control_networks = {}  # client_id -> ControlNetwork
        self.connected_clients = []  # List of connected client IDs
        self.current_control = 'server'  # 'server', 'client_0', 'client_1'
        self.last_mouse_pos = WindowsInput.get_cursor_position()
        self.screen_width = 1920  # Will be updated
        self.screen_height = 1080  # Will be updated
        self.running = False
        self.return_control_socket = None
        self.return_control_thread = None
    
    def start(self):
        """Start server"""
        self.running = True
        
        # Get screen dimensions
        try:
            self.screen_width = self.gui.root.winfo_screenwidth()
            self.screen_height = self.gui.root.winfo_screenheight()
        except Exception as e:
            logger.warning(f"Could not get screen dimensions: {e}")
            self.screen_width = 1920
            self.screen_height = 1080
        
        self.discovery.start()
        self.input_capture.start()
        
        # Set up input callbacks
        self.input_capture.on_mouse_move(self._on_mouse_move)
        self.input_capture.on_mouse_click(self._on_mouse_click)
        self.input_capture.on_key_press(self._on_key_press)
        self.input_capture.on_key_release(self._on_key_release)
        
        # Start return control listener
        self._start_return_control_listener()
        
        # Schedule GUI updates from main thread
        if self.gui and hasattr(self.gui, 'root'):
            try:
                self.gui.root.after(1000, self._update_gui)
            except Exception as e:
                logger.warning(f"Could not schedule GUI update: {e}")
        
        logger.info(f"Server started with screen size: {self.screen_width}x{self.screen_height}")
    
    def stop(self):
        """Stop server"""
        self.running = False
        self.discovery.stop()
        self.input_capture.stop()
        
        # Stop return control listener
        if self.return_control_socket:
            try:
                self.return_control_socket.close()
            except:
                pass
        
        for ctrl in self.control_networks.values():
            ctrl.stop()
        self.control_networks.clear()
        logger.info("Server stopped")
    
    def connect_client(self, client_id):
        """Connect to a specific client"""
        if len(self.connected_clients) >= 2:
            messagebox.warning("Warning", "Maximum 2 clients connected")
            return False
        
        clients = self.discovery.discovered_clients
        if client_id not in clients:
            messagebox.showerror("Error", "Client not found")
            return False
        
        client_ip = clients[client_id]['ip']
        control = ControlNetwork(client_ip, role='server')
        control.register_callback('return_control', self._handle_return_control)
        control.start()
        
        self.control_networks[client_id] = control
        if client_id not in self.connected_clients:
            self.connected_clients.append(client_id)
        
        logger.info(f"Connected to client: {client_id}")
        return True
    
    def connect_client_by_ip(self, ip, client_id):
        """Connect to a client by manual IP address"""
        if len(self.connected_clients) >= 2:
            messagebox.warning("Warning", "Maximum 2 clients connected")
            return False
        
        try:
            control = ControlNetwork(ip, role='server')
            control.register_callback('return_control', self._handle_return_control)
            control.start()
            
            self.control_networks[client_id] = control
            if client_id not in self.connected_clients:
                self.connected_clients.append(client_id)
            
            logger.info(f"Connected to client by IP: {ip}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to {ip}: {e}")
            return False
    
    def disconnect_client(self, client_id):
        """Disconnect from a client"""
        if client_id in self.control_networks:
            self.control_networks[client_id].stop()
            del self.control_networks[client_id]
        
        if client_id in self.connected_clients:
            self.connected_clients.remove(client_id)
        
        logger.info(f"Disconnected from client: {client_id}")
    
    def _handle_return_control(self):
        """Handle return control from client"""
        # Switch back to the previous control
        if self.current_control != 'server':
            if self.current_control == 'client_1':
                self.current_control = 'client_0'
            elif self.current_control == 'client_0':
                self.current_control = 'server'
            
            self.gui.update_control_indicator(self.current_control)
            logger.info(f"Control switched to {self.current_control}")
    
    def _start_return_control_listener(self):
        """Start listening for return control packets from clients"""
        try:
            self.return_control_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.return_control_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.return_control_socket.bind(('', CONTROL_PORT + 1000))  # Use high port number
            self.return_control_socket.settimeout(1.0)
            
            self.return_control_thread = threading.Thread(
                target=self._return_control_listen_loop,
                daemon=True
            )
            self.return_control_thread.start()
            logger.info(f"Server return control listener started on port {CONTROL_PORT + 1000}")
        except OSError as e:
            logger.warning(f"Could not start return control listener: {e}")
    
    def _return_control_listen_loop(self):
        """Listen for return control packets from clients"""
        while self.running:
            try:
                data, addr = self.return_control_socket.recvfrom(1024)
                packet = json.loads(data.decode('utf-8'))
                
                if isinstance(packet, dict) and packet.get('type') == 'return_control':
                    self._handle_return_control()
                    logger.debug(f"Received return control from {addr[0]}")
            except socket.timeout:
                pass
            except Exception as e:
                if self.running:
                    logger.debug(f"Error in return control listen loop: {e}")
    
    def _on_mouse_move(self, x, y, dx, dy):
        """Handle mouse movement"""
        if not self.running or self.current_control == 'server':
            self.last_mouse_pos = (x, y)
            return
        
        # Check for edge switching
        if self._check_cursor_edge():
            return
        
        # Forward to current client
        if self.current_control.startswith('client_'):
            client_idx = int(self.current_control.split('_')[1])
            if client_idx < len(self.connected_clients):
                client_id = self.connected_clients[client_idx]
                if client_id in self.control_networks:
                    self.control_networks[client_id].send_mouse_move(dx, dy)
        
        self.last_mouse_pos = (x, y)
    
    def _on_mouse_click(self, x, y, button, pressed):
        """Handle mouse click"""
        if not self.running or self.current_control == 'server':
            return
        
        if pressed:
            # Only forward if we have connection
            if self.current_control.startswith('client_'):
                client_idx = int(self.current_control.split('_')[1])
                if client_idx < len(self.connected_clients):
                    client_id = self.connected_clients[client_idx]
                    if client_id in self.control_networks:
                        self.control_networks[client_id].send_mouse_click(button)
    
    def _on_key_press(self, key):
        """Handle key press"""
        if not self.running or self.current_control == 'server':
            return
        
        if self.current_control.startswith('client_'):
            client_idx = int(self.current_control.split('_')[1])
            if client_idx < len(self.connected_clients):
                client_id = self.connected_clients[client_idx]
                if client_id in self.control_networks:
                    self.control_networks[client_id].send_key_event(key, True)
    
    def _on_key_release(self, key):
        """Handle key release"""
        if not self.running or self.current_control == 'server':
            return
        
        if self.current_control.startswith('client_'):
            client_idx = int(self.current_control.split('_')[1])
            if client_idx < len(self.connected_clients):
                client_id = self.connected_clients[client_idx]
                if client_id in self.control_networks:
                    self.control_networks[client_id].send_key_event(key, False)
    
    def _check_cursor_edge(self):
        """Check if cursor is at edge and switch control"""
        x, y = self.last_mouse_pos
        
        if x >= self.screen_width - CURSOR_EDGE_THRESHOLD:
            # Moving right - switch to next client
            if self.current_control == 'server':
                if len(self.connected_clients) > 0:
                    self.current_control = 'client_0'
                    self.gui.update_control_indicator(self.current_control)
                    return True
            elif self.current_control == 'client_0':
                if len(self.connected_clients) > 1:
                    self.current_control = 'client_1'
                    self.gui.update_control_indicator(self.current_control)
                    return True
            elif self.current_control == 'client_1':
                self.current_control = 'server'
                self.gui.update_control_indicator(self.current_control)
                return True
        
        return False
    
    def _update_discovered_clients(self):
        """Update discovered clients in GUI"""
        clients = self.discovery.get_discovered_clients()
        self.gui.update_discovered_clients(clients)
    
    def _update_gui(self):
        """Update GUI periodically - must be called from main thread"""
        if self.running:
            try:
                self._update_discovered_clients()
                # Schedule next update from main thread
                self.gui.root.after(1000, self._update_gui)
            except Exception as e:
                logger.warning(f"Error updating GUI: {e}")

# ============================================================================
# CLIENT LOGIC
# ============================================================================

class ClientController:
    """Client-side control logic"""
    
    def __init__(self, gui):
        self.gui = gui
        self.discovery = DiscoveryManager(mode='client')
        self.control_network = None
        self.running = False
        self.cursor_monitor_thread = None
    
    def start(self):
        """Start client"""
        self.running = True
        self.discovery.start()
        
        # Set up control network
        self.control_network = ControlNetwork(
            client_ip='255.255.255.255',
            role='client'
        )
        self.control_network.register_callback('return_control', self._on_return_control)
        self.control_network.start()
        
        # Start cursor monitoring
        self.cursor_monitor_thread = threading.Thread(
            target=self._monitor_cursor,
            daemon=True
        )
        self.cursor_monitor_thread.start()
        
        logger.info("Client started")
    
    def stop(self):
        """Stop client"""
        self.running = False
        self.discovery.stop()
        if self.control_network:
            self.control_network.stop()
    
    def _monitor_cursor(self):
        """Monitor cursor position for edge detection"""
        last_send_time = time.time()
        
        while self.running:
            try:
                x, y = WindowsInput.get_cursor_position()
                
                # Check if cursor reached left edge
                if x <= CURSOR_EDGE_THRESHOLD:
                    # Send return control with throttling
                    if time.time() - last_send_time > 0.5:
                        if self.control_network:
                            self.control_network.send_return_control()
                        last_send_time = time.time()
                
                time.sleep(0.05)
            except Exception as e:
                logger.warning(f"Error in cursor monitor: {e}")
    
    def _on_return_control(self):
        """Handle control return from server"""
        logger.info("Control returned to server")

# ============================================================================
# TKINTER GUI
# ============================================================================

class MeshControlGUI:
    """Tkinter GUI for Mesh Control"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("Mesh Control")
        self.root.geometry("600x700")
        self.root.resizable(False, False)
        
        self.server = None
        self.client = None
        self.running_mode = None
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Set up UI components"""
        # Create a scrollable frame for everything
        main_canvas = tk.Canvas(self.root)
        scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=main_canvas.yview)
        scrollable_frame = ttk.Frame(main_canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: main_canvas.configure(scrollregion=main_canvas.bbox("all"))
        )
        
        main_canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        main_canvas.configure(yscrollcommand=scrollbar.set)
        
        main_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Title
        title_frame = ttk.Frame(scrollable_frame)
        title_frame.pack(fill=tk.X, padx=10, pady=10)
        
        title_label = ttk.Label(title_frame, text="Mesh Control", 
                               font=("Arial", 16, "bold"))
        title_label.pack()
        
        # Mode Selection
        mode_frame = ttk.LabelFrame(scrollable_frame, text="Mode Selection", padding=10)
        mode_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.mode_var = tk.StringVar(value="server")
        ttk.Radiobutton(mode_frame, text="Server", variable=self.mode_var, 
                       value="server").pack(anchor=tk.W)
        ttk.Radiobutton(mode_frame, text="Client", variable=self.mode_var, 
                       value="client").pack(anchor=tk.W)
        
        # Status Area
        status_frame = ttk.LabelFrame(scrollable_frame, text="Status", padding=10)
        status_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.status_label = ttk.Label(status_frame, text="Stopped", 
                                     font=("Arial", 10))
        self.status_label.pack(anchor=tk.W)
        
        # Connection Status
        conn_frame = ttk.LabelFrame(scrollable_frame, text="Connection Status", padding=10)
        conn_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.conn_status_label = ttk.Label(conn_frame, text="Not connected")
        self.conn_status_label.pack(anchor=tk.W)
        
        # Network Info (Diagnostic)
        self.network_info_label = ttk.Label(conn_frame, text="", font=("Arial", 8), foreground="gray")
        self.network_info_label.pack(anchor=tk.W)
        
        # Manual IP Connection
        manual_ip_frame = ttk.LabelFrame(scrollable_frame, text="Manual Client IP Connection", padding=10)
        manual_ip_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ip_input_frame = ttk.Frame(manual_ip_frame)
        ip_input_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(ip_input_frame, text="Client IP:").pack(side=tk.LEFT, padx=5)
        self.manual_ip_var = tk.StringVar()
        self.manual_ip_entry = ttk.Entry(ip_input_frame, textvariable=self.manual_ip_var, width=20)
        self.manual_ip_entry.pack(side=tk.LEFT, padx=5)
        
        self.connect_ip_btn = ttk.Button(manual_ip_frame, text="Connect by IP",
                                        command=self._on_connect_by_ip,
                                        state=tk.DISABLED)
        self.connect_ip_btn.pack(py=5)
        
        self.manual_ip_status_label = ttk.Label(manual_ip_frame, text="", 
                                               font=("Arial", 8), foreground="blue")
        self.manual_ip_status_label.pack(anchor=tk.W)
        
        # Discovered Clients
        clients_frame = ttk.LabelFrame(scrollable_frame, text="Discovered Clients", padding=10)
        clients_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Listbox with scrollbar
        scrollbar = ttk.Scrollbar(clients_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.clients_listbox = tk.Listbox(clients_frame, yscrollcommand=scrollbar.set, height=6)
        self.clients_listbox.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.clients_listbox.yview)
        
        self.discovery_timeout_label = ttk.Label(clients_frame, text="", 
                                                 font=("Arial", 8), foreground="orange")
        self.discovery_timeout_label.pack(anchor=tk.W)
        
        # Client Network Settings
        client_settings_frame = ttk.LabelFrame(scrollable_frame, text="Client Network Settings", padding=10)
        client_settings_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.client_ip_label = ttk.Label(client_settings_frame, text="IP Address: Not set")
        self.client_ip_label.pack(anchor=tk.W)
        
        self.client_adapter_label = ttk.Label(client_settings_frame, text="Network Adapter: Unknown")
        self.client_adapter_label.pack(anchor=tk.W)
        
        self.discovery_mode_label = ttk.Label(client_settings_frame, text="Discovery Mode: Disabled")
        self.discovery_mode_label.pack(anchor=tk.W)
        
        self.enable_discovery_btn = ttk.Button(client_settings_frame, text="Enable Discovery Mode",
                                              command=self._on_enable_discovery,
                                              state=tk.DISABLED)
        self.enable_discovery_btn.pack(py=5)
        
        # Server Diagnostics
        server_diag_frame = ttk.LabelFrame(scrollable_frame, text="Server Network Diagnostics", padding=10)
        server_diag_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.server_ip_label = ttk.Label(server_diag_frame, text="Server IP: Not set")
        self.server_ip_label.pack(anchor=tk.W)
        
        self.server_subnet_label = ttk.Label(server_diag_frame, text="Subnet Mask: Unknown")
        self.server_subnet_label.pack(anchor=tk.W)
        
        diag_button_frame = ttk.Frame(server_diag_frame)
        diag_button_frame.pack(fill=tk.X, pady=10)
        
        self.scan_network_btn = ttk.Button(diag_button_frame, text="Scan Network",
                                          command=self._on_scan_network,
                                          state=tk.DISABLED)
        self.scan_network_btn.pack(side=tk.LEFT, padx=5)
        
        self.ping_client_btn = ttk.Button(diag_button_frame, text="Ping Selected",
                                         command=self._on_ping_selected,
                                         state=tk.DISABLED)
        self.ping_client_btn.pack(side=tk.LEFT, padx=5)
        
        self.show_network_info_btn = ttk.Button(diag_button_frame, text="Network Info",
                                               command=self._on_show_network_info)
        self.show_network_info_btn.pack(side=tk.LEFT, padx=5)
        
        self.diag_status_label = ttk.Label(server_diag_frame, text="", 
                                          font=("Arial", 8), foreground="green")
        self.diag_status_label.pack(anchor=tk.W)
        
        # Control Indicator
        control_frame = ttk.LabelFrame(scrollable_frame, text="Current Control", padding=10)
        control_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.control_label = ttk.Label(control_frame, text="Server", 
                                      font=("Arial", 11, "bold"),
                                      foreground="green")
        self.control_label.pack()
        
        # Buttons
        button_frame = ttk.Frame(scrollable_frame)
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.start_btn = ttk.Button(button_frame, text="Start",
                                   command=self._on_start)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = ttk.Button(button_frame, text="Stop", command=self._on_stop,
                                  state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        self.connect_btn = ttk.Button(button_frame, text="Connect Selected",
                                     command=self._on_connect_client,
                                     state=tk.DISABLED)
        self.connect_btn.pack(side=tk.LEFT, padx=5)
        
        self.diag_btn = ttk.Button(button_frame, text="Network Diagnostics",
                                  command=self._on_diagnostics)
        self.diag_btn.pack(side=tk.LEFT, padx=5)
    
    def _on_start(self):
        """Start based on mode selection"""
        mode = self.mode_var.get()
        if mode == 'server':
            self._on_start_server()
        else:
            self._on_start_client()
    
    def _on_start_server(self):
        """Start server"""
        self.server = ServerController(self)
        self.server.start()
        self.running_mode = 'server'
        
        # Show network info
        server_ip = NetworkUtils.get_local_ip()
        self.network_info_label.config(
            text=f"Server IP: {server_ip} | Discovery Port: {DISCOVERY_PORT} | Listening for clients..."
        )
        self.server_ip_label.config(text=f"Server IP: {server_ip}")
        
        self.status_label.config(text="Server running...")
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.connect_btn.config(state=tk.NORMAL)
        self.scan_network_btn.config(state=tk.NORMAL)
        self.ping_client_btn.config(state=tk.NORMAL)
        self.connect_ip_btn.config(state=tk.NORMAL)
        
        # Disable mode selection
        for child in self.root.winfo_children():
            if isinstance(child, ttk.Frame):
                for subchild in child.winfo_children():
                    if isinstance(subchild, ttk.Radiobutton):
                        subchild.config(state=tk.DISABLED)
        
        # Start 5-second discovery timeout
        self.discovery_timeout_label.config(text="Scanning for clients (5 sec)...", foreground="blue")
        self.root.after(5000, self._check_discovery_timeout)
        
        logger.info("Server mode activated")
    
    def _on_start_client(self):
        """Start client"""
        self.client = ClientController(self)
        self.client.start()
        self.running_mode = 'client'
        
        # Show network info
        client_ip = NetworkUtils.get_local_ip()
        hostname = NetworkUtils.get_hostname()
        self.network_info_label.config(
            text=f"Client IP: {client_ip} | Hostname: {hostname} | Broadcasting..."
        )
        self.client_ip_label.config(text=f"IP Address: {client_ip}")
        self.discovery_mode_label.config(text=f"Discovery Mode: Enabled", foreground="green")
        self.enable_discovery_btn.config(state=tk.NORMAL)
        
        self.status_label.config(text="Client running...")
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        
        # Disable mode selection
        for child in self.root.winfo_children():
            if isinstance(child, ttk.Frame):
                for subchild in child.winfo_children():
                    if isinstance(subchild, ttk.Radiobutton):
                        subchild.config(state=tk.DISABLED)
        
        logger.info("Client mode activated")
    
    def _on_stop(self):
        """Stop server/client"""
        if self.server:
            self.server.stop()
            self.server = None
        
        if self.client:
            self.client.stop()
            self.client = None
        
        self.running_mode = None
        self.status_label.config(text="Stopped")
        self.network_info_label.config(text="")
        self.conn_status_label.config(text="Not connected")
        self.manual_ip_status_label.config(text="")
        self.discovery_timeout_label.config(text="")
        self.diag_status_label.config(text="")
        self.client_ip_label.config(text="IP Address: Not set")
        self.discovery_mode_label.config(text="Discovery Mode: Disabled")
        self.server_ip_label.config(text="Server IP: Not set")
        self.server_subnet_label.config(text="Subnet Mask: Unknown")
        
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.connect_btn.config(state=tk.DISABLED)
        self.scan_network_btn.config(state=tk.DISABLED)
        self.ping_client_btn.config(state=tk.DISABLED)
        self.connect_ip_btn.config(state=tk.DISABLED)
        self.enable_discovery_btn.config(state=tk.DISABLED)
        
        # Re-enable mode selection
        for child in self.root.winfo_children():
            if isinstance(child, ttk.Frame):
                for subchild in child.winfo_children():
                    if isinstance(subchild, ttk.Radiobutton):
                        subchild.config(state=tk.NORMAL)
        
        self.clients_listbox.delete(0, tk.END)
        
        logger.info("Stopped")
    
    def _on_connect_client(self):
        """Connect to selected client"""
        if not self.server:
            messagebox.showerror("Error", "Server not running")
            return
        
        selection = self.clients_listbox.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a client")
            return
        
        client_id = self.clients_listbox.get(selection[0])
        if self.server.connect_client(client_id):
            self.conn_status_label.config(
                text=f"Connected to: {client_id}"
            )
            messagebox.showinfo("Success", f"Connected to {client_id}")
    
    def update_discovered_clients(self, clients):
        """Update the list of discovered clients"""
        current_selection = self.clients_listbox.curselection()
        current_items = set(self.clients_listbox.get(0, tk.END))
        new_items = set(clients)
        
        # Only update if there are changes
        if current_items != new_items:
            self.clients_listbox.delete(0, tk.END)
            for client in sorted(clients):
                self.clients_listbox.insert(tk.END, client)
    
    def update_control_indicator(self, control):
        """Update control indicator"""
        control_text = {
            'server': 'Server',
            'client_0': 'Client 1',
            'client_1': 'Client 2'
        }.get(control, control)
        
        self.control_label.config(text=control_text)
    
    def _on_diagnostics(self):
        """Show network diagnostics dialog"""
        import subprocess
        
        diag_info = "=== Mesh Control Network Diagnostics ===\n\n"
        
        # Get local IP
        local_ip = NetworkUtils.get_local_ip()
        hostname = NetworkUtils.get_hostname()
        diag_info += f"Your Computer:\n"
        diag_info += f"  Hostname: {hostname}\n"
        diag_info += f"  IP Address: {local_ip}\n\n"
        
        # Try to get full network info
        try:
            result = subprocess.run(
                ['ipconfig'],
                capture_output=True,
                text=True,
                timeout=5
            )
            diag_info += "Full Network Configuration:\n"
            # Filter to show only relevant info
            lines = result.stdout.split('\n')
            for i, line in enumerate(lines):
                if any(x in line for x in ['Adapter', 'IPv4', 'Subnet Mask', 'Default Gateway', 'DHCP']):
                    diag_info += line + "\n"
        except Exception as e:
            diag_info += f"Could not retrieve full config: {e}\n"
        
        diag_info += f"\n=== Mesh Control Config ===\n"
        diag_info += f"Discovery Port: {DISCOVERY_PORT}\n"
        diag_info += f"Control Port: {CONTROL_PORT}\n"
        diag_info += f"Return Control Port: {CONTROL_PORT + 1000}\n"
        diag_info += f"Broadcast Address: {BROADCAST_ADDRESS}\n"
        
        # Show in messagebox
        messagebox.showinfo("Network Diagnostics", diag_info)
    
    def _on_connect_by_ip(self):
        """Connect to a client using manual IP address"""
        ip = self.manual_ip_var.get().strip()
        
        if not ip:
            messagebox.showwarning("Warning", "Please enter a client IP address")
            return
        
        # Validate IP format
        parts = ip.split('.')
        if len(parts) != 4 or not all(part.isdigit() for part in parts):
            messagebox.showerror("Error", "Invalid IP address format")
            return
        
        if not self.server:
            messagebox.showerror("Error", "Server not running")
            return
        
        try:
            # Create a fake client entry for manual connection
            client_id = f"Manual-{ip}"
            if self.server.connect_client_by_ip(ip, client_id):
                self.manual_ip_status_label.config(
                    text=f"✓ Connected to {ip}",
                    foreground="green"
                )
                messagebox.showinfo("Success", f"Connected to {ip}")
            else:
                self.manual_ip_status_label.config(
                    text=f"✗ Failed to connect to {ip}",
                    foreground="red"
                )
                messagebox.showerror("Error", f"Failed to connect to {ip}")
        except Exception as e:
            messagebox.showerror("Error", f"Connection error: {e}")
            logger.error(f"Manual IP connection error: {e}")
    
    def _on_enable_discovery(self):
        """Enable/toggle client discovery broadcasting"""
        if not self.client:
            messagebox.showerror("Error", "Client not running")
            return
        
        # For now, discovery is automatically enabled
        # This button could be used to restart discovery or show status
        messagebox.showinfo("Discovery Mode", "Client is broadcasting its presence every 2 seconds")
    
    def _on_scan_network(self):
        """Rescan the network for clients"""
        if not self.server:
            messagebox.showwarning("Warning", "Server not running")
            return
        
        self.diag_status_label.config(text="Scanning network...", foreground="blue")
        self.server.discovery.discovered_clients.clear()
        self.clients_listbox.delete(0, tk.END)
        
        # The discovery manager will find clients automatically
        # Give it 3 seconds to discover
        self.root.after(3000, self._scan_complete)
    
    def _scan_complete(self):
        """Called when scan completes"""
        clients = self.server.discovery.get_discovered_clients()
        if clients:
            self.diag_status_label.config(text=f"✓ Found {len(clients)} client(s)", foreground="green")
        else:
            self.diag_status_label.config(text="✗ No clients found", foreground="orange")
    
    def _on_ping_selected(self):
        """Ping the selected client in the listbox"""
        selection = self.clients_listbox.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a client first")
            return
        
        client_id = self.clients_listbox.get(selection[0])
        clients = self.server.discovery.discovered_clients
        
        if client_id not in clients:
            messagebox.showerror("Error", "Client not found")
            return
        
        client_ip = clients[client_id]['ip']
        self.diag_status_label.config(text=f"Pinging {client_ip}...", foreground="blue")
        self.root.update()
        
        try:
            result = subprocess.run(
                ['ping', '-n', '1', client_ip],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                self.diag_status_label.config(
                    text=f"✓ {client_id} is reachable",
                    foreground="green"
                )
                messagebox.showinfo("Ping Result", f"✓ {client_ip} is reachable")
            else:
                self.diag_status_label.config(
                    text=f"✗ {client_id} is unreachable",
                    foreground="red"
                )
                messagebox.showwarning("Ping Result", f"✗ {client_ip} is unreachable (100% packet loss)")
        except Exception as e:
            messagebox.showerror("Error", f"Ping failed: {e}")
            logger.error(f"Ping error: {e}")
    
    def _on_show_network_info(self):
        """Show detailed network information"""
        try:
            result = subprocess.run(
                ['ipconfig', '/all'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            info = "Network Configuration (extract):\n\n"
            lines = result.stdout.split('\n')
            
            in_adapter = False
            for line in lines:
                if 'adapter' in line.lower():
                    in_adapter = True
                    info += f"\n{line}\n"
                elif in_adapter and any(x in line for x in ['IPv4', 'Subnet Mask', 'Default Gateway', 'DHCP']):
                    info += line + "\n"
                elif in_adapter and line.strip() == "":
                    in_adapter = False
            
            messagebox.showinfo("Network Information", info)
        except Exception as e:
            messagebox.showerror("Error", f"Could not retrieve network info: {e}")

# ============================================================================
# MAIN APPLICATION
# ============================================================================

def main():
    """Main application entry point"""
    root = tk.Tk()
    app = MeshControlGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
