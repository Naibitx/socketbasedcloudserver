import socket
import os

IP = "localhost"
PORT= 4450
ADDR = (IP, PORT)
SIZE = 1024
FORMAT = "utf-8"

def connection_to_server(): #connecitng to server function
    client_socket= socket,socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect(ADDR)
    print(f"Connected to server in {IP}: {PORT}")
    return client_socket

def upload_file(client_socket, filename):
    if not os.path.exists(filename):
        print("File cant be found OH OH")
        return
    client_socket.sendall(f"upload {filename}".encode(FORMAT))
    response = client_socket.recv(SIZE).decode(FORMAT)

    if response == "REAADY":
        with open(filename, "rb") as f:
            data = f.read()
            client_socket.sendall(data)
        print("File was successfully uplaoded")
    else:
        print(f"Server response: {response}")


