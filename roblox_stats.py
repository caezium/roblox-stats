#!/usr/bin/env python3
"""
roblox_stats.py — pull analytics for every game tied to a Roblox account.

Enumerates:
  - games you own personally
  - games owned by every community (group) you belong to
  - WITH a cookie: also private / unpublished group experiences (via develop API)

For each universe, fetches the public stats Roblox exposes via API:
  current players (CCU), total visits, favorites, up/down votes, created/updated.

playtime / retention / DAU are NOT available from any Roblox API — they live
only in the Creator Hub Analytics Dashboard. This pulls everything reachable.

Cookie: optional. Put your .ROBLOSECURITY in a local file (default: ./.cookie).
It is read only from that file, never printed, never committed (.gitignore'd).
The cookie unlocks private/unpublished group games + private stats.

Usage:
  python3 roblox_stats.py <username>
  python3 roblox_stats.py --id <userId>
  python3 roblox_stats.py --id <userId> --csv out.csv
  python3 roblox_stats.py --id <userId> --no-cookie      # force public-only
  python3 roblox_stats.py --id <userId> --cookie-file path
  python3 roblox_stats.py --id <userId> --mine-only      # skip groups
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
import csv as csvmod

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 roblox-stats/2.0"
COOKIE = None  # set at runtime from --cookie-file


def _req(url, method="GET", body=None, auth=True):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"User-Agent": UA, "Accept": "application/json"}
    if data:
        headers["Content-Type"] = "application/json"
    if auth and COOKIE:
        headers["Cookie"] = f".ROBLOSECURITY={COOKIE}"
    for attempt in range(6):
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 2 ** attempt
                print(f"  …rate limited, waiting {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
            if e.code in (401, 403):
                raise PermissionError(f"{e.code} on {url}")
            raise
    raise RuntimeError(f"gave up after retries: {url}")


def resolve_user(name):
    out = _req("https://users.roblox.com/v1/usernames/users", "POST",
               {"usernames": [name], "excludeBannedUsers": False}, auth=False)
    data = out.get("data") or []
    if not data:
        raise SystemExit(f"No Roblox user found for '{name}'.")
    u = data[0]
    return u["id"], u.get("displayName") or u.get("name")


def user_info(uid):
    return _req(f"https://users.roblox.com/v1/users/{uid}", auth=False)


def whoami():
    try:
        return _req("https://users.roblox.com/v1/users/authenticated")
    except Exception:
        return None


def get_groups(uid):
    out = _req(f"https://groups.roblox.com/v2/users/{uid}/groups/roles", auth=False)
    groups = []
    for entry in out.get("data", []):
        g = entry["group"]
        role = entry.get("role", {})
        groups.append({"id": g["id"], "name": g["name"],
                       "role": role.get("name", "?"), "rank": role.get("rank", 0)})
    return groups


def _paged(url_base, key_id="id"):
    """Walk any paginated Roblox list endpoint -> list of {universeId, name}."""
    out, cursor = [], None
    while True:
        url = url_base + (f"&cursor={cursor}" if cursor else "")
        d = _req(url)
        for g in d.get("data", []):
            out.append({"universeId": g.get(key_id),
                        "name": g.get("name"),
                        "rootPlaceId": (g.get("rootPlace") or {}).get("id")})
        cursor = d.get("nextPageCursor")
        if not cursor:
            break
        time.sleep(0.3)
    return out


def user_games(uid, access):
    return _paged(f"https://games.roblox.com/v2/users/{uid}/games?accessFilter={access}&limit=50&sortOrder=Asc")


def group_games_public(gid):
    return _paged(f"https://games.roblox.com/v2/groups/{gid}/games?accessFilter=Public&limit=50&sortOrder=Asc")


def group_universes_dev(gid):
    """Full group inventory incl private/unpublished. Raises PermissionError if no dev access."""
    return _paged(f"https://develop.roblox.com/v1/groups/{gid}/universes?sortOrder=Asc&limit=50")


# Developer "Crown of O's" MAU awards — owning a tier proves a game hit that
# Monthly Active User milestone. This is the ONLY API-derivable MAU signal
# (the analytics API doesn't expose MAU). asset_id -> (label, mau).
MAU_CROWNS = [
    (5731050224, "Gold", "100+"),
    (5731051458, "Bombastic", "1K+"),
    (5731052645, "Adurite", "10K+"),
    (5731053584, "Sparkle Time", "100K+"),
    (5731054790, "Black Iron", "1M+"),
]


def mau_floor(uid):
    """Return (highest_label, highest_mau, owned_list) from Crown of O's ownership."""
    owned = []
    for aid, label, mau in MAU_CROWNS:
        try:
            r = _req(f"https://inventory.roblox.com/v1/users/{uid}/items/Asset/{aid}/is-owned")
            if r is True or str(r).lower() == "true":
                owned.append((label, mau))
        except Exception:
            pass
        time.sleep(0.2)
    if not owned:
        return None, None, []
    # tiers are listed ascending; highest owned = best floor (ignores award-bug gaps)
    label, mau = owned[-1]
    return label, mau, owned


def place_to_universe(place_id):
    out = _req(f"https://apis.roblox.com/universes/v1/places/{place_id}/universe")
    return out.get("universeId")


def resolve_extra(token):
    """Accept a game URL, place id, or universe id -> universeId. Heuristic on URL shape."""
    import re
    t = token.strip()
    m = re.search(r"/games/(\d+)", t)          # roblox.com/games/<placeId>/Name
    if m:
        return place_to_universe(int(m.group(1)))
    m = re.search(r"universeId=?(\d+)", t, re.I)
    if m:
        return int(m.group(1))
    if t.isdigit():
        # bare number: try as place first (most pasted IDs are place ids), fall back to universe
        try:
            u = place_to_universe(int(t))
            if u:
                return u
        except Exception:
            pass
        return int(t)
    return None


def fetch_stats(universe_ids):
    stats = {}
    uids = list(universe_ids)
    for i in range(0, len(uids), 50):
        ids = ",".join(str(x) for x in uids[i:i + 50])
        out = _req(f"https://games.roblox.com/v1/games?universeIds={ids}")
        for g in out.get("data", []):
            stats[g["id"]] = {
                "playing": g.get("playing", 0), "visits": g.get("visits", 0),
                "favorites": g.get("favoritedCount", 0),
                "created": (g.get("created") or "")[:10],
                "updated": (g.get("updated") or "")[:10],
            }
        time.sleep(0.4)
    for i in range(0, len(uids), 50):
        ids = ",".join(str(x) for x in uids[i:i + 50])
        try:
            out = _req(f"https://games.roblox.com/v1/games/votes?universeIds={ids}")
            for v in out.get("data", []):
                if v["id"] in stats:
                    up, dn = v.get("upVotes", 0), v.get("downVotes", 0)
                    tot = up + dn
                    stats[v["id"]]["likeRatio"] = round(100 * up / tot, 1) if tot else None
        except Exception:
            pass
        time.sleep(0.4)
    return stats


def main():
    global COOKIE
    ap = argparse.ArgumentParser()
    ap.add_argument("user", nargs="?")
    ap.add_argument("--id", type=int)
    ap.add_argument("--mine-only", action="store_true")
    ap.add_argument("--extra", nargs="+", default=[],
                    help="extra games to include: game URLs, place IDs, or universe IDs "
                         "(for collabs on accounts you don't own)")
    ap.add_argument("--no-cookie", action="store_true")
    ap.add_argument("--cookie-file", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cookie"))
    ap.add_argument("--csv")
    args = ap.parse_args()

    if not args.no_cookie and os.path.exists(args.cookie_file):
        c = open(args.cookie_file).read().strip()
        if c:
            COOKIE = c
    authed = COOKIE is not None
    if authed:
        me = whoami()
        print(f"Cookie loaded — authed as {me.get('name') if me else '??'}." if me
              else "Cookie present but auth check failed — continuing public-only.")
        if not me:
            COOKIE = None
            authed = False

    if args.id:
        uid = args.id
        info = user_info(uid)
        display = info.get("displayName") or info.get("name")
    elif args.user:
        uid, display = resolve_user(args.user)
    else:
        ap.error("provide a username or --id")

    print(f"\n=== {display} (userId {uid})  [{'AUTHED' if authed else 'PUBLIC-ONLY'}] ===\n")

    label, mau, owned = mau_floor(uid)
    if label:
        tiers = ", ".join(f"{l} ({m})" for l, m in owned)
        print(f"MAU floor: best game crossed >= {mau} MAU  "
              f"(highest crown: {label} Crown of O's)")
        print(f"  crowns owned: {tiers}\n")
    else:
        print("MAU floor: no Crown of O's awards owned (no game has hit 100+ MAU, "
              "or awards weren't granted).\n")

    # rows: list of dict(owner, game, universeId, private)
    rows = []

    print("Fetching your personal games…")
    pub_personal = {g["universeId"] for g in user_games(uid, "Public")}
    full_personal = user_games(uid, "2" if authed else "Public")
    for g in full_personal:
        rows.append({"owner": "(you)", "game": g["name"], "universeId": g["universeId"],
                     "private": g["universeId"] not in pub_personal})

    if not args.mine_only:
        groups = get_groups(uid)
        print(f"You're in {len(groups)} communities.")
        for grp in groups:
            label = f"{grp['name']} [{grp['role']}]"
            pub_list = group_games_public(grp["id"])
            pub_ids = {g["universeId"] for g in pub_list}
            full = None
            if authed:
                try:
                    full = group_universes_dev(grp["id"])  # incl private/unpublished
                except PermissionError:
                    full = None  # member-only group: no dev access
            if full is None:
                full = pub_list  # fall back to public list (has names)
            for g in full:
                rows.append({"owner": label, "game": g["name"], "universeId": g["universeId"],
                             "private": g["universeId"] not in pub_ids})
            n_priv = sum(1 for g in full if g["universeId"] not in pub_ids)
            extra = f"  (+{n_priv} private)" if n_priv else ""
            print(f"  {label}: {len(full)} games{extra}")
            time.sleep(0.2)

    if args.extra:
        have = {r["universeId"] for r in rows}
        for tok in args.extra:
            try:
                u = resolve_extra(tok)
            except Exception as e:
                print(f"  extra '{tok}': {e}", file=sys.stderr)
                continue
            if not u:
                print(f"  extra '{tok}': could not resolve", file=sys.stderr)
                continue
            if u in have:
                print(f"  extra '{tok}' -> universe {u}: already in list, skipping")
                continue
            info = _req(f"https://games.roblox.com/v1/games?universeIds={u}").get("data", [])
            name = info[0].get("name") if info else "?"
            cre = (info[0].get("creator") or {}).get("name") if info else "?"
            rows.append({"owner": f"(extra · by {cre})", "game": name, "universeId": u,
                         "private": False})
            have.add(u)
            print(f"  added extra: {name} (universe {u}, creator {cre})")

    universe_ids = [r["universeId"] for r in rows if r["universeId"]]
    print(f"\nFetching live stats for {len(universe_ids)} games…\n")
    stats = fetch_stats(universe_ids)

    merged = []
    for r in rows:
        s = stats.get(r["universeId"], {})
        merged.append({**r,
                       "playing": s.get("playing", 0), "visits": s.get("visits", 0),
                       "favorites": s.get("favorites", 0), "likeRatio": s.get("likeRatio"),
                       "created": s.get("created", ""), "updated": s.get("updated", "")})
    merged.sort(key=lambda x: x["visits"], reverse=True)

    print(f"{'P':>1} {'PLAYING':>7} {'VISITS':>13} {'FAVS':>9} {'LIKE%':>5}  GAME / OWNER")
    print("-" * 96)
    for m in merged:
        like = f"{m['likeRatio']}" if m["likeRatio"] is not None else "-"
        flag = "🔒" if m["private"] else " "
        print(f"{flag:>1} {m['playing']:>7} {m['visits']:>13,} {m['favorites']:>9,} {like:>5}  "
              f"{(m['game'] or '?')[:34]:<34}  {m['owner']}")
    print("-" * 96)
    print(f"  {sum(m['playing'] for m in merged):>7} {sum(m['visits'] for m in merged):>13,}"
          f"   TOTAL  ({len(merged)} games, {sum(1 for m in merged if m['private'])} private 🔒)\n")

    if args.csv and merged:
        with open(args.csv, "w", newline="") as f:
            w = csvmod.DictWriter(f, fieldnames=list(merged[0].keys()))
            w.writeheader()
            w.writerows(merged)
        print(f"Wrote {args.csv}")


if __name__ == "__main__":
    main()
