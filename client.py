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

def download_file(client_socket, filename): #file downloading function
    client_socket.sendall(f"download {filename}".encode(FORMAT))
    response = client_socket.recv(SIZE).decode(FORMAT)

    if response == "NOT_FOUND":
        print("we did not find the file on the server pal")
        return
    elif response == "READY":
        if not os.path.exists("downloads"): #we are making sure the downloads folder exists
            os.mkdir("downloads")
        
        with open(f"downloads/ {filename}", "wb") as f:
            data = client_socket.revc(4096)
            f.write(data)
        print(f"File '{filename}' was downloaded to /downloads/")
    else:
        print(f"Server reponse: {response}")

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
            client_socket.sendall(command.encode(FORMAT))
            print("Exiting")
            break

        elif command.startswith("uplaod"): #handles upload comamnd
            parts= command.split()
            if len(parts) == 2:
                upload_file(client_socket, parts[1])
            else:
                print("Using: upload <filename>")
            continue
        elif command.startswith("downalod"): #handles donwload command
            parts= command.split()
            if len(parts) == 2:
                download_file(client_socket, parts[1])
            else:
                print("Using: download <filename>")
            continue
        client_socket.sendall(command.encode(FORMAT))
        data= client_socket.recv(4096).decode(FORMAT)
        print("Server:", data)

if __name__== "__main__":
    client_socket= connection_to_server()
    try:
        menu_client(client_socket)
    except KeyboardInterrupt:
        print("\n Connection was closed by user")
    finally:
        client_socket.close()
        print("\nConnection closed")
