ROB RUN HANG WATCHER

WHAT IT DOES

When a server move sends you to a battle server that isn't answering, the game sits on
"...waiting for status information" for 60 seconds and then kicks you back. This tool spots that
about 2 seconds in, plays a warning sound and shows a notification, so you can relaunch right away
instead of waiting.

WHAT IT DOESN'T DO

It does not fix the bug. Only Kefir's servers choose which battle server you get, and nothing outside
the game can make them choose again. This only stops you losing a minute each time it happens.

BEFORE YOU START

Extract the zip to a normal folder first. It won't work from inside the zip.
If Windows warns you about it: right-click the zip, choose Properties, tick Unblock, click OK, then
extract it again.
The whole tool is RobRunHangWatcher.ps1. It's plain text, so you can read it in Notepad before running it.

HOW TO USE IT

1. Double-click Start.bat. A window opens, says it's running, then minimizes itself after 3 seconds.
   Leave it running while you play. If something goes wrong, the error stays on screen.
2. To hear the warning once: open a terminal in this folder and run Start.bat -TestAlert
3. When you hear the warning, relaunch the game, or wait for the kick and try again.
4. To stop it, open its window and press Ctrl+C.

Optional and experimental: Start.bat -AutoRestart
After the first failed connect attempt (5 to 10 seconds in) it asks the game window to close, the
same as clicking X, then starts the game through Steam. You still press Play yourself. It restarts
at most 5 times per run, at most once every 2 minutes, and never force-kills the game.

HOW IT WORKS AND WHY IT'S SAFE

It reads Player.log, the plain text log the game writes to
%USERPROFILE%\AppData\LocalLow\Kefir\ROB RUN\.

It does not:
- open the game's process or read its memory
- change any game file
- send, block or change any network traffic
- press keys or click for you

It only touches the game in -AutoRestart mode, and only with a normal window close request.

The moves.csv file it writes lists the time, server, IP, port, ping and result of each move. It
contains no account details or tokens.

No third-party tool can be guaranteed safe. Kefir's published terms and Easy Anti-Cheat's rules were
not available to check, so use it at your own risk.
