import os
import socket
import threading
import hashlib
import logging
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
try:
    from analytics import record_transfer, record_event
except Exception:
    def record_transfer(*args, **kwargs):
        pass

    def record_event(*args, **kwargs):
        pass

# Logging setup
logging.basicConfig(
    filename="server.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

IP = "localhost"          # Listen on all interfaces
PORT = 4450
ADDR = (IP, PORT)
SIZE = 64 * 1024
FORMAT = "utf-8"
SERVER_PATH = os.path.join(BASE_DIR, "server")
os.makedirs(SERVER_PATH, exist_ok=True)


def check_credentials(username: str, password: str) -> bool:
    try:
        with open("users.txt", "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                stored_user, stored_hash, stored_salt = line.split(":")
                if username == stored_user:
                    salt = bytes.fromhex(stored_salt)
                    candidate = hashlib.sha256(
                        password.encode() + salt
                    ).hexdigest()
                    return candidate == stored_hash
    except FileNotFoundError:
        logging.error("users.txt not found for authentication")
    except ValueError:
        logging.error("Malformed line in users.txt")
    return False


def authenticate(conn: socket.socket, addr):
    try:
        # Ask for username
        conn.send("AUTH@USERNAME".encode(FORMAT))
        username = conn.recv(SIZE).decode(FORMAT).strip()

        # Ask for password
        conn.send("AUTH@PASSWORD".encode(FORMAT))
        password = conn.recv(SIZE).decode(FORMAT).strip()

        if check_credentials(username, password):
            conn.send("AUTH@OK".encode(FORMAT))
            logging.info("Authentication successful for %s from %s", username, addr)
            record_event("server", "LOGIN_OK", 0, 0, status="OK", note=username)
            return username
        else:
            conn.send("AUTH@FAIL".encode(FORMAT))
            logging.warning("Authentication FAILED for %s from %s", username, addr)
            record_event("server", "LOGIN_FAIL", 0, 0, status="FAIL", note=username)
            return None

    except Exception as e:
        logging.error("Authentication error for %s: %s", addr, e)
        try:
            conn.send(f"ERR@Authentication error: {e}".encode(FORMAT))
        except Exception:
            pass
        return None


def handle_upload(conn, addr, parts):
    # parts: ["UPLOAD", filename, filesize]
    if len(parts) < 3:
        conn.send("ERR@Invalid UPLOAD command".encode(FORMAT))
        return

    filename = parts[1]
    try:
        filesize = int(parts[2])
    except ValueError:
        conn.send("ERR@Invalid file size".encode(FORMAT))
        return

    filepath = os.path.join(SERVER_PATH, filename)
    ext = os.path.splitext(filename)[1].lower()

    allowed_exts = [".txt", ".mp3", ".wav", ".mp4", ".avi", ".mkv"]
    if ext not in allowed_exts:
        conn.send("ERR@Unsupported file type.".encode(FORMAT))
        return

    # If file exists, ask about overwrite
    if os.path.exists(filepath):
        conn.send("ERR@File exists. Overwrite? (y/n)".encode(FORMAT))
        choice = conn.recv(SIZE).decode(FORMAT).strip().lower()
        if choice != "y":
            conn.send("OK@Upload cancelled.".encode(FORMAT))
            logging.info("[%s] cancelled upload of %s", addr, filename)
            return

    conn.send("OK@READY".encode(FORMAT))

    received = 0
    start = time.perf_counter()
    with open(filepath, "wb") as f:
        while received < filesize:
            chunk = conn.recv(min(SIZE, filesize - received))
            if not chunk:
                break
            f.write(chunk)
            received += len(chunk)
    end = time.perf_counter()

    actual_size = os.path.getsize(filepath)
    if ext == ".txt" and actual_size < 25 * 1024 * 1024:
        os.remove(filepath)
        conn.send("ERR@Text file too small (min 25MB)".encode(FORMAT))
        return
    elif ext in [".mp3", ".wav"] and actual_size < 1 * 1024 * 1024 * 1024:
        os.remove(filepath)
        conn.send("ERR@Audio file too small (min 1GB)".encode(FORMAT))
        return
    elif ext in [".mp4", ".avi", ".mkv"] and actual_size < 2 * 1024 * 1024 * 1024:
        os.remove(filepath)
        conn.send("ERR@Video file too small (min 2GB)".encode(FORMAT))
        return

    logging.info("[%s] uploaded file %s (%d bytes)", addr, filename, received)
    record_transfer("server", "UPLOAD", filename, received, start, end, status="OK")
    conn.send(f"OK@Uploaded {filename}".encode(FORMAT))


def handle_download(conn, addr, parts):
    if len(parts) < 2:
        conn.send("ERR@Invalid DOWNLOAD command".encode(FORMAT))
        return

    filename = parts[1]
    filepath = os.path.join(SERVER_PATH, filename)

    if not os.path.exists(filepath):
        conn.send("ERR@File not found.".encode(FORMAT))
        return

    filesize = os.path.getsize(filepath)
    ext = os.path.splitext(filename)[1].lower()
    allowed_exts = [".txt", ".mp3", ".wav", ".mp4", ".avi", ".mkv"]

    if ext not in allowed_exts:
        conn.send("ERR@Unsupported file type.".encode(FORMAT))
        return

    # Send size and wait for READY
    conn.send(f"OK@{filesize}".encode(FORMAT))
    ack = conn.recv(SIZE).decode(FORMAT).strip()
    if ack != "READY":
        return

    start = time.perf_counter()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(SIZE)
            if not chunk:
                break
            conn.sendall(chunk)
    end = time.perf_counter()

    logging.info("[%s] downloaded file %s (%d bytes)", addr, filename, filesize)
    record_transfer("server", "DOWNLOAD", filename, filesize, start, end, status="OK")


def handle_client(conn: socket.socket, addr):
    logging.info("Client connected from %s", addr)
    username = authenticate(conn, addr)
    if not username:
        logging.info("Closing connection for unauthenticated client %s", addr)
        conn.close()
        return

    # After successful login, send welcome message
    conn.send(f"OK@Welcome {username}".encode(FORMAT))

    try:
        while True:
            data = conn.recv(SIZE).decode(FORMAT)
            if not data:
                break

            parts = data.strip().split("@")
            cmd = parts[0]

            if cmd == "LOGOUT":
                logging.info("[%s] requested LOGOUT", addr)
                break

            elif cmd == "UPLOAD":
                handle_upload(conn, addr, parts)

            elif cmd == "DOWNLOAD":
                handle_download(conn, addr, parts)

            elif cmd == "DELETE":
                if len(parts) < 2:
                    conn.send("ERR@Missing filename for DELETE".encode(FORMAT))
                    continue
                filename = parts[1]
                filepath = os.path.join(SERVER_PATH, filename)
                if not os.path.exists(filepath):
                    conn.send("ERR@File not found.".encode(FORMAT))
                    continue
                os.remove(filepath)
                logging.info("[%s] deleted file %s", addr, filename)
                conn.send(f"OK@Deleted {filename}".encode(FORMAT))

            elif cmd == "DIR":
                try:
                    items = os.listdir(SERVER_PATH)
                    listing = "\n".join(items) if items else "Directory is empty."
                    conn.send(f"OK@{listing}".encode(FORMAT))
                except Exception as e:
                    conn.send(f"ERR@Directory error: {e}".encode(FORMAT))

            elif cmd == "SUBFOLDER":
                if len(parts) < 3:
                    conn.send("ERR@Usage: SUBFOLDER@<create|delete>@<name>".encode(FORMAT))
                    continue
                action = parts[1].lower()
                folder_name = parts[2]
                folder_path = os.path.join(SERVER_PATH, folder_name)

                try:
                    if action == "create":
                        os.makedirs(folder_path, exist_ok=True)
                        conn.send(f"OK@Subfolder '{folder_name}' created".encode(FORMAT))
                    elif action == "delete":
                        if os.path.isdir(folder_path) and not os.listdir(folder_path):
                            os.rmdir(folder_path)
                            conn.send(f"OK@Subfolder '{folder_name}' deleted".encode(FORMAT))
                        else:
                            conn.send("ERR@Subfolder not empty or not found".encode(FORMAT))
                    else:
                        conn.send("ERR@Invalid SUBFOLDER action".encode(FORMAT))
                except Exception as e:
                    conn.send(f"ERR@Subfolder error: {e}".encode(FORMAT))

            else:
                conn.send("ERR@Unknown command".encode(FORMAT))

    except Exception as e:
        logging.error("Error while handling client %s: %s", addr, e)
        try:
            conn.send(f"ERR@{e}".encode(FORMAT))
        except Exception:
            pass
    finally:
        logging.info("Client disconnected %s", addr)
        conn.close()


def main():
    os.makedirs(SERVER_PATH, exist_ok=True)
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(ADDR)
    server.listen()
    print(f"[SERVER] Listening on {IP}:{PORT}")
    logging.info("Server listening on %s:%s", IP, PORT)

    while True:
        conn, addr = server.accept()
        thread = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
        thread.start()


if __name__ == "__main__":
    main()
