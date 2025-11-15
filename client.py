import socket
import os
import time
from analytics import record_transfer, record_event
from cryptography.fernet import Fernet

IP = "10.200.102.97"
PORT = 4450
ADDR = (IP, PORT)
SIZE = 64 * 1024
FORMAT = "utf-8"

cipher = None
_leftover = {}

def recv_line(sock):
    fil = sock.fileno()
    if fil not in _leftover:
        _leftover[fil] = b""
    buffer = _leftover[fil]
    while b"\n" not in buffer:
        chunk = sock.recv(1024)
        if not chunk:
            break
        buffer += chunk
    if b"\n" in buffer:
        line, rest = buffer.split(b"\n", 1)
        _leftover[fil] = rest
        return line
    _leftover[fil] = b""
    return buffer

def connection_to_server():
    global cipher
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect(ADDR)
    key_msg = recv_line(client_socket)  # read only the AES key line
    cipher = Fernet(key_msg)
    print(f"Connected to server in {IP}:{PORT}")
    return client_socket

def authenticate(client_socket):
    while True:
        server_msg = recv_line(client_socket).decode(FORMAT)  # read the prompt
        if server_msg.startswith("AUTH@Username:"):
            username = input("Username: ")
            client_socket.send(username.encode(FORMAT))
        elif server_msg.startswith("AUTH@Password:"):
            password = input("Password: ")
            client_socket.send(password.encode(FORMAT))
        elif server_msg.startswith("OK@Login"):
            print("Login successful.")
            return True
        elif server_msg.startswith("ERR@"):
            print("Login failed. Try again.")
            return False

def upload_file(client_socket, filename):
    if not os.path.exists(filename):
        print("File cant be found OH OH")
        return
    ext = os.path.splitext(filename)[1].lower()
    file_sizes = {".txt": 25*1024*1024, ".mp3": 1*1024*1024*1024,
                  ".wav": 1*1024*1024*1024, ".mp4": 2*1024*1024*1024,
                  ".avi": 2*1024*1024*1024, ".mkv": 2*1024*1024*1024}
    filesize = os.path.getsize(filename)
    if ext not in file_sizes or filesize < file_sizes[ext]:
        print(f"File type or size not allowed. Minimum {file_sizes.get(ext,0)} bytes.")
        return

    client_socket.send(f"UPLOAD@{filename}@{filesize}".encode(FORMAT))
    response = recv_line(client_socket).decode(FORMAT)
    status, msg = response.split("@", 1)

    if status == "ERR" and "Overwrite" in msg:
        choice = input("Server says file exists. Overwrite? (y/n): ")
        client_socket.send(choice.encode(FORMAT))
        response = recv_line(client_socket).decode(FORMAT)
        status, msg = response.split("@", 1)
        if status == "OK" and "cancelled" in msg:
            print(msg)
            return

    if status == "OK":
        start = time.perf_counter()
        with open(filename, "rb") as f:
            while True:
                data = f.read(SIZE)
                if not data:
                    break
                client_socket.sendall(data)
        end = time.perf_counter()
        record_transfer("client", "UPLOAD", filename, filesize, start, end)
        print("File uploaded successfully.")

def download_file(client_socket, filename):
    client_socket.send(f"DOWNLOAD@{filename}".encode(FORMAT))
    response = recv_line(client_socket).decode(FORMAT)
    status, msg = response.split("@", 1)
    if status == "ERR":
        print("we did not find the file on the server pal")
        return

    filesize = int(msg)
    client_socket.send("READY".encode(FORMAT))
    if not os.path.exists("downloads"):
        os.mkdir("downloads")
    filepath = f"downloads/{filename}"
    start = time.perf_counter()
    with open(filepath, "wb") as f:
        remaining = filesize
        while remaining > 0:
            chunk = client_socket.recv(min(SIZE, remaining))
            if not chunk:
                break
            f.write(chunk)
            remaining -= len(chunk)
    end = time.perf_counter()
    record_transfer("client", "DOWNLOAD", filename, filesize, start, end)
    print(f"File '{filename}' was downloaded to /downloads/")

def menu_client(client_socket):
    while True:
        print("\n-----Menu-----")
        print(" upload <filename>\n")
        print(" download <filename>\n")
        print(" delete <filename>\n")
        print(" dir\n")
        print(" subfolder <create|delete> <folder>\n")
        print(" exit")
        command = input("\n Enter command: ").strip()
        if command.lower() == "exit":
            client_socket.send("LOGOUT@".encode(FORMAT))
            break
        elif command.startswith("upload"):
            parts = command.split()
            if len(parts) == 2:
                upload_file(client_socket, parts[1])
            else:
                print("Usage: upload <filename>")
        elif command.startswith("download"):
            parts = command.split()
            if len(parts) == 2:
                download_file(client_socket, parts[1])
            else:
                print("Usage: download <filename>")
        else:
            parts = command.split()
            cmd_start = time.perf_counter()
            if len(parts) == 1 and parts[0] == "dir":
                client_socket.send("DIR".encode(FORMAT))
            elif parts[0] == "delete" and len(parts) >= 2:
                client_socket.send(f"DELETE@{parts[1]}".encode(FORMAT))
            elif parts[0] == "subfolder" and len(parts) >= 3:
                client_socket.send(f"SUBFOLDER@{parts[1]}@{parts[2]}".encode(FORMAT))
            else:
                print("Invalid command.")
                continue
            data = recv_line(client_socket).decode(FORMAT)
            cmd_end = time.perf_counter()
            print("Server:", data)
            record_event("client", parts[0], cmd_start, cmd_end)

if __name__ == "__main__":
    client_socket = connection_to_server()
    if authenticate(client_socket):
        menu_client(client_socket)
    client_socket.close()
    print("\nConnection closed")