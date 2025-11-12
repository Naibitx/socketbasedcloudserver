#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Author : Ayesha S. Dina

import os
import socket
import threading
import hashlib
import logging


logging.basicConfig(
    filename='server.log', 
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

IP = "localhost" ### gethostname()
PORT = 4450
ADDR = (IP,PORT)
SIZE = 1024
FORMAT = "utf-8"
SERVER_PATH = "server"

def authenticate(conn):
        conn.send("AUTH@Username:".encode(FORMAT))
        username = conn.recv(SIZE).decode(FORMAT)
        conn.send("AUTH@Password:".encode(FORMAT))
        password = conn.recv(SIZE).decode(FORMAT)

        hashed_pw = hashlib.sha256(password.encode()).hexdigest()

        with open("users.txt", "r") as f:
                for line in f:
                    stored_user, stored_hash = line.strip().split(":")
                    if username == stored_user and hashed_pw == stored_hash:
                            conn.send("OK@Login successful.".encode(FORMAT))
                            print(f"[AUTH] Login successful for user: {username}")
                            return True
        conn.send("ERR@Invalid credentials.".encode(FORMAT))
        logging.warning(f"Failed login attempt for user: {username}")
        print(f"[AUTH] Failed login attempt for user: {username}")
        return False

### to handle the clients
def handle_client (conn,addr):

    if not authenticate(conn):
        logging.info(f"Authentication failed for {addr}.")
        conn.close()
        return

    logging.info(f"{addr} - Authentication successful.")


    print(f"[CONNECT] Client connected: {addr}")
    logging.info(f"Client connected: {addr}")
    conn.send("OK@Welcome to the server".encode(FORMAT))

    while True:
        data = conn.recv(SIZE).decode(FORMAT)
        data = data.split("@")
        cmd = data[0]
       
        send_data = "OK@"

        if cmd == "LOGOUT":
            break

        elif cmd == "TASK":
            print(f"[TASK] Command received from {addr}")
        logging.info(f"{addr} issued TASK command")
            send_data += "LOGOUT from the server.\n"
            conn.send(send_data.encode(FORMAT))

        elif cmd == "UPLOAD":
            try:
                filename = data[1]
                filesize = int(data[2])
                filepath = os.path.join(SERVER_PATH, filename)

                # Check if file exists
                if os.path.exists(filepath):
                    conn.send("ERR@File exists. Overwrite? (y/n)".encode(FORMAT))
                    choice = conn.recv(SIZE).decode(FORMAT)
                    if choice.lower() != "y":
                        conn.send("OK@Upload cancelled.".encode(FORMAT))
                        logging.info(f"{addr} cancelled upload of file: {filename}")
                        print(f"[UPLOAD] {addr} cancelled upload of {filename}")
                        continue

                conn.send("OK@Ready to receive.".encode(FORMAT))

                # Receive file in chunks
                with open(filepath, "wb") as f:
                    received = 0
                    while received < filesize:
                        bytes_read = conn.recv(SIZE)
                        if not bytes_read:
                            break
                        f.write(bytes_read)
                        received += len(bytes_read)

                conn.send(f"OK@Uploaded {filename}".encode(FORMAT))
                logging.info(f"{addr} uploaded file: {filename}")
                print(f"[UPLOAD] {addr} → {filename}")

            except Exception as e:
                logging.error(f"Upload failed for {addr}: {str(e)}")
                print(f"[UPLOAD ERROR] {addr} failed: {str(e)}")
                conn.send(f"ERR@Upload failed: {str(e)}".encode(FORMAT))

        elif cmd == "DOWNLOAD":
            try:
                filename = data[1]
                filepath = os.path.join(SERVER_PATH, filename)

                if not os.path.exists(filepath):
                    conn.send("ERR@File not found.".encode(FORMAT))
                    continue

                filesize = os.path.getsize(filepath)
                conn.send(f"OK@{filesize}".encode(FORMAT))

                # Wait for client ready
                ack = conn.recv(SIZE).decode(FORMAT)
                if ack != "READY":
                    continue

                with open(filepath, "rb") as f:
                    while True:
                        bytes_read = f.read(SIZE)
                        if not bytes_read:
                            break
                        conn.sendall(bytes_read)

                conn.send("OK@Download complete.".encode(FORMAT))
                logging.info(f"{addr} downloaded file: {filename}")
                print(f"[DOWNLOAD] {addr} ← {filename}")

            except Exception as e:
                conn.send(f"ERR@Download failed: {str(e)}".encode(FORMAT))
                logging.error(f"Download failed for {addr}: {str(e)}")
                print(f"[DOWNLOAD ERROR] {addr} failed: {str(e)}")

        elif cmd == "DELETE":
            try:
                filename = data[1]
                filepath = os.path.join(SERVER_PATH, filename)

                if not os.path.exists(filepath):
                    conn.send("ERR@File not found.".encode(FORMAT))
                    continue

                os.remove(filepath)
                conn.send(f"OK@Deleted {filename}".encode(FORMAT))
                logging.info(f"{addr} deleted file: {filename}")
                print(f"[DELETE] {addr} removed {filename}")

            except Exception as e:
                conn.send(f"ERR@Delete failed: {str(e)}".encode(FORMAT))
                logging.error(f"Delete failed for {addr}: {str(e)}")
                print(f"[DELETE ERROR] {addr} failed: {str(e)}")

        elif cmd == "DIR":
            try:
                items = os.listdir(SERVER_PATH)
                file_list = "\n".join(items) if items else "Directory is empty."
                conn.send(f"OK@{file_list}".encode(FORMAT))
                logging.info(f"{addr} requested directory listing")
                print(f"[DIR] {addr} requested directory listing")
            except Exception as e:
                conn.send(f"ERR@Directory read failed: {str(e)}".encode(FORMAT))
                logging.error(f"Directory listing failed for {addr}: {str(e)}")
                print(f"[DIR ERROR] {addr} failed directory listing: {str(e)}")

        elif cmd == "SUBFOLDER":
            try:
                action = data[1]        # "create" or "delete"
                folder_name = data[2]
                folder_path = os.path.join(SERVER_PATH, folder_name)

                if action.lower() == "create":
                    os.makedirs(folder_path, exist_ok=True)
                    conn.send(f"OK@Subfolder '{folder_name}' created.".encode(FORMAT))
                    logging.info(f"{addr} {action} subfolder: {folder_name}")
                    print(f"[SUBFOLDER] {addr} created '{folder_name}'")

                elif action.lower() == "delete":
                    if os.path.exists(folder_path):
                        os.rmdir(folder_path)
                        conn.send(f"OK@Subfolder '{folder_name}' deleted.".encode(FORMAT))
                        logging.info(f"{addr} {action} subfolder: {folder_name}")
                        print(f"[SUBFOLDER] {addr} deleted '{folder_name}'")
                    else:
                        conn.send("ERR@Subfolder not found.".encode(FORMAT))
                        print(f"[SUBFOLDER ERROR] {addr} tried to delete missing folder '{folder_name}'")
                else:
                    conn.send("ERR@Invalid subfolder command.".encode(FORMAT))
                    print(f"[SUBFOLDER ERROR] {addr} sent invalid command '{action}'")

            except Exception as e:
                conn.send(f"ERR@Subfolder operation failed: {str(e)}".encode(FORMAT))
                logging.error(f"Subfolder operation failed for {addr}: {str(e)}")
                print(f"[SUBFOLDER ERROR] {addr} failed {action} '{folder_name}': {str(e)}")


    print(f"[DISCONNECT] Client disconnected: {addr}")
    logging.info(f"Client disconnected: {addr}")
    conn.close()


def main():
    os.makedirs(SERVER_PATH, exist_ok=True)
    print(f"[SERVER] Started and listening on {IP}:{PORT}")
    logging.info(f"Server started on {IP}:{PORT}")
    server = socket.socket(socket.AF_INET,socket.SOCK_STREAM) ## used IPV4 and TCP connection
    server.bind(ADDR) # bind the address
    server.listen() ## start listening
    while True:
        conn, addr = server.accept() ### accept a connection from a client
        thread = threading.Thread(target = handle_client, args = (conn, addr)) ## assigning a thread for each client
        thread.start()


if __name__ == "__main__":
    main()

