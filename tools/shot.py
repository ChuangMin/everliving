"""Render the page to PNGs so someone can actually look at it.

`tests/page_check.js` runs the page's JavaScript against a stub DOM, which catches a
typo or a NaN coordinate but is blind to everything that makes a picture a picture:
what got cropped, what sits on top of what, whether the thing that moves ever moves
somewhere wrong. This closes that gap without a test framework, a browser extension
or a network dependency — it drives whichever Chromium is already on the machine in
headless mode.

**The animation timeline is pinned, not played.** Chrome's `--virtual-time-budget`
advances `setInterval` (the clock in the corner really does tick) but leaves CSS
animations where they started, so a screenshot "60 seconds in" is the same image as
one at zero. Instead each frame is rendered with a negative `animation-delay` and the
animation paused, which places every animation at an exact offset. That is stronger
than waiting anyway: sampling a 240-second camera cycle at its extremes takes no
longer than sampling its start, and it's reproducible.

    python tools/shot.py                          # 工作間, three points in the cycle
    python tools/shot.py --scene 潮線 --action 淹水
    python tools/shot.py --at 0 120 --size 900x1400

Written for whoever is looking next, human or agent. The output directory is printed
so the files can be opened straight from the terminal.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

PAGE = Path(__file__).resolve().parent.parent / "src" / "everliving" / "static" / "index.html"

#: Where Chromium usually lives on Windows. First one that exists wins.
CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
)


def find_browser() -> str:
    for path in CANDIDATES:
        if Path(path).is_file():
            return path
    for name in ("chrome", "chromium", "msedge", "google-chrome"):
        found = shutil.which(name)
        if found:
            return found
    raise SystemExit("找不到 Chrome/Edge。裝一個,或用 --browser 指定路徑。")


def pinned_page(source: str, offset: float) -> str:
    """The page with every animation frozen at `offset` seconds into its cycle.

    `!important` on both properties because the sheet sets `animation` shorthand per
    selector, and a shorthand would otherwise reset the delay we're trying to impose.
    """
    override = (
        "<style>*,*::before,*::after{"
        f"animation-delay:-{offset}s!important;"
        "animation-play-state:paused!important;"
        "animation-fill-mode:both!important}</style>"
    )
    # Last style in <head> wins on equal specificity, and !important beats the rest.
    return source.replace("</head>", override + "</head>", 1)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="shot")
    parser.add_argument("--scene", default=None, help="哪個場景(預設用頁面的開場)。")
    parser.add_argument("--action", default=None, help="焊接 / 停電 / 淹水 / 起霧。")
    parser.add_argument(
        "--at",
        type=float,
        nargs="+",
        default=[0, 52, 120],
        metavar="S",
        help="在動畫週期的第幾秒取樣(可給多個)。預設 0/52/120 大致是漂移的兩個極端加中間。",
    )
    parser.add_argument("--size", default="1100x820", metavar="WxH")
    parser.add_argument("--out", default="shots", help="PNG 放哪(預設 ./shots)。")
    parser.add_argument("--browser", default=None)
    parser.add_argument(
        "--page",
        default=None,
        help="改用別的 HTML(拿 `git show HEAD:…` 存下來的舊版做前後對照用)。",
    )
    parser.add_argument("--tag", default=None, help="輸出檔名的前綴,預設由場景與動作組成。")
    args = parser.parse_args(argv)

    browser = args.browser or find_browser()
    width, _, height = args.size.partition("x")
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    query = []
    if args.scene:
        query.append(f"scene={quote(args.scene)}")
    if args.action:
        query.append(f"action={quote(args.action)}")
    suffix = ("?" + "&".join(query)) if query else ""

    source = Path(args.page or PAGE).read_text(encoding="utf-8")
    tag = args.tag or "-".join(filter(None, [args.scene, args.action])) or "default"

    written = []
    with tempfile.TemporaryDirectory() as tmp:
        for offset in args.at:
            # A file per offset rather than one rewritten in place: Chrome is started
            # fresh each time and a shared name invites a stale read.
            page = Path(tmp) / f"page_{offset:g}.html"
            page.write_text(pinned_page(source, offset), encoding="utf-8")
            target = out_dir / f"{tag}_t{offset:g}s.png"
            subprocess.run(
                [
                    browser,
                    "--headless=new",
                    "--disable-gpu",
                    "--hide-scrollbars",
                    f"--window-size={width},{height}",
                    # Long enough for the drawing code to run; nothing here waits on
                    # the network, and the API call is expected to fail on file://.
                    "--virtual-time-budget=1500",
                    f"--screenshot={target.resolve()}",
                    page.resolve().as_uri() + suffix,
                ],
                check=True,
                capture_output=True,
            )
            if not target.is_file():
                raise SystemExit(f"沒截到圖:{target}")
            written.append(target)

    print(f"用的是 {browser}")
    for path in written:
        print(f"  {path.resolve()}  ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
