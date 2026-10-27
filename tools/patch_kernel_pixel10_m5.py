#!/usr/bin/env python3
"""
Patch kernel.pixel10 for Milestone 5:
1. Skip Qualcomm GCC probe in sweet_usb_probe
2. Insert trampoline at 0x74ec860 to invoke sweet_usb_probe on md0 root mount
3. Update DWC3 base from 0x0a600000 to 0x0c400000 (Google Tensor G5)
4. Bypass Qualcomm QUSB2 PHY (0x088e2000) at 0x74ecb48
5. Bypass Qualcomm QSCRATCH (0x0a6f8800) at 0x74ed0b4
6. Redirect gadget_start exit at 0x74ed218 to clean epilogue (0x74ecbc4)
7. Hook IOFindBSDRoot md0 completion at 0x7a419ac to jump to trampoline
"""
import struct, sys

PATH = "xnu/out-0081/xnu-kernel/kernel.pixel10"
data = bytearray(open(PATH, "rb").read())

# 1. 0x4e8850 (VA 0x74ec850): b 0x74ec9ec (skip GCC)
struct.pack_into("<I", data, 0x4e8850, 0x14000067)

# 2. 0x4e8860 (VA 0x74ec860): sweet_md0_trampoline
trampoline = [
    0x97ffffe7,  # bl 0xfffffe00074ec7fc <_sweet_usb_probe>
    0xd2800019,  # mov x25, #0
    0x52800015,  # mov w21, #0
    0xf00034bb,  # adrp x27, 0xfffffe0007b83000
    0x911ce37b,  # add x27, x27, #0x738
    0x1415541a,  # b 0xfffffe0007a418dc <_IOFindBSDRoot+0xbe8>
]
for idx, insn in enumerate(trampoline):
    struct.pack_into("<I", data, 0x4e8860 + idx * 4, insn)

# 3. 0x4e89ec (VA 0x74ec9ec): mov w0, #0x0c400000
struct.pack_into("<I", data, 0x4e89ec, 0x52a18800)

# 4. 0x4e8b48 (VA 0x74ecb48): b 0x74ecbc4 (skip Qualcomm QUSB2 PHY probe)
struct.pack_into("<I", data, 0x4e8b48, 0x1400001f)

# 5. 0x4e90b4 (VA 0x74ed0b4): b 0x74ed130 (skip Qualcomm QSCRATCH)
struct.pack_into("<I", data, 0x4e90b4, 0x1400001f)

# 6. 0x4e9218 (VA 0x74ed218): b 0x74ecbc4 (return to epilogue)
struct.pack_into("<I", data, 0x4e9218, 0x17fffe6b)

# 7. 0xa3d9ac (VA 0x7a419ac): b 0x74ec860 (hook md0 completion to trampoline)
struct.pack_into("<I", data, 0xa3d9ac, 0x17eaabad)

open(PATH, "wb").write(data)
print(f"Successfully applied Milestone 5 patches to {PATH}")
