import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CDN_URL_RE = re.compile(r"(https://cdn\.jsdelivr\.net/gh/origin2019/Jun@main/[^\"'\s]+)")


def short_version(value):
    value = value.strip()
    if len(value) > 8:
        return value[:8]
    return value


def bump_file(path, version):
    with open(path, "r", encoding="utf-8", newline="") as f:
        content = f.read()

    def repl(match):
        url = match.group(1)
        v_match = re.search(r"\?v=[A-Za-z0-9._-]+$", url)
        if v_match:
            return url[: v_match.start()] + f"?v={version}"
        if "?" in url:
            return url
        return url + f"?v={version}"

    new_content = CDN_URL_RE.sub(repl, content)
    if new_content != content:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(new_content)
        print(f"updated: {path}")
        return True
    return False


def main():
    version = os.environ.get("BUMP_VERSION") or (sys.argv[1] if len(sys.argv) > 1 else None)
    if not version:
        print("usage: python scripts/bump_version.py <version>  (or set BUMP_VERSION env)")
        return 1
    version = short_version(version)

    changed = 0
    for dirpath, _, filenames in os.walk(ROOT):
        if ".git" in dirpath:
            continue
        for filename in filenames:
            if filename.endswith(".html"):
                if bump_file(os.path.join(dirpath, filename), version):
                    changed += 1
    print(f"version={version}, updated {changed} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())