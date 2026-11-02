<!--
part_b.md — Part B subsections (chipcode / firmware).

Same format as part_a.md; headings are numbered 3.1, 3.2, ...

Only add sections here when an image actually moved and the reason matters.
aq62_chipcode (BOOT, TZ, AOP, CPUCP, BTFM, WLAN) is held at the ES2 pin this
release, so only the modem has prose.
-->

## AT Command (MPSS)
commits: 11f173a39, b6dd7f275, 1a96be861

- Cavli AT command layer added to the modem, enabled by the `CAVLI_SECTION` build flag.
- `ATI`, `AT+GMI`, `AT+GMM`, `AT+GMR` and `AT+GSN` now return Cavli product information.
- Firmware version update to `0.0.3`;

## RF / FTM
commits: 69c0c564e, ca657e1c7, 5a1153de6, 4c0c80163

- FTM (factory test mode) bring-up in MPSS.
- New `AT$CRXFTM` / `AT$CTXFTM` commands for RX / TX AGC measurement in FTM.
- New `AT+RFI` command.
