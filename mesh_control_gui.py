import socket
import json
import ctypes
from pynput import mouse, keyboard

PORT = 6060

user32 = ctypes.windll.user32

# ---------------- Windows Input ----------------

def move_mouse(dx, dy):
    user32.mouse_event(0x0001, dx, dy, 0, 0)

def mouse_click():
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    user32.mouse_event(0x0004, 0, 0, 0, 0)

def key_event(key, down=True):
    vk = user32.VkKeyScanA(ord(key)) & 0xff
    if down:
        user32.keybd_event(vk, 0, 0, 0)
    else:
        user32.keybd_event(vk, 0, 2, 0)

# ---------------- CLIENT ----------------

def run_client():

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", PORT))

    print("Client listening...")

    while True:

        data, addr = sock.recvfrom(1024)
        msg = json.loads(data.decode())

        t = msg[0]

        if t == "m":
            dx, dy = msg[1], msg[2]
            move_mouse(dx, dy)

        elif t == "c":
            mouse_click()

        elif t == "k":
            key_event(msg[1], msg[2])

# ---------------- SERVER ----------------

def run_server():

    client_ip = input("Enter client IP: ")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    screen_w = user32.GetSystemMetrics(0)

    control = False
    last_x = 0
    last_y = 0

    def send(msg):
        sock.sendto(json.dumps(msg).encode(), (client_ip, PORT))

    def on_move(x, y):

        nonlocal control, last_x, last_y

        dx = x - last_x
        dy = y - last_y

        last_x = x
        last_y = y

        if not control:

            if x >= screen_w - 1:
                control = True
                user32.ShowCursor(False)
                print("Control switched to client")

        else:
            send(["m", dx, dy])

    def on_click(x, y, button, pressed):

        if control and pressed:
            send(["c"])

    def on_press(key):

        if control:
            try:
                send(["k", key.char, True])
            except:
                pass

    def on_release(key):

        if control:
            try:
                send(["k", key.char, False])
            except:
                pass

    mouse.Listener(on_move=on_move, on_click=on_click).start()

    keyboard.Listener(
        on_press=on_press,
        on_release=on_release
    ).start()

    print("Server running...")

    while True:
        pass

# ---------------- MAIN ----------------

print("Mesh Control")

print("1. Server")
print("2. Client")

mode = input("> ")

if mode == "1":
    run_server()

elif mode == "2":
    run_client()