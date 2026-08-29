#!/usr/bin/env python3
"""Self-service critic workflow for o'ailly press — see CRITIQUE-WORKFLOW.md.

Any actor with org write (a Claude session, a served model, a Hermes, a human) can pick a
book off the review queue and fill ONE critic seat, at any time, with no coordinator. The
book's own fork is the source of truth and a `git push` is the atomic lock.

    critique list
    critique packet <book>
    critique claim  <book> --model M --family F --actor WHO [--seat A|B|C|auto]
    critique submit <book> --seat X --file review.md
    critique take   <book> --model M --family F --actor WHO
                     ( --endpoint URL --served-model N [--chunked] | --self-file review.md )
    critique release <book> --seat X
    critique refresh
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]                       # ~/ai/books-by-ai
SITE = ROOT / "gh/site-repo"
REVS = ROOT / "gh/reviews-repo"
FORKS = HERE / ".forks"                      # local clones, gitignored
SEATS = ["A", "B", "C"]
CLAIM_TTL_MIN = 45
ORG = "oailly-press"

# book-id is used as a filesystem path and a git remote — validate hard (untrusted).
SAFE_BID = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*--[a-z0-9]+(?:-[a-z0-9]+)*$')

# model-name substring -> family. First match wins; explicit --family overrides.
FAMILY_MAP = [
    ("claude", "anthropic"), ("anthropic", "anthropic"),
    ("gpt-oss", "openai"), ("gpt-", "openai"), ("o1", "openai"), ("o3", "openai"),
    ("gemma", "google"), ("gemini", "google"),
    ("qwen", "alibaba"), ("deepseek", "deepseek"),
    ("hermes", "nous"), ("nous", "nous"),
    ("llama", "meta"), ("mistral", "mistral"), ("mixtral", "mistral"),
    ("phi", "microsoft"), ("command", "cohere"), ("yi", "01ai"),
    ("mimo", "xiaomi"), ("xiaomi", "xiaomi"), ("muse", "muse"), ("glimmer", "muse"),
]


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def family_of(model: str) -> str | None:
    m = (model or "").lower()
    for key, fam in FAMILY_MAP:
        if key in m:
            return fam
    return None


def die(msg: str, code: int = 1):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def sh(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        die(f"{' '.join(cmd)}\n{r.stderr.strip()[:400]}")
    return r


# ---------------------------------------------------------------- fork + state

def check_bid(book: str) -> str:
    if not SAFE_BID.match(book):
        die(f"invalid book-id {book!r} (expected account--title)")
    return book


def status_of(book: str) -> dict:
    """Read the book's state from the local site-repo status mirror."""
    p = SITE / "status" / f"{book}.json"
    if not p.is_file():
        die(f"no status file for {book} at {p}; is it in the pipeline yet?")
    return json.loads(p.read_text())


def pass_and_dir(state: str) -> tuple[int, str]:
    """Which pass a book in this state needs, and the review subdir the seats live in."""
    if state in ("0-pending", "1-critics"):
        return 2, "v1"          # pass-2 panel reviews the submitted v1
    if state == "3-verification":
        return 3, "v2"          # pass-3 verification reviews the revised v2
    die(f"state {state!r} is not a critic state (need 0-pending, 1-critics, or 3-verification)")


def fork_dir(book: str) -> Path:
    """Ensure a fresh local clone of the book's fork and return its path."""
    FORKS.mkdir(exist_ok=True)
    d = FORKS / book
    repo = book.split("--", 1)[1]              # org repo is named by the title-slug half
    url = f"git@github.com:{ORG}/{repo}.git"
    if d.is_dir():
        sh(["git", "-C", str(d), "fetch", "--quiet", "origin"])
        sh(["git", "-C", str(d), "reset", "--hard", "--quiet", "origin/main"])
    else:
        r = sh(["git", "clone", "--quiet", url, str(d)], check=False)
        if r.returncode != 0:
            die(f"could not clone fork {url}:\n{r.stderr.strip()[:300]}")
    return d


def manifest_families(fork: Path) -> list[str]:
    m = json.loads((fork / "manifest.json").read_text())
    fams = set()
    for w in m.get("provenance", {}).get("written_by", []):
        f = family_of(w.get("model", ""))
        fams.add(f or (w.get("model", "").lower() or "unknown"))
    return sorted(fams)


# ---------------------------------------------------------------- SEATS.json

def seats_path(fork: Path, vdir: str) -> Path:
    return fork / "review" / vdir / "SEATS.json"


def review_filename(pass_no: int, seat: str) -> str:
    """Pass-2 panel reviews are critic-X.md; pass-3 verification reviews are verify-X.md."""
    return f"critic-{seat}.md" if pass_no == 2 else f"verify-{seat}.md"


def reconstruct_from_files(fork: Path, vdir: str, pass_no: int) -> dict:
    """Detect a panel already filled via the manual flow (critic-*.md / verify-*.md with no
    SEATS.json). Returns {seat: filled-info} so a completed legacy panel is not re-opened."""
    d = fork / "review" / vdir
    found = {}
    for seat in SEATS:
        p = d / review_filename(pass_no, seat)
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        model = "unknown"
        for line in text.splitlines():
            if line.strip().upper().startswith("CRITIC:"):
                model = line.split(":", 1)[1].strip()[:80] or "unknown"
                break
        fam = family_of(model) or re.sub(r'[^a-z0-9]+', '-', model.lower()).strip('-')[:24] or "unknown"
        found[seat] = {"state": "filled", "model": model, "family": fam,
                       "actor": "legacy-file", "verdict": tally_verdict(text, pass_no)}
    return found


def load_seats(fork: Path, vdir: str, book: str, pass_no: int) -> dict:
    p = seats_path(fork, vdir)
    if p.is_file():
        return json.loads(p.read_text())
    # no SEATS.json: seed a fresh panel, but honor any reviews already filed by the old flow
    seats = {s: {"state": "open"} for s in SEATS}
    seats.update(reconstruct_from_files(fork, vdir, pass_no))
    return {
        "book_id": book, "pass": pass_no, "version": vdir,
        "author_families": manifest_families(fork),
        "seats": seats,
        "seeded": now(),
    }


def seated_families(seats: dict, exclude: str | None = None) -> set[str]:
    out = set()
    for s, info in seats["seats"].items():
        if s == exclude:
            continue
        if info.get("state") in ("claimed", "filled") and info.get("family"):
            out.add(info["family"])
    return out


def stale(info: dict) -> bool:
    if info.get("state") != "claimed" or not info.get("at"):
        return False
    try:
        t = datetime.strptime(info["at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    return (datetime.now(timezone.utc) - t).total_seconds() > CLAIM_TTL_MIN * 60


def open_seats(seats: dict) -> list[str]:
    return [s for s in SEATS
            if seats["seats"][s].get("state") == "open" or stale(seats["seats"][s])]


def commit_push_seats(fork: Path, vdir: str, seats: dict, msg: str) -> bool:
    """Write SEATS.json, commit, push. Returns True on success, False on non-fast-forward
    (someone else pushed first — the caller must re-fetch and retry)."""
    p = seats_path(fork, vdir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(seats, indent=2) + "\n")
    sh(["git", "-C", str(fork), "add", str(p.relative_to(fork))])
    sh(["git", "-C", str(fork), "commit", "--quiet", "-m", msg])
    r = sh(["git", "-C", str(fork), "push", "--no-verify", "--quiet", "origin", "main"], check=False)
    if r.returncode == 0:
        return True
    # rejected? undo our local commit and signal retry
    sh(["git", "-C", str(fork), "reset", "--hard", "--quiet", "origin/main"], check=False)
    sh(["git", "-C", str(fork), "fetch", "--quiet", "origin"])
    sh(["git", "-C", str(fork), "reset", "--hard", "--quiet", "origin/main"], check=False)
    return False


# ---------------------------------------------------------------- claim

def do_claim(book, model, family, actor, seat_pref) -> tuple[Path, str, str]:
    """Atomically claim a seat. Returns (fork, seat, vdir). Raises via die() on failure."""
    check_bid(book)
    fam = (family or family_of(model) or "").lower()
    if not fam:
        die(f"cannot infer family for model {model!r}; pass --family")
    st = status_of(book)
    pass_no, vdir = pass_and_dir(st["state"])

    for attempt in range(6):
        fork = fork_dir(book)
        seats = load_seats(fork, vdir, book, pass_no)
        if fam in seats["author_families"]:
            die(f"family {fam!r} authored this book — a critic may not share the author family "
                f"(authors: {', '.join(seats['author_families'])})")
        already = seated_families(seats)
        if fam in already:
            die(f"family {fam!r} already holds a seat on this panel; the three seats must be "
                f"distinct families (seated: {', '.join(sorted(already))})")
        avail = open_seats(seats)
        if not avail:
            die(f"no open seats on {book} {vdir} — panel is full or complete")
        seat = seat_pref if seat_pref and seat_pref != "auto" else avail[0]
        if seat not in avail:
            die(f"seat {seat} is not open (open: {', '.join(avail) or 'none'})")
        seats["seats"][seat] = {"state": "claimed", "model": model, "family": fam,
                                "actor": actor, "at": now()}
        ok = commit_push_seats(fork, vdir, seats,
                               f"claim seat {seat}: {model} (family {fam}) by {actor}")
        if ok:
            return fork, seat, vdir
        # lost the race — loop re-fetches and re-picks
    die("could not claim a seat after 6 attempts (heavy contention); try again")


# ---------------------------------------------------------------- submit

REQUIRED_HEADER_TOKENS = ("CRITIC:", "PASS:")
VERDICT_TOKENS = ("SALVAGEABLE", "PUBLISH", "DON'T PUBLISH", "DONT PUBLISH")
COMMON_SECTIONS = ("## Verdict summary", "## Blocking findings", "## Suggestions")
FICTION_SECTIONS = (
    "## Continuity-and-consistency audit",
    "## Craft-axis scores",
    "## Density finding",
)
NONFICTION_SECTIONS = ("## Fact-check sample", "## Scores")


# (phrase, normalized). Order only matters for readability — resolution is positional.
_VERDICT_PHRASES = (
    ("UNSALVAGEABLE", "UNSALVAGEABLE"),
    ("SALVAGEABLE", "SALVAGEABLE"),
    ("DO NOT PUBLISH", "DONT-PUBLISH"),
    ("DON'T PUBLISH", "DONT-PUBLISH"),
    ("DONT PUBLISH", "DONT-PUBLISH"),
    ("PUBLISH", "PUBLISH"),
)


def _verdict_in(span: str) -> str | None:
    """The verdict a span declares = the LAST-stated verdict token, longest-at-a-locus winning.

    The template says the verdict paragraph ENDS with the verdict, so last-position wins:
    this correctly reads 'no inaccuracy warrants DON'T PUBLISH. VERDICT: PUBLISH' as PUBLISH
    and 'not UNSALVAGEABLE — SALVAGEABLE' as SALVAGEABLE. Ranking by (end-offset, length) lets
    the containing phrase win nested ties (UNSALVAGEABLE ⊃ SALVAGEABLE, DON'T PUBLISH ⊃ PUBLISH).
    """
    up = span.upper()
    hits = []
    for phrase, norm in _VERDICT_PHRASES:
        for match in re.finditer(
            rf"(?<![A-Z]){re.escape(phrase)}(?![A-Z])", up
        ):
            hits.append((match.end(), len(phrase), norm))
    if not hits:
        return None
    return max(hits)[2]


def tally_verdict(text: str, pass_no: int | None = None) -> str:
    # Prefer the '## Verdict summary' section (where the verdict is declared); fall back to the
    # whole review only if that section carries no verdict token. Never scan prose for a substring.
    m = re.search(r'##\s*verdict\s+summary\b(.*?)(?:\n##\s|\Z)', text, re.I | re.S)
    verdict = (m and _verdict_in(m.group(1))) or _verdict_in(text) or "UNCLEAR"
    allowed = {
        2: {"SALVAGEABLE", "UNSALVAGEABLE"},
        3: {"PUBLISH", "DONT-PUBLISH"},
    }
    if pass_no in allowed and verdict not in allowed[pass_no]:
        return "UNCLEAR"
    return verdict


def validate_review(text: str, pass_no: int, is_fiction: bool):
    if len(text.strip()) < 800:
        die("review body is too short (<800 chars) — did the model return empty content?")
    missing = [t for t in REQUIRED_HEADER_TOKENS if t not in text]
    if missing:
        die(f"review is missing template header tokens: {', '.join(missing)}")
    pass_match = re.search(r"(?im)^PASS:\s*([23])\b", text)
    if not pass_match or int(pass_match.group(1)) != pass_no:
        die(f"review PASS header must name the active pass ({pass_no})")
    required_sections = COMMON_SECTIONS + (FICTION_SECTIONS if is_fiction else NONFICTION_SECTIONS)
    if pass_no == 3:
        required_sections += ("## Pass-3 only: findings ledger",)
    lower = text.lower()
    missing_sections = [heading for heading in required_sections if heading.lower() not in lower]
    if missing_sections:
        shelf = "FICTION" if is_fiction else "general"
        die(f"{shelf} review is missing required sections: {', '.join(missing_sections)}")
    summary = re.search(r"##\s*verdict\s+summary\b(.*?)(?:\n##\s|\Z)", text, re.I | re.S)
    summary_text = summary.group(1) if summary else ""
    unfilled = (
        re.search(r"SALVAGEABLE\s*/\s*UNSALVAGEABLE", summary_text, re.I)
        or re.search(r"PUBLISH\s*/\s*(?:DON'T|DONT|DO NOT)\s+PUBLISH", summary_text, re.I)
    )
    if unfilled or tally_verdict(text, pass_no) == "UNCLEAR":
        expected = "SALVAGEABLE/UNSALVAGEABLE" if pass_no == 2 else "PUBLISH/DON'T PUBLISH"
        die(f"review must select one Pass-{pass_no} verdict ({expected}) at the end of its summary")


def do_submit(book, seat, text, actor=None) -> dict:
    check_bid(book)
    seat = seat.upper()
    if seat not in SEATS:
        die(f"seat must be one of {SEATS}")
    st = status_of(book)
    pass_no, vdir = pass_and_dir(st["state"])

    for attempt in range(6):
        fork = fork_dir(book)
        manifest = json.loads((fork / "manifest.json").read_text())
        is_fiction = manifest.get("book", {}).get("shelf") == "fiction"
        validate_review(text, pass_no, is_fiction)
        verdict = tally_verdict(text, pass_no)
        seats = load_seats(fork, vdir, book, pass_no)
        info = seats["seats"].get(seat, {})
        if info.get("state") == "filled":
            die(f"seat {seat} is already filled by {info.get('model')} — nothing to submit")
        model = info.get("model", "unknown")
        family = info.get("family", "unknown")
        who = actor or info.get("actor", "unknown")
        header = (f"<!-- CRITIC {seat} · {model} · family:{family} · pass {pass_no} · {now()} -->\n"
                  f"CRITIC: {model} (family {family}, actor {who})\n"
                  f"DATE: {now()[:10]}\nPASS: {pass_no}\nAUTO-TALLIED VERDICT: {verdict}\n\n---\n\n")
        rp = fork / "review" / vdir / review_filename(pass_no, seat)
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(header + text.strip() + "\n")
        seats["seats"][seat] = {"state": "filled", "model": model, "family": family,
                                "actor": who, "at": now(), "verdict": verdict}
        # write both the review and the seats update in one commit
        sh(["git", "-C", str(fork), "add", str(rp.relative_to(fork))])
        seats_path(fork, vdir).write_text(json.dumps(seats, indent=2) + "\n")
        sh(["git", "-C", str(fork), "add", str(seats_path(fork, vdir).relative_to(fork))])
        sh(["git", "-C", str(fork), "commit", "--quiet", "-m",
            f"seat {seat} filled: {model} ({family}) — {verdict}"])
        r = sh(["git", "-C", str(fork), "push", "--no-verify", "--quiet", "origin", "main"], check=False)
        if r.returncode == 0:
            filled = [s for s in SEATS if seats["seats"][s].get("state") == "filled"]
            complete = panel_complete(seats)
            return {"seat": seat, "verdict": verdict, "filled": filled,
                    "complete": complete, "seats": seats, "fork": str(fork),
                    "pass": pass_no, "vdir": vdir}
        sh(["git", "-C", str(fork), "reset", "--hard", "--quiet", "origin/main"], check=False)
    die("could not submit after 6 attempts (contention)")


def panel_complete(seats: dict) -> bool:
    filled = [i for i in seats["seats"].values() if i.get("state") == "filled"]
    fams = {i.get("family") for i in filled}
    return len(filled) >= 3 and len(fams) >= 3


def panel_tally(seats: dict) -> dict:
    verdicts = [i.get("verdict") for i in seats["seats"].values() if i.get("state") == "filled"]
    unsalv = sum(1 for v in verdicts if v == "UNSALVAGEABLE")
    dontpub = sum(1 for v in verdicts if v == "DONT-PUBLISH")
    if seats["pass"] == 2:
        rec = "KILL — recommend to judge (>=2 UNSALVAGEABLE)" if unsalv >= 2 else "ADVANCE to 2-revision"
    else:
        rec = "DON'T PUBLISH — recommend to judge (>=2)" if dontpub >= 2 else "ADVANCE to judge (PUBLISH-leaning)"
    return {"verdicts": verdicts, "recommendation": rec}


# ---------------------------------------------------------------- serve a review

def produce_via_endpoint(fork, endpoint, served_model, pass_no, chunked) -> str:
    """Import run_critics' model callers to fill a seat from a served endpoint."""
    sys.path.insert(0, str(HERE))
    import run_critics as rc
    if chunked:
        return rc.chunked_review(endpoint, served_model, fork, pass_no=pass_no)
    packet = sh([sys.executable, str(HERE / "assemble_critic_packet.py"), str(fork), str(pass_no)]).stdout
    return rc.call_model(endpoint, served_model, packet)


# ---------------------------------------------------------------- dashboard

def refresh_dashboard() -> dict:
    """Rebuild reviews-repo/review-queue.json from every book that has a status file.
    open_jobs = panels still needing a critic; awaiting_judge = complete panels."""
    open_jobs, awaiting_judge = [], []
    for sp in sorted((SITE / "status").glob("*.json")):
        book = sp.stem
        try:
            st = json.loads(sp.read_text())
        except Exception:
            continue
        state = st.get("state", "")
        if state not in ("0-pending", "1-critics", "3-verification"):
            continue
        try:
            pass_no, vdir = pass_and_dir(state)
            fork = fork_dir(book)
            seats = load_seats(fork, vdir, book, pass_no)
        except SystemExit:
            continue
        complete = panel_complete(seats)
        entry = {
            "book_id": book, "state": state, "pass": pass_no, "version": vdir,
            "author_families": seats["author_families"],
            "open_seats": [] if complete else open_seats(seats),
            "seats": {s: seats["seats"][s] for s in SEATS},
            "complete": complete,
        }
        if complete:
            entry["tally"] = panel_tally(seats)
            awaiting_judge.append(entry)
        else:
            open_jobs.append(entry)
    out = {"generated": now(), "open_jobs": open_jobs, "awaiting_judge": awaiting_judge}
    dash = REVS / "review-queue.json"
    dash.write_text(json.dumps(out, indent=2) + "\n")
    return out


# ---------------------------------------------------------------- commands

def cmd_list(a):
    dash = refresh_dashboard()
    jobs = dash["open_jobs"]
    judge = dash.get("awaiting_judge", [])
    if not jobs and not judge:
        print("No books awaiting review. Queue is clear.")
        return
    if judge:
        print("Panels COMPLETE, awaiting judge (no critic action needed):")
        for j in judge:
            print(f"  ✓ {j['book_id']} [pass {j['pass']}] — {j['tally']['recommendation']}")
        print()
    if not jobs:
        print("No panels currently need a critic.")
        return
    print(f"Open critic seats — {len(jobs)} book(s) waiting for review:\n")
    for j in jobs:
        tag = "PANEL COMPLETE" if j["complete"] else f"open seats: {', '.join(j['open_seats']) or 'none'}"
        print(f"● {j['book_id']}  [pass {j['pass']} · {j['version']}]  — {tag}")
        print(f"    authors: {', '.join(j['author_families'])}  (a critic may NOT share these)")
        for s in SEATS:
            i = j["seats"][s]
            state = i.get("state", "open")
            if state == "open":
                print(f"    seat {s}: open")
            else:
                print(f"    seat {s}: {state:7} {i.get('model','?')} ({i.get('family','?')})"
                      + (f" → {i.get('verdict')}" if i.get("verdict") else ""))
        print()


def cmd_packet(a):
    check_bid(a.book)
    st = status_of(a.book)
    pass_no, _ = pass_and_dir(st["state"])
    fork = fork_dir(a.book)
    r = sh([sys.executable, str(HERE / "assemble_critic_packet.py"), str(fork), str(pass_no)])
    sys.stdout.write(r.stdout)


def cmd_claim(a):
    fork, seat, vdir = do_claim(a.book, a.model, a.family, a.actor, a.seat)
    print(f"✓ claimed seat {seat} on {a.book} ({vdir}) for {a.model}.")
    print(f"  Next: read the manuscript, write the filled template, then:")
    print(f"    critique submit {a.book} --seat {seat} --file <your-review.md>")
    print(f"  Get the exact packet to read with:  critique packet {a.book}")


def _report_submit(res, book):
    print(f"✓ seat {res['seat']} filled on {book} → verdict {res['verdict']}")
    print(f"  filled seats: {', '.join(res['filled'])} of {SEATS}")
    if res["complete"]:
        t = panel_tally(res["seats"])
        print(f"\n=== PANEL COMPLETE ({book} pass {res['pass']}) ===")
        print(f"  verdicts: {', '.join(v for v in t['verdicts'] if v)}")
        print(f"  → {t['recommendation']}")
        if res["pass"] == 2:
            print("  Publisher next: dry-run queue/advance_state.py to 2-revision, then --apply.")
        else:
            print("  Publisher next: dry-run queue/prepare_judge_case.py, then --apply;")
            print("  only after the report card is pushed, advance explicitly to 4-judge.")
    refresh_dashboard()


def cmd_submit(a):
    text = Path(a.file).read_text() if a.file else sys.stdin.read()
    res = do_submit(a.book, a.seat, text, a.actor)
    _report_submit(res, a.book)


def cmd_take(a):
    if not a.self_file and not a.endpoint:
        die("take needs either --self-file <review.md> or --endpoint URL --served-model N")
    fork, seat, vdir = do_claim(a.book, a.model, a.family, a.actor, a.seat)
    print(f"✓ claimed seat {seat}; producing review…", flush=True)
    try:
        if a.self_file:
            text = Path(a.self_file).read_text()
        else:
            st = status_of(a.book)
            pass_no, _ = pass_and_dir(st["state"])
            text = produce_via_endpoint(fork, a.endpoint, a.served_model, pass_no, a.chunked)
    except SystemExit:
        do_release(a.book, seat)
        raise
    except Exception as e:
        do_release(a.book, seat)
        die(f"review production failed ({str(e)[:160]}); released seat {seat}")
    res = do_submit(a.book, seat, text, a.actor)
    _report_submit(res, a.book)


def do_release(book, seat):
    check_bid(book)
    seat = seat.upper()
    st = status_of(book)
    pass_no, vdir = pass_and_dir(st["state"])
    for _ in range(6):
        fork = fork_dir(book)
        seats = load_seats(fork, vdir, book, pass_no)
        if seats["seats"].get(seat, {}).get("state") != "claimed":
            return  # nothing to release
        seats["seats"][seat] = {"state": "open"}
        if commit_push_seats(fork, vdir, seats, f"release seat {seat}"):
            return


def cmd_release(a):
    do_release(a.book, a.seat)
    print(f"✓ released seat {a.seat} on {a.book}")
    refresh_dashboard()


def cmd_refresh(a):
    d = refresh_dashboard()
    print(f"✓ review-queue.json rebuilt: {len(d['open_jobs'])} open job(s)")


def main():
    p = argparse.ArgumentParser(prog="critique", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list").set_defaults(fn=cmd_list)
    sub.add_parser("refresh").set_defaults(fn=cmd_refresh)

    pk = sub.add_parser("packet"); pk.add_argument("book"); pk.set_defaults(fn=cmd_packet)

    for name, fn in (("claim", cmd_claim),):
        c = sub.add_parser(name); c.add_argument("book")
        c.add_argument("--model", required=True); c.add_argument("--family")
        c.add_argument("--actor", required=True); c.add_argument("--seat", default="auto")
        c.set_defaults(fn=fn)

    s = sub.add_parser("submit"); s.add_argument("book")
    s.add_argument("--seat", required=True); s.add_argument("--file")
    s.add_argument("--actor"); s.set_defaults(fn=cmd_submit)

    t = sub.add_parser("take"); t.add_argument("book")
    t.add_argument("--model", required=True); t.add_argument("--family")
    t.add_argument("--actor", required=True); t.add_argument("--seat", default="auto")
    t.add_argument("--endpoint"); t.add_argument("--served-model", dest="served_model")
    t.add_argument("--chunked", action="store_true"); t.add_argument("--self-file", dest="self_file")
    t.set_defaults(fn=cmd_take)

    r = sub.add_parser("release"); r.add_argument("book")
    r.add_argument("--seat", required=True); r.set_defaults(fn=cmd_release)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
