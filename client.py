import socket
import os

IP = "10.200.102.97"
PORT= 4450
ADDR = (IP, PORT)
SIZE = 64 * 1024
FORMAT = "utf-8"

def connection_to_server(): #connecitng to server function
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect(ADDR)
    print(f"Connected to server in {IP}: {PORT}")
    return client_socket

def authenticate(client_socket): #login function
    while True:
        server_msg = client_socket.recv(SIZE).decode(FORMAT)

        if server_msg.startswith("AUTH@Username"):
            username = input("Username: ")
            client_socket.send(username.encode(FORMAT))

        elif server_msg.startswith("AUTH@Password"):
            password = input("Password: ")
            client_socket.send(password.encode(FORMAT))

        elif server_msg.startswith("OK@Login"):
            print("Login successful.")
            return True

        elif server_msg.startswith("ERR@"):
            print("Login failed. Try again.")
            return False

def upload_file(client_socket, filename): #file uploading function
    if not os.path.exists(filename):
        print("File cant be found OH OH")
        return

    filesize = os.path.getsize(filename)
    client_socket.send(f"UPLOAD@{filename}@{filesize}".encode(FORMAT))

    response = client_socket.recv(SIZE).decode(FORMAT)
    status, msg = response.split("@", 1)

    if status == "ERR":
        print("Server response:", msg)
        return

    if status == "OK":
        with open(filename, "rb") as f:
            while True:
                data = f.read(SIZE)
                if not data:
                    break
                client_socket.sendall(data)
        print("File was successfully uplaoded")

def download_file(client_socket, filename): #file downloading function
    client_socket.send(f"DOWNLOAD@{filename}".encode(FORMAT))
    response = client_socket.recv(SIZE).decode(FORMAT)

    status, msg = response.split("@", 1)

    if status == "ERR":
        print("we did not find the file on the server pal")
        return

    filesize = int(msg)
    client_socket.send("READY".encode(FORMAT))

    if not os.path.exists("downloads"): #we are making sure the downloads folder exists
        os.mkdir("downloads")
        
    filepath = f"downloads/{filename}"
    with open(filepath, "wb") as f:
        remaining = filesize
        while remaining > 0:
            chunk = client_socket.recv(min(SIZE, remaining))
            if not chunk:
                break
            f.write(chunk)
            remaining -= len(chunk)

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

        command= input("\n Enter command: ").strip()

        if command.lower() == "exit": #this handles the exit command
            client_socket.send("LOGOUT@".encode(FORMAT))
            print("Exiting")
            break

        elif command.startswith("upload"): #handles upload comamnd
            parts= command.split()
            if len(parts) == 2:
                upload_file(client_socket, parts[1])
            else:
                print("Using: upload <filename>")
            continue

        elif command.startswith("download"): #handles donwload command
            parts= command.split()
            if len(parts) == 2:
                download_file(client_socket, parts[1])
            else:
                print("Using: download <filename>")
            continue

        parts = command.split()

        if len(parts) == 1:
            if command == "dir":
                client_socket.send("DIR".encode(FORMAT))

        else:
            if parts[0] == "delete":
                client_socket.send(f"DELETE@{parts[1]}".encode(FORMAT))
            elif parts[0] == "subfolder":
                client_socket.send(f"SUBFOLDER@{parts[1]}@{parts[2]}".encode(FORMAT))
            else:
                print("Invalid command.")
                continue

        data= client_socket.recv(4096).decode(FORMAT)
        print("Server:", data)

if __name__== "__main__":
    client_socket= connection_to_server()
    if authenticate(client_socket):
        menu_client(client_socket)
    client_socket.close()
    print("\nConnection closed")
