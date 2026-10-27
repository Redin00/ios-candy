#!/usr/bin/env python3
import socket, sys, os

port = 5140
log_path = sys.argv[1] if len(sys.argv) > 1 else "logs/live-pixel10.txt"
os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(("0.0.0.0", port))
print(f"[*] Listening on UDP port {port} (saving to {log_path})...", flush=True)

with open(log_path, "a", encoding="utf-8", errors="replace") as f:
    while True:
        try:
            data, addr = sock.recvfrom(65536)
            text = data.decode("utf-8", errors="replace")
            sys.stdout.write(text)
            sys.stdout.flush()
            f.write(text)
            f.flush()
        except KeyboardInterrupt:
            break
