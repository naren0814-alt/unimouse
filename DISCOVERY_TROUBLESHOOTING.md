# Mesh Control - Client Discovery Troubleshooting

## Problem: Client Not Appearing in Server List

If you started both server and client but the client doesn't appear, the most common cause is **UDP broadcast being blocked or not working on your network**.

## Diagnostic Steps

### 1. **Check the Network Info Display**
   - Server should show: `Server IP: [your-ip] | Discovery Port: 15050 | Listening for clients...`
   - Client should show: `Client IP: [your-ip] | Hostname: [computer-name] | Broadcasting...`
   - **If either doesn't show, there's a startup issue**

### 2. **Check the Log File**
   Look in `mesh_control.log` for these messages:

   **Server should show:**
   ```
   INFO - Server discovery listening on port 15050
   INFO - Server IP: [your-ip]
   ```

   **Client should show:**
   ```
   INFO - Client broadcasting presence: [hostname] at [your-ip]
   INFO - Broadcasting to 255.255.255.255:15050 every 2.0s
   ```

   **If you see these, the issue is network-based, not application-based.**

### 3. **Confirm You're On the Same Network**
   ```powershell
   # On both computers:
   ipconfig /all
   
   # Look for the "IPv4 Address" under your network adapter
   # Should be similar: 192.168.x.x, 10.x.x.x, or 172.16-31.x.x
   ```

### 4. **Test Reachability**
   ```powershell
   # On server, ping the client IP:
   ping [client-ip]
   
   # On client, ping the server IP:
   ping [server-ip]
   ```
   If ping fails, you're not on the same network or there's a firewall rule blocking it.

### 5. **Check Windows Firewall**
   Even with "Private" selected, you need to explicitly allow the app:
   
   **Option A: Allow Python through Firewall**
   1. Open Windows Defender Firewall
   2. Click "Allow an app through firewall"
   3. Find "Python" → Check "Private Networks"
   4. Click OK
   5. Restart Mesh Control

   **Option B: Allow Discovery Port Explicitly**
   1. Open Windows Defender Firewall
   2. Click "Advanced settings"
   3. Click "Inbound Rules" → "New Rule"
   4. Port → UDP → Port 15050 → Allow → Private
   5. Name it "Mesh Control Discovery"
   6. Click Finish

### 6. **Test Broadcast Support**
   ```powershell
   # From PowerShell, run this diagnostic:
   python -c "
   import socket
   s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
   s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
   try:
       s.sendto(b'TEST', ('255.255.255.255', 15050))
       print('✓ Broadcast send successful')
   except Exception as e:
       print(f'✗ Broadcast failed: {e}')
   s.close()
   "
   ```

## Solutions by Network Type

### **Private Home Network (Recommended)**
If you have a home router and both devices are on Wi-Fi or ethernet:

1. Both computers should see each other with ping
2. Python should be allowed through firewall (private)
3. Restart Mesh Control
4. **Wait 5-10 seconds** for discovery

### **Corporate/Office Network**
Corporate networks often block broadcast traffic:

1. Try using **Ethernet** instead of Wi-Fi
2. Check if your IT allows broadcast (likely no)
3. **Use static IP entry** as a workaround (see below)

### **Isolated Virtual Network**
Some VM networks don't support broadcast:

1. Check VM network settings (should be "Bridged")
2. Ensure VM network adapter is in Bridged mode, not NAT
3. May need to reconfigure VM networking

## Workaround: Manual IP Entry

If broadcast doesn't work, you can manually enter the client's IP on the server:

**Coming in next version** - A dialog to enter IP addresses manually.

For now, you can hardcode in your copy:

1. Open `mesh_control_gui.py`
2. Find line with `DISCOVERY_PORT = 15050`
3. Add the client IP manually:
   ```python
   MANUAL_CLIENTS = [
       {"hostname": "LAPTOP-CLIENT", "ip": "192.168.1.100"}
   ]
   ```

## Network Diagram

```
Expected Setup:
┌─────────────────────────────────────┐
│         Router / Switch             │
│                                     │
├──────────────────┬──────────────────┤
│                  │                  │
Server (192.168.1.50)  Client (192.168.1.100)
│                  │                  │
├──────────────────┴──────────────────┤
│                                     │
│ Both can ping each other ✓          │
│ Broadcast allowed ✓                 │
│ Firewall allows Python ✓            │
└─────────────────────────────────────┘
```

## Common Reasons for Failure

| Issue | Symptoms | Solution |
|-------|----------|----------|
| Different Networks | Ping fails | Use same Wi-Fi/LAN |
| Broadcast Blocked | Ping works, but no client list | Allow UDP broadcast |
| Firewall Blocking | App shows started but nothing happens | Allow Python through firewall |
| Wrong Port Range | Timeouts in logs | Check firewall rules |
| Network Switch/Isolation | Devices isolated | Check router/switch settings |
| VPN Active | Broadcast doesn't cross VPN | Disable VPN or disable VPN for this app |

## Debug Checklist

Before asking for help, verify:

- [ ] Both computers on same subnet (check IP addresses)
- [ ] Can ping from one to the other
- [ ] Server shows "Listening" message
- [ ] Client shows "Broadcasting" message
- [ ] Log shows broadcast packets being sent (check mesh_control.log)
- [ ] Python is allowed through Windows Firewall (private)
- [ ] No VPN active on either computer
- [ ] Tried restarting both applications
- [ ] Waited at least 5 seconds after starting client

## If Still Not Working

1. **Share the log output** - Copy relevant lines from `mesh_control.log`
2. **Test network** - Run `ipconfig /all` on both machines
3. **Test ping** - Show ping results between computers
4. **Check firewall** - Verify Python is allowed
5. **Check router** - Verify it's not blocking broadcast (rare, but possible)

## Performance Tips

- Use **Ethernet** instead of Wi-Fi for better discovery reliability
- Ensure both devices have **stable internet connectivity**
- Restart WiFi if having intermittent failures
- Some networks require a few seconds longer for broadcast to propagate

## Next Steps

1. Check network info display in the GUI
2. Review mesh_control.log for errors
3. Verify firewall settings
4. Test ping between computers
5. Restart both applications
6. Wait 5-10 seconds

If discovery still fails, your network likely blocks UDP broadcast. This is common in enterprise and some public networks.

---

**Latest Update**: Added network diagnostics to GUI - server and client now display their IP addresses and port information for easier troubleshooting.
