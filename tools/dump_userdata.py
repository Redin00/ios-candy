#!/usr/bin/env python3
"""
Dump an Android block device (e.g. userdata) over ADB with on-the-fly gzip compression,
real-time throughput tracking, and SHA-256 verification.
"""

import argparse
import hashlib
import os
import subprocess
import sys
import time

def parse_args():
    parser = argparse.ArgumentParser(description="Dump Android block device over ADB.")
    parser.add_argument(
        "--out",
        default="/home/redinn/IT_Stuff/Projects/ios-artifacts/userdata_backup_pixel10.img.gz",
        help="Destination file path (default: .img.gz)"
    )
    parser.add_argument(
        "--dev",
        default="/dev/block/sda35",
        help="Device node on target (default: /dev/block/sda35)"
    )
    return parser.parse_args()

def check_env(dev):
    # Verify adb connection
    try:
        out = subprocess.check_output(["adb", "get-state"], stderr=subprocess.STDOUT).decode().strip()
        if out != "device":
            print(f"[!] adb device state is '{out}', expected 'device'.", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"[!] Failed to check adb state: {e}", file=sys.stderr)
        sys.exit(1)

    # Verify su access
    try:
        out = subprocess.check_output(["adb", "shell", "su -c id"], stderr=subprocess.STDOUT).decode().strip()
        if "uid=0(root)" not in out:
            print(f"[!] su check failed: {out}", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"[!] su check threw exception: {e}", file=sys.stderr)
        sys.exit(1)

    # Get block size
    try:
        size_str = subprocess.check_output(
            ["adb", "shell", f"su -c 'blockdev --getsize64 {dev}'"],
            stderr=subprocess.STDOUT
        ).decode().strip()
        total_raw_bytes = int(size_str)
        return total_raw_bytes
    except Exception as e:
        print(f"[!] Failed to get block device size for {dev}: {e}", file=sys.stderr)
        sys.exit(1)

def main():
    args = parse_args()
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)

    print(f"[*] Checking device environment for {args.dev}...")
    total_raw_bytes = check_env(args.dev)
    raw_gib = total_raw_bytes / (1024 ** 3)
    raw_gb = total_raw_bytes / 1e9
    print(f"[*] Target device: {args.dev}")
    print(f"[*] Raw partition size: {total_raw_bytes:,} bytes ({raw_gib:.2f} GiB / {raw_gb:.2f} GB)")
    print(f"[*] Destination: {args.out}")

    cmd = ["adb", "exec-out", f"su -c 'gzip -1 < {args.dev}'"]
    print(f"[*] Starting streaming dump: {' '.join(cmd)}")
    start_time = time.time()
    last_print = start_time
    bytes_transferred = 0
    last_bytes = 0

    hasher = hashlib.sha256()

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    try:
        with open(args.out, "wb") as f_out:
            while True:
                chunk = proc.stdout.read(1024 * 1024)  # 1 MiB chunks
                if not chunk:
                    break
                f_out.write(chunk)
                hasher.update(chunk)
                bytes_transferred += len(chunk)

                now = time.time()
                if now - last_print >= 5.0:
                    dt = now - last_print
                    speed = (bytes_transferred - last_bytes) / dt / (1024 * 1024)
                    elapsed = now - start_time
                    m, s = divmod(int(elapsed), 60)
                    h, m = divmod(m, 60)
                    out_gib = bytes_transferred / (1024 ** 3)
                    print(
                        f"[{h:02d}:{m:02d}:{s:02d}] Dumped: {out_gib:.2f} GiB compressed "
                        f"({bytes_transferred:,} B) | Speed: {speed:.1f} MB/s",
                        flush=True
                    )
                    last_print = now
                    last_bytes = bytes_transferred

        proc.wait()
        if proc.returncode != 0:
            err = proc.stderr.read().decode()
            print(f"[!] adb exec-out terminated with code {proc.returncode}: {err}", file=sys.stderr)
            sys.exit(proc.returncode)

    except KeyboardInterrupt:
        print("\n[!] Interrupted by user. Cleaning up...", file=sys.stderr)
        proc.kill()
        sys.exit(130)

    elapsed = time.time() - start_time
    m, s = divmod(int(elapsed), 60)
    h, m = divmod(m, 60)
    final_sha256 = hasher.hexdigest()

    sha_path = args.out + ".sha256"
    with open(sha_path, "w") as f_sha:
        f_sha.write(f"{final_sha256}  {os.path.basename(args.out)}\n")

    out_gib = bytes_transferred / (1024 ** 3)
    avg_speed = (bytes_transferred / elapsed) / (1024 * 1024)
    print("=" * 60)
    print(f"[+] DUMP COMPLETED SUCCESSFULLY in {h:02d}:{m:02d}:{s:02d}")
    print(f"[+] Total compressed size: {bytes_transferred:,} bytes ({out_gib:.2f} GiB)")
    print(f"[+] Average transfer speed: {avg_speed:.2f} MB/s")
    print(f"[+] Output file: {args.out}")
    print(f"[+] SHA-256: {final_sha256}")
    print(f"[+] Checksum saved to: {sha_path}")
    print("=" * 60)

if __name__ == "__main__":
    main()
