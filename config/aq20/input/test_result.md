<!--
test_result.md — Section 4 "Test Result".

Text before the first `##` becomes the section intro. Then one `##` heading per
table, each followed by a Markdown table. Headings are numbered 4.1, 4.2, ...

Do NOT paste results you have not seen. If testing has not run, say so in the
intro and leave the Result column as REPLACE_ME. A visible placeholder is
honest; a fabricated  is not, and nobody downstream can tell the difference.
-->

These results run on Cavli AQ20 EVK and required setup.

## Functional Test

|Function Area | Test Case | Result |
|---|---|---|
|Basic system functionality | ADB shell, reboot and bootloader |  Pass |
|| USB enumeration |    Pass |
|| Fastboot loading. reboot and continue |   Pass  |
|| AT Port functionality |   Pass  |
|| USB connect/disconnect |   Pass  |
|| Test large data sent over AT port |    Pass |
|Connectivity|Network connection|  Pass |
||SMS over IMS|  Pass |
||Voice call|  Blocking as HW not supported |
||Network switching|  Pass |
|Sleep & wakeup|Enter to sleep and Wakeup over LTE. Get current consumption|  Pass |
||Enter to sleep and Wakeup over SMS. Get current consumption|  Pass |
||Enter to sleep and Wakeup over GPIO. Get current consumption|  Pass |
||Enter to sleep and Wakeup over Power key. Get current consumption|  Pass |
|Software Update|Full OTA flow testing from Precondition check, Download, Install, rollback (if any).|  Pass |
||OTA testing for both 2K and 4K image|  Partial(4K Only) |
|Audio|Check loadable audio driver and its functionality|  Not implemented yet (plan to implement on V1.2.11) |
|GNSS|Enable GNSS|  Pass |
||Disable GNSS|  Pass |
||Check GNSS fix position timing/performance|  Pass |
|Basic feature application|MQTT|  Pass |
||HTTP|  Pass |
||TCP|  Pass |
||Get modem info: ICCID, IMEI, IMSI…|  Pass |
|Security|Secure boot|  Pass |


## Performance Test

| Test Case | Result |
|---|---|
| Ethernet,rndis,rmnet_data to LTE  | NA |
| Local Ethernet DL/UL Speed  | 727/343 Mbps |

## Boot Up Time

| Check Point | Timing (seconds) |
|---|---|
| AT_READY  |  ~20.58 |



## Current Consumption

| Power Mode | AQ20 Linux 3 - Cavli Module in EVK @5VDC (mA) |
|---|---|
| Normal mode  | ~54.54 |
| Standby Mode: USB disable, GNSS disable, Cellular network **ON**, NAD is **ON** (CS/PS), SoC is LPM mode  | NA |
| Suspend mode: USB disable, GNSS disable, Cellular network **OFF**, NAD is **LPM** (no CS/PS), SoC is LPM mode  | NA |
| Shutdown Mode: USB disable, GNSS disable, Cellular network **OFF**, both NAD and Soc in **shutdown** mode  | NA |

