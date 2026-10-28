#!/bin/bash
# Build the Pixel 10 (frankel / laguna) shim and wrap it in boot.img (v2 and v4).
set -euo pipefail
cd "$(dirname "$0")"
CC="clang --target=aarch64-linux-gnu"
OBJCOPY=llvm-objcopy
READELF=llvm-readelf
NM=llvm-nm
CFLAGS="-O2 -ffreestanding -nostdlib -fno-pic -fno-jump-tables -mgeneral-regs-only -mstrict-align -fno-stack-protector -Wall -Wextra ${SHIM_CFLAGS:-}"
mkdir -p out
for f in start.S shim.c console.c mmu.c fdt.c loader.c; do
	$CC $CFLAGS -c $f -o out/${f%.*}.o
done
# The image runs wherever ABL puts it with no relocation pass: only the
# header's image_size (start.o, linked at 0) may be an absolute address.
abs=$($READELF -r out/shim.o out/console.o out/mmu.o out/fdt.o out/loader.o | grep -c ABS64 || true)
[ "$abs" = 0 ] || { echo "error: $abs absolute relocations in C objects" >&2; exit 1; }
$CC $CFLAGS -fuse-ld=lld -static -T shim.ld -Wl,--build-id=none -Wl,-N \
	out/start.o out/shim.o out/console.o out/mmu.o out/fdt.o out/loader.o -o out/shim.elf
$OBJCOPY -O binary out/shim.elf out/Image
# ABL copies the file; pad to image_size so .bss/stacks exist as zeroed bytes.
size=$($NM out/shim.elf | awk '$3=="_end"{print strtonum("0x"$1)}')
truncate -s "$size" out/Image
# Ramdisk: an xnu payload (tools/mkpayload.py) if given as $1, else an empty
# newc cpio (ABL dislikes a zero-size ramdisk on some builds) -> diagnostics.
if [ -n "${1:-}" ]; then
	cp "$1" out/ramdisk.bin
else
	(cd out && rm -rf rd && mkdir rd && cd rd && find . | cpio -o -H newc --quiet | gzip -9 > ../ramdisk.bin)
fi
DTB_FILE="../dtb/frankel_base.dtb"
[ -f "$DTB_FILE" ] || DTB_FILE="../dtb/frankel.dtb"
python3 - <<'EOF'
import struct, os

def pad(b, align):
    r = len(b) % align
    return b + (b"\x00" * (align - r) if r else b"")

kernel = open("out/Image", "rb").read()
ramdisk = open("out/ramdisk.bin", "rb").read()
dtb_path = "../dtb/frankel_base.dtb" if os.path.exists("../dtb/frankel_base.dtb") else "../dtb/frankel.dtb"
dtb = open(dtb_path, "rb").read()

# 1. boot.img v2 (self-contained kernel + ramdisk + base DTB)
page_sz = 4096
os_version = (16 << 25) | (2026 - 2000) << 4 | 10

# Valid bootconfig trailer for ramdisk
bc_body = b""
bc_csum = sum(bc_body) & 0xffffffff
bc_trailer = struct.pack("<II", len(bc_body), bc_csum) + b"#BOOTCONFIG\n"
rd_with_bc = ramdisk + bc_trailer

hdr_v2 = bytearray(page_sz)
struct.pack_into("<8s10I", hdr_v2, 0,
    b"ANDROID!",
    len(kernel), 0x80080000,
    len(rd_with_bc), 0x8be00000,
    0, 0,
    0x8a000000, page_sz,
    2, os_version)
cmdline = b"console=null"
hdr_v2[64:64+len(cmdline)] = cmdline
struct.pack_into("<I", hdr_v2, 1644, 1660)      # header_size (0x66c)
struct.pack_into("<I", hdr_v2, 1648, len(dtb))  # dtb_size (0x670)
struct.pack_into("<Q", hdr_v2, 1652, 0x8a000000)# dtb_addr (0x674)
with open("out/shim-boot.img", "wb") as f:
    f.write(hdr_v2)
    f.write(pad(kernel, page_sz))
    f.write(pad(rd_with_bc, page_sz))
    f.write(pad(dtb, page_sz))

# 2. boot.img v4 (uses phone's vendor_kernel_boot_a DTB, matches stock boot_a layout)
hdr_v4 = bytearray(page_sz)
struct.pack_into("<8sIIII16xI", hdr_v4, 0,
    b"ANDROID!", len(kernel), len(rd_with_bc),
    os_version, 0x630, 4)
hdr_v4[44:44+len(cmdline)] = cmdline
with open("out/shim-boot-v4.img", "wb") as f:
    f.write(hdr_v4)
    f.write(pad(kernel, page_sz))
    f.write(pad(rd_with_bc, page_sz))

# 3. boot.img v4 without ramdisk (matches stock boot_a header where ramdisk_size=0)
hdr_v4_nord = bytearray(page_sz)
struct.pack_into("<8sIIII16xI", hdr_v4_nord, 0,
    b"ANDROID!", len(kernel), 0,
    os_version, 0x630, 4)
hdr_v4_nord[44:44+len(cmdline)] = cmdline
with open("out/shim-boot-v4-nord.img", "wb") as f:
    f.write(hdr_v4_nord)
    f.write(pad(kernel, page_sz))
EOF

# Add AVB hash footers to all images (pads to 64 MiB partition size and adds valid VBMeta + footer)
avbtool add_hash_footer --image out/shim-boot.img --partition_size 67108864 --partition_name boot
avbtool add_hash_footer --image out/shim-boot-v4.img --partition_size 67108864 --partition_name boot
avbtool add_hash_footer --image out/shim-boot-v4-nord.img --partition_size 67108864 --partition_name boot
ls -lh out/Image out/shim-boot.img out/shim-boot-v4.img out/shim-boot-v4-nord.img
