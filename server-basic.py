import os
import socket
import threading
import hashlib
import logging
import time
from analytics import record_transfer, record_event
from cryptography.fernet import Fernet

logging.basicConfig(
    filename='server.log', 
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

IP = "0.0.0.0" ### gethostname()
PORT = 4450
ADDR = (IP,PORT)
SIZE = 64 * 1024
FORMAT = "utf-8"
SERVER_PATH = "server"

AES_Key= Fernet.generate_key()
cipher= Fernet (AES_Key)

def generate_unique_filename(filename): # Helps avoid overwriting existing files
    base, ext = os.path.splitext(filename)
    counter = 1
    unique_filename = filename
    while os.path.exists(os.path.join(SERVER_PATH, unique_filename)):
        unique_filename = f"{base}_{counter}{ext}"
        counter += 1
    return unique_filename

def generate_salt():
    return os.urandom(16)

def hash_password(password, salt):
    return hashlib.sha256(password.encode() + salt).hexdigest()

_leftover = {}

def send_ctrl(conn, text):
    conn.sendall((text + "\n").encode(FORMAT))

def recv_ctrl(conn):
    fil = conn.fileno()
    if fil not in _leftover:
        _leftover[fil] = b""
    if b"\n" in _leftover[fil]:
        line, rest = _leftover[fil].split(b"\n", 1)
        _leftover[fil] = rest
        return line.decode(FORMAT)
    buffer = _leftover[fil]
    while True:
        try:
            chunk = conn.recv(1024)
        except Exception:
            return None
        if not chunk:
            if buffer:
                val = buffer.decode(FORMAT)
                _leftover[fil] = b""
                return val
            return None
        buffer += chunk
        if b"\n" in buffer:
            line, rest = buffer.split(b"\n", 1)
            _leftover[fil] = rest
            return line.decode(FORMAT)

def recv_raw(conn, n):
    fil = conn.fileno()
    if fil not in _leftover:
        _leftover[fil] = b""
    data = b""
    if _leftover[fil]:
        take = _leftover[fil][:n]
        data += take
        _leftover[fil] = _leftover[fil][len(take):]
    while len(data) < n:
        chunk = conn.recv(n - len(data))
        if not chunk:
            break
        data += chunk
    return data

def authenticate(conn):
        try:
            conn.sendall(AES_Key + b"\n")
            send_ctrl(conn, "AUTH@Username:")
            username = recv_ctrl(conn)
            if username is None:
                return False
            send_ctrl(conn, "AUTH@Password:")
            password = recv_ctrl(conn)
            if password is None:
                return False

            with open("users.txt", "r") as f:
                for line in f:
                    stored_user, stored_hash, stored_salt = line.strip().split(":")
                    if username == stored_user:
                        salt = bytes.fromhex(stored_salt)
                        hashed_pw = hash_password(password, salt)
                        if hashed_pw == stored_hash:
                            send_ctrl(conn, "OK@Login successful.")
                            print(f"[AUTH] Login successful for user: {username}")
                            return True
                send_ctrl(conn, "ERR@Invalid credentials.")
                logging.warning(f"Failed login attempt for user: {username}")
                print(f"[AUTH] Failed login attempt for user: {username}")
                return False
        except Exception as e:
            logging.error (f"Authentication error: {str(e)}")
            try:
                send_ctrl(conn, f"ERR@Authentication error: {str(e)}")
            except Exception:
                pass
            return False

def handle_client (conn,addr):
    connect_time = time.perf_counter()
    record_event("server", "CLIENT_CONNECT", connect_time, connect_time)
    
    if not authenticate(conn):
        logging.info(f"Authentication failed for {addr}.")
        conn.close()
        return

    logging.info(f"{addr} - Authentication successful.")
    print(f"[CONNECT] Client connected: {addr}")
    send_ctrl(conn, "OK@Welcome to the server")

    while True:
        try:
            ctrl = recv_ctrl(conn)
            if ctrl is None:
                break

            data = ctrl.split("@")
            cmd = data[0]
            CHUNK_SIZE = 64 * 1024
            send_data = "OK@"

            if cmd == "LOGOUT":
                break

            elif cmd == "TASK":
                print(f"[TASK] Command received from {addr}")
                logging.info(f"{addr} issued TASK command")
                send_data += "LOGOUT from the server.\n"
                send_ctrl(conn, send_data.strip())

            elif cmd == "UPLOAD":
                upload_start = time.perf_counter()
                try:
                    filename = data[1]
                    filesize = int(data[2])
                    filepath = os.path.join(SERVER_PATH, filename)
                    ext = os.path.splitext(filename)[1].lower()
                    if ext not in [".txt", ".mp3", ".wav", ".mp4", ".avi", ".mkv"]:
                        send_ctrl(conn, "ERR@Unsupported file type.")
                        continue

                    if os.path.exists(filepath):
                        send_ctrl(conn, "ERR@File exists. Overwrite? (y/n)")
                        choice = recv_ctrl(conn)
                        if choice is None or choice.lower() != "y":
                            send_ctrl(conn, "OK@Upload cancelled.")
                            logging.info(f"{addr} cancelled upload of file: {filename}")
                            print(f"[UPLOAD] {addr} cancelled upload of {filename}")
                            continue

                    filepath = os.path.join(SERVER_PATH, filename)
                    send_ctrl(conn, "OK@Ready to receive.")

                    received = 0
                    with open(filepath, "wb") as f:
                        while received < filesize:
                            to_read = min(CHUNK_SIZE, filesize - received)
                            bytes_read = recv_raw(conn, to_read)
                            if not bytes_read:
                                break
                            f.write(bytes_read)
                            received += len(bytes_read)

                    if not os.path.exists(filepath):
                        send_ctrl(conn, f"ERR@Upload failed: incomplete transfer.")
                        continue

                    actual_size = os.path.getsize(filepath)
                    if ext == ".txt" and actual_size < 25 * 1024 * 1024:
                        os.remove(filepath)
                        send_ctrl(conn, "ERR@Text file too small (min 25 MB).")
                        continue
                    elif ext in [".mp3", ".wav"] and actual_size < 1 * 1024 * 1024 * 1024:
                        os.remove(filepath)
                        send_ctrl(conn, "ERR@Audio file too small (min 1 GB).")
                        continue
                    elif ext in [".mp4", ".avi", ".mkv"] and actual_size < 2 * 1024 * 1024 * 1024:
                        os.remove(filepath)
                        send_ctrl(conn, "ERR@Video file too small (min 2 GB).")
                        continue

                    send_ctrl(conn, f"OK@Uploaded {filename}")
                    logging.info(f"{addr} uploaded file: {filename}")
                    print(f"[UPLOAD] {addr} → {filename}")
                    upload_end = time.perf_counter()
                    record_transfer("server", "UPLOAD", filename, actual_size, upload_start, upload_end)

                except Exception as e:
                    logging.error(f"Upload failed for {addr}: {str(e)}")
                    print(f"[UPLOAD ERROR] {addr} failed: {str(e)}")
                    try:
                        send_ctrl(conn, f"ERR@Upload failed: {str(e)}")
                    except Exception:
                        pass

            elif cmd == "DOWNLOAD":
                download_start = time.perf_counter()
                try:
                    filename = data[1]
                    filepath = os.path.join(SERVER_PATH, filename)
                    if not os.path.exists(filepath):
                        send_ctrl(conn, "ERR@File not found.")
                        continue

                    filesize = os.path.getsize(filepath)
                    ext = os.path.splitext(filename)[1].lower()

                    if ext == ".txt" and filesize < 25 * 1024 * 1024:
                        send_ctrl(conn, "ERR@Text file too small (min 25 MB).")
                        continue
                    elif ext in [".mp3", ".wav"] and filesize < 1 * 1024 * 1024 * 1024:
                        send_ctrl(conn, "ERR@Audio file too small (min 1 GB).")
                        continue
                    elif ext in [".mp4", ".avi", ".mkv"] and filesize < 2 * 1024 * 1024 * 1024:
                        send_ctrl(conn, "ERR@Video file too small (min 2 GB).")
                        continue
                    elif ext not in [".txt", ".mp3", ".wav", ".mp4", ".avi", ".mkv"]:
                        send_ctrl(conn, "ERR@Unsupported file type.")
                        continue

                    send_ctrl(conn, f"OK@{filesize}")
                    ack = recv_ctrl(conn)
                    if ack is None or ack != "READY":
                        continue

                    with open(filepath, "rb") as f:
                        while True:
                            bytes_read = f.read(CHUNK_SIZE)
                            if not bytes_read:
                                break
                            conn.sendall(bytes_read)

                    send_ctrl(conn, "OK@Download complete.")
                    logging.info(f"{addr} downloaded file: {filename}")
                    print(f"[DOWNLOAD] {addr} ← {filename}")
                    download_end = time.perf_counter()
                    record_transfer("server", "DOWNLOAD", filename, filesize, download_start, download_end)

                except Exception as e:
                    try:
                        send_ctrl(conn, f"ERR@Download failed: {str(e)}")
                    except Exception:
                        pass
                    logging.error(f"Download failed for {addr}: {str(e)}")
                    print(f"[DOWNLOAD ERROR] {addr} failed: {str(e)}")

            elif cmd == "DELETE":
                try:
                    filename = data[1]
                    filepath = os.path.join(SERVER_PATH, filename)
                    if not os.path.exists(filepath):
                        send_ctrl(conn, "ERR@File not found.")
                        continue
                    os.remove(filepath)
                    send_ctrl(conn, f"OK@Deleted {filename}")
                    logging.info(f"{addr} deleted file: {filename}")
                    print(f"[DELETE] {addr} removed {filename}")
                except Exception as e:
                    try:
                        send_ctrl(conn, f"ERR@Delete failed: {str(e)}")
                    except Exception:
                        pass
                    logging.error(f"Delete failed for {addr}: {str(e)}")
                    print(f"[DELETE ERROR] {addr} failed: {str(e)}")

            elif cmd == "DIR":
                try:
                    items = os.listdir(SERVER_PATH)
                    file_list = "\n".join(items) if items else "Directory is empty."
                    send_ctrl(conn, f"OK@{file_list}")
                    logging.info(f"{addr} requested directory listing")
                    print(f"[DIR] {addr} requested directory listing")
                except Exception as e:
                    try:
                        send_ctrl(conn, f"ERR@Directory read failed: {str(e)}")
                    except Exception:
                        pass
                    logging.error(f"Directory listing failed for {addr}: {str(e)}")
                    print(f"[DIR ERROR] {addr} failed directory listing: {str(e)}")

            elif cmd == "SUBFOLDER":
                try:
                    action = data[1]
                    folder_name = data[2]
                    folder_path = os.path.join(SERVER_PATH, folder_name)
                    if action.lower() == "create":
                        os.makedirs(folder_path, exist_ok=True)
                        send_ctrl(conn, f"OK@Subfolder '{folder_name}' created.")
                        logging.info(f"{addr} {action} subfolder: {folder_name}")
                        print(f"[SUBFOLDER] {addr} created '{folder_name}'")
                    elif action.lower() == "delete":
                        if os.path.exists(folder_path):
                            os.rmdir(folder_path)
                            send_ctrl(conn, f"OK@Subfolder '{folder_name}' deleted.")
                            logging.info(f"{addr} {action} subfolder: {folder_name}")
                            print(f"[SUBFOLDER] {addr} deleted '{folder_name}'")
                        else:
                            send_ctrl(conn, "ERR@Subfolder not found.")
                            print(f"[SUBFOLDER ERROR] {addr} tried to delete missing folder '{folder_name}'")
                    else:
                        send_ctrl(conn, "ERR@Invalid subfolder command.")
                        print(f"[SUBFOLDER ERROR] {addr} sent invalid command '{action}'")
                except Exception as e:
                    try:
                        send_ctrl(conn, f"ERR@Subfolder operation failed: {str(e)}")
                    except Exception:
                        pass
                    logging.error(f"Subfolder operation failed for {addr}: {str(e)}")
                    print(f"[SUBFOLDER ERROR] {addr} failed {action} '{folder_name}': {str(e)}")

        except Exception as e:
            try:
                send_ctrl(conn, f"ERR@{str(e)}")
            except Exception:
                pass
            logging.error(f"Client {addr} error: {str(e)}")

    print(f"[DISCONNECT] Client disconnected: {addr}")
    logging.info(f"Client disconnected: {addr}")
    conn.close()

def main():
    os.makedirs(SERVER_PATH, exist_ok=True)
    print(f"[SERVER] Started and listening on {IP}:{PORT}")
    logging.info(f"Server started on {IP}:{PORT}")
    server = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    server.bind(ADDR)
    server.listen()
    while True:
        conn, addr = server.accept()
        thread = threading.Thread(target = handle_client, args = (conn, addr))
        thread.start()

if __name__ == "__main__":
    main()
