# Mesh Control - Multi-Computer Control Application

A Python-based Windows application that allows one computer (server) to control up to two other computers (clients) using a single keyboard and mouse over a local network.

## Features

- **Automatic Client Discovery**: Clients broadcast their presence automatically via UDP
- **Smooth Cursor Switching**: Seamless control transition between computers at screen edges
- **Low-Latency UDP Networking**: Uses UDP for responsive input forwarding
- **Windows Native Input API**: Direct input injection via ctypes (not PyAutoGUI)
- **Tkinter GUI**: Simple, intuitive graphical interface
- **Support for Up to 2 Clients**: Connect and control up to 2 remote computers simultaneously
- **Physical PCs and VMs**: Works with both physical computers and Windows virtual machines

## Requirements

- **Python**: 3.11 or higher
- **OS**: Windows 10 or Windows 11
- **Network**: Local network connection between computers
- **No Manual IP Configuration**: Uses automatic discovery

## Installation

1. **Clone or Download the Project**
   ```powershell
   cd h:\Projects\unimouse
   ```

2. **Install Dependencies**
   ```powershell
   pip install -r requirements.txt
   ```
   
   Or manually install:
   ```powershell
   pip install pynput>=1.7.6
   ```

## Usage

### Starting the Application

From the project directory:
```powershell
python mesh_control_gui.py
```

### Server Setup

1. Open Mesh Control on the server computer
2. Select the **"Server"** radio button
3. Click **"Start"** button
4. Wait for clients to appear in the "Discovered Clients" list
5. Select up to 2 clients from the list
6. Click **"Connect Selected"** for each client

### Client Setup

1. Open Mesh Control on each client computer
2. Select the **"Client"** radio button
3. Click **"Start"** button
4. The client will automatically broadcast its presence to the server

### Using Mesh Control

Once connected:

1. **Server Screen**: Use keyboard and mouse normally on the server
2. **Move to Client 1**: Move your mouse to the right edge of the server screen
3. **Move to Client 2**: If connected, move the mouse to the right edge of Client 1's screen
4. **Return to Server**: Move the mouse to the left edge of the client screen

The system works like a wireless multi-screen setup:
- **Server → Client 1 → Client 2 → Server** (cycle)
- All keyboard and mouse input follows the cursor

## Network Configuration

### Default Ports

- **Discovery Port**: 15050 (UDP broadcast)
- **Control Port**: 16060 (UDP input forwarding to clients)
- **Return Control Port**: 17060 (UDP return signal from clients)

### Broadcast Packets

The client sends discovery packets every 2 seconds:
```json
{
  "type": "mesh_client",
  "hostname": "<computer_name>",
  "ip": "<local_ip_address>"
}
```

### Control Packets

From server to client:
- **Mouse Move**: `["m", dx, dy]`
- **Mouse Click**: `["c", button]`
- **Keyboard**: `["k", key, state]` (state: true=down, false=up)

From client to server:
- **Return Control**: `{"type": "return_control"}`

## Performance

- **Smooth Movement**: Uses relative mouse movement for natural cursor transitions
- **Low Latency**: UDP-based communication for responsive input
- **Background Threads**: Network and input capture run asynchronously

## Logging

The application creates a log file `mesh_control.log` in the working directory. This can be useful for troubleshooting issues.

## Troubleshooting

### Clients Not Discovered
- Ensure all computers are on the same local network
- Check Windows Firewall - allow UDP traffic on ports 5050, 6060, 6061
- Verify IP addresses are in the same subnet

### Input Not Working on Client
- Ensure the client is ready (status shows "Client running")
- Check that mouse is within the control area
- Try moving mouse to edge and back to trigger proper control transfer

### Cursor Not Visible
- This is normal - cursor visibility is managed by the system
- Move mouse back toward the left edge to return control to server

### Connection Lost
- Reconnect the client from the server GUI
- Restart the affected application

## Advanced Features

### Cursor Edge Detection
- **Threshold**: 5 pixels from screen edge
- **Left Edge**: Trigger return control (client to server)
- **Right Edge**: Trigger forward (server to next client)

### Multi-Client Cycling
With 2 clients connected:
1. Server (right edge) → Client 1 (left edge returns to server)
2. Server (right edge) → Client 1 (right edge) → Client 2
3. Client 2 (left edge) → Client 1 (left edge) → Server

## Architecture

The application is organized into several components:

- **GUI (Tkinter)**: User interface and status display
- **Windows Input Injection**: ctypes-based input sending
- **Network Discovery**: UDP broadcast for client detection
- **Server Logic**: Main control and forwarding logic
- **Client Logic**: Input reception and cursor monitoring
- **Input Capture**: pynput-based keyboard/mouse listening
- **Cursor Edge Detection**: Automatic screen boundary detection

## Security Notes

- This application is designed for a trusted local network
- All communication is unencrypted (local network only)
- No authentication is implemented (assumed trusted network)
- For use on untrusted networks, consider VPN or network isolation

## Known Limitations

- **Maximum 2 Clients**: Design limitation for simplicity
- **Local Network Only**: Requires direct network connectivity
- **Windows Only**: Currently Windows 10/11 specific
- **No Network Encryption**: Designed for trusted LANs

## Troubleshooting Connection Issues

1. **Firewall**: Add exceptions for ports 5050, 6060, 6061 (UDP)
2. **Network**: Ensure computers can ping each other
3. **Restart**: Close and restart both server and clients
4. **Logs**: Check mesh_control.log for error messages

## Version Information

- **Version**: 1.0
- **Python**: 3.11+
- **Dependencies**: pynput 1.7.6+
- **Platform**: Windows 10/11

## License

This project is provided as-is for local network use.

## Support

Check the log file for detailed error messages and troubleshooting information.

---

**Enjoy seamless multi-computer control with Mesh Control!**
