# ROB RUN Connection Patch

> **UNOFFICIAL. EXPERIMENTAL. NOT APPROVED BY KEFIR OR EASY ANTI-CHEAT.**
>
> **THIS COULD GET YOU BANNED. ACCOUNT SAFETY IS UNKNOWN. USE AT YOUR OWN RISK.**
>
> May fail or cause disconnects. Requires administrator access and changes network routing.

Attempts to recover stalled server joins without restarting ROB RUN. Limited live testing; not a proven universal fix.

## How to run

1. [Download **ROB-RUN-Connection-Patch.zip**](https://github.com/tayvin21/robrun-connection-patch/releases/latest). Windows 10/11 **x64** only.
2. **Extract all files.** Start ROB RUN normally through Steam.
3. Double-click **START.cmd**, read the warning, choose **R** (local logs) or **N** (no logs), and approve the administrator prompt.

By choosing R or N, you acknowledge this is unofficial, could get you banned, and may fail or disconnect you. No safety, reliability or anti-cheat compatibility is promised. You choose to use it at your own risk. Nothing here excludes rights that cannot legally be excluded.

Leave the window open: **ARMED / TESTING / CONNECTED**. It rearms after you leave the location. Press **Enter** to request a safe stop, then leave any relayed location normally. Closing the window mid-session can disconnect you. No Python installation needed. Do not disable antivirus or EAC to run it.

**CONTROLS.cmd:** status, safe stop, helper restart, automatic rearm on/off, emergency stop. **UNINSTALL.cmd:** stop and remove this copy. Your game and shared drivers are kept. No Windows autostart or automatic game restart is installed.

## What it does

Reads the game's log. On a stalled battle join, creates a temporary local relay, forwards requests unchanged first, then proposes fresh ENet session identifiers and updates their checksum. It does not edit game files or memory, restart the game, or upload anything. Normal server authentication still occurs. It uses a server-IP route, so other traffic to that same IP can be affected. IPv6 and fragmented packets are unsupported.

**Logs:** local only, ON by default, capped at **256 KiB**. Choose **N** to disable new logging; remove the logs folder after stopping to erase old logs. No raw game logs, packets, IPs, account IDs or tokens. **EXPORT-LOGS.cmd** creates one text file, at most **128 KiB**. Review it before sharing. Nothing uploads automatically.

**Think this might be a virus?** Inspect this GitHub source yourself, or ask an AI/security reviewer to inspect it. An AI review or clean scan is **not a safety guarantee**.

**AI-assisted:** Developed with AI assistance; may contain mistakes.
