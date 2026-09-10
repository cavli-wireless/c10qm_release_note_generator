# Release Note SDK 2.0.0 & Modem 2.0.0

## Big Upgrade: LA 4.0 → LA 5.0 (Cavli CQS290 / QCM2290 IoT)

**Cavli SDK Release:** 2.0.0 — based on Qualcomm QCM2290.LA.5.0\
**Modem version:** 2.0.0 (MPSS.HA.1.1-00549)\
**Platform:** Qualcomm QCM2290 (Cavli CQS290 module)\
**From:** `Snapdragon_Mid_2020_IOT.SPF.4.0` — QCM2290.LA.4.0 (RNO-240710023155, 10-Jul-2024)\
**To:** `IOT_High_Mid_2024.SPF.1.0` — QCM2290.LA.5.0 (RNO-260220023709, 20-Feb-2026)\
**Android:** 14 (U) — Linux kernel: 4.19 → 5.15 (GKI, Kernel Platform 2.0)\

---

## 1. Overview

This is a **big upgrade** from the `Snapdragon_Mid_2020_IOT.SPF.4.0` program (internally QCM2290.LA.**4.0**) to the `IOT_High_Mid_2024.SPF.1.0` program (internally QCM2290.LA.**5.0**).

Major architectural changes:

- **Kernel:** moved from the legacy `LA.UM.9.15.2` kernel (Linux 4.19) to **Kernel Platform 2.0** `KERNEL.PLATFORM.2.0.r12` (Linux 5.15 GKI) — kernel/vendor split following the GKI model.
- **HLOS System:** `LA.QSSI.14.0.r1` → `LA.QSSI.14.0.r3`; Android 11 branch (`LA.QSSI.11.0`) dropped.
- **HLOS Vendor:** `LA.UM.9.15.2` → `LA.VENDOR.13.2.1.r2` (Divar vendor line), with new `LA.QISI.13.0.r1`.
- **ADSP:** major bump `ADSP.VT.5.4.1` → `ADSP.VT.5.4.3.c1` (Divar).
- Synchronized updates to MPSS, TZ, BOOT, BTFM, WLAN, RPM.

This release's changes are organized into two domains:

- **Part A — Android SDK (HLOS):** peripherals, functions, features, EDK2 bootloader, kernel drivers, frameworks, vendor apps. See Section 2.
- **Part B — Chipcode (Firmware):** MPSS (modem), BOOT, TZ, RPM, ADSP and their build tooling. See Section 3.

The full LA 4.0 → LA 5.0 Build ID comparison table is in **Appendix A**.

---


## 2. Part A — Android SDK (HLOS): Peripherals, Functions & Features

Peripheral bring-up and feature enablement on the Android/HLOS side (bengal + qssi source trees).

**Supported peripherals (CQS290 EVK):**

| Category | Support |
|---|---|
| Display | MIPI DSI 1280x800 LCD |
| Input / Touch | Goodix GT911 capacitive touch (I2C) |
| Audio | 3.5 mm headphone jack |
| Multimedia / Camera | 2x Sony IMX258 CSI camera (PDAF) |
| Connectivity | WLAN 1x1 802.11a/b/g/n/ac, Bluetooth 5.0, GNSS |

**Android SDK change set (Cavli commits):**

| Commit | Area | Change |
|---|---|---|
| `429e15c` | vendor / camera | Add IMX258 PDAF to CHI-SDK |
| `6606492` | msm-kernel / power | Charger driver: skip battery checks (battery-less module) |
| `bb9d61f` | proprietary / storage | Disable HS400 Enhanced Strobe on new HW rev (fall back to HS400) |
| `8887e23` | proprietary / power | Remove PSY_IIO (battery-less config) |
| `0a524a1` | vendor/cavli / OTA | Automotive support + OTA file:// / content:// URI handling |
| `a369820` | device/qcom | Change product model name |
| `4ef3e4b` | qssi/device/qcom | Change product model name (system) |
| `fb32dfc` | edk2 | EDK2 bootloader aligned to Kernel Platform 2.0 |
| `3bc828b` | vendor/cavli/build-tools | Enable job build configuration |
| `ced2ca2` | vendor/cavli/setup | Suppress change-log output during compile |
| `c8d4a62` | qssi/device/qcom | HLOS baseline sync — LA.QSSI.14.0.R3 |
| `5688606` | qssi/frameworks | HLOS baseline sync — LA.QSSI.14.0.R3 |
| `1771cc0` | qssi/vendor | HLOS baseline sync — LA.QSSI.14.0.R3 |
| `e7e29b0` | bengal/device/qcom | Vendor baseline sync — LA.VENDOR r1_000020.1 |


### 2.1 Display / Touch / Audio

- **Display:** MIPI DSI 1280x800 LCD panel brought up to Android UI.
- **Touch:** Goodix GT911 capacitive touch controller over I2C.
- **Audio:** 3.5 mm headphone jack playback/record path.

### 2.2 Camera — IMX258 PDAF `429e15c`

Brought up 2x Sony IMX258 CSI image sensors with PDAF (Phase Detection Auto Focus) support, integrated into the Qualcomm CHI-SDK camera stack.

### 2.3 Storage — eMMC HS400 tuning `bb9d61f`

On the new HW revision, HS400 Enhanced Strobe fails the bus-width switch at 200 MHz (CMD6 returns -EILSEQ / -84 during devfreq scale-up), flooding CQHCI error dumps and triggering a watchdog reset. The interface now disables HS400ES and falls back to plain HS400 (CMD21 tuning), giving enough timing on the affected silicon.

### 2.4 Power — Battery-less operation `6606492` `8887e23`

The CQS290 module has no external Qualcomm SMB charger IC and no battery. The charger driver now skips battery current / presence / status checks (debug-battery mode) to prevent false errors, and PSY_IIO is removed from the kernel config for the battery-less configuration.

### 2.5 OTA Update & Applications `0a524a1`

- **Local OTA update application (SystemUpdater):**
- Detects the automotive platform and uses /data/local/tmp as the default update path.
- Separates file:// and content:// URI handling with proper permission management, plus a File-API based discovery path for file:// sources.
- Bundled utility / validation applications: GPS Test, Open Camera, Organic Maps, and the ATI app.

### 2.6 Product Identity `a369820` `4ef3e4b`

Product model name presented to the OS updated to Android IOT (vendor + system device configs).

### 2.7 Bootloader (EDK2) `fb32dfc`

Bootloader (EDK2) aligned to the new Kernel Platform 2.0 (KERNEL.PLATFORM.2.0.R12).

### 2.8 Build / Setup Tooling & HLOS Baseline `3bc828b` `ced2ca2` `c8d4a62` `5688606` `1771cc0` `e7e29b0`

Vendor build-tools enabled for job builds; setup suppresses change-log output during compile.
HLOS baseline sync to LA.QSSI.14.0.r3 (system device/frameworks/vendor) and the LA.VENDOR.13.2.1.r2 vendor line.


---

## 3. Part B — Chipcode (Firmware): Modem, Boot, TZ, RPM, ADSP

Low-level firmware bring-up and customizations in the chipcode/ tree.

**Chipcode change set (Cavli commits):**

| Commit | Image | Change |
|---|---|---|
| `533743e` | MPSS.HA.1.1 (Modem) | ATCoP: Cavli vendor extensions + ATI / +RFI commands, EFS identity |
| `dcc4e79` | BOOT.XF.4.1 | Enable PM_LDO_17 for RF antenna path |
| `71151f6` | build-tools | Build scripts + configuration for IoT LA 5.0 |
| `d335cd1` | ADSP.VT.5.4.3.c1 | Baseline sync — iot_high_mid_2024_spf_1_0 r1.0_00020.1 |
| `dd6c512` | RPM.BF.1.10 | Baseline sync — iot_high_mid_2024_spf_1_0 r1.0_00020.1 |
| `34db77f` | chipcode (top) | Baseline sync — iot_high_mid_2024_spf_1_0 r1.0_00020.1 |


### 3.1 Modem (MPSS) — Vendor AT Command Interface `533743e`

- **Cavli vendor AT command set** for device identification and RF information, under interface/atcop/cavli/:
- ATI overridden to report the full module identity: manufacturer, model, description, IMEI / SVN, part number, serial number, hardware version, modem version, and build date.
- New +RFI command reports the RFC version and QCN version.
- Device identity (HW/SW version, part number, serial number, QCN version) is persisted in the modem EFS under /nv/item_files/cavli/ and read back via cav_efs.

### 3.2 Boot — RF Front End / Power `dcc4e79`

PM_LDO_17 is enabled at the bootloader (BOOT.XF.4.1) stage to supply power to the RF antenna path.

### 3.3 RPM / ADSP baseline `dd6c512` `d335cd1`

RPM and ADSP synchronized to the LA 5.0 firmware baseline (iot_high_mid_2024_spf_1_0, r1.0_00020.1). ADSP is a major bump ADSP.VT.5.4.1 → ADSP.VT.5.4.3.c1 (Divar).

### 3.4 TZ — QUP / QP Access Control

QUPv3 Serial Engine (SE) allocation and TrustZone (TZ) access-control mapping used on the CQS290 module (default profile, from QUPAC_Access.c).

| SE | Protocol | Mode | NS Owner | AllowFifo | Load | ModExcl | Function (Peripheral) |
|---|---|---|---|---|---|---|---|
| QUPV3_0_SE0 | UART_4W | FIFO | AC_HLOS | TRUE | TRUE | FALSE | Free — available for external peripheral (UART) |
| QUPV3_0_SE1 | I2C | FIFO | AC_HLOS | TRUE | TRUE | FALSE | SMB / EEPROM / PM8008 (PMIC) |
| QUPV3_0_SE2 | I2C | GSI | AC_HLOS | FALSE | TRUE | FALSE | Legacy Touch |
| QUPV3_0_SE3 | UART_4W | FIFO | AC_HLOS | TRUE | TRUE | FALSE | BT HCI |
| QUPV3_0_SE4 | UART_2W | FIFO | AC_HLOS | FALSE | TRUE | FALSE | Debug UART |
| QUPV3_0_SE5 | SPI | GSI | AC_HLOS | FALSE | TRUE | TRUE | Free — available for external peripheral (SPI) |

> **Note:** In the Qualcomm reference design SE0 is used for the NFC eSE (UART) and SE5 for a Fingerprint sensor (SPI). The Cavli CQS290 EVK does not populate NFC or a Fingerprint sensor, so these two Serial Engines are left free and are available for the customer to connect their own external peripherals (SE0 as UART, SE5 as SPI). The remaining SEs are assigned as shown above.

### 3.5 Chipcode Build System `71151f6`

Dedicated LA 5.0 build scripts and configuration for ADSP, Boot, CDSP, Modem (MPSS), RPM, and TrustZone.


---

## 4. Test Results — Qualcomm LA 5.0 (Qualcomm reference board)

The results below are reproduced from Qualcomm's LA 5.0 release note (RNO-260220023709) and were obtained on Qualcomm's reference/QRD platform, not on Cavli hardware. They confirm the software baseline.


### 4.1 Functional / Peripheral Test Cases

| Test Case | Result |
|---|---|
| Build loading (PCAT / JTAG / Fastboot) | PASS |
| UART shell | PASS |
| FBC till Android UI (Display) | PASS |
| ADB (shell / push / remount) | PASS |
| ADB reboot (bootloader / edl) & Fastboot reboot | PASS |
| ADSP / CDSP / MPSS / WPSS PIL | PASS |
| Camera front/rear (preview + snapshot) | PASS |
| Camcorder front/rear | PASS |
| Audio playback/record + AV playback/record | PASS |
| Graphics | PASS |
| Dump collection | PASS |
| BT connect & pairing | PASS |
| WiFi connect & browsing | PASS |

### 4.2 Modem Test Cases (dual-SIM)

| Combination | MO SIM-1 | MO SIM-2 | MT SIM-1 | MT SIM-2 | Data SIM-1 | Data SIM-2 | SMS SIM-1 | SMS SIM-2 |
|---|---|---|---|---|---|---|---|---|
| GSM + GSM | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass |
| GSM + UMTS | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass |
| GSM + LTE | Pass | NA | Pass | NA | Pass | – | Pass | NA |
| UMTS + UMTS | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass |
| UMTS + LTE | Pass | NA | Pass | NA | Pass | Pass | Pass | NA |
| UMTS + GSM | Pass | Pass | Pass | Pass | Pass | Pass | Pass | Pass |
| LTE + GSM | NA | Pass | NA | Pass | Pass | Pass | NA | Pass |
| LTE + UMTS | NA | Pass | NA | Pass | Pass | Pass | NA | Pass |

---

## 5. Known Issues

- Kernel version mapping (4.19 → 5.15 GKI) is inferred from the Qualcomm program designations and is not explicitly printed in the Qualcomm release-note PDF.
- SSC QUP per-engine sensor assignment is not named in the source table (bus/ownership only — see 3.4).

---

## Appendix A — Build ID Comparison (QCM2290 META Build)

**LA 4.0 Meta Build:** `QCM2290.LA.4.0-00041-STD.PROD-1` (Milestone Post-CS7) **LA 5.0 Meta Build:** `QCM2290.LA.5.0-00053-STD.PROD-1` (Milestone Post-CS8)

| Software Image | LA 4.0 Build ID | LA 5.0 Build ID | Note |
|---|---|---|---|
| META | QCM2290.LA.4.0-00041-STD.PROD-1 | QCM2290.LA.5.0-00053-STD.PROD-1 | Big upgrade 4.0 → 5.0 |
| Kernel | LA.UM.9.15.2.r1-09900-KAMORTA.QSSI14.0-1 (kernel 4.19) | KERNEL.PLATFORM.2.0.r12-06100-kernel.0-1 (kernel 5.15 GKI) | New kernel platform |
| HLOS System | LA.QSSI.14.0.r1-15800-qssi.0-1 | LA.QSSI.14.0.r3-03300-qssi.0-1 | r1 → r3 |
| HLOS System (A11) | LA.QSSI.11.0.r1-22500-qssi.0-1 | (removed) | Android 11 dropped |
| HLOS Vendor | (part of LA.UM.9.15.2) | LA.VENDOR.13.2.1.r2-14000-DIVAR.QSSI14.0-1 | New vendor line |
| QISI | – | LA.QISI.13.0.r1-02300-qssi.0-1 | New in LA5.0 |
| ADSP | ADSP.VT.5.4.1-00389.8-KAMORTA-1 | ADSP.VT.5.4.3.c1-00118-DIVAR-1 | Major bump |
| BOOT | BOOT.XF.4.1-00392-KAMORTALAZ-1 | BOOT.XF.4.1-00408-KAMORTALAZ-1 | 00392 → 00408 |
| MPSS (Modem) | MPSS.HA.1.1-00471-KD_ALL_PACK-1 | MPSS.HA.1.1-00549-KD_ALL_PACK-2 | 00471 → 00549 |
| RPM | RPM.BF.1.10-00224-KAMORTAAAAAANAZR-1 | RPM.BF.1.10-00225-KAMORTAAAAAANAZR-1 | 00224 → 00225 |
| TZ.APPS | TZ.APPS.2.0-00281-KAMORTAAAAAANAZT-2 | TZ.APPS.2.0-00340-KAMORTAAAAAANAZT-1 | 00281 → 00340 |
| TZ.XF | TZ.XF.5.1-01183-ADJKAMORTAAANAZT-2 | TZ.XF.5.1-01213-ADJKAMORTAAANAZT-2 | 01183 → 01213 |
| BTFM.CMC.1.2.0 | BTFM.CMC.1.2.0-00218-QCACHROMZ-2 | BTFM.CMC.1.2.0-00222-QCACHROMZ-3 | 00218 → 00222 |
| BTFM.CMC.1.3.0 | BTFM.CMC.1.3.0-00115-QCACHROMZ-1 | BTFM.CMC.1.3.0-00153-QCACHROMZ-1 | 00115 → 00153 |
| VIDEO | VIDEO.VE.6.0-00053-PROD-2 | VIDEO.VE.6.0-00053-PROD-2 | Unchanged |
| WLAN | WLAN.HL.3.3.7.c1-00515-QCAHLSWMTPLZ-1 | WLAN.HL.3.3.7.c1-00553-QCAHLSWMTPLZ-1 | 00515 → 00553 |
| WLAN_ADDON | WLAN_ADDON.HL.1.0-00078-CNSS_RMZ_WAPI-1 | WLAN_ADDON.HL.1.0-00078-CNSS_RMZ_WAPI-1 | Unchanged |

> HLOS tags (LA 5.0): Vendor AU: AU_LINUX_ANDROID_LA.VENDOR.13.2.1.R2.11.00.00.1017.140 · Kernel AU: AU_LINUX_KERNEL.PLATFORM.2.0.R12.00.00.00.019.061 · System AU: AU_LINUX_ANDROID_LA.QSSI.14.0.R3.14.00.00.1236.033 · QISI AU: AU_LINUX_ANDROID_LA.QISI.13.0.R1.11.00.00.1316.023 · LKG: Keystone UKQ1.251204.001, Android Upstream UPM1.231025.065.
