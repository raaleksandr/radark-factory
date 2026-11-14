"""Fake `ho`: answers from a JSON file named by FAKE_HO_DATA.

Read keys: "inbox:<team>", "show:<id>", "list:<team>". A value {"exit": N, "error": {...}} fails with code N;
a top-level key named after a write command (e.g. "new") with such a value makes that command fail.
Write commands change the file: `new` adds "show:<id>", a recipient inbox item and a "list:<team>" item;
`respond` / `decline` add the recipient's event and, with auto-close, a sender `close` event (set
"no_auto_close_on_decline": true to keep a declined handover open); `close` closes; `sync` does nothing.
`teams` lists the teams of hub.json in HO_HUB.
Timing keys (harness-survive-sleep): "_delay": {cmd: seconds} waits before answering; "_hang_once": [cmd] makes the
next such call hang (60 s) and "_die_once": [cmd] makes it exit 1 with no output; either is used up by that call.
`--version` (ho-contract-check D5) answers from "_version": absent -> version 0.2.0, contract 1, features ["hub-lock"]
(the hub lock, parallel-sessions D6; give a "_version" without "features" for an ho without it); {"exit": N} -> exit N
with nothing on stdout (an ho too old for the flag); another dict -> printed as the JSON answer; a string -> printed
as is (not JSON).
Every call (and a stdin body) is appended to FAKE_HO_DATA + ".calls"."""
import datetime as dt
import json
import os
import sys
import time

args = [a for a in sys.argv[1:] if a != "--json"]
path = os.environ["FAKE_HO_DATA"]
team = os.environ.get("HO_TEAM")
stdin = sys.stdin.buffer.read().decode("utf-8") if "--body" in args and args[args.index("--body") + 1] == "-" else None
with open(path + ".calls", "a", encoding="utf-8") as fh:
    call = {"args": args, "team": team, "hub": os.environ.get("HO_HUB")}
    if stdin is not None:
        call["stdin"] = stdin
    fh.write(json.dumps(call) + "\n")
with open(path, encoding="utf-8") as fh:
    data = json.load(fh)

if args and args[0] == "--version":
    answer = data.get("_version", {"schema_version": 1, "version": "0.2.0", "contract": 1,
                                       "features": ["hub-lock"]})
    if isinstance(answer, dict) and "exit" in answer:
        sys.exit(answer["exit"])
    print(answer if isinstance(answer, str) else json.dumps(answer))
    sys.exit(0)


def use_once(key):
    if args[0] not in data.get(key, []):
        return False
    data[key].remove(args[0])
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    return True


if use_once("_hang_once"):
    time.sleep(60)
if use_once("_die_once"):
    sys.exit(1)
time.sleep(data.get("_delay", {}).get(args[0], 0))


def now():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def opt(name, many=False):
    found = [args[i + 1] for i, a in enumerate(args) if a == name and i + 1 < len(args)]
    return found if many else (found[0] if found else None)


def fail(value):
    print(json.dumps({"schema_version": 1, "error": value["error"]}))
    sys.exit(value["exit"])


def save_and_print(value):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    print(json.dumps({"schema_version": 1, **value}))
    sys.exit(0)


def summary(h):
    return {k: v for k, v in h.items() if k not in ("body", "events")}


cmd = args[0]
if isinstance(data.get(cmd), dict) and "exit" in data[cmd]:
    fail(data[cmd])
if cmd == "new":
    n = data.get("_next", 1)
    data["_next"] = n + 1
    hid, at = f"HO-FAKE-{n:04d}", now()
    to = opt("--to")
    h = {"id": hid, "title": opt("--title"), "from": team, "to": [to], "expects": opt("--expects"),
         "status": "open", "tags": opt("--tag", True), "refs": opt("--ref", True),
         "auto_close": "--auto-close" in args, "created": at, "last_activity": at,
         "body": stdin if stdin is not None else (opt("-m") or ""), "events": []}
    data[f"show:{hid}"] = h
    inbox = data.setdefault(f"inbox:{to}", {"action_required": [], "to_review": []})
    inbox.setdefault("action_required", []).append({**summary(h), "my_state": "pending"})
    data.setdefault(f"list:{team}", {"items": []})["items"].append(summary(h))
    save_and_print(summary(h))
if cmd in ("respond", "decline", "close"):
    key = f"show:{args[1]}"
    if key not in data:
        fail({"exit": 2, "error": {"code": "handover_not_found", "message": "not found"}})
    h, at = data[key], now()
    h["events"].append({"at": at, "team": team, "action": cmd, "body": (opt("-m") or stdin or "") + "\n"})
    if cmd == "close" or (h.get("auto_close") and not (cmd == "decline" and data.get("no_auto_close_on_decline"))):
        if cmd != "close":
            h["events"].append({"at": at, "team": h["from"], "action": "close",
                                "body": "Auto-closed: all recipients are satisfied.\n"})
        h["status"] = "closed"
    h["last_activity"] = at
    for t in h.get("to", []):
        inbox = data.get(f"inbox:{t}", {})
        inbox["action_required"] = [i for i in inbox.get("action_required", []) if i["id"] != h["id"]]
    for item in data.get(f"list:{h['from']}", {}).get("items", []):
        if item["id"] == h["id"]:
            item.update(summary(h))
    save_and_print(summary(h))
if cmd == "sync":
    save_and_print({"committed": True, "pushed": False, "actions": []})
if cmd == "teams":
    with open(os.path.join(os.environ["HO_HUB"], "hub.json"), encoding="utf-8") as fh:
        save_and_print({"teams": json.load(fh)["teams"]})
if cmd == "inbox":
    key = f"inbox:{team}"
    default = {"team": team, "action_required": [], "to_review": [], "updates": []}
elif cmd == "show":
    key, default = f"show:{args[1]}", {"exit": 2, "error": {"code": "handover_not_found", "message": "not found"}}
elif cmd == "list":
    key, default = f"list:{args[args.index('--from') + 1]}", {"items": []}
else:
    key, default = cmd, {"exit": 1, "error": {"code": "usage", "message": f"fake ho: {cmd} unsupported"}}
value = data.get(key, default)
if "exit" in value:
    fail(value)
print(json.dumps({"schema_version": 1, **value}))
