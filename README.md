# ROB RUN Connection Patch

> **UNOFFICIAL. EXPERIMENTAL. NOT APPROVED BY KEFIR OR EASY ANTI-CHEAT.**
>
> **THIS COULD GET YOU BANNED. ACCOUNT SAFETY IS UNKNOWN. USE AT YOUR OWN RISK.**
>
> May fail or cause disconnects. Requires administrator access and changes network routing.

Attempts to recover stalled server joins without restarting ROB RUN.

**Security notice:** Defender flagged the withdrawn v0.2.0 ZIP as `Trojan:Script/Wacatac.B!ml`. A false positive has not been confirmed. Do not override antivirus protection; a clean scan is not a safety guarantee.

**Recommended version: [v0.3.0](https://github.com/tayvin21/robrun-connection-patch/releases/tag/v0.3.0).** Game build 26535791 (Nov 9, 2026) broke v0.2.4 and older: they no longer recognise a stalled join and do nothing. Use v0.2.5 or newer. See [CHANGELOG.md](CHANGELOG.md) for every version.

## How to run

1. [Download the ZIP](https://github.com/tayvin21/robrun-connection-patch/releases/download/v0.3.0/ROB-RUN-Connection-Patch.zip). Requires Windows 10/11 **x64**. All dependencies are included.
2. Right-click the ZIP and select **Extract All**.
3. With ROB RUN open, run **START.cmd**. Read the warning, choose **R** (logs on) or **N** (logs off), and approve administrator access. **No game restart required.**

By choosing R or N, you acknowledge this is unofficial, could get you banned, and may fail or disconnect you. No safety, reliability or anti-cheat compatibility is promised. You choose to use it at your own risk. Nothing here excludes rights that cannot legally be excluded.

## The live view

The helper window is an animated display of what the game is doing, so you can see exactly what is happening:

- how many servers the game is **connected to** and **connecting to** (account, region and battle), each with its address and ping;
- every connection attempt on the selected server as a timing bar, with the patch's actions (repair started, edited proposal sent, server replied, connected through the relay) marked on it;
- a history of recent joins: connected directly, repaired by the patch, did not connect, and whether the server ended it or kicked you.

Keys: **1 2 3** pick a server, **ENTER** or **S** safe stop. Leave any relayed location normally before stopping. Closing the window mid-session can disconnect you. Status always has words and symbols, never colour alone.

It uses plain ASCII symbols by default and richer symbols in Windows Terminal. To force either, put `{"unicode": true}` or `{"unicode": false}` in `settings.json` next to `patch.py`.

**Try it without the game:** run **DEMO.cmd**. It replays a scripted session (a clean join, a server-side kick, a stall the patch could not see, and two stalls it repaired). No game, no administrator rights, no network changes.

## Updates

START checks GitHub for a newer release and tells you in the launcher and at the top of the live view. To install it, choose **V** at the START prompt (or option 8 in the Controls menu).

- **What is sent:** one anonymous request to `api.github.com` asking for this project's release list, at most once every six hours, from the un-elevated launcher (not from the administrator helper). GitHub sees your IP address, as with any web request. Nothing else is sent: no identifiers, no usage data.
- **Turn it off:** Controls option 9, or `{"check_updates": false}` in `settings.json`.
- **How an update installs:** the ZIP is downloaded from this repository's release page, checked against the SHA-256 published with that release, unpacked into a **new folder next to your current copy**, and its own file manifest is verified again. Your running copy is never modified, and your settings are carried over. Then stop the old window and run START in the new folder; delete the old folder whenever you like.
- **What this does not protect against:** the SHA-256 comes from the same GitHub project as the download, so it catches corruption and tampering in transit, not a compromised project account. Releases are not code-signed.

## Settings

Optional `settings.json` next to `patch.py` (Controls writes the first two for you):

| Key | Default | Effect |
|--|--|--|
| `auto_rearm` | `true` | Rearm after leaving a repaired location |
| `check_updates` | `true` | Ask GitHub for new releases at start |
| `unicode` | auto | Force the richer symbol set on or off |

Choose **O** in START for status, helper restart, automatic rearming, emergency stop and log export. **UNINSTALL.cmd** removes the patch; it keeps your game and shared drivers. Technical files are in **app/**. No Windows autostart or automatic game restart is installed.

## What it does

Reads the game log and temporarily relays stalled battle connections. After forwarding unchanged requests, it proposes fresh ENet session identifiers and updates their checksum. Server authentication remains in place. No game-file or memory edits. The server-IP route may affect other traffic to that IP. IPv6 and fragmented packets are unsupported.

**Diagnostics:** local only, on by default, capped at **256 KiB**. **N** disables new logging. Delete **app/logs/** after stopping to erase existing logs. No raw game logs, packets, IPs, account IDs or tokens. **START > O > 7** exports a text file of up to **128 KiB** for manual sharing. Nothing uploads automatically.

**Source review:** inspect the code yourself or use an AI/security reviewer. Neither an AI review nor an antivirus scan guarantees safety.

The source ZIP downloads the runnable package on first launch and checks its pinned checksum. Internet access is required for that preparation.

**AI-assisted:** Developed with AI assistance; may contain mistakes.
