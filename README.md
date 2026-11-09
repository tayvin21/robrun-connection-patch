# ROB RUN Connection Patch

> **UNOFFICIAL. EXPERIMENTAL. NOT APPROVED BY KEFIR OR EASY ANTI-CHEAT.**
>
> **THIS COULD GET YOU BANNED. ACCOUNT SAFETY IS UNKNOWN. USE AT YOUR OWN RISK.**
>
> May fail or cause disconnects. Requires administrator access and changes network routing.

Attempts to recover stalled server joins without restarting ROB RUN.

**Security notice:** Defender flagged the withdrawn v0.2.0 ZIP as `Trojan:Script/Wacatac.B!ml`. A false positive has not been confirmed. Do not override antivirus protection; a clean scan is not a safety guarantee.

**Recommended version: [v0.2.5](https://github.com/tayvin21/robrun-connection-patch/releases/tag/v0.2.5)**, the current download. **This is a post-hotfix patch: it exists because the game's Nov 9, 2026 hotfix (build 26535791) broke older versions. If you use v0.2.4 or older, upgrade: after that hotfix to build 26535791 (Nov 9, 2026) they no longer recognise a stalled join and do nothing.** v0.2.5 reads the changed game log line. Older releases are kept only so old links work. Affected-user confirmation is still pending.

## How to run

1. [Download the ZIP](https://github.com/tayvin21/robrun-connection-patch/releases/download/v0.2.5/ROB-RUN-Connection-Patch.zip). Requires Windows 10/11 **x64**. All dependencies are included.
2. Right-click the ZIP and select **Extract All**.
3. With ROB RUN open, run **START.cmd**. Read the warning, choose **R** (logs on) or **N** (logs off), and approve administrator access. **No game restart required.**

By choosing R or N, you acknowledge this is unofficial, could get you banned, and may fail or disconnect you. No safety, reliability or anti-cheat compatibility is promised. You choose to use it at your own risk. Nothing here excludes rights that cannot legally be excluded.

The window shows **ARMED / TESTING / CONNECTED**. Press **Enter**, or choose **S** in START, to request a safe stop; leave the relayed location normally. Closing the window mid-session can disconnect you.

**v0.2.5:** game build 26535791 added `isProxyPreferred=...` to the battle address log line, so earlier versions never recognised the battle server and never started a repair. This version reads the new line. In one test session on build 26535791 it repaired 2 of 2 stalled joins (on two different servers) within about 5 seconds, where the previous version did nothing and the game kept failing for over a minute. Two repairs is a small sample, and the game's separate server-side kicks after a successful join are not something this patch can fix.

**v0.2.4:** cleanup only, no intended behavior change. **v0.2.3:** removes the one-hour idle shutdown. The helper stays armed while the game is running unless you stop it or disable automatic rearming. Retry limits now show a warning. **PATCH IS STOPPED** means an open window is no longer helping. For upgrades, safely stop the old copy before running the new ZIP from a separate folder.

Choose **O** in START for status, helper restart, automatic rearming, emergency stop and log export. **UNINSTALL.cmd** removes the patch; it keeps your game and shared drivers. Technical files are in **app/**. No Windows autostart or automatic game restart is installed.

## What it does

Reads the game log and temporarily relays stalled battle connections. After forwarding unchanged requests, it proposes fresh ENet session identifiers and updates their checksum. Server authentication remains in place. No game-file or memory edits. The server-IP route may affect other traffic to that IP. IPv6 and fragmented packets are unsupported.

**Diagnostics:** local only, on by default, capped at **256 KiB**. **N** disables new logging. Delete **app/logs/** after stopping to erase existing logs. No raw game logs, packets, IPs, account IDs or tokens. **START > O > 7** exports a text file of up to **128 KiB** for manual sharing. Nothing uploads automatically.

**Source review:** inspect the code yourself or use an AI/security reviewer. Neither an AI review nor an antivirus scan guarantees safety.

The source ZIP downloads the runnable package on first launch and checks its pinned checksum. Internet access is required for that preparation.

**AI-assisted:** Developed with AI assistance; may contain mistakes.
