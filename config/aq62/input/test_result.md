<!--
test_result.md — Section 4 "Test Result".

Text before the first `##` becomes the section intro. Then one `##` heading per
table, each followed by a Markdown table. Headings are numbered 4.1, 4.2, ...

Do NOT paste results you have not seen. If testing has not run, say so in the
intro and leave the Result column as REPLACE_ME. A visible placeholder is
honest; a fabricated one is not, and nobody downstream can tell the difference.
-->

These results run on Cavli AQ62 EVK and required setup.

## Functional Test

|Function Area | Test Case | Result |
|---|---|---|
|Basic system functionality | ADB shell, reboot and bootloader | Pass |
|| USB enumeration | Pass |
|| Fastboot loading, reboot and continue | Pass|
|| AT Port functionality | Pass |
|Connectivity | Network connection | Pass |
|Ethernet | USXGMII link with AQR113C | Pass |
|Sleep & wakeup | UART clock off/on with `uart_at_clk` | Pass |
|RF | FTM RX/TX AGC | Pass |

## Performance Test

| Test Case | Result |
|---|---|
| Ethernet (USXGMII) UL/DL Speed | 1.5 Gbps/ 4.69 Gbps |
| 5G Throughput (from APSS) | 1.5 Gbps  |
| 5G Throughput (IPA) |  2.0 Gbps  |

## Boot Up Time

| Check Point | Timing (seconds) |
|---|---|
| System ready | 22 secs|
