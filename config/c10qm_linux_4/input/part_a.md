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

An empty file is valid: Part A then has just the change table and no prose.

The AT command interface (apps_proc/cavli) is the subsystem customers care
about most — the CQS290 reference gives its equivalent a dedicated numbered
section. Recent work there worth writing up: +CCOPS fix, CME/CMS error
reporting on AT commands (MCH-269), MBN upload command (MCH-264), URC port
command and "urc enable on all channel by default", AT+CLPORT, DFOTA exec fix.
Check each actually ships on AQ20 — that repo is shared with cqm220/c10qm/c20qm.
-->

## AT Command & SDK API
commits:

- New ``AT+CMEE=<cme_mode>`` command to select CME error mode for reporting. e.g: ``AT+CMEE=1`` to report ``+CME ERROR: 102``. 
- New ``AT+CURCCFG="urcport",<port>`` command to configure URC port. e.g: ``AT+CURCCFG="urcport","mux2"``, supported port: ``uart``,``usb1``,``usb2``,``mux1``,``mux2``,``mux3``,``mux4``,``vat``,``all``
- New ``AT+CSTKEN``, ``AT+CSTKENV``, ``AT+CSTKTR`` command to support SIM Toolkit V2
- Improve ``ATE`` command on AT port
- Fix ``cavCCopsGet`` causing crash system when response data is too big.
- Fix AT command timed out within 200ms due to index out of bound declared array


## Audio
commits:

- Improve **NAU8810** codec, support TDM and kctrl for setting PGA Volume, ALC Enable Switch, ADC Oversampling Rate, etc.

## Memory
commits:

- Support new NAND variant **512MB** with **2K** Page Size, support both non-AB and AB OTA for new variant.
