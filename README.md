# ROB RUN Connection Patch

> **DEFENDER NOTICE:** Microsoft Defender flagged the older v0.2.0 ZIP as `Trojan:Script/Wacatac.B!ml`; that download remains withdrawn. A false positive has not been confirmed. v0.2.1 is a smaller, repackaged experimental build, not a Microsoft-approved fix. A clean scan does not guarantee safety. Do not override antivirus protection.

> **UNOFFICIAL. EXPERIMENTAL. NOT APPROVED BY KEFIR OR EASY ANTI-CHEAT.**
>
> **THIS COULD GET YOU BANNED. ACCOUNT SAFETY IS UNKNOWN. USE AT YOUR OWN RISK.**
>
> May fail or cause disconnects. Requires administrator access and changes network routing.

Attempts to recover stalled server joins without restarting ROB RUN. Limited live testing; not a proven universal fix.

## How to run

1. [Download **ROB-RUN-Connection-Patch.zip**](https://github.com/tayvin21/robrun-connection-patch/releases/download/v0.2.1/ROB-RUN-Connection-Patch.zip). Windows 10/11 **x64** only.
2. Right-click the ZIP, choose **Extract All**, then open the extracted folder. Everything is included; no Python, Tailscale or other installation needed.
3. Keep ROB RUN open. Double-click **START.cmd**, read the warning, choose **R** (local logs) or **N** (no logs), and approve the administrator prompt. **No game restart required.**

By choosing R or N, you acknowledge this is unofficial, could get you banned, and may fail or disconnect you. No safety, reliability or anti-cheat compatibility is promised. You choose to use it at your own risk. Nothing here excludes rights that cannot legally be excluded.

Leave the window open: **ARMED / TESTING / CONNECTED**. It rearms after you leave the location. Press **Enter** to request a safe stop, then leave any relayed location normally. Closing the window mid-session can disconnect you. No Python installation needed. Do not disable antivirus or EAC to run it.

The folder contains only **START.cmd**, **UNINSTALL.cmd**, and **app/**. In START, choose **S** to stop or **O** for status, helper restart, rearming, emergency stop and log export. **UNINSTALL.cmd** removes this copy. Your game and shared drivers are kept. No Windows autostart or automatic game restart is installed.

## What it does

Reads the game's log. On a stalled battle join, creates a temporary local relay, forwards requests unchanged first, then proposes fresh ENet session identifiers and updates their checksum. It does not edit game files or memory, restart the game, or upload anything. Normal server authentication still occurs. It uses a server-IP route, so other traffic to that same IP can be affected. IPv6 and fragmented packets are unsupported.

**Logs:** local only, ON by default, capped at **256 KiB**. Choose **N** to disable new logging; remove the logs folder after stopping to erase old logs. No raw game logs, packets, IPs, account IDs or tokens. **START > O > 7** creates one text file, at most **128 KiB**. Review it before sharing. Nothing uploads automatically.

**Think this might be a virus?** Inspect this GitHub source yourself, or ask an AI/security reviewer to inspect it. An AI review or clean scan is **not a safety guarantee**.

GitHub's source ZIP prepares the runnable package on first launch (internet required), verifying its pinned checksum before opening the launcher.

**AI-assisted:** Developed with AI assistance; may contain mistakes.
