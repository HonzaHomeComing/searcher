#!/usr/bin/env python3
"""
Short Seek — windowed short-form video search with site blacklist toggles.

One-file app. Install deps, then run:

  pip install duckduckgo-search pillow requests
  python3 short_seek.py
"""

from __future__ import annotations

import json
import re
import threading
import webbrowser
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import tkinter as tk
from tkinter import messagebox, ttk

try:
    from duckduckgo_search import DDGS
except ImportError:  # pragma: no cover
    try:
        from ddgs import DDGS  # type: ignore
    except ImportError:
        DDGS = None  # type: ignore

try:
    from PIL import Image, ImageTk
except ImportError:  # pragma: no cover
    Image = None  # type: ignore
    ImageTk = None  # type: ignore

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore


APP_NAME = "Short Seek"
SETTINGS_PATH = Path.home() / ".short_seek_settings.json"
MAX_RESULTS = 36
SHORT_MAX_SECONDS = 180
THUMB_W, THUMB_H = 160, 284
COLUMNS = 4

PLATFORMS: list[tuple[str, str, tuple[str, ...]]] = [
    ("youtube", "YouTube", ("youtube.com", "youtu.be")),
    ("tiktok", "TikTok", ("tiktok.com",)),
    ("instagram", "Instagram", ("instagram.com",)),
    ("facebook", "Facebook", ("facebook.com", "fb.watch", "fb.com")),
    ("linkedin", "LinkedIn", ("linkedin.com",)),
    ("vimeo", "Vimeo", ("vimeo.com",)),
    ("dailymotion", "Dailymotion", ("dailymotion.com", "dai.ly")),
    ("other", "Other", ()),
]

PLATFORM_COLORS = {
    "youtube": "#FF0000",
    "tiktok": "#25F4EE",
    "instagram": "#E4405F",
    "facebook": "#1877F2",
    "linkedin": "#0A66C2",
    "vimeo": "#1AB7EA",
    "dailymotion": "#00AAFF",
    "other": "#9AA0A6",
}

SITE_QUERIES = {
    "tiktok": "site:tiktok.com/video",
    "instagram": "site:instagram.com/reel",
    "facebook": "site:facebook.com/reel OR site:fb.watch",
    "linkedin": "site:linkedin.com",
    "vimeo": "site:vimeo.com",
    "dailymotion": "site:dailymotion.com",
}


@dataclass
class Video:
    title: str
    url: str
    platform: str
    channel: str
    duration: str
    thumbnail: str


def parse_duration_seconds(duration: str | None) -> int | None:
    if not duration:
        return None
    parts = duration.strip().split(":")
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None
    if len(nums) == 1:
        return nums[0]
    if len(nums) == 2:
        return nums[0] * 60 + nums[1]
    if len(nums) == 3:
        return nums[0] * 3600 + nums[1] * 60 + nums[2]
    return None


def is_short(duration: str | None) -> bool:
    seconds = parse_duration_seconds(duration)
    if seconds is None:
        return True
    return 0 < seconds <= SHORT_MAX_SECONDS


def detect_platform(url: str, publisher: str = "") -> str:
    try:
        host = urlparse(url).hostname or ""
        host = host.lower().removeprefix("www.")
    except Exception:
        host = ""
    for pid, _label, domains in PLATFORMS:
        if pid == "other":
            continue
        if any(host == d or host.endswith("." + d) for d in domains):
            return pid
    hint = (publisher or "").lower()
    for pid, label, _domains in PLATFORMS:
        if pid != "other" and label.lower() in hint:
            return pid
    return "other"


def youtube_thumb(url: str) -> str:
    match = re.search(r"(?:v=|/shorts/|youtu\.be/)([\w-]{6,})", url)
    if not match:
        return ""
    return f"https://i.ytimg.com/vi/{match.group(1)}/hqdefault.jpg"


def http_get_bytes(url: str, timeout: float = 12.0) -> bytes | None:
    if not url:
        return None
    headers = {"User-Agent": "Mozilla/5.0 ShortSeek/1.0"}
    try:
        if requests is not None:
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            return response.content
        req = Request(url, headers=headers)
        with urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception:
        return None


def load_settings() -> dict:
    defaults = {"blacklist": {pid: False for pid, _label, _domains in PLATFORMS}}
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        defaults["blacklist"].update(data.get("blacklist") or {})
    except Exception:
        pass
    return defaults


def save_settings(settings: dict) -> None:
    try:
        SETTINGS_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    except Exception:
        pass


def search_youtube_innertube(query: str) -> list[Video]:
    """Keyless YouTube search via the public Innertube web client."""
    if requests is None:
        return []
    try:
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        home = session.get("https://www.youtube.com/", timeout=15)
        match = re.search(r'"INNERTUBE_API_KEY":"([^"]+)"', home.text)
        api_key = match.group(1) if match else "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8"
        payload = {
            "context": {
                "client": {
                    "clientName": "WEB",
                    "clientVersion": "2.20240101.00.00",
                    "hl": "en",
                    "gl": "US",
                }
            },
            "query": f"{query} #shorts",
        }
        resp = session.post(
            f"https://www.youtube.com/youtubei/v1/search?prettyPrint=false&key={api_key}",
            json=payload,
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    out: list[Video] = []
    seen: set[str] = set()

    def add(vid: str, title: str, channel: str = "", duration: str = "", thumb: str = "") -> None:
        if not vid or vid in seen:
            return
        if duration and not is_short(duration):
            return
        seen.add(vid)
        out.append(
            Video(
                title=title or "Untitled video",
                url=f"https://www.youtube.com/shorts/{vid}",
                platform="youtube",
                channel=channel or "YouTube",
                duration=duration or "",
                thumbnail=thumb or f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
            )
        )

    def walk(node: object) -> None:
        if isinstance(node, dict):
            short = node.get("shortsLockupViewModel")
            if isinstance(short, dict):
                endpoint = (
                    ((short.get("onTap") or {}).get("innertubeCommand") or {}).get(
                        "reelWatchEndpoint"
                    )
                    or {}
                )
                vid = endpoint.get("videoId") or ""
                if not vid:
                    entity = short.get("entityId") or ""
                    vid = entity.replace("shorts-shelf-item-", "")
                accessibility = short.get("accessibilityText") or ""
                title = accessibility.split(",")[0].strip() if accessibility else ""
                thumbs = ((endpoint.get("thumbnail") or {}).get("thumbnails")) or []
                thumb = thumbs[-1]["url"] if thumbs else ""
                # Prefer vertical frame thumb when present
                add(vid, title, thumb=thumb)

            renderer = node.get("videoRenderer")
            if isinstance(renderer, dict) and "videoId" in renderer:
                vid = renderer["videoId"]
                title = ""
                runs = (renderer.get("title") or {}).get("runs") or []
                if runs:
                    title = "".join(part.get("text", "") for part in runs)
                length = ((renderer.get("lengthText") or {}).get("simpleText")) or ""
                channel = ""
                owner = renderer.get("ownerText") or renderer.get("shortBylineText") or {}
                owner_runs = owner.get("runs") or []
                if owner_runs:
                    channel = owner_runs[0].get("text") or ""
                thumbs = (renderer.get("thumbnail") or {}).get("thumbnails") or []
                thumb = thumbs[-1]["url"] if thumbs else ""
                add(vid, title, channel=channel, duration=length, thumb=thumb)

            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(data)
    return out


def search_ddg_videos(query: str) -> list[Video]:
    if DDGS is None:
        return []
    out: list[Video] = []
    try:
        with DDGS() as ddgs:
            items = list(ddgs.videos(f"{query} shorts", max_results=40))
    except Exception:
        return []
    for item in items:
        url = item.get("content") or item.get("url") or ""
        if not url:
            continue
        duration = item.get("duration") or ""
        if not is_short(duration):
            continue
        publisher = item.get("publisher") or ""
        platform = detect_platform(url, publisher)
        out.append(
            Video(
                title=item.get("title") or "Untitled video",
                url=url,
                platform=platform,
                channel=item.get("uploader") or publisher or platform,
                duration=duration,
                thumbnail=item.get("image") or youtube_thumb(url),
            )
        )
    return out


def search_platform_pages(query: str, blacklist: dict[str, bool]) -> list[Video]:
    if DDGS is None:
        return []
    out: list[Video] = []
    try:
        with DDGS() as ddgs:
            for platform, site_q in SITE_QUERIES.items():
                if blacklist.get(platform):
                    continue
                try:
                    results = list(ddgs.text(f"{query} {site_q}", max_results=8))
                except Exception:
                    continue
                for item in results:
                    url = item.get("href") or item.get("link") or ""
                    if not url:
                        continue
                    detected = detect_platform(url)
                    if detected not in (platform, "other"):
                        continue
                    out.append(
                        Video(
                            title=item.get("title") or "Untitled video",
                            url=url,
                            platform=platform,
                            channel=urlparse(url).hostname or platform,
                            duration="",
                            thumbnail=youtube_thumb(url),
                        )
                    )
    except Exception:
        return out
    return out


def dedupe(videos: list[Video]) -> list[Video]:
    seen: set[str] = set()
    out: list[Video] = []
    for video in videos:
        key = re.sub(r"[?#].*$", "", video.url).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(video)
    return out


def search_short_videos(
    query: str, blacklist: dict[str, bool]
) -> tuple[list[Video], list[str]]:
    errors: list[str] = []
    collected: list[Video] = []

    def run(label: str, fn: Callable[[], list[Video]]) -> None:
        try:
            collected.extend(fn())
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{label}: {exc}")

    run("DuckDuckGo videos", lambda: search_ddg_videos(query))
    if not blacklist.get("youtube"):
        run("YouTube", lambda: search_youtube_innertube(query))
    run("Platform pages", lambda: search_platform_pages(query, blacklist))

    filtered = [v for v in dedupe(collected) if not blacklist.get(v.platform, False)]
    filtered.sort(key=lambda v: (bool(v.duration), bool(v.thumbnail)), reverse=True)
    return filtered[:MAX_RESULTS], errors


class ShortSeekApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1100x760")
        self.minsize(860, 600)
        self.configure(bg="#121417")

        self.settings = load_settings()
        self.blacklist_vars = {
            pid: tk.BooleanVar(value=bool(self.settings["blacklist"].get(pid, False)))
            for pid, _label, _domains in PLATFORMS
            if pid != "other"
        }
        self.photo_cache: list = []
        self._search_token = 0
        self.sources_visible = False

        self._build_style()
        self._build_ui()
        self._refresh_sources_badge()

    def _build_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Root.TFrame", background="#121417")
        style.configure("Card.TFrame", background="#1a1d23")
        style.configure(
            "Title.TLabel",
            background="#121417",
            foreground="#f1f3f4",
            font=("Segoe UI", 18, "bold"),
        )
        style.configure(
            "Muted.TLabel",
            background="#121417",
            foreground="#9aa0a6",
            font=("Segoe UI", 10),
        )
        style.configure(
            "Card.TLabel",
            background="#1a1d23",
            foreground="#f1f3f4",
            font=("Segoe UI", 9),
        )
        style.configure(
            "Accent.TButton",
            font=("Segoe UI", 10, "bold"),
            padding=(14, 8),
        )
        style.configure("TCheckbutton", background="#1a1d23", foreground="#f1f3f4")
        style.map("TCheckbutton", background=[("active", "#1a1d23")])

    def _build_ui(self) -> None:
        root = ttk.Frame(self, style="Root.TFrame", padding=16)
        root.pack(fill="both", expand=True)

        header = ttk.Frame(root, style="Root.TFrame")
        header.pack(fill="x")
        ttk.Label(header, text=APP_NAME, style="Title.TLabel").pack(side="left")
        ttk.Label(
            header,
            text="  Short videos from across the web",
            style="Muted.TLabel",
        ).pack(side="left", padx=(8, 0))
        self.sources_btn = ttk.Button(
            header, text="Sources", command=self.toggle_sources
        )
        self.sources_btn.pack(side="right")

        search_row = ttk.Frame(root, style="Root.TFrame")
        search_row.pack(fill="x", pady=(16, 8))
        self.query_var = tk.StringVar()
        entry = ttk.Entry(search_row, textvariable=self.query_var, font=("Segoe UI", 12))
        entry.pack(side="left", fill="x", expand=True, ipady=6)
        entry.bind("<Return>", lambda _event: self.start_search())
        ttk.Button(
            search_row, text="Search", style="Accent.TButton", command=self.start_search
        ).pack(side="left", padx=(10, 0))
        entry.focus_set()

        self.sources_panel = ttk.Frame(root, style="Card.TFrame", padding=12)
        ttk.Label(
            self.sources_panel,
            text="Blacklist sites — turn a toggle on to hide that site",
            style="Card.TLabel",
        ).pack(anchor="w", pady=(0, 8))
        for pid, label, _domains in PLATFORMS:
            if pid == "other":
                continue
            row = ttk.Frame(self.sources_panel, style="Card.TFrame")
            row.pack(fill="x", pady=3)
            color = PLATFORM_COLORS[pid]
            swatch = tk.Canvas(
                row, width=12, height=12, bg="#1a1d23", highlightthickness=0
            )
            swatch.create_oval(1, 1, 11, 11, fill=color, outline=color)
            swatch.pack(side="left", padx=(0, 8))
            ttk.Label(row, text=label, style="Card.TLabel").pack(side="left")
            ttk.Checkbutton(
                row,
                text="Blacklist",
                variable=self.blacklist_vars[pid],
                command=self.on_blacklist_change,
            ).pack(side="right")

        self.status_var = tk.StringVar(
            value="Type a keyword, then Search. Use Sources to blacklist sites."
        )
        self.status_label = ttk.Label(
            root, textvariable=self.status_var, style="Muted.TLabel"
        )
        self.status_label.pack(anchor="w", pady=(4, 8))

        canvas_wrap = ttk.Frame(root, style="Root.TFrame")
        canvas_wrap.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(canvas_wrap, bg="#121417", highlightthickness=0)
        scrollbar = ttk.Scrollbar(
            canvas_wrap, orient="vertical", command=self.canvas.yview
        )
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.grid_frame = ttk.Frame(self.canvas, style="Root.TFrame")
        self.canvas_window = self.canvas.create_window(
            (0, 0), window=self.grid_frame, anchor="nw"
        )
        self.grid_frame.bind(
            "<Configure>",
            lambda _event: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all(
            "<Button-4>", lambda _event: self.canvas.yview_scroll(-1, "units")
        )
        self.canvas.bind_all(
            "<Button-5>", lambda _event: self.canvas.yview_scroll(1, "units")
        )

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self.canvas_window, width=event.width)

    def _on_mousewheel(self, event: tk.Event) -> None:
        delta = -1 if getattr(event, "delta", 0) > 0 else 1
        self.canvas.yview_scroll(delta, "units")

    def toggle_sources(self) -> None:
        if self.sources_visible:
            self.sources_panel.pack_forget()
            self.sources_visible = False
        else:
            self.sources_panel.pack(fill="x", pady=(0, 8), before=self.status_label)
            self.sources_visible = True
        self._refresh_sources_badge()

    def _refresh_sources_badge(self) -> None:
        blocked = sum(1 for var in self.blacklist_vars.values() if var.get())
        self.sources_btn.configure(
            text=f"Sources ({blocked} blocked)" if blocked else "Sources"
        )

    def on_blacklist_change(self) -> None:
        self.settings["blacklist"] = {
            pid: var.get() for pid, var in self.blacklist_vars.items()
        }
        self.settings["blacklist"].setdefault("other", False)
        save_settings(self.settings)
        self._refresh_sources_badge()

    def start_search(self) -> None:
        query = self.query_var.get().strip()
        if not query:
            return
        if DDGS is None and requests is None:
            messagebox.showerror(
                APP_NAME,
                "Install dependencies first:\n\n"
                "pip install duckduckgo-search pillow requests",
            )
            return

        self._search_token += 1
        token = self._search_token
        self.status_var.set("Searching short videos…")
        self._clear_results()

        blacklist = {pid: var.get() for pid, var in self.blacklist_vars.items()}
        blacklist["other"] = False

        def worker() -> None:
            videos, errors = search_short_videos(query, blacklist)
            self.after(0, lambda: self._show_results(token, videos, errors))

        threading.Thread(target=worker, daemon=True).start()

    def _clear_results(self) -> None:
        for child in self.grid_frame.winfo_children():
            child.destroy()
        self.photo_cache.clear()

    def _show_results(
        self, token: int, videos: list[Video], errors: list[str]
    ) -> None:
        if token != self._search_token:
            return
        self._clear_results()
        if not videos:
            message = (
                "No short videos found. Try another keyword or unblock sites in Sources."
            )
            if errors:
                message += "\n" + " · ".join(errors[:2])
            self.status_var.set(message)
            return

        note = f"Found {len(videos)} short videos"
        if errors:
            note += f"  (some sources failed: {errors[0]})"
        self.status_var.set(note)

        for index, video in enumerate(videos):
            self._add_card(index, video)

    def _add_card(self, index: int, video: Video) -> None:
        row, col = divmod(index, COLUMNS)
        card = tk.Frame(self.grid_frame, bg="#1a1d23", padx=6, pady=6)
        card.grid(row=row, column=col, padx=8, pady=10, sticky="n")

        thumb_wrap = tk.Frame(card, bg="#23272f", width=THUMB_W, height=THUMB_H)
        thumb_wrap.pack()
        thumb_wrap.pack_propagate(False)

        thumb_label = tk.Label(
            thumb_wrap,
            text="▶",
            bg=PLATFORM_COLORS.get(video.platform, "#9AA0A6"),
            fg="#ffffff",
            font=("Segoe UI", 28, "bold"),
            cursor="hand2",
        )
        thumb_label.pack(fill="both", expand=True)
        thumb_label.bind("<Button-1>", lambda _e, u=video.url: webbrowser.open(u))

        if video.duration:
            tk.Label(
                thumb_wrap,
                text=video.duration,
                bg="#000000",
                fg="#ffffff",
                font=("Segoe UI", 8, "bold"),
                padx=4,
                pady=1,
            ).place(x=8, rely=1.0, anchor="sw", y=-8)

        meta = tk.Frame(card, bg="#1a1d23")
        meta.pack(fill="x", pady=(8, 0))
        platform_label = next(
            (label for pid, label, _domains in PLATFORMS if pid == video.platform),
            "Other",
        )
        tk.Label(
            meta,
            text=f"{platform_label} · {video.channel}",
            bg="#1a1d23",
            fg="#9aa0a6",
            font=("Segoe UI", 8),
            wraplength=THUMB_W,
            justify="left",
            anchor="w",
        ).pack(fill="x")
        title = tk.Label(
            meta,
            text=video.title,
            bg="#1a1d23",
            fg="#f1f3f4",
            font=("Segoe UI", 9),
            wraplength=THUMB_W,
            justify="left",
            anchor="w",
            cursor="hand2",
        )
        title.pack(fill="x", pady=(2, 0))
        title.bind("<Button-1>", lambda _e, u=video.url: webbrowser.open(u))

        if video.thumbnail and Image is not None and ImageTk is not None:
            threading.Thread(
                target=self._load_thumb,
                args=(thumb_label, video.thumbnail),
                daemon=True,
            ).start()

    def _load_thumb(self, label: tk.Label, url: str) -> None:
        raw = http_get_bytes(url)
        if not raw or Image is None or ImageTk is None:
            return
        try:
            img = Image.open(BytesIO(raw)).convert("RGB")
            img = img.resize((THUMB_W, THUMB_H), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)

            def apply() -> None:
                if not label.winfo_exists():
                    return
                self.photo_cache.append(photo)
                label.configure(image=photo, text="")

            self.after(0, apply)
        except Exception:
            return


def main() -> None:
    app = ShortSeekApp()
    app.mainloop()


if __name__ == "__main__":
    main()
