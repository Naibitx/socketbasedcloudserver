import socket
import os

IP = "localhost"
PORT= 4450
ADDR = (IP, PORT)
SIZE = 1024
FORMAT = "utf-8"

def connection_to_server():
    client_socket= socket,socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect(ADDR)
    print(f"Connected to server in {IP}: {PORT}")
    return client_socket
