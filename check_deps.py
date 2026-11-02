import json
import sys
import urllib.error
import urllib.request

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import Version

TARGET = Version("3.11")
API = "https://pypi.org/pypi"


def fetch(url):
    """for Return parsed JSON, or None on 404."""
    req = urllib.request.Request(url, headers={"User-Agent": "dep-checker/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def parse_line(line):
    
    if "==" not in line:
        return None
    name, _, version = line.partition("==")
    return name.strip(), version.strip()


def min_python(spec_text):

    try:
        spec = SpecifierSet(spec_text)
    except InvalidSpecifier:
        return None
    best = None
    for s in spec:
        if s.operator in (">=", "==", "~="):
            v = Version(s.version)
            if best is None or v > best:
                best = v
        elif s.operator == ">":
            v = Version(s.version)
            if best is None or v > best:
                best = v
    return best


def main(path):
    with open(path) as f:
        lines = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]

    checked = len(lines)
    not_found = []
    incompatible = []
    candidates = []  # (min_python, name, version, requires_python)

    for line in lines:
        parsed = parse_line(line)
        if parsed is None:
            print(f"  [skip] {line} (no == pin)", file=sys.stderr)
            continue
        name, version = parsed

        # Does the package itself exist?
        if fetch(f"{API}/{name}/json") is None:
            not_found.append(line)
            print(f"  [404 pkg] {line}", file=sys.stderr)
            continue

        # Does that exact release exist?
        release = fetch(f"{API}/{name}/{version}/json")
        if release is None:
            not_found.append(line)
            print(f"  [404 ver] {line}", file=sys.stderr)
            continue

        rp = release["info"].get("requires_python") or ""
        if not rp.strip():
           
            print(f"  [ok] {line}  requires_python=<none>", file=sys.stderr)
            continue

        try:
            spec = SpecifierSet(rp)
        except InvalidSpecifier:
            print(f"  [ok] {line}  requires_python={rp!r} (unparseable)", file=sys.stderr)
            continue

        # The release exists and declares requires_python, so it is a candidate
        # for "highest requirement" whether or not it supports 3.11.
        mp = min_python(rp)
        if mp is not None:
            candidates.append((mp, name, version, rp))

        # prereleases=True so 3.11 is matched against bounds like <3.11
        if not spec.contains(TARGET, prereleases=True):
            incompatible.append(line)
            print(f"  [incompat] {line}  requires_python={rp}  min={mp}", file=sys.stderr)
            continue

        print(f"  [ok] {line}  requires_python={rp}  min={mp}", file=sys.stderr)

    print(f"Dependencies checked: {checked}")
    print(f"Not found on PyPI: {len(not_found)}")
    print(f"Incompatible with Python 3.11: {len(incompatible)}")

    if candidates:
        mp, name, version, rp = max(candidates, key=lambda c: c[0])
        print(f"Highest requirement: {name}=={version} (>={mp})")
    else:
        print("Highest requirement: none")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "requirements.txt")
