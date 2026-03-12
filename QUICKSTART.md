# Mesh Control - Quick Start Guide

## 5-Minute Setup

### Prerequisites
- Python 3.11+ installed on all computers
- All computers on the same Wi-Fi or LAN
- User account with administrator privileges

### Installation (All Computers)

1. **Download/Clone the Project**
   ```powershell
   # Navigate to your projects folder
   cd h:\Projects\unimouse
   ```

2. **Install Dependencies** (One-time only)
   ```powershell
   pip install pynput
   ```

### Run the Application

From the project folder, open PowerShell and run:
```powershell
python mesh_control_gui.py
```

A window titled "Mesh Control" will appear.

---

## Quickest Setup

### On the SERVER Computer

1. Open `mesh_control_gui.py`
2. Select **"Server"** (default)
3. Click **"Start"** button
4. Wait 5 seconds...
5. Clients should appear in the list below
6. Click on a client and click **"Connect Selected"**
7. Repeat for second client (optional)

### On Each CLIENT Computer

1. Open `mesh_control_gui.py`
2. Select **"Client"**
3. Click **"Start"** button
4. Status should show "Client running..."
5. Done! Appears on server

### Using It

Move your mouse to the **right edge** of your server screen and it will seamlessly move to the first connected client's screen.

Move the mouse to the **right edge** of client 1 to access client 2 (if connected).

Move to the **left edge** of any client screen to return to the server.

---

## Troubleshooting (First Things to Try)

### "Clients not appearing on server"

1. Check both computers can ping each other:
   ```powershell
   ping 192.168.x.x
   ```

2. Check Windows Firewall:
   - Open Windows Firewall → Allow an app
   - Find Python → Check "Private Networks"

3. Restart Mesh Control on both computers

### "Input not working when moved to client"

1. Try moving the mouse back toward the center
2. Then toward the left edge
3. Then back to the center

This resets the control state.

### "Connection drops frequently"

1. Check network stability
2. Check for interference (if using Wi-Fi)
3. Try using a wired connection

---

## What Works out of the Box

✓ Mouse movement  
✓ Left, right, middle mouse clicks  
✓ Keyboard typing  
✓ Alt+Tab switching  
✓ Special keys (Enter, Backspace, etc.)  

## What Doesn't Work

✗ Scroll wheel (partial support)  
✗ Custom mouse buttons (only L/M/R)  
✗ Multiple monitors on host (uses primary)  
✗ Network login (local network only)  

---

## Common Tasks

### Change Server After Starting
1. Click **"Stop"** on old server
2. Click **"Stop"** on all clients
3. Select new server
4. Click **"Start"** on new server
5. Click **"Start"** on all clients

### Disconnect a Specific Client
While server is running:
1. Unplug client computer or
2. Click **"Stop"** on client computer
3. It will disappear from the list in ~10 seconds

### Stop Everything
1. Click **"Stop"** on server and clients
2. Close the window

---

## Settings to Know About

### Default Configuration

**Discovery Broadcast Interval**: 2 seconds  
**Client Timeout**: 10 seconds  
**Cursor Edge Threshold**: 5 pixels  
**Control Ports**: 6060, 6061  
**Discovery Port**: 5050  

To change these, edit the constants at the top of `mesh_control_gui.py`:

```python
DISCOVERY_INTERVAL = 2.0  # Change to 5.0 for slower updates
CLIENT_HEARTBEAT_TIMEOUT = 10.0  # Change to 20.0 for longer timeout
CURSOR_EDGE_THRESHOLD = 5  # Change to 10 for larger edge area
```

---

## FAQs

**Q: Can I use this over the internet?**  
A: Not recommended - no encryption or authentication. Use only on trusted LANs.

**Q: Will this work with my laptop?**  
A: Yes, as long as it's on the same network as other computers.

**Q: Can I control more than 2 clients?**  
A: Not without modifying code. Edit `CONTROL_PORT` and state machine logic in `ServerController`.

**Q: Does this work on Mac/Linux?**  
A: Not currently - Windows-only due to ctypes Windows API usage.

**Q: Is there a client application for phones/tablets?**  
A: No, Windows only.

---

## Log File

If you encounter issues, check `mesh_control.log` in the same folder:

```powershell
# View latest errors
Get-Content mesh_control.log -Tail 20
```

---

## Getting Help

1. Check the log file
2. Try restarting the application
3. Check network connectivity with ping
4. Verify Windows Firewall settings
5. Read the full README.md file

---

## What to Expect

When working correctly:

- Client list updates in ~2 seconds after startup
- Cursor transitions feel smooth and natural
- Input is nearly instantaneous (<10ms latency)
- No lag when controlling client computers
- Disconnecting/reconnecting is seamless

---

**Enjoy controlling multiple computers!**

---

## Common Error Messages

| Error | Solution |
|-------|----------|
| "Client not found" | Wait 5 seconds and try again |
| "Failed to send control packet" | Check firewall |
| "Socket already in use" | Restart application |
| "Permission denied" | Run as Administrator |

---

For more detailed information, see:
- `README.md` - Full documentation
- `ARCHITECTURE.md` - Technical details
- `mesh_control.log` - Detailed error logs
