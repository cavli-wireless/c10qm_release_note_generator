<!--
known_issues.md — Section 5.

One bullet per issue. Worth including: open defects, anything in the document
that is inferred rather than verified, and anything deliberately out of scope.

The bullet below is a verified observation from the repo, not a guess: BOOT
(boot_images), BTFM (btfm_proc) and CNSS (cnss_proc) were last modified by
6d29dedb4 on 2024-04-10, the initial LE.UM.2.3.6-55700-9x07 import. Keep it if
that is expected for this product; delete it if a newer Qualcomm baseline was
supposed to land.
-->

- ``AT+CDAI`` command is not working on AQ20
- OTA for AB partition is not available
- ``AT+CMUX`` are not working (kernel not supported)
- ``AT+CLSWB=2`` rebooting device
- ``AT+WS46=12`` doesn't switch network RAT
- ``FTP`` command with large message causing hang
- ``AT+COPS=?`` crash modules
- ``cavCalUpSpeedSet``, ``cavCalDlSpeedSet``, ``cavCalUpSpeedGet``, ``cavCalDlSpeedGet``, ``cavCLATENCYGet`` return ERROR
- ``cavCADCREADGet``, `cavGpioSet` failed due to hardware not support
