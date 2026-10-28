# iOS 16 on Google Pixel 10 (frankel / laguna, Tensor G5) - Working Notes

## Target Device Specifications
- **Device:** Google Pixel 10 (`frankel`, SKU `GK2MP`), HW rev MP1.0, bootloader unlocked.
- **SoC:** Google Tensor G5 (`laguna`), ARMv9.2-A.
- **CPU Cluster:** 8 cores in homogeneous cluster configuration:
  - 1× Cortex-X4 @ 3.40 GHz (core 7)
  - 5× Cortex-A725 @ 3.00 GHz (cores 2..6)
  - 2× Cortex-A520 @ 1.95 GHz (cores 0..1)
- **DRAM:** 12 GiB LPDDR5X (Samsung, 4-channel).
  - Upper DRAM bank: `0x880000000` (34 GiB..36 GiB), 2 GiB allocated to XNU.
  - Lower DRAM bank: contains firmware carve-outs protected by Google Network On Chip (GNOC) firewall policies.
- **Storage:** 256 GiB Kioxia UFS 4.0, Google UFSHCI host controller at `0x3c400000`.
  - Partition `userdata`: `/dev/block/sda35` (LUN 0, 220 GiB, 4096-byte blocks).
- **USB:** Synopsys DWC3 at `0x0c400000`. DMA restricted to 32-bit addresses (`< 4 GiB`) via `simple_usb_bus` interconnect; bounce buffer located at `0x8b000000`.
- **Interrupts & Timer:** ARM GICv3 (GICD `0x05880000`, GICR `0x05900000`), VTIMER PPI 11 (INTID 27), frequency 38.4 MHz.
- **Security / Power:** Titan M2 / GSA chip; PSCI warm reset via SMC (`0x84000009`).

---

## Bring-up Milestones & Status

### Milestone 1–3: Bare-Metal Shim Diagnostic on Hardware
- **ABL Bootloader Analysis:**
  - Disassembled `backup/abl_a.img`: ABL runs at EL1 (`CurrentEL == 4`, `0x2e8e08 == 0`).
  - Handoff jump occurs via `0x6c934 -> 0x6c900 -> br x7` (EL1) with `x0 = 0x8a000000` (DTB) and `x7 = 0x80080000` (kernel entry).
  - MMU and D-cache disabled by ABL (`msr sctlr_el1, x2` clearing bits 0 and 2), interrupts masked (`DAIFSet 0xf`).
  - Boot image v2 header parser in ABL (`0x6bb54..0x6bc40` and `0x6ce74`):
    - `header_size` at offset 1644 (`0x66c`) = 1660 (`0x67c`).
    - `recovery_dtbo_size` at offset 1632 (`0x660`) must be 0.
    - `dtb_size` at offset 1648 (`0x670`) = length of concatenated DTBs.
    - `dtb_addr` at offset 1652 (`0x674`) = `0x8a000000`.
    - Padded to 64 MiB (`67108864` bytes) with valid AVB hash footer (`avbtool add_hash_footer --partition_size 67108864 --partition_name boot`).
  - Concatenated DTB (`dtb/frankel_base.dtb`): ABL matches chip revision (product_id=5, major=1, minor=0, pkg_mode=0 for MP1.0 / B0) and selects DTB 1.
- **Interconnect Firewall (GNOC) Discovery:**
  - On Tensor G5, all `no-map;` firmware carveouts (e.g. `bldr_log_reserved@95600000`) are hardware-protected by GNOC firewall policies. Any read/write from Non-Secure EL1 triggers an immediate interconnect bus error (`DECERR`) and warm reset with reason `cbeb` / `gnoc_error`.
  - Mapping addresses below 4 GB as Normal memory (`NC_FLAGS`) permits speculative CPU prefetch into secure carveouts, tripping the firewall. Kept all addresses below 4 GB as Device-nGnRnE (`DEV_FLAGS`).
  - VeriSilicon DC9x00 DPU: ABL isolates the display bus (`SSWRP_DPU`) before branching; writes to unclocked hardware fault on the interconnect.
- **Milestone 3 Execution Success:**
  - Shim executed all diagnostics cleanly without GNOC faults.
  - Tested 16K granule MMU, memory latency, GICv3 PPI/SGI, and SMP PSCI CPU_ON for cores 1..7.
  - Clean PSCI reset reached; Android verified `RST_STAT: 0x0`, `CDD reboot reason: 0x0000`.

---

### Milestone 4: Apple XNU Kernel Boot on Tensor G5
- **Early Hardware Crash Fixes:**
  - Tensor G5 has a 60-second hardware watchdog (`watchdog_cl0` at `0x200c4000`, `watchdog_cl1` at `0x200c5000`). Implemented `disable_wdt()` in `shim/loader.c` unlocking with `0x00c0ffee` and clearing bit 0, combined with `fastboot oem watchdog disable`.
  - Moved `disable_wdt()` and enabled instruction cache (`SCTLR_EL1.I`) BEFORE the 22 MiB copy loop in `shim/loader.c` to prevent watchdog timeouts with MMU off.
  - Patched open-source XNU Astris JTAG loops (`wfe; b .` in `_handle_debugger_trap`, `_panic_trap_to_debugger`, `_panic_spin_forever`) and `haltRestart` (`_ZN18IODTPlatformExpert11haltRestartEj`) to branch to ARM PSCI warm reset (`mov w0, #0x84000009; smc #0`).
  - NOP'd early framebuffer diagnostic writes into lower RAM and redirected Stage 0 logging to Synopsys DW APB UART (`0x0db62000`).
- **Hardware Verification:**
  - Booted with `fastboot boot shim/out/shim-boot-v4.img`.
  - Kernel ran stably for >5 minutes without watchdog bites, resets, or GNOC faults.
  - Manual Power key long-press confirmed clean shutdown: `CDD reboot reason: 0xcccc`.

---

### Milestone 5: USB CDC-ECM Console & Ramdisk Root Bringup
- **Ramdisk Root (`rd=md0`):**
  - Built static ad-hoc signed Mach-O `tools/init.macho` using `tools/sweet-init.S` and `tools/mkinit.py`.
  - Embedded as RAMDisk at `0x8824c8000` (`size=0x8000`) and declared in `/chosen/memory-map/RAMDisk`.
  - Fixed `sweet-init.S` to fallback from `O_RDWR` to `O_WRONLY`/stdout on mockfs and proceed unconditionally to `SYS_reboot` (syscall 55).
- **Synopsys DWC3 USB Driver Porting:**
  - Relocated DWC3 physical base to Tensor G5 `0x0c400000` (`sweet_usb_probe` at `0x4e89ec`).
  - Bypassed Qualcomm GCC register probe, QUSB2 PHY probe, and QSCRATCH VBUS override.
  - Implemented Tensor G5 VBUS override at `0x0c637028` (`dp_top_csr`).
  - Allocated DWC3 DMA bounce buffer in 32-bit lower RAM at `0x8b000000` (`_ml_io_map(0x8b000000, 0x4000)`) matching `dma-ranges = <0x0 0x0 0x0 0x0 0x1 0x0>` on `simple_usb_bus`.
  - Hooked `IOFindBSDRoot` md0 mount completion (`0xa3d9ac`) to `sweet_md0_trampoline` at `0x4e8860`.
- **Milestone 5 Hardware Bisection Verification (2026-10-28):**
  - `xnu_entry` probe (`0x4890fc`): reached, PSCI reset verified in 1m16s.
  - `md0` probe (`0x4e8860`): reached, PSCI reset verified in 1m22s. Confirms XNU MMU, GICv3, VTIMER, Mach, BSD, VFS, and mockfs ramdisk root mount.
  - `md0_after_usb` probe (`0x4e8864`): reached, PSCI reset verified in 1m17s. Confirms Synopsys DWC3 USB driver initialization without interconnect faults.
  - Full Milestone 5 Boot: PID 1 (`tools/init.macho` as `/sbin/launchd`) spawned, executed banner, slept, and executed `SYS_reboot`, triggering clean warm PSCI reboot back to Android (`ro.boot.bootreason = reboot`, `ADB_UP` verified in 1m26s).

---

### Milestone 6: Full iOS 16 Root Mount from UFS & Apple `launchd`
- **Target Partition:** Internal UFS `userdata` partition `/dev/block/sda35` (LUN 0, 220 GiB, 4096-byte blocks).
- **Apple Artifacts (Downloaded & Verified):**
  - Downloaded official Apple iOS 16.7.16 (`20H392`, iPhone X `iPhone10,3`) restore DMGs via `tools/remotezip.py` into `/home/redinn/IT_Stuff/Projects/ios-artifacts/`:
    - `087-86698-044.dmg` (OS rootfs, 4,730,814,044 bytes, CRC-32 ok)
    - `087-86593-047.dmg` (SystemOS cryptex, 2,743,074,816 bytes, CRC-32 ok)
    - `087-86715-047.dmg` (AppOS cryptex, 10,485,760 bytes, CRC-32 ok)
- **Step 1 (UFS Driver on Tensor G5 - Verified on Physical Hardware 2026-10-28):**
  - Implemented and verified hardware bisection probes (`ufs_userdata` at `0x4e34e0`, `ufs_done` at `0x4e3690`) in `tools/patch_kernel_pixel10_m5.py`.
  - Fixed `_serial_init` mapping target for `RAMOOPS_PMSG` (offset `0xa775b0` now calls `_ml_io_map` at `0x7490300`) and enabled `cons_ops.flags = 1` in `_fbcon_probe`.
  - Replaced panic handlers with infinite `wfe; b .` loops so any driver failure or panic halts the device, while reaching the probe triggers clean PSCI reset.
  - Executed read-only UFS probe via RAM boot (`fastboot boot` with `rd=ufsroot0`):
    - XNU mapped UFSHCI registers at `0x3c400000`.
    - 64-bit DMA allocation above 4GB (`0x880000000`) accepted by UFSHCI (`CAP_64AS`).
    - Polled SCSI `TEST UNIT READY` (0x00) succeeded on LUN 0.
    - Polled SCSI `READ(10)` read LBA 1 and verified GPT signature (`EFI PART`).
    - Partition search parsed GPT table and matched `userdata` (`/dev/block/sda35`).
    - `bdevsw_add` and `cdevsw_add_with_bdev` registered `/dev/ufsroot0`.
    - Both `ufs_userdata` and `ufs_done` probes executed cleanly, triggering automated warm PSCI reset back to Android (`ADB_UP` verified in 1m35s, `ro.boot.bootreason = reboot`, `cdd_reboot_reason = 1:0000`).
    - Android installation, partitions, and user data remained 100% untouched.
- **Step 2 (Active / Next):**
  - Build HFS+ root image `ios16-root-20H392.img` with `tools/mkiosroot.sh` using host tools `apfs-fuse-git` and `hfsprogs`.
  - Apply `tools/sweet-root-tweaks.py`.
  - Flash to `userdata` (`fastboot flash -S 512M userdata ios16-root-20H392.simg`) after confirming backup/destructive step with user.
- **Step 3:**
  - Boot full iOS 16.7.16 system and run unmodified Apple `/sbin/launchd`.

---

## Technical Reference & Memory Map (Pixel 10 / Tensor G5)

```
0x05880000 - 0x05890000  ARM GICv3 GICD
0x05900000 - 0x05b00000  ARM GICv3 GICR (8 redistributors)
0x0c400000 - 0x0c500000  Synopsys DWC3 USB Controller
0x0c637000 - 0x0c637100  DP TOP CSR (VBUS override at 0x0c637028, Top Enable at 0x0c637044)
0x0db62000 - 0x0db63000  Synopsys DW APB UART
0x200c4000 - 0x200c5000  Watchdog CL0 (unlock: 0x00c0ffee, bit 0 = enable)
0x200c5000 - 0x200c6000  Watchdog CL1
0x3c400000 - 0x3c410000  Google UFSHCI UFS Host Controller
0x80080000               ABL kernel entry point (EL1)
0x8a000000               Device Tree Blob (DTB)
0x8b000000 - 0x8b004000  Synopsys DWC3 32-bit DMA bounce buffer
0x95200000 - 0x95400000  RAMOOPS_CON (written by ABL on boot)
0x95400000 - 0x95600000  RAMOOPS_PMSG (DBGC persistent ring, preserved across reboots)
0x880000000 - 0x900000000 Upper DRAM bank (2 GiB managed by XNU, 16K pages)
0x8824c8000              Milestone 5 mockfs RAMDisk
```
