# roblox-stats

Pull every analytics signal Roblox actually exposes for **all** of an account's
games — yours and every community (group) you develop in — in one command.
Zero dependencies (Python stdlib only), public-data by default, optional cookie
for private games.

```
$ python3 roblox_stats.py yourname           # example output

=== yourname (userId 123456)  [PUBLIC-ONLY] ===

MAU floor: best game crossed >= 10K+ MAU  (highest crown: Adurite Crown of O's)
  crowns owned: Gold (100+), Adurite (10K+)

P PLAYING        VISITS      FAVS LIKE%  GAME / OWNER
------------------------------------------------------------------------------
        0        88,604       329  70.1  Ragdoll Land            Studio A [Owner]
       12        18,678       218  78.8  Some Obby               Studio B [Developer]
        0           298         2  85.7  Test Game               (you)
------------------------------------------------------------------------------
       12       107,580   TOTAL  (3 games, 0 private 🔒)
```

## The headline feature: an MAU floor, derived from inventory

Roblox **does not expose Monthly Active Users (MAU) through any API** — it's
locked inside the Creator Hub dashboard. But Roblox awards an escalating series
of developer hats, the **["Crown of O's"](https://roblox.fandom.com/wiki/Crown_of_O's_(series))**,
for crossing MAU milestones — and *inventory ownership is public and checkable*.

So this tool checks which crowns an account owns and reports the **MAU floor**:

| Crown | MAU milestone |
|---|---|
| Gold | 100+ |
| Bombastic | 1K+ |
| Adurite | 10K+ |
| Sparkle Time | 100K+ |
| Black Iron | 1M+ |

Owning the Adurite crown proves a game hit **10,000+ MAU** — a real product
metric you otherwise can't get from the API. As far as I know, no other Roblox
stats tool does this.

## What it pulls

| Signal | Source | Needs cookie? |
|---|---|---|
| Current players (CCU), total visits, favorites, like % | public games API | no |
| Created / last-updated dates | public games API | no |
| Every game you own + games in every group you're in | public enumeration | no |
| MAU floor (Crown of O's) | public inventory | no |
| **Private / unpublished group games** | develop API | **yes** |
| Arbitrary collab games on other accounts (`--extra`) | place→universe resolve | no |

**Not available from any Roblox API** (Creator Hub dashboard only, no endpoint
exists): exact MAU, playtime, retention, DAU, demographics. This tool pulls
everything that *is* reachable.

## Usage

```bash
python3 roblox_stats.py <username>            # by username
python3 roblox_stats.py --id <userId>         # by user id
python3 roblox_stats.py <username> --csv out.csv
python3 roblox_stats.py <username> --mine-only        # skip groups
python3 roblox_stats.py <username> --extra https://www.roblox.com/games/123/Name
python3 roblox_stats.py <username> --no-cookie        # force public-only
```

No install needed — Python 3.8+ and the standard library. Built-in 429 backoff.

## Cookie (optional, for private games)

Copy `.cookie.example` to `.cookie` and paste your `.ROBLOSECURITY` value. The
file is read locally, never printed, and is gitignored. With it, the tool also
lists private/unpublished games in groups where you have developer access.

> ⚠️ **Your `.ROBLOSECURITY` cookie is full account access and bypasses 2FA.**
> Never share it, never paste it anywhere online, never commit it. If it leaks,
> log out of Roblox to invalidate it. You don't need it for the public stats.

## Legitimate use / Terms of Service

This is a **read-only, personal-use** tool for inspecting your own account's
public data. Reading Roblox's public web endpoints is widely done (Rolimon's,
Ro-Tracker, etc.), but note that **automating requests with a `.ROBLOSECURITY`
cookie is against [Roblox's Terms of Use](https://en.help.roblox.com/hc/en-us/articles/115004647846).**
Use the cookie mode only on your own account and at your own risk. Prefer
public-only mode (the default) whenever it's enough.

## License

MIT — see [LICENSE](LICENSE).
