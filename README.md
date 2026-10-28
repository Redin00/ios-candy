# ios-sweet (Pixel 10 / Tensor G5)

**Apple's iOS 16 running on Google Pixel 10 (Tensor G5).**

This project ports Apple's open-source XNU kernel (`xnu-8796`, the iOS 16 generation) to the **Google Pixel 10** (`frankel`, SoC `laguna` / Google Tensor G5). On top of it runs the **unmodified iOS 16.7.16 (`20H392`) userland of the iPhone X (`iPhone10,3` / `D22AP`)**: `launchd`, system daemons, `backboardd`, `SpringBoard`, and stock applications.

---

## Hardware Platform (Reference Test Device)

The specifications below represent the **physical reference device used for development and hardware testing**. The kernel storage driver and boot shim are designed to adapt dynamically across storage capacities and devices sharing the Tensor G5 platform.

| Component | Test Device Specification | Compatibility & Variations |
| --- | --- | --- |
| **Device / SKU** | Google Pixel 10 (`frankel`, SKU `GK2MP`), HW rev MP1.0, bootloader unlocked | Compatible with Tensor G5 (`laguna`) family devices (e.g. Pixel 10 / Pro / XL / Fold) |
| **SoC** | Google Tensor G5 (`laguna`), ARMv9.2-A | Identical MMIO layout across Tensor G5 platforms |
| **CPU Cluster** | 8 cores: 1× Cortex-X4 @ 3.40 GHz, 5× Cortex-A725 @ 3.00 GHz, 2× Cortex-A520 @ 1.95 GHz | Homogeneous SMP scheduling via PSCI CPU_ON |
| **Memory** | 12 GiB LPDDR5X (Samsung) | XNU manages 2 GiB in the upper DRAM bank at `0x880000000` (34 GiB..36 GiB) with 16 KiB translation pages |
| **Internal Storage** | 256 GiB Kioxia UFS 4.0 (`userdata` @ `/dev/block/sda35`, 220 GiB, 4096-byte blocks) | **Dynamic GPT discovery**: compatible with 128 GiB, 256 GiB, and 512 GiB storage tiers |
| **Storage Controller** | Google UFSHCI host controller at `0x3c400000` | 64-bit DMA addressing (`CAP_64AS`) above 4 GiB |
| **USB** | Synopsys DWC3 at `0x0c400000` (device mode CDC-ECM) | Interconnect restricted to 32-bit DMA (`< 4 GiB`); bounce buffer at `0x8b000000` |
| **Interrupts & Timer** | ARM GICv3 (GICD `0x05880000`, GICR `0x05900000`), VTIMER PPI 11 (INTID 27), frequency 38.4 MHz | Standard ARM Generic Timer & GICv3 architecture |
| **Console & Logs** | Persistent DBGC ramoops ring at `0x95400000`, Synopsys DW APB UART at `0x0db62000`, live UDP stream (port 5140) | Preserved across warm PSCI reboots |
| **Security / Reset** | Titan M2 security chip; ARM PSCI warm reset via SMC (`0x84000009`) | Standard PSCI system reset interface |

---

## Execution Model: Bring-Up Harness vs Persistent iOS

A key architectural distinction exists between **how the kernel is loaded during bring-up** and **how iOS executes**:

1. **Kernel Loading (Temporary Bring-Up Harness):**
   - During active development, the boot image is delivered via `fastboot boot shim-boot-v4.img`.
   - The kernel and boot shim are loaded directly into RAM via USB **without overwriting the device's boot partition (`boot_a`)**.
   - This provides a non-destructive harness: a simple device restart returns immediately to Android without brick risk.
   - **Untethered Target:** Once stable, the boot image can be flashed permanently to the `boot` partition (`fastboot flash boot shim-boot-v4.img`), allowing the Pixel 10 to power on directly into iOS standalone without a computer.

2. **Persistent iOS Execution (Physical Internal UFS):**
   - **iOS does NOT run in a ramdisk.** The 16 GiB unmodified Apple root filesystem (`launchd`, dyld shared cache, UIKit, frameworks, system apps) lives directly on the physical internal UFS flash inside the `userdata` partition (`/dev/block/sda35`).
   - The Apple XNU kernel mounts the physical HFS+ filesystem from UFS via `sweet_ufs` (`rd=ufsroot0`), reading binaries, frameworks, and writing data persistently to the physical flash chip, exactly like real Apple hardware.

---

## Status & Milestones

- **Milestone 1–3 (Bare-metal Shim on Hardware):** ✅ Achieved
  - ABL bootloader handoff via temporary `fastboot boot`.
  - AVB hash footer generation on 64 MiB padded boot images.
  - Bypassed GNOC (Google Network On Chip) interconnect firewall violations by avoiding firmware carve-outs.
  - Initialized 16 KiB translation granule MMU, verified memory access, GICv3 Redistributor PPI, VTIMER, and secondary CPU cores 1..7 via PSCI CPU_ON.
- **Milestone 4 (XNU Kernel on Tensor G5):** ✅ Achieved
  - Kernel ported and booted on physical Google Tensor G5 hardware.
  - Disabled 60-second hardware watchdog (`watchdog_cl0` at `0x200c4000`).
  - Patched open-source XNU Astris JTAG hang loops (`wfe; b .`) and `haltRestart` to execute clean ARM PSCI warm resets (`smc #0` with `0x84000009`).
  - Kernel runs stably without faults or resets.
- **Milestone 5 (Userspace Execution & Ramdisk Root):** ✅ Achieved
  - Booted Mach-O static executable `tools/init.macho` as `/sbin/launchd` on a mockfs ramdisk (`rd=md0`).
  - Process 1 spawned, executed, printed banner, and executed `SYS_reboot` (syscall 55) triggering automated PSCI reset back to Android.
  - Synopsys DWC3 USB driver ported with 32-bit DMA bounce buffer at `0x8b000000`.
- **Milestone 6 (Full iOS 16 Root Mount from UFS & Apple `launchd`):** 🔄 In Progress
  - **Storage Hardware Verification:** ✅ Verified on physical hardware. Read-only UFS probe verified that XNU takes over UFSHCI at `0x3c400000`, 64-bit DMA works, reads physical GPT partition table (`EFI PART`), finds `userdata` (`/dev/block/sda35`), and registers `/dev/ufsroot0`.
  - **Apple Artifacts:** ✅ Downloaded and verified official iOS 16.7.16 (`20H392`) restore DMGs (`087-86698-044.dmg`, `087-86593-047.dmg`, `087-86715-047.dmg`).
  - **Next Step:** Assemble case-sensitive HFS+ image `ios16-root-20H392.img`, apply bring-up tweaks, flash to `userdata`, and launch unmodified Apple `/sbin/launchd`.

---

## How It Boots

```
Google ABL (stock Pixel 10 bootloader, unlocked)
  -> fastboot boot shim-boot-v4.img            (temporary in RAM; boot partition untouched)
     -> shim: disables watchdog, sets up 16K MMU, loads XNU payload
        -> XNU Mach-O (kernel.pixel10) + Apple Device Tree (ADT) + boot-args
           -> sweet_ufs driver -> physical GPT partition (userdata on UFS LUN 0)
              -> dyld + dyld shared cache -> /sbin/launchd -> iOS daemons
```

---

## How to Build and Run

### 1. Requirements

- Physical Google Pixel 10 (`frankel`) or compatible Tensor G5 device with bootloader unlocked.
- Linux host PC (Arch Linux recommended) with `fastboot`, `adb`, `img2simg`, `rsync`.
- Host tools for root creation: `apfs-fuse-git` and `hfsprogs` (available via AUR: `yay -S apfs-fuse-git hfsprogs`).
- Clang / LLVM toolchain for cross-compiling the bare-metal shim.

### 2. Download Apple IPSW Artifacts

Download the official iOS 16.7.16 (`20H392`, iPhone X `iPhone10,3`) DMGs from Apple CDN into a local `ios-artifacts/` directory using `tools/remotezip.py`:

```sh
mkdir -p ios-artifacts
python3 tools/remotezip.py https://updates.cdn-apple.com/2025FallFCS/fullrestores/122-77006/1158E502-D76D-4226-AA06-ED5E30CD1111/iPhone10,3,iPhone10,6_16.7.16_20H392_Restore.ipsw 087-86698-044.dmg ios-artifacts
python3 tools/remotezip.py https://updates.cdn-apple.com/2025FallFCS/fullrestores/122-77006/1158E502-D76D-4226-AA06-ED5E30CD1111/iPhone10,3,iPhone10,6_16.7.16_20H392_Restore.ipsw 087-86593-047.dmg ios-artifacts
python3 tools/remotezip.py https://updates.cdn-apple.com/2025FallFCS/fullrestores/122-77006/1158E502-D76D-4226-AA06-ED5E30CD1111/iPhone10,3,iPhone10,6_16.7.16_20H392_Restore.ipsw 087-86715-047.dmg ios-artifacts
```

### 3. Build the iOS Root Filesystem Image

```sh
tools/mkiosroot.sh \
  ios-artifacts/087-86698-044.dmg \
  ios-artifacts/087-86593-047.dmg \
  ios-artifacts/087-86715-047.dmg \
    ios16-root-20H392.img 16G

sudo fsck.hfsplus -fy ios16-root-20H392.img
sudo mount -t hfsplus -o loop,force ios16-root-20H392.img /mnt/iosroot
sudo python3 tools/sweet-root-tweaks.py /mnt/iosroot
sudo umount /mnt/iosroot
img2simg ios16-root-20H392.img ios16-root-20H392.simg
```

### 4. Build the Apple Device Tree (ADT) and Boot Image

```sh
# Generate ADT for Pixel 10 hardware
python3 tools/mkadt.py shim/out/pixel10.adt --pixel10

# Assemble XNU payload
python3 tools/mkpayload.py xnu/out-0081/xnu-kernel/kernel.pixel10 shim/out/pixel10.adt shim/out/payload-pixel10.bin \
    --cmdline "debug=0x6 serial=0x23 cpus=1 keepsyms=1 rd=ufsroot0 unentitled_ios_sim_launch=1 ignition_level=1 sweetusb=2"

# Compile bare-metal shim and wrap into signed boot image
cd shim && ./build.sh ../shim/out/payload-pixel10.bin
```

### 5. Boot on Device

```sh
# Device in bootloader mode (fastboot)
fastboot oem watchdog disable
fastboot boot shim/out/shim-boot-v4.img
```

---

## Repository Layout

| Path | Description |
| --- | --- |
| `shim/` | Bare-metal AArch64 boot shim (EL1 setup, 16K MMU, PSCI, watchdog management) |
| `xnu/patches/` | XNU patch series for ARM64 platforms, drivers, and bring-up |
| `tools/mkadt.py` | Generates minimal Apple Device Tree (ADT) tailored for Pixel 10 (Tensor G5) |
| `tools/mkpayload.py` | Resolves dyld chained fixups and packs Mach-O kernel + ADT into shim payload |
| `tools/mkiosroot.sh` | Extracts Apple APFS cryptexes/rootfs and builds case-sensitive journaled HFS+ image |
| `tools/sweet-root-tweaks.py` | Configures iOS 16 userland (Setup bypass, mobileactivationd ark, daemon configs) |
| `tools/patch_kernel_pixel10_m5.py` | Automated patching script for Pixel 10 kernel (USB, DMA, PSCI resets, probes) |
| `tools/listen_console.py` | UDP console listener for live kernel logging over USB CDC-ECM (port 5140) |
| `tools/remotezip.py` | HTTP range request extractor for individual members of Apple restore IPSWs |
| `NOTES.md` | Detailed engineering log, hardware facts, register addresses, and bisection notes |

---

## Important Constraints

- **Fastboot RAM Boot Only (Development):** Use `fastboot boot <image>` to preserve the stock Android bootloader and partitions during development.
- **Never Run `fastboot getvar`:** On Pixel 10 ABL, `fastboot getvar` can hang USB communication.
- **Data Protection:** Writing to `userdata` replaces existing Android data. Confirm any destructive write steps before proceeding.
- **Proprietary Files:** Device dumps, serial numbers, and downloaded Apple DMGs remain outside of git (`ios-artifacts/`).
