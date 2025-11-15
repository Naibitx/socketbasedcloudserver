import socket
import os
import time

# Try to import analytics; if it fails, define no-op functions
try:
    from analytics import record_transfer, record_event
except Exception:
    def record_transfer(*args, **kwargs):
        pass

    def record_event(*args, **kwargs):
        pass

IP = "127.0.0.1"  # Use 127.0.0.1 when client and server are on the same machine
PORT = 4450
ADDR = (IP, PORT)
SIZE = 64 * 1024
FORMAT = "utf-8"


def connection_to_server():
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect(ADDR)
    print(f"Connected to server at {IP}:{PORT}")
    return client_socket


def authenticate(client_socket):
    """
    Handles the AUTH handshake with the server.
    """
    while True:
        msg = client_socket.recv(SIZE).decode(FORMAT)
        if not msg:
            print("Server closed connection during authentication.")
            return False

        parts = msg.strip().split("@")
        tag = parts[0]

        if tag == "AUTH":
            if len(parts) < 2:
                print("Malformed AUTH message from server.")
                return False
            step = parts[1]

            if step == "USERNAME":
                username = input("Username: ")
                client_socket.send(username.encode(FORMAT))

            elif step == "PASSWORD":
                password = input("Password: ")
                client_socket.send(password.encode(FORMAT))

            elif step == "OK":
                print("Login successful.")
                # Receive welcome line sent right after login
                welcome = client_socket.recv(SIZE).decode(FORMAT)
                if welcome:
                    print("Server:", welcome)
                return True

            elif step == "FAIL":
                print("Invalid username or password.")
                return False

        elif tag == "ERR":
            print("Authentication error from server:", "@".join(parts[1:]))
            return False

        else:
            # Any other message before login is unexpected
            print("Unexpected message during authentication:", msg)
            return False


def upload_file(client_socket, filename):
    if not os.path.exists(filename):
        print("File not found.")
        return

    filesize = os.path.getsize(filename)
    cmd = f"UPLOAD@{os.path.basename(filename)}@{filesize}"
    client_socket.send(cmd.encode(FORMAT))

    response = client_socket.recv(SIZE).decode(FORMAT)
    status, msg = response.split("@", 1)

    if status == "ERR":
        if "Overwrite" in msg:
            choice = input("Server says file exists. Overwrite? (y/n): ").strip().lower()
            client_socket.send(choice.encode(FORMAT))
            response = client_socket.recv(SIZE).decode(FORMAT)
            status, msg = response.split("@", 1)
            if status == "OK" and "cancelled" in msg:
                print("Upload cancelled by user choice.")
                return
        else:
            print("Server error:", msg)
            return

    if status == "OK" and msg == "READY":
        start = time.perf_counter()
        with open(filename, "rb") as f:
            while True:
                data = f.read(SIZE)
                if not data:
                    break
                client_socket.sendall(data)
        end = time.perf_counter()
        record_transfer(
            "client", "UPLOAD", os.path.basename(filename),
            filesize, start, end, status="OK"
        )
        final_msg = client_socket.recv(SIZE).decode(FORMAT)
        print("Server:", final_msg)
    else:
        print("Unexpected response from server:", response)


def download_file(client_socket, filename):
    client_socket.send(f"DOWNLOAD@{filename}".encode(FORMAT))
    response = client_socket.recv(SIZE).decode(FORMAT)

    status, msg = response.split("@", 1)
    if status == "ERR":
        print("Server error:", msg)
        return

    filesize = int(msg)
    client_socket.send("READY".encode(FORMAT))

    os.makedirs("downloads", exist_ok=True)
    filepath = os.path.join("downloads", filename)

    start = time.perf_counter()
    remaining = filesize
    with open(filepath, "wb") as f:
        while remaining > 0:
            chunk = client_socket.recv(min(SIZE, remaining))
            if not chunk:
                break
            f.write(chunk)
            remaining -= len(chunk)
    end = time.perf_counter()

    record_transfer("client", "DOWNLOAD", filename, filesize, start, end, status="OK")
    print(f"Downloaded '{filename}' to downloads/")


def menu_client(client_socket):
    while True:
        print("\n----- Menu -----")
        print(" upload <filename>")
        print(" download <filename>")
        print(" delete <filename>")
        print(" dir")
        print(" subfolder <create|delete> <foldername>")
        print(" exit")

        command = input("\nEnter command: ").strip()
        if not command:
            continue

        if command.lower() == "exit":
            client_socket.send("LOGOUT".encode(FORMAT))
            print("Exiting...")
            break

        parts = command.split()

        if parts[0] == "upload" and len(parts) == 2:
            upload_file(client_socket, parts[1])
            continue

        if parts[0] == "download" and len(parts) == 2:
            download_file(client_socket, parts[1])
            continue

        # Simple commands handled directly
        if parts[0] == "dir" and len(parts) == 1:
            client_socket.send("DIR".encode(FORMAT))
        elif parts[0] == "delete" and len(parts) == 2:
            client_socket.send(f"DELETE@{parts[1]}".encode(FORMAT))
        elif parts[0] == "subfolder" and len(parts) == 3:
            client_socket.send(f"SUBFOLDER@{parts[1]}@{parts[2]}".encode(FORMAT))
        else:
            print("Invalid command syntax.")
            continue

        # Receive generic response for these commands
        data = client_socket.recv(SIZE).decode(FORMAT)
        print("Server:", data)


if __name__ == "__main__":
    sock = connection_to_server()
    if authenticate(sock):
        menu_client(sock)
    sock.close()
    print("Connection closed.")