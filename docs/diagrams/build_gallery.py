"""Write docs/diagrams/README.md from manifest.json and the specs it lists.

Usage: python3 build_gallery.py   (standard library only)
"""
import json
import sys
from pathlib import Path

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent
manifest = json.loads((root / "manifest.json").read_text())

HEAD = """# Architecture diagrams

{intro}

Each diagram comes as an `.svg` (used here and in the top-level README), a `.png` for slides and
reports, and an `.html` page. [`index.html`](index.html) has them all on one page and follows
your light or dark theme; open it from a clone, because GitHub shows HTML as source.

"""

FOOT = """## Changing a diagram

The JSON files in [`specs/`](specs) are the source. The pictures are drawn from them by the
architecture-flowmaps skill for Claude Code:

```bash
python3 ~/.claude/skills/architecture-flowmaps/scripts/flowmap.py render specs/pairing.json --png -o .
```

```bash
python3 ~/.claude/skills/architecture-flowmaps/scripts/flowmap.py page manifest.json -o index.html
```

Run both from this folder, then run `python3 build_gallery.py` to rebuild this page so its steps
match the specs. When the code
changes, check it first, then edit the spec.
"""


def anchor(title):
    keep = "".join(c for c in title.lower() if c.isalnum() or c in " -")
    return keep.replace(" ", "-")


out = [HEAD.format(intro=manifest["intro"]), "## Contents\n"]
specs = []
for section in manifest["sections"]:
    out.append(f"- **{section['title']}**: " + ", ".join(
        f"[{json.loads((root / p).read_text())['title']}](#{anchor(json.loads((root / p).read_text())['title'])})"
        for p in section["specs"]))
out.append("")

for section in manifest["sections"]:
    out.append(f"## {section['title']}\n\n{section['intro']}\n")
    for path in section["specs"]:
        spec = json.loads((root / path).read_text())
        sid = spec.get("id") or Path(path).stem
        out.append(f"### {spec['title']}\n")
        out.append(f"{spec['claim']}\n")
        out.append(f"![{spec['title']}]({sid}.svg)\n")
        steps = spec.get("steps", [])
        numbered = [s for s in steps if isinstance(s, str)]
        lettered = [s for s in steps if isinstance(s, dict)]
        if numbered:
            out.extend(f"{i}. {s}" for i, s in enumerate(numbered, 1))
            out.append("")
        if lettered:
            out.extend(f"- **{s['id']}.** {s['text']}" for s in lettered)
            out.append("")
        if spec.get("notes"):
            out.append("**Notes**\n")
            out.extend(f"- {n}" for n in spec["notes"])
            out.append("")
        out.append(f"Files: [`{sid}.png`]({sid}.png) · [`{sid}.html`]({sid}.html) · "
                   f"[`specs/{sid}.json`](specs/{sid}.json)\n")

out.append(FOOT)
(root / "README.md").write_text("\n".join(out))
print("wrote", root / "README.md")
