# Changelog

Versions follow `MAJOR.MINOR.PATCH`. The number lives in one file, `VERSION`; a release is the git tag `vX.Y.Z` with
`ROB-RUN-Connection-Patch.zip` attached and its SHA-256 published in the release notes. The patch is experimental
whatever the release flag says; v0.3.0 and later are published as the GitHub "Latest" release. The updater only installs a release that publishes a SHA-256 and whose download matches it.

## v0.3.2

Three fixes from a player's bug report (GitHub issue #1), checked against the code and covered by new tests:

- Fix: servers named like `battle-g1-gcore-7` (seen on EU hosts) were not recognised, so the patch never started a repair for those players. It now accepts those names.
- Fix: when the game lists two server addresses for one join (a proxy and the direct server) and switches between them every few seconds, the patch now covers both instead of only the first.
- Fix: a reconnect step inside a battle no longer removes the working route. It is removed only when the battle ends or a new one starts.
- Not changed: the report also suggests the game's own connection can sometimes skip the route entirely. That is one PC's observation and is not reproduced here, so it is still open.

## v0.3.1

- Fix: running `Update.ps1 -Mode Check` by hand no longer prints an empty table; only the launcher asks for the result object.
- First release delivered through the built-in updater: choose `V` at the START prompt on v0.3.0.

## v0.3.0

- **Live console view.** The helper window is now an animated ANSI display instead of scrolling text: how many servers
  the game is connected to or connecting to (account, region, battle), every connection attempt with its timing, what
  the patch did and when, and a short history of recent joins. Keys: `1` `2` `3` pick a server, `ENTER` or `S` safe stop.
  Plain ASCII symbols are used unless Windows Terminal is detected; `settings.json` `"unicode": true` or `false` forces it.
- **`DEMO.cmd`.** Replays a scripted session in the same view with no game, no administrator rights and no network changes.
- **Update checker and updater.** `START.cmd` asks GitHub once every six hours whether a newer release exists and says so
  in the launcher and in the live view. Choose `V` at the prompt (or Controls option 8) to download it. The download is
  checked against the SHA-256 published with the release, unpacked into a new folder next to the current copy, and its
  own integrity manifest is verified again. The current copy is never modified. Turn checks off with Controls option 9
  or `"check_updates": false` in `settings.json`.
- **Versioning.** Single `VERSION` file, this changelog, and `tools/publish_release.py` to build, scan, tag and publish.
- Fix: Controls "automatic rearm" no longer overwrites the other settings.
- Removed the scrolling-text display.

## v0.2.5

Post-hotfix patch. Game build 26535791 (Nov 9, 2026) added `isProxyPreferred=...` to the battle address line in the
game log, so v0.2.4 and older no longer recognised a stalled join and did nothing. This version reads the new line.
Repaired 2 of 2 stalled joins in the first test session.

## v0.2.4

Cleanup of v0.2.3 (dead code removed, a stale link fixed, lint tidied). No intended behavior change.

## v0.2.3

Removed the one-hour idle shutdown that left the launcher open but the helper stopped. Added an explicit
"PATCH IS STOPPED" notice and visible retry-budget warnings.

## v0.2.2, v0.2.1

Experimental connection patch releases. v0.2.0 was withdrawn after a Defender false-positive detection
(`Trojan:Script/Wacatac.B!ml`, unconfirmed); no security bypass was involved.
