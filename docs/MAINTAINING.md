# Maintaining the ROB RUN Connection Patch

For whoever picks this up next (including a future AI session). The README is for users; this is how it works, what
breaks it, and how to ship a fix. Everything here was verified in practice on 2026-11-09 unless marked otherwise.

## What it does, in one paragraph

Some ROB RUN battle joins stall: the game sends its ENet connect request to the battle server and gets no answer, then
retries forever. The helper reads the game's `Player.log`, notices a battle join that has not connected after about
two seconds, adds a temporary route for that server through a Wintun adapter, and relays the game's UDP from a fresh
source port. After forwarding three unchanged requests it sends one edited connect proposal (fresh session ids, CRC
fixed). If the server answers, the game's next attempt connects through the relay. The route is removed when the
location ends. No game files or memory are touched.

## Files

| File | Role |
|--|--|
| `patch.py` | Entry point, relay and watcher glue, `inspect_connect` (the 53-byte ENet connect packet), control flow |
| `transport.py` | Wintun adapter, UDP relay, and `Watcher`, which turns `Player.log` lines into a join state machine (the regexes live here) |
| `tracking.py` | Session state for the live view: parses the same log lines plus the patch's own events. Allowlisted fields only; tokens and ids are never parsed |
| `console.py` | The ANSI live view (rendering is pure and unit-tested; `Live` redraws about 8 times a second on the alternate screen) |
| `demo.py` | Scripted session behind `DEMO.cmd` |
| `diagnostics.py` | Bounded local log (`logs/diagnostics.jsonl`) and its export |
| `Launch.ps1`, `Controls.ps1`, `START.cmd`, `UNINSTALL.cmd`, `DEMO.cmd` | Launcher, control menu, entry points |
| `Update.ps1` | Update check and installer (PowerShell, un-elevated) |
| `build_release.py` | Builds the release ZIP from pinned Python and Wintun archives |
| `tools/publish_release.py` | Test, build, Defender scan, tag and publish. `tools/Bootstrap.ps1` is the source-tree launcher, pinned to a release by that tool |
| `VERSION`, `CHANGELOG.md` | The only version source and the release notes |

Networking for updates runs in PowerShell because the bundled Python runtime is deliberately stripped (no `ssl`, no
`idna` codec). Do not add network code to the Python side.

## When the game updates (the thing that broke on 2026-11-09)

The patch depends on the exact text of a few game log lines and on the ENet connect packet layout. A game update can
change either and the patch will then silently do nothing.

What happened: build 26535791 added `isProxyPreferred=False` to the battle address line, so the pattern in
`Watcher.read_line` (`GetAddress completed ... dnsAddresses=N addresses=IP`) stopped matching. The helper never learned
the server name, never started a repair, and joins stalled exactly as before. The fix was one regex (v0.2.5).

**After any Steam update to the game, check this:**

1. Join a battle and read `Player.log` (`%USERPROFILE%\AppData\LocalLow\Kefir\ROB RUN\Player.log`). The lines the code
   needs, with their current shape:
   - `NetworkStep - Changed on "InBattle"` (and `"InRealmNotInBattle"` when it ends)
   - `ConnectUpdater.GetAddress completed id=battle host=prod-game-...-battle-gcore-NN... dnsAddresses=1 isProxyPreferred=False addresses=A.B.C.D`
   - `ConnectUpdater.PeerConnect started id=battle address=A.B.C.D:PORT rtt=N attempts=N`
   - `ConnectUpdater.PeerConnect complete id=battle ...`, then `ConnectUpdater.Connect completed id=battle`
   - On a stall: `PeerConnect attempt failed`, `PeerConnect failed`, `Connect failed id=battle reason=connect_failed`, repeating
   - Each message is preceded by a stamp line `[YYYY-MM-DD HH:MM:SS.mmm] [tick]`, which `tracking.py` uses for timing
2. **Symptom of a broken log pattern:** a join that keeps failing with repeated `PeerConnect failed` lines, while
   `diagnostics.jsonl` shows no `trial` event at all.
3. **Symptom of a changed packet layout:** `trial` and `baseline` events appear, but there is never a `fresh_proposal`
   or the server never answers (`reply` missing). Inspect `inspect_connect` in `patch.py`.
4. Fix in `transport.py` (and `tracking.py`, which parses the same lines), add a test that uses the real new line
   (see `test_build_26535791_address_line_still_names_the_server`), bump `VERSION`, add a `CHANGELOG.md` section, ship.

To see what else a game update changed, dump the new `GameAssembly.dll` and `global-metadata.dat` with Il2CppDumper
and diff the `Network.dll` types against the previous dump. On build 26535791 the retry loops (`ConnectInternal`,
`AttemptWhile`, `StartHost`, `GetAddresses`) were unchanged in size; `ConnectUpdater.Connect` grew (it now remembers
direct connections and marks a host unstable if a direct connection drops quickly, preferring the proxy path), and
players in Russia now default to the proxy path. Read game files statically; never touch the running process (Easy
Anti-Cheat).

## Evidence so far (be careful what you claim)

Build 26535791, 2026-11-09, one player: v0.2.5 and v0.3.x repaired 5 of 5 stalled joins on four different servers,
each within about 5 seconds of the join starting (the patch waits 2 seconds before acting). Before the fix the same
stall retried 11 times over a minute and failed. This is a small sample from one machine. It is not proof of cause for
every report, and it says nothing about the separate problem below.

**Not fixed and not fixable here:** the server sometimes kicks a player right after a clean connect
(`Successfully joined room`, then `DisconnectedNetworkPeerPacket` and `NotifyDisconnected UserKicked`). This happens
with no stall and with no patch involved; it is server-side. A "fall under the map, then get kicked" report is this,
not the connect stall.

## Testing

```
python -W ignore -m unittest discover -s tests
```

40 tests, about 7 seconds, no game needed. They cover the packet checks, the join state machine, the tracker (including
that tokens never appear in state), console rendering at several sizes in both symbol sets, and the updater against
fake GitHub data (wrong or missing SHA-256, a zip that escapes its folder, version mismatch, foreign download URL,
existing target folder). The updater tests need Windows PowerShell. The Wintun relay itself can only be tested with the
real game, so live behaviour is checked by reading `app/logs/diagnostics.jsonl` and `Player.log` together.

## Releasing

```
python tools/publish_release.py                 dry run: tests, clean build from HEAD, Defender scan, shows the notes
python tools/publish_release.py --publish --title "Short title"
```

It refuses a dirty tree or a non-main branch, refuses a tag that already exists, builds from `git archive HEAD` (so
only committed files ship), requires a clean Defender scan, pins `tools/Bootstrap.ps1`, pushes `main`, creates the
release as GitHub's Latest (add `--prerelease` to avoid that), and fails loudly if the uploaded digest differs from the
local one. Notes come from the matching `## vX.Y.Z` section of `CHANGELOG.md`, so write that first. A release must
publish its SHA-256 (the tool puts it in the notes); the updater refuses releases that do not.

## How updates work for users

`Launch.ps1` runs `Update.ps1 -Mode Check` before elevating. It asks `api.github.com` for the release list (cached six
hours in `app/update-check.json`; a launch within a second or so of a new release can cache the old answer, and `V`
always forces a fresh check), and passes the new version to the helper so the live view shows an "UPDATE" line.
Choosing `V` runs `Update.ps1 -Mode Install`: it picks the newest `vX.Y.Z` release with the right asset, requires its
SHA-256, downloads from this repository's release URL only, verifies the digest, unpacks into a new sibling folder
(path-escape and size limits enforced), checks that the package `VERSION` equals the tag and that every file matches
the package's own `SHA256SUMS.txt`, copies `settings.json`, and never touches the running copy. Verified end to end
against the real GitHub on 2026-11-09 (v0.2.5 copy to v0.3.0, and a real v0.3.0 to v0.3.1 upgrade through the launcher).

Limits, stated in the README too: the digest comes from the same GitHub project as the download, so a compromised
project account is not detected, and releases are not code-signed.

## Hard rules for changes

- No telemetry. The only network request is the optional update check, and it is documented and switchable.
- The status view must never read or show account tokens or player ids. They appear in the game log (confirmed during
  an owner-authorised audit); `tracking.py` parses allowlisted fields only and a test enforces it. Warn people not to
  paste a raw `Player.log` publicly.
- Do not move any recovery logic that touches routes, adapters or the Wintun session into the un-elevated side, and do
  not add network code to the elevated Python process.
- Keep the AI-assistance, unofficial, ban-risk and dependency-licence disclosures in the README.
- Do not restart or attach to the game process; read files and logs only.
- Test fixtures and docs use fake tokens and ids only. Real values from `Player.log` (authorization token, player id, room id) must never be copied into the repository; a secret scanner will flag them and git history keeps them.
