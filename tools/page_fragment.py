"""Reduce a published (wrapped) page to the fragment form the Artifact tool publishes.

    python tools/page_fragment.py fetched/index.html docs/index.artifact.html
"""
import sys
from pathlib import Path

src, dst = Path(sys.argv[1]), Path(sys.argv[2])
html = src.read_text(encoding="utf-8")
start = html.index("<title>")
end = html.rindex("</body>")
dst.parent.mkdir(parents=True, exist_ok=True)
dst.write_text(html[start:end], encoding="utf-8")
print(f"fragment written: {dst} ({end - start} bytes)")
