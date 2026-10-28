#!/usr/bin/env python3
"""
Patch kernel.pixel10 for Milestone 5:
1. Skip Qualcomm GCC probe in sweet_usb_probe (0x4e8850)
2. Insert trampoline at 0x74ec860 (0x4e8860) to invoke sweet_usb_probe on md0 root mount
3. Update DWC3 base from 0x0a600000 to 0x0c400000 (Google Tensor G5) at 0x4e89ec
4. Bypass Qualcomm QUSB2 PHY (0x088e2000) at 0x4e8b48
5. Implement Tensor G5 VBUS override at 0x0c637028 (dp_top_csr) at 0x4e90b4
6. Redirect gadget_start exit at 0x4e9218 to clean epilogue (0x74ecbc4)
7. Hook IOFindBSDRoot md0 completion at 0xa3d9ac to jump to trampoline
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

# 5. 0x4e90b4 (VA 0x74ed0b4): Tensor G5 VBUS override at 0x0c637028 (dp_top_csr)
vbus_override = [
    0x528e0000,  # mov w0, #0x7000
    0x72a18c60,  # movk w0, #0xc63, lsl #16 (0x0c637000)
    0x52802001,  # mov w1, #0x100
    0x97fe8c90,  # bl 0xfffffe0007490300 <_ml_io_map>
    0xb40000a0,  # cbz x0, +20 (to b 0x74ed130)
    0xb9402808,  # ldr w8, [x0, #0x28]
    0x32100508,  # orr w8, w8, #0x30000 (bits 16 & 17: usb3_vbus | usb2_vbus)
    0xb9002808,  # str w8, [x0, #0x28]
    0xd5033f9f,  # dsb sy
    0x14000016,  # b 0xfffffe00074ed130
]
for idx, insn in enumerate(vbus_override):
    struct.pack_into("<I", data, 0x4e90b4 + idx * 4, insn)

# 6. 0x4e9218 (VA 0x74ed218): b 0x74ecbc4 (return to epilogue)
struct.pack_into("<I", data, 0x4e9218, 0x17fffe6b)

# 7. 0xa3d9ac (VA 0x7a419ac): b 0x74ec860 (hook md0 completion to trampoline)
struct.pack_into("<I", data, 0xa3d9ac, 0x17eaabad)

# 8. 0x4e8b10 (VA 0x74ecb10): use 32-bit bounce buffer at 0x8b000000 for DWC3 DMA (<4GB)
dma_bounce = [
    0x52800000,  # mov w0, #0
    0x72b16000,  # movk w0, #0x8b00, lsl #16 (0x8b000000)
    0x52880001,  # mov w1, #0x4000 (16KB)
    0x97fe8df9,  # bl 0xfffffe0007490300 <_ml_io_map>
    0xf9000680,  # str x0, [x20, #0x8] (ud.dma = va)
    0x52800008,  # mov w8, #0
    0x72b16008,  # movk w8, #0x8b00, lsl #16 (0x8b000000)
    0xd0005b29,  # adrp x9, 0xfffffe0008052000
    0xf9059128,  # str x8, [x9, #0xb20] (ud.dma_pa = 0x8b000000)
    0x910123f6,  # add x22, sp, #0x48 (restore x22 pointer to ifnet_init_params!)
    0x1400003b,  # b 0xfffffe00074ecc24
]
for idx, insn in enumerate(dma_bounce):
    struct.pack_into("<I", data, 0x4e8b10 + idx * 4, insn)

# 9. 0xa76f64 (VA 0x7a7af64): NOP fbcon_init (ret) to prevent clearing RAMOOPS buffer
struct.pack_into("<I", data, 0xa76f64, 0xd65f03c0)

# 10. 0xa77030 (VA 0x7a7b030): ramoops_putc hook in fbcon_transmit_data
ramoops_putc = [
    0xb0002fc1,  # adrp x1, 0xfffffe0008074000
    0xf940b421,  # ldr x1, [x1, #0x168] (fbcon_base = RAMOOPS_CON VA)
    0xb4000241,  # cbz x1, +72 (ret at 0x7a7b080)
    0xb9400022,  # ldr w2, [x1] (hdr[0])
    0x52884883,  # mov w3, #0x4244
    0x72a868e3,  # movk w3, #0x4347, lsl #16 (0x43474244 = 'DBGC')
    0x6b03005f,  # cmp w2, w3
    0x54000080,  # b.eq +16 (has_sig at 0x7a7b05c)
    0xb9000023,  # str w3, [x1] (hdr[0] = 'DBGC')
    0xb900043f,  # str wzr, [x1, #4] (hdr[1] = start = 0)
    0xb900083f,  # str wzr, [x1, #8] (hdr[2] = size = 0)
    0xb9400822,  # has_sig: ldr w2, [x1, #8] (current size)
    0x52800003,  # mov w3, #0
    0x72a001e3,  # movk w3, #0x0f, lsl #16 (0x0f0000 = MAX)
    0x6b03005f,  # cmp w2, w3
    0x540000a2,  # b.hs +20 (ret at 0x7a7b080)
    0x91003024,  # add x4, x1, #12 (data buffer)
    0x38224880,  # strb w0, [x4, w2, uxtw] (data[size] = c)
    0x11000442,  # add w2, w2, #1 (size++)
    0xb9000822,  # str w2, [x1, #8] (update size)
    0xd65f03c0,  # ret
]
for idx, insn in enumerate(ramoops_putc):
    struct.pack_into("<I", data, 0xa77030 + idx * 4, insn)

# 11. 0xa775b0 (VA 0x7a7b5b0): replace ml_io_map_wcomb with ml_io_map (Device-nGnRnE)
# to prevent speculative prefetch across 0x95400000 into bldr_log_reserved@95600000
struct.pack_into("<I", data, 0xa775b0, 0x97e854b4)

# 12. 0x9f91ec (VA 0x79fd1ec): implement PSCI_SYSTEM_RESET (0x84000009) unconditionally in haltRestart
# replacing Apple's entire function entry so both reboot() and panic() auto-reset via PSCI
psci_reset = [
    0x52800120,  # mov w0, #9
    0x72b08000,  # movk w0, #0x8400, lsl #16 (0x84000009 = PSCI_SYSTEM_RESET)
    0xd4000003,  # smc #0
    0x14000000,  # b .
]
for idx, insn in enumerate(psci_reset):
    struct.pack_into("<I", data, 0x9f91ec + idx * 4, insn)

# 13. Route all panic hang/spin loops (wfe; b .) to PSCI_SYSTEM_RESET helper
# Helper at 0x481204 (VA 0x7485204, inside sweet_early_panic right after ret):
for idx, insn in enumerate(psci_reset):
    struct.pack_into("<I", data, 0x481204 + idx * 4, insn)

# 13a. 0x321608 (VA 0x7325608): in _handle_debugger_trap when panicDebugging != 0
struct.pack_into("<I", data, 0x321608, 0x14057eff)  # b 0x7485204

# 13b. 0x321a08 (VA 0x7325a08): in _panic_trap_to_debugger replacing DebuggerTrapWithState & wfe loop
struct.pack_into("<I", data, 0x321a08, 0x14057dff)  # b 0x7485204

# 13c. 0x321c34 (VA 0x7325c34): in _panic_spin_forever replacing wfe loop
struct.pack_into("<I", data, 0x321c34, 0x14057d74)  # b 0x7485204

open(PATH, "wb").write(data)
print(f"Successfully applied Milestone 5 patches to {PATH}")
