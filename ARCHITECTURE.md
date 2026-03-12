# Mesh Control - Architecture Guide

## Overview

Mesh Control is a multi-computer control application that uses UDP networking to enable seamless keyboard and mouse control across multiple Windows computers. The architecture is designed for low-latency operation over local networks.

## System Components

### 1. GUI Layer (Tkinter)
**File Location**: `mesh_control_gui.py` - `MeshControlGUI` class

Responsibilities:
- Provide user interface for mode selection
- Display discovered clients
- Show connection status
- Display current control indicator
- Handle user interactions

Key UI Elements:
- Mode selection (Server/Client)
- Start/Stop buttons
- Client discovery list
- Connection status indicators
- Control indicator (Server/Client 1/Client 2)

### 2. Network Discovery System
**Components**:
- `DiscoveryManager` class
- UDP broadcast on port 5050
- Client broadcast interval: 2 seconds

**Server Discovery Flow**:
1. Server listens on port 5050 for broadcasts
2. Clients broadcast presence every 2 seconds
3. Server maintains client list with heartbeat timeout (10 seconds)
4. Stale clients auto-removed

**Client Discovery Flow**:
1. Client sends UDP broadcast to 255.255.255.255:5050
2. Packet contains: hostname, IP, discovery type

### 3. Control Networking
**Components**:
- `ControlNetwork` class
- Bidirectional UDP communication
- Control port: 6060 (client listen), 6061 (server listen)

**Packet Types**:

**Mouse Control**:
- `["m", dx, dy]` - Mouse relative movement

**Mouse Click**:
- `["c", button]` - Click (left/right/middle)

**Keyboard**:
- `["k", key, down]` - Key press/release

**Return Control**:
- `{"type": "return_control"}` - Signal to return control to server

### 4. Input Capture System
**Components**:
- `InputCapture` class using pynput
- Separate threads for mouse and keyboard
- Non-blocking event listeners

**Captured Events**:
- Mouse movement (with delta tracking)
- Mouse clicks (button identification)
- Keyboard press/release

### 5. Windows Input Injection
**Components**:
- `WindowsInput` class
- ctypes-based Windows API calls
- Direct SendInput usage

**Supported Operations**:
- `move_mouse(dx, dy)` - Relative movement
- `mouse_click(button, down)` - Click events
- `key_down(key)` / `key_up(key)` - Keyboard events

**Virtual Key Code Mapping**:
- Special keys (Enter, Space, etc.) have predefined VK codes
- Regular characters mapped to ASCII values

### 6. Server Logic
**Components**:
- `ServerController` class
- Main control flow orchestration
- Client management

**Key Responsibilities**:
- Listen for client broadcasts via DiscoveryManager
- Manage up to 2 connected clients
- Capture local input and forward to clients
- Detect cursor edge transitions
- Manage control indicator state
- Periodically update GUI with discovered clients

**Control States**:
- `'server'` - Local server control
- `'client_0'` - First connected client
- `'client_1'` - Second connected client

**Cursor Edge Switching Logic**:
```
Screen Layout:
╔─────────────────────┐
│     Server Screen   │
└─────────────────────┘┌─────────────────────┐
                       │    Client 1 Screen  │
                       └─────────────────────┘┌─────────────────────┐
                                              │    Client 2 Screen  │
                                              └─────────────────────┘
```

Behavior:
- Cursor x >= (width - threshold) → Switch right
- Cursor x <= threshold → Switch left

### 7. Client Logic
**Components**:
- `ClientController` class
- Cursor edge monitoring
- Control packet reception

**Key Responsibilities**:
- Broadcast presence via DiscoveryManager
- Listen for control packets from server
- Inject received input locally
- Monitor cursor position
- Detect left edge for return_control

**Cursor Monitoring**:
- Runs in background thread
- Checks cursor position every 50ms
- Sends return_control when x <= threshold
- Throttles return_control (1 per 500ms max)

## Data Flow

### Server to Client Control

```
User Input (Server)
        ↓
InputCapture (pynput)
        ↓
ServerController._on_mouse_move/click etc.
        ↓
Check Control State
        ↓
ControlNetwork.send_mouse_move/click/key
        ↓
UDP Send to Client IP:6060
        ↓
Client ControlNetwork._listen_loop
        ↓
WindowsInput.move_mouse/mouse_click/keybd_event
        ↓
Local Input Injection (Client)
```

### Client to Server Return Control

```
Client Cursor Reaches Left Edge
        ↓
ClientController._monitor_cursor (detects x <= threshold)
        ↓
ControlNetwork.send_return_control
        ↓
UDP Send to Server IP:6061
        ↓
Server ControlNetwork._listen_loop
        ↓
ServerController._handle_return_control
        ↓
Control State Changed
        ↓
GUI Update: update_control_indicator
```

## Threading Model

The application uses multiple background threads:

1. **Discovery Thread** (DiscoveryManager)
   - Server: Listens for client broadcasts
   - Client: Broadcasts presence periodically

2. **Input Capture Threads** (pynput)
   - Mouse listener thread
   - Keyboard listener thread

3. **Control Network Listen Thread** (ControlNetwork)
   - Listens for incoming control packets
   - Processes and injects local input

4. **Cursor Monitor Thread** (Client only)
   - Monitors cursor position
   - Detects edge transitions

5. **GUI Update Thread**
   - Periodic GUI refresh for client list

## Key Design Decisions

### UDP vs TCP
**Chosen**: UDP
**Reason**: Lower latency, connectionless, suitable for high-frequency input events

### Tkinter vs PyQt/QT/wxPython
**Chosen**: Tkinter
**Reason**: Built-in with Python, minimal dependencies, suitable for simple GUI

### pynput vs PyAutoGUI
**Chosen**: pynput for input capture, ctypes for input injection
**Reason**: 
- pynput: Better cross-platform event capture
- ctypes: Lower-level API control, more reliable input injection

### Manual Key Serialization vs VK Code
**Chosen**: Key string with fallback to VK code
**Reason**: More flexible, handles both special keys and characters

## Port Usage

| Port | Direction | Purpose |
|------|-----------|---------|
| 5050 | UDP Broadcast | Client discovery |
| 6060 | UDP Listen (Client) | Control packet reception |
| 6061 | UDP Listen (Server) | Return control signals |

## Error Handling

### Network Errors
- Timeouts handled with socket.timeout
- Malformed packets logged and skipped
- Stale clients auto-removed

### Input Injection Errors
- Invalid keys logged but don't crash
- Missing VK codes gracefully degraded
- Mouse movement errors are non-fatal

### Threading Errors
- Daemon threads clean up on exit
- Listener threads have try-except blocks
- Socket cleanup in stop() methods

## Performance Considerations

1. **Mouse Movement Latency**
   - Delta-based movement reduces packet size
   - UDP provides low overhead
   - Typical RTT: <1ms on local network

2. **CPU Usage**
   - Idle: Minimal (listening only)
   - Active use: <5% per control channel
   - pynput listeners: ~1-2% background

3. **Network Bandwidth**
   - Mouse move: ~20 bytes per packet
   - Keyboard: ~30 bytes per packet
   - Typical rate: 50-100 packets/sec during active use
   - Total: <50KB/s typical, <200KB/s peak

4. **Memory Usage**
   - Base: ~20-30MB (Python + UI)
   - Per client: ~1-2MB (listeners + buffers)
   - Total: ~25-35MB typical

## Extension Points

### Adding More Clients
- Change `MAX_CLIENTS` constant (currently 2)
- Update control state machine in `ServerController`
- GUI would need additional buttons/indicators

### Custom Input Filtering
- Subclass `InputCapture`
- Override callback handlers
- Implement filtering logic

### Enhanced Packet Format
- Use MessagePack or Protocol Buffers instead of JSON
- Reduce packet size and parsing overhead
- Maintain backward compatibility

### Network Security
- Add HMAC-based authentication to packets
- Encrypt packets with AES
- Implement IP whitelisting

### Graphical Improvements
- Multi-threaded GUI updates
- Real-time connection quality indicator
- Visual feedback for cursor transitions
- System tray integration

## Testing Recommendations

1. **Unit Tests**
   - WindowsInput virtual key mapping
   - Packet serialization/deserialization
   - State machine transitions

2. **Integration Tests**
   - Server-client discovery
   - Control packet forwarding
   - Cursor edge detection

3. **Load Tests**
   - High-frequency input (1000+ packets/sec)
   - Multiple rapid edge switches
   - Long-duration operation (8+ hours)

4. **Environment Tests**
   - VM network conditions
   - Wireless network latency
   - Multiple concurrent connections

## Deployment Notes

1. **Firewall Configuration**
   - Open UDP ports 5050, 6060, 6061
   - Allow Python executable in firewall exceptions

2. **Network Requirements**
   - Computers must be on same subnet or routes must exist
   - Broadcast must not be blocked by router

3. **Antivirus Compatibility**
   - ctypes input injection may trigger alerts
   - Add to trusted apps as needed
   - pynput listeners may require permissions

4. **Virtual Machine Considerations**
   - Ensure VM network is bridged (not NAT)
   - Test with various amounts of VM resources
   - Check for input injection limitations in VM

---

This architecture provides a clean separation of concerns, good extensibility, and reasonable performance for local network use cases.
