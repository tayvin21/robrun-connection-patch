# ROB RUN: why server moves hang on "...waiting for status information"

Observed on PC, US region, build 26509119, on 2026-11-08. This is one player's data: 48 server moves across 4 play sessions. Server addresses are deliberately left out. Battle server names are enough for the developers to find them.

## What happens

When the game moves you (changing area, going to the hub, leaving prison after dying), the server picks a battle server and the game connects to it. Sometimes that battle server never answers. The machine still responds to ping, but the game connection gets no reply.

**23 of the 48 moves failed this way, and the failures split by server number:**

| Battle servers | Connected |
|---|---|
| `gcore-0` to `gcore-31` | 22 of 23 |
| `gcore-32` and up | 3 of 25 |

- Every trip through the hub failed (6 of 6), including one on low-numbered `gcore-9`.
- `battle-gcore-69` was assigned 4 times and failed every time.
- It doesn't look like the player's connection or a stuck client. Retrying without closing the game worked 11 of 20 times, and working servers connected right after failures.

It looks like a group of battle servers can't be reached on the game port but is still being given players. Why they stop answering isn't visible from the client.

The full list is in [failed-moves-utc.txt](failed-moves-utc.txt), and one hang is shown in [log-excerpt-one-hang.txt](log-excerpt-one-hang.txt).

## Why it takes 60 seconds

1. The game keeps retrying the same server, about 8 times in a row.
2. Each attempt lasts ping x 127 ms (54 ms ping = 6.9 s). The 5 s limit in ENet is only checked when a resend timer fires.
3. Nothing in the log shows the game telling the server it can't reach that battle server.
4. The only way out is a 60 second timeout on the server side, which sends you back to the realm screen.

`Player.log` stack traces show this path: `Network.ConnectUpdater:Update()` starting `<Connect>d__15`, again and again for the same host.

## Suggested fix in the game

1. Give up on a connection attempt after about 2.5 seconds. A healthy connection took at most 0.106 s in these logs.
2. After 2 failed attempts on the same server, stop retrying and tell the server it can't be reached, so it can assign a different one.
3. When the server moves you elsewhere, stop the old connection attempt.
4. If logging in to the region server times out, try again instead of failing.

## Suggested fix on the servers

1. Check battle servers `gcore-32` and up first.
2. Only assign battle servers that recently passed a check on the game connection itself. A ping check won't catch these.
3. After a failed move, don't send the player back to the server that just failed.
4. If several players in a row can't reach a server, stop sending new players there and flag it.

With these changes a dead server would cost about 5 seconds and a new assignment, instead of 60 seconds and starting over.

## Code example

[connect-fix.cs](connect-fix.cs) shows the shape of these changes. It was written without access to Kefir's source and has not been compiled or run, so treat it as a sketch for their developers. Nothing is handed to a battle server until the player has connected, so the fix should not affect cars and gear moving with the player, but only Kefir can confirm that.
