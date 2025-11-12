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

def upload_file(client_socket, filename): #file uploading function
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

def download_file(client_socket, filename):
    client_socket.sendall(f"download {filename}".encode(FORMAT))
    response = client_socket.recv(SIZE).decode(FORMAT)

    if response == "NOT_FOUND":
        print("we did not find the file on the server pal")
        return
    elif response == "READY":
        if not os.path.exists("downloads"):#we are making sure the downloads folder exists
            os.mkdir("downloads")
        
        with open(f"downloads/ {filename}", "wb") as f:
            data = client_socket.revc(4096)
            f.write(data)
        print(f"File '{filename}' was downloaded to /downloads/")
    else:
        print(f"Server reponse: {response}")

