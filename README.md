# ROB RUN Hang Watcher

An unofficial community tool for ROB RUN on Windows. Not affiliated with or endorsed by Kefir.

Server moves in ROB RUN can sit on **"...waiting for status information"** for 60 seconds and then kick you back. This tool notices about 2 seconds in, so you can relaunch or get ready to retry instead of staring at the screen.

**It does not fix the bug.** Kefir's servers choose which battle server you get, and nothing outside the game can make them choose again. The tool only tells you sooner. The bug itself is written up in [bug-report/FINDINGS.md](bug-report/FINDINGS.md).

## Download and run

1. Download `ROB-RUN-Hang-Watcher.zip` from [Releases](../../releases/latest).
2. If Windows warns you about it, right-click the zip, choose Properties, tick Unblock, and click OK.
3. Extract it to a normal folder. It won't work from inside the zip.
4. Double-click `Start.bat`. A window opens, says it's running, and minimizes itself after 3 seconds. Leave it running while you play.

To hear the warning once, open a terminal in that folder and run `Start.bat -TestAlert`. To stop the watcher, open its window and press Ctrl+C.

Requires Windows and the PowerShell 5.1 that comes with it. Nothing to install.

## What it touches

It reads `Player.log`, the plain text log the game writes to `%USERPROFILE%\AppData\LocalLow\Kefir\ROB RUN\`.

It does **not**:

- open the game's process or read its memory
- change any game file
- send, block or change any network traffic
- press keys or click for you

It writes one file, `moves.csv`, next to the script. It lists the time, server, IP, port, ping and result of each move, with no account details or tokens. It stays on your PC.

### Optional, experimental: `Start.bat -AutoRestart`

After the first failed connect attempt, this asks the game window to close (the same as clicking X) and starts the game through Steam. You still press Play. It restarts at most 5 times per run, at most once every 2 minutes, and never force-kills the game. This mode has not yet been verified against the real game.

## Review it yourself

All of the logic is in one readable script: [watcher/RobRunHangWatcher.ps1](watcher/RobRunHangWatcher.ps1). `Start.bat` only launches it. It uses `-ExecutionPolicy Bypass` for that one launch because Windows blocks unsigned scripts by default, and it doesn't change your system's settings.

## How it was tested

Replaying 51 real moves from one player's logs (27 good, 24 hangs), it flagged every hang and raised no false alarms. Healthy connects took at most 0.106 s and failed attempts at least 5.09 s, so the 2-second threshold has a wide margin.

## Use at your own risk

No third-party tool can be guaranteed safe to use with a game protected by Easy Anti-Cheat, and Kefir's rules may change. This tool stays outside the game by design, but that is not a promise from Kefir or from Easy Anti-Cheat.

## License

[MIT](LICENSE)
