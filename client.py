import socket
import os
import time
import getpass


try:
    from analytics import record_transfer, record_event
except Exception:
    def record_transfer(*args, **kwargs):
        pass

    def record_event(*args, **kwargs):
        pass

IP = "localhost" 
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
                password = getpass.getpass("Password: ")
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


def upload_file(client_socket, filename):  # file uploading function
    if not os.path.exists(filename):
        print("File cant be found OH OH")
        return

    filesize = os.path.getsize(filename)
    base_name = os.path.basename(filename)

    client_socket.send(f"UPLOAD@{base_name}@{filesize}\n".encode(FORMAT))

    #first response: either error, overwrite prompt, or READY
    response = client_socket.recv(SIZE).decode(FORMAT)
    status, msg = response.split("@", 1)

    #handle "file exists, overwrite?"
    if status == "ERR" and "Overwrite" in msg:
        choice = input("Server says file exists. Overwrite? (y/n): ").strip().lower()
        client_socket.send(choice.encode(FORMAT))
        response = client_socket.recv(SIZE).decode(FORMAT)
        status, msg = response.split("@", 1)
        if status == "OK" and "cancelled" in msg:
            print("Upload cancelled.")
            return
        elif status == "ERR":
            print("Server error:", msg)
            return

    #if server is ready, stream the file
    if status == "OK":
        start = time.perf_counter()
        with open(filename, "rb") as f:
            while True:
                data = f.read(SIZE)
                if not data:
                    break
                client_socket.sendall(data)
        end = time.perf_counter()

        # Log analytics
        record_transfer("client", "UPLOAD", base_name, filesize, start, end)

        # Final confirmation from server
        final_msg = client_socket.recv(SIZE).decode(FORMAT)
        print("Server:", final_msg)
    else:
        print("Server error:", msg)


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

        data = client_socket.recv(SIZE).decode(FORMAT)
        print("Server:", data)


if __name__ == "__main__":
    sock = connection_to_server()
    if authenticate(sock):
        menu_client(sock)
    sock.close()
    print("Connection closed.")