from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
import sys

ROOT = Path(__file__).resolve().parents[1]
HTML_FILES = sorted(ROOT.rglob("*.html"))
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.ids = set()
        self.links = []
        self.title = ""
        self.in_title = False
        self.h1_count = 0
        self.errors = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.add(attrs["id"])
        if tag == "title":
            self.in_title = True
        if tag == "h1":
            self.h1_count += 1
        for attr in ("href", "src"):
            if attrs.get(attr):
                self.links.append(attrs[attr])
        if tag not in VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag in VOID:
            return
        if tag not in self.stack:
            self.errors.append(f"unexpected closing tag </{tag}>")
            return
        while self.stack:
            current = self.stack.pop()
            if current == tag:
                break

    def handle_data(self, data):
        if self.in_title:
            self.title += data.strip()

failed = []
parsed = {}
for file in HTML_FILES:
    parser = PageParser()
    try:
        parser.feed(file.read_text(encoding="utf-8"))
        parser.close()
    except Exception as exc:
        failed.append(f"{file.relative_to(ROOT)}: parser error: {exc}")
        continue
    if not parser.title:
        failed.append(f"{file.relative_to(ROOT)}: missing <title>")
    if parser.h1_count != 1:
        failed.append(f"{file.relative_to(ROOT)}: expected exactly one <h1>, found {parser.h1_count}")
    if parser.stack:
        failed.append(f"{file.relative_to(ROOT)}: unclosed tags: {', '.join(parser.stack)}")
    for error in parser.errors:
        failed.append(f"{file.relative_to(ROOT)}: {error}")
    parsed[file.resolve()] = parser

for file, parser in parsed.items():
    for raw in parser.links:
        parts = urlsplit(raw)
        if parts.scheme or parts.netloc or not parts.path:
            continue
        target = (file.parent / unquote(parts.path)).resolve()
        if target.is_dir():
            target = target / "index.html"
        if not target.exists():
            failed.append(f"{file.relative_to(ROOT)}: broken local link or asset: {raw}")
            continue
        if parts.fragment and target.suffix.lower() == ".html":
            target_parser = parsed.get(target)
            if target_parser and unquote(parts.fragment) not in target_parser.ids:
                failed.append(f"{file.relative_to(ROOT)}: missing anchor #{parts.fragment} in {target.relative_to(ROOT)}")

if failed:
    print("\n".join(f"FAIL: {item}" for item in failed))
    sys.exit(1)

print(f"PASS: validated {len(HTML_FILES)} HTML page(s), page titles, heading structure, local links, assets and anchors.")
