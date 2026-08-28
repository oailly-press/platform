"""Gates 3+4: citation resolution and code execution.

Citations: every manifest grounded_in entry and every reference in backmatter.md must
resolve — URL (HTTP HEAD/GET, unless --offline), DOI (doi.org), ISBN (checksum), or a
lab_entry/interview/standard/dataset (format-checked only; those resolve at Pass 2).

Code: fenced blocks in chapters run in a scratch sandbox per the manifest's
code_listing_policy. Info-string containing 'fragment' or 'no-run' skips execution
(allowed only under executable_plus_marked_fragments). Runners: python, bash/sh.
Other languages are warned as unexecutable in v1, not rejected.
"""

from __future__ import annotations

import ipaddress
import os
import re
import resource
import signal
import socket
import subprocess
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

from common import finding, read_chapter, split_code_fences

URL_RE = re.compile(r"https?://[^\s)>\]]+")
TIMEOUT_NET = 15
MAX_URLS = 200  # cap outbound probes (resource + noise)
TIMEOUT_RUN = 20
MAX_EXEC_BLOCKS = 40  # cap executed listings per run


def _sandbox_limits():
    resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
    resource.setrlimit(resource.RLIMIT_AS, (512 << 20, 512 << 20))
    resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
    resource.setrlimit(resource.RLIMIT_FSIZE, (8 << 20, 8 << 20))


def _isbn_valid(raw: str) -> bool:
    s = re.sub(r"[^0-9Xx]", "", raw)
    if len(s) == 10:
        total = sum((10 - i) * (10 if c in "Xx" else int(c)) for i, c in enumerate(s))
        return total % 11 == 0
    if len(s) == 13:
        total = sum((1 if i % 2 == 0 else 3) * int(c) for i, c in enumerate(s))
        return total % 10 == 0
    return False


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None  # do not auto-follow; each hop must be re-validated by policy


_no_redirect = urllib.request.build_opener(_NoRedirect)


def _host_is_public(url: str) -> bool:
    """Reject loopback/link-local/private/reserved targets (SSRF guard)."""
    try:
        host = urllib.parse.urlparse(url).hostname
        if not host:
            return False
        for fam, _, _, _, sockaddr in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return False
        return True
    except Exception:
        return False


def _url_resolves(url: str) -> tuple[bool, str]:
    if not _host_is_public(url):
        return False, "refused: non-public/unresolvable host (SSRF guard)"
    req = urllib.request.Request(url, method="HEAD",
                                 headers={"User-Agent": "oailly-pass1-gate/1.0"})
    try:
        with _no_redirect.open(req, timeout=TIMEOUT_NET) as r:
            return r.status < 400, f"HTTP {r.status}"
    except urllib.error.HTTPError as he:
        if he.code in (301, 302, 303, 307, 308):
            return False, f"HTTP {he.code} redirect (not followed — cite the final URL)"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "oailly-pass1-gate/1.0"})
            with _no_redirect.open(req, timeout=TIMEOUT_NET) as r:
                return r.status < 400, f"HTTP {r.status} (GET)"
        except Exception as e:
            return False, str(e)[:120]
    except Exception as e:
        return False, str(e)[:120]


def check_citations(manifest: dict, book_dir: Path, offline: bool = False) -> list[dict]:
    f = []
    entries = list(manifest.get("provenance", {}).get("grounded_in", []) or [])
    back = book_dir / "backmatter.md"
    ref_urls: list[str] = []
    if back.is_file():
        text = back.read_text(encoding="utf-8")
        m = re.split(r"^##\s+references\s*$", text, flags=re.IGNORECASE | re.MULTILINE)
        if len(m) > 1:
            ref_urls = URL_RE.findall(m[1])

    for i, e in enumerate(entries):
        kind, ref = e.get("kind"), (e.get("reference") or "").strip()
        loc = f"grounded_in[{i}]"
        if not ref:
            f.append(finding("citations", "reject", "REFERENCE_EMPTY",
                             "empty reference", loc))
            continue
        if kind == "isbn" and not _isbn_valid(ref):
            f.append(finding("citations", "reject", "ISBN_INVALID",
                             f"ISBN checksum fails: {ref}", loc))
        elif kind == "doi":
            ref_urls.append("https://doi.org/" + ref.removeprefix("https://doi.org/"))
        elif kind == "url":
            ref_urls.append(ref)

    if offline:
        if ref_urls:
            f.append(finding("citations", "warn", "URLS_UNCHECKED_OFFLINE",
                             f"{len(ref_urls)} URL(s) not resolved (offline mode); "
                             "run online before verdict", "references"))
        return f

    unique = list(dict.fromkeys(ref_urls))
    if len(unique) > MAX_URLS:
        f.append(finding("citations", "reject", "TOO_MANY_URLS",
                         f"{len(unique)} distinct citation URLs exceeds cap {MAX_URLS}", "references"))
        unique = unique[:MAX_URLS]
    dead = []
    for url in unique:
        ok, detail = _url_resolves(url)
        if not ok:
            dead.append((url, detail))
    for url, detail in dead:
        f.append(finding("citations", "reject", "REFERENCE_DEAD",
                         f"does not resolve ({detail}): {url}", "references"))
    return f


RUNNERS = {"python": ["python3"], "python3": ["python3"],
           "bash": ["bash"], "sh": ["sh"], "shell": ["bash"]}
UNRUNNABLE_SILENT = {"", "text", "json", "yaml", "toml", "mermaid", "output",
                     "console", "diff", "csv", "ini", "makefile", "dockerfile"}


def check_code(manifest: dict, book_dir: Path, no_exec: bool = False) -> list[dict]:
    f = []
    policy = manifest.get("structure", {}).get("code_listing_policy", "no_code")
    blocks = []
    for ch in manifest.get("structure", {}).get("chapters", []):
        src = ch.get("source_file", "")
        text = read_chapter(book_dir, src)
        if text is None:
            continue
        _, code = split_code_fences(text)
        blocks += [(src, b) for b in code]

    if policy == "no_code":
        langs = {b["info"].split()[0].lower() for _, b in blocks if b["info"]}
        if langs - UNRUNNABLE_SILENT:
            f.append(finding("code", "reject", "UNDECLARED_CODE",
                             f"policy is no_code but executable-language listings exist: "
                             f"{sorted(langs - UNRUNNABLE_SILENT)}", "manifest"))
        return f

    executed = 0
    for src, b in blocks:
        info = b["info"].lower()
        lang = info.split()[0] if info else ""
        loc = f"{src}:{b['start_line']}"
        is_fragment = "fragment" in info or "no-run" in info
        if is_fragment:
            if policy == "all_executable":
                f.append(finding("code", "reject", "FRAGMENT_UNDER_STRICT_POLICY",
                                 "listing marked fragment but policy is all_executable", loc))
            continue
        if lang not in RUNNERS:
            if lang not in UNRUNNABLE_SILENT:
                f.append(finding("code", "warn", "LANGUAGE_UNSUPPORTED",
                                 f"no v1 runner for '{lang}'; mark as fragment or "
                                 "extend runners", loc))
            continue
        if no_exec:
            f.append(finding("code", "warn", "CODE_UNEXECUTED",
                             f"'{lang}' listing not executed (--no-exec)", loc))
            continue
        executed += 1
        if executed > MAX_EXEC_BLOCKS:
            f.append(finding("code", "reject", "TOO_MANY_LISTINGS",
                             f"more than {MAX_EXEC_BLOCKS} executable listings — refuse to run the rest", loc))
            break
        with tempfile.TemporaryDirectory(prefix="oailly-gate-") as tmp:
            script = Path(tmp) / ("listing." + ("py" if lang.startswith("py") else "sh"))
            script.write_text("\n".join(b["lines"]), encoding="utf-8")
            proc = subprocess.Popen(RUNNERS[lang] + [str(script)], cwd=tmp, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    start_new_session=True, preexec_fn=_sandbox_limits,
                                    env={"PATH": "/usr/bin:/bin", "HOME": tmp})
            try:
                out, err = proc.communicate(timeout=TIMEOUT_RUN)
                if proc.returncode != 0:
                    tail = (err or out).strip().splitlines()[-3:]
                    f.append(finding("code", "reject", "LISTING_FAILS",
                                     f"exit {proc.returncode}: {' | '.join(tail)}", loc))
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.communicate()
                f.append(finding("code", "reject", "LISTING_TIMEOUT",
                                 f"no result in {TIMEOUT_RUN}s (mark long-running "
                                 "listings as fragments)", loc))
    return f
