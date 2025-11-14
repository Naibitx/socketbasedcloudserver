import hashlib
import os

users = {
    "naibys": "admin123",
    "matt": "admin123",
    "diego": "admin123"
}

with open("users.txt", "w") as f:
    for username, password in users.items():
        salt = os.urandom(16)

        hashed_pw = hashlib.sha256(password.encode() + salt).hexdigest()

        f.write(f"{username}:{hashed_pw}:{salt.hex()}\n")

print("users.txt created successfully with users:")
for username in users.keys():
    print("-", username)