<!--
part_a.md — Part A subsections (Linux SDK & services).

One `##` block per THEME, not per commit. Group related commits and explain
what changed and why it matters to someone integrating the SDK. The change
table above already lists every commit, so repeating it here adds nothing.

  ## Heading text
  commits: e86e6da, 5638f66      <- optional; renders as code pills by the heading

  Body. Markdown works: **bold**, `code`, - bullets, tables.

Headings are numbered automatically (2.1, 2.2, ...) — do not number them
yourself, and inserting a section never means renumbering the rest.
-->

## Ethernet
commits: 0e8162950, 572aba88a, 96cebf9cf

- Enable USXGMII in-band auto-negotiation on the **AQR113C** PHY (stmmac + Aquantia PHY driver).

## Power Management
commits: a3289037d

- New `uart_at_clk on|off` script to switch the AT UART clock for sleep.
- UART auto-suspend re-enabled in the device tree (`qcom,auto-suspend-disable` removed).
- `/sys/power/autosleep` is now set to `off` at boot.

## System
commits: c1178b87f

- Download mode is no longer enabled by default a crash reboots the device instead of entering ramdump mode.

## Build & SDK
commits: 410017c, beb8295, f011c82, 7ce009e, 7e9cf3f, 2fee377, 1dd6c8b0d

- New SDK generation flow for AQ62.
- `at-bridge`  added to the SDK packaging to forward at command from UART, USB to modem.
- Add `uart_at_clk` script to control UART clock
- Local builds now build the **perf** variant of apps and kernel.
- `set_bb_env.sh` no longer fails when the repo manifest is missing.
