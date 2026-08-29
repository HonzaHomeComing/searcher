#!/usr/bin/env python3
"""
Short Seek — windowed short-video search (any site, under 5 minutes)
with a custom website blacklist.

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
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen
from html import unescape
from collections import defaultdict

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
MAX_RESULTS = 40
SHORT_MAX_SECONDS = 5 * 60  # under 5 minutes
THUMB_W, THUMB_H = 160, 284
COLUMNS = 4


@dataclass
class Video:
    title: str
    url: str
    site: str
    channel: str
    duration: str
    thumbnail: str


def parse_duration_seconds(duration: str | None) -> int | None:
    if not duration:
        return None
    text = duration.strip().lower()
    # "1:23" / "1:02:03"
    if re.fullmatch(r"\d{1,2}(?::\d{2}){1,2}", text):
        parts = [int(p) for p in text.split(":")]
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    # "50 seconds", "3 minutes", "1 minute 12 seconds"
    seconds = 0
    found = False
    hours = re.search(r"(\d+)\s*hours?", text)
    mins = re.search(r"(\d+)\s*min", text)
    secs = re.search(r"(\d+)\s*sec", text)
    if hours:
        seconds += int(hours.group(1)) * 3600
        found = True
    if mins:
        seconds += int(mins.group(1)) * 60
        found = True
    if secs:
        seconds += int(secs.group(1))
        found = True
    if found:
        return seconds
    return None


def format_duration(seconds: int | None) -> str:
    if seconds is None or seconds <= 0:
        return ""
    if seconds < 3600:
        return f"{seconds // 60}:{seconds % 60:02d}"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h}:{m:02d}:{s:02d}"


def is_under_five_minutes(duration: str | None, title: str = "") -> bool:
    if re.search(r"\bLIVE\b|24/7", title or "", flags=re.I):
        return False
    seconds = parse_duration_seconds(duration)
    if seconds is None:
        # Shorts shelves often omit length; keep them. Long/unknown live streams filtered above.
        return True
    return 0 < seconds <= SHORT_MAX_SECONDS


def normalize_domain(value: str) -> str:
    value = (value or "").strip().lower()
    if not value:
        return ""
    if "://" not in value:
        value = "https://" + value
    try:
        host = urlparse(value).hostname or ""
    except Exception:
        host = value
    host = host.removeprefix("www.")
    # Allow pasting a bare domain without scheme parsing weirdness
    if not host:
        host = value.split("/")[0].removeprefix("www.")
    return host.strip(".")


def site_from_url(url: str) -> str:
    return normalize_domain(url)


def youtube_thumb(url: str) -> str:
    match = re.search(r"(?:v=|/shorts/|youtu\.be/)([\w-]{6,})", url)
    if not match:
        return ""
    return f"https://i.ytimg.com/vi/{match.group(1)}/hqdefault.jpg"


def is_blacklisted(domain: str, blacklist: list[str]) -> bool:
    domain = normalize_domain(domain)
    if not domain:
        return False
    for blocked in blacklist:
        blocked = normalize_domain(blocked)
        if not blocked:
            continue
        if domain == blocked or domain.endswith("." + blocked):
            return True
    return False


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
    defaults: dict = {"blacklist": []}
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        raw = data.get("blacklist") or []
        # Migrate old platform-map settings if present
        if isinstance(raw, dict):
            raw = [k for k, v in raw.items() if v and k != "other"]
            # map old ids to domains
            mapping = {
                "youtube": "youtube.com",
                "tiktok": "tiktok.com",
                "instagram": "instagram.com",
                "facebook": "facebook.com",
                "linkedin": "linkedin.com",
                "vimeo": "vimeo.com",
                "dailymotion": "dailymotion.com",
            }
            raw = [mapping.get(x, x) for x in raw]
        defaults["blacklist"] = sorted(
            {normalize_domain(x) for x in raw if normalize_domain(x)}
        )
    except Exception:
        pass
    return defaults


def save_settings(settings: dict) -> None:
    try:
        clean = {
            "blacklist": sorted(
                {normalize_domain(x) for x in settings.get("blacklist", []) if normalize_domain(x)}
            )
        }
        SETTINGS_PATH.write_text(json.dumps(clean, indent=2), encoding="utf-8")
    except Exception:
        pass


def parse_bing_aria(label: str) -> tuple[str, str, str]:
    """Parse Bing video aria-label into title, duration, channel."""
    parts = [p.strip() for p in label.split("·")]
    title = parts[0] if parts else label
    # Strip trailing "from YouTube" style suffixes in the title segment
    title = re.sub(r"\s+from\s+\w[\w\s]*$", "", title, flags=re.I).strip()
    duration = ""
    channel = ""
    for part in parts[1:]:
        low = part.lower()
        if low.startswith("duration"):
            duration = part.split(":", 1)[-1].strip()
        elif low.startswith("uploaded by"):
            channel = part.split("by", 1)[-1].strip()
    seconds = parse_duration_seconds(duration)
    return title, format_duration(seconds) if seconds else duration, channel


def search_bing_videos(query: str) -> list[Video]:
    """
    Open-web short video search via Bing Videos (any publisher/domain).
    Uses the short-duration filter, then keeps clips under 5 minutes.
    """
    if requests is None:
        return []
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    # Several query shapes help surface non-YouTube publishers on the open web.
    query_variants = [
        query,
        f"{query} clip",
        f"{query} short video",
        f"{query} reel OR shorts OR tiktok OR instagram",
    ]
    out: list[Video] = []
    seen: set[str] = set()

    for variant in query_variants:
        url = (
            "https://www.bing.com/videos/search?"
            f"q={quote_plus(variant)}&qft=+filterui:duration-short"
        )
        try:
            html = requests.get(url, headers=headers, timeout=20).text
        except Exception:
            continue

        metas = re.findall(r'mmeta="(\{&quot;.*?&quot;\})"', html)
        arias = re.findall(r'aria-label="([^"]+)"[^>]*class="mc_vtvc_link"', html)

        for index, raw in enumerate(metas):
            try:
                meta = json.loads(unescape(raw))
            except Exception:
                continue
            video_url = meta.get("murl") or meta.get("pgurl") or ""
            if not video_url:
                continue
            key = video_url.strip().lower()
            if key in seen:
                continue
            seen.add(key)

            title = ""
            duration = ""
            channel = ""
            if index < len(arias):
                title, duration, channel = parse_bing_aria(arias[index])
            if not is_under_five_minutes(duration, title):
                continue

            site = site_from_url(video_url)
            thumb = meta.get("turl") or youtube_thumb(video_url)
            # Bing thumbs sometimes need unescaping
            thumb = unescape(thumb or "")
            out.append(
                Video(
                    title=title or "Untitled video",
                    url=video_url,
                    site=site,
                    channel=channel or site,
                    duration=duration,
                    thumbnail=thumb,
                )
            )

    return out


def search_ddg_videos(query: str) -> list[Video]:
    if DDGS is None:
        return []
    try:
        with DDGS() as ddgs:
            items = list(ddgs.videos(query, max_results=50))
    except Exception:
        return []

    out: list[Video] = []
    for item in items:
        url = item.get("content") or item.get("url") or ""
        if not url:
            continue
        duration = item.get("duration") or ""
        if not is_under_five_minutes(duration, item.get("title") or ""):
            continue
        site = site_from_url(url)
        out.append(
            Video(
                title=item.get("title") or "Untitled video",
                url=url,
                site=site,
                channel=item.get("uploader") or item.get("publisher") or site,
                duration=duration,
                thumbnail=item.get("image") or youtube_thumb(url),
            )
        )
    return out


def search_web_pages_for_videos(query: str) -> list[Video]:
    """Fallback: web search hits that look like video pages on any domain."""
    if DDGS is None:
        return []
    patterns = (
        r"/video/",
        r"/videos/",
        r"/watch",
        r"/shorts/",
        r"/reel/",
        r"/reels/",
        r"/clip/",
        r"/clips/",
        r"vimeo\.com/\d+",
        r"youtu\.be/",
        r"tiktok\.com/.*/video/",
        r"dailymotion\.com/video/",
        r"streamable\.com/",
        r"rumble\.com/",
        r"bitchute\.com/",
        r"odysee\.com/",
        r"facebook\.com/reel/",
        r"instagram\.com/reel/",
        r"\.(mp4|webm)(?:$|\?)",
    )
    combined = re.compile("|".join(patterns), re.I)
    out: list[Video] = []
    try:
        with DDGS() as ddgs:
            items = list(
                ddgs.text(
                    f"{query} (video OR clip OR reel OR shorts OR tiktok OR vimeo)",
                    max_results=40,
                )
            )
    except Exception:
        return []

    for item in items:
        url = item.get("href") or item.get("link") or ""
        if not url or not combined.search(url):
            continue
        site = site_from_url(url)
        out.append(
            Video(
                title=item.get("title") or "Untitled video",
                url=url,
                site=site,
                channel=site,
                duration="",
                thumbnail=youtube_thumb(url),
            )
        )
    return out


def search_youtube_innertube(query: str) -> list[Video]:
    """Keyless YouTube search for short clips via Innertube."""
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

    def add(
        vid: str,
        title: str,
        channel: str = "",
        duration: str = "",
        thumb: str = "",
    ) -> None:
        if not vid or vid in seen:
            return
        if duration and not is_under_five_minutes(duration, title):
            return
        seen.add(vid)
        out.append(
            Video(
                title=title or "Untitled video",
                url=f"https://www.youtube.com/watch?v={vid}",
                site="youtube.com",
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


def dedupe(videos: list[Video]) -> list[Video]:
    seen: set[str] = set()
    out: list[Video] = []
    for video in videos:
        key = video.url.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(video)
    return out


def diversify_by_site(videos: list[Video], limit: int) -> list[Video]:
    """Round-robin across domains so one site cannot fill the whole grid."""
    buckets: dict[str, list[Video]] = defaultdict(list)
    for video in videos:
        buckets[video.site or "unknown"].append(video)

    # Prefer sites with fewer items first when picking order of buckets? 
    # Actually rotate through all sites fairly.
    site_order = sorted(buckets.keys(), key=lambda s: (s == "youtube.com", s))
    out: list[Video] = []
    while len(out) < limit and any(buckets.values()):
        for site in site_order:
            if not buckets[site]:
                continue
            out.append(buckets[site].pop(0))
            if len(out) >= limit:
                break
    return out


def search_videos(query: str, blacklist: list[str]) -> tuple[list[Video], list[str]]:
    errors: list[str] = []
    collected: list[Video] = []

    for label, fn in (
        ("Open web (Bing)", lambda: search_bing_videos(query)),
        ("Open web (DuckDuckGo videos)", lambda: search_ddg_videos(query)),
        ("Open web pages", lambda: search_web_pages_for_videos(query)),
        ("YouTube", lambda: search_youtube_innertube(query)),
    ):
        try:
            collected.extend(fn())
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{label}: {exc}")

    filtered = [
        v
        for v in dedupe(collected)
        if not is_blacklisted(v.site, blacklist)
        and is_under_five_minutes(v.duration, v.title)
    ]
    # Prefer items that have a known duration, then mix sites.
    filtered.sort(key=lambda v: (bool(v.duration), bool(v.thumbnail)), reverse=True)
    mixed = diversify_by_site(filtered, MAX_RESULTS)
    return mixed, errors


class ShortSeekApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1100x760")
        self.minsize(860, 600)
        self.configure(bg="#121417")

        self.settings = load_settings()
        self.blacklist: list[str] = list(self.settings.get("blacklist") or [])
        self.photo_cache: list = []
        self._search_token = 0
        self.blacklist_visible = False
        self._last_videos: list[Video] = []

        self._build_style()
        self._build_ui()
        self._refresh_blacklist_btn()

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

    def _build_ui(self) -> None:
        root = ttk.Frame(self, style="Root.TFrame", padding=16)
        root.pack(fill="both", expand=True)

        header = ttk.Frame(root, style="Root.TFrame")
        header.pack(fill="x")
        ttk.Label(header, text=APP_NAME, style="Title.TLabel").pack(side="left")
        ttk.Label(
            header,
            text="  Whole web · videos under 5 minutes",
            style="Muted.TLabel",
        ).pack(side="left", padx=(8, 0))
        self.blacklist_btn = ttk.Button(
            header, text="Blacklist", command=self.toggle_blacklist_panel
        )
        self.blacklist_btn.pack(side="right")

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

        # Custom blacklist panel (hidden until opened)
        self.blacklist_panel = ttk.Frame(root, style="Card.TFrame", padding=12)
        ttk.Label(
            self.blacklist_panel,
            text="Blacklist any website — results from these domains are hidden",
            style="Card.TLabel",
        ).pack(anchor="w", pady=(0, 8))

        add_row = ttk.Frame(self.blacklist_panel, style="Card.TFrame")
        add_row.pack(fill="x", pady=(0, 8))
        self.domain_var = tk.StringVar()
        domain_entry = ttk.Entry(add_row, textvariable=self.domain_var)
        domain_entry.pack(side="left", fill="x", expand=True, ipady=3)
        domain_entry.bind("<Return>", lambda _e: self.add_blacklist_domain())
        ttk.Button(add_row, text="Add site", command=self.add_blacklist_domain).pack(
            side="left", padx=(8, 0)
        )

        list_wrap = ttk.Frame(self.blacklist_panel, style="Card.TFrame")
        list_wrap.pack(fill="x")
        self.blacklist_list = tk.Listbox(
            list_wrap,
            height=6,
            bg="#23272f",
            fg="#f1f3f4",
            selectbackground="#4fc3a8",
            selectforeground="#06110e",
            highlightthickness=0,
            borderwidth=0,
            font=("Segoe UI", 10),
        )
        self.blacklist_list.pack(side="left", fill="x", expand=True)
        ttk.Button(list_wrap, text="Remove", command=self.remove_selected_blacklist).pack(
            side="left", padx=(8, 0), anchor="n"
        )
        self._reload_blacklist_listbox()

        self.status_var = tk.StringVar(
            value="Search the whole web for videos under 5 minutes. Blacklist any domain you want to hide."
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

    def toggle_blacklist_panel(self) -> None:
        if self.blacklist_visible:
            self.blacklist_panel.pack_forget()
            self.blacklist_visible = False
        else:
            self.blacklist_panel.pack(fill="x", pady=(0, 8), before=self.status_label)
            self.blacklist_visible = True
        self._refresh_blacklist_btn()

    def _refresh_blacklist_btn(self) -> None:
        n = len(self.blacklist)
        self.blacklist_btn.configure(
            text=f"Blacklist ({n})" if n else "Blacklist"
        )

    def _reload_blacklist_listbox(self) -> None:
        self.blacklist_list.delete(0, tk.END)
        for domain in self.blacklist:
            self.blacklist_list.insert(tk.END, domain)

    def _persist_blacklist(self) -> None:
        self.blacklist = sorted({normalize_domain(d) for d in self.blacklist if d})
        self.settings["blacklist"] = list(self.blacklist)
        save_settings(self.settings)
        self._reload_blacklist_listbox()
        self._refresh_blacklist_btn()

    def add_blacklist_domain(self, domain: str | None = None) -> None:
        value = normalize_domain(domain if domain is not None else self.domain_var.get())
        if not value:
            return
        if value not in self.blacklist:
            self.blacklist.append(value)
            self._persist_blacklist()
        self.domain_var.set("")
        # Re-filter currently shown results without a new network search
        if self._last_videos:
            self._render_videos(
                [v for v in self._last_videos if not is_blacklisted(v.site, self.blacklist)]
            )

    def remove_selected_blacklist(self) -> None:
        selection = list(self.blacklist_list.curselection())
        if not selection:
            return
        # Remove from the end so indices stay valid
        for index in reversed(selection):
            domain = self.blacklist_list.get(index)
            if domain in self.blacklist:
                self.blacklist.remove(domain)
        self._persist_blacklist()

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
        self.status_var.set("Searching videos under 5 minutes…")
        self._clear_results()

        blacklist = list(self.blacklist)

        def worker() -> None:
            videos, errors = search_videos(query, blacklist)
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
        self._last_videos = list(videos)
        if not videos:
            message = (
                "No short videos found. Try another keyword, or remove sites from Blacklist."
            )
            if errors:
                message += "\n" + " · ".join(errors[:2])
            self.status_var.set(message)
            self._clear_results()
            return

        note = f"Found {len(videos)} videos under 5 minutes"
        if errors:
            note += f"  (some sources failed: {errors[0]})"
        self.status_var.set(note)
        self._render_videos(videos)

    def _render_videos(self, videos: list[Video]) -> None:
        self._clear_results()
        if not videos:
            self.status_var.set(
                "No results left after blacklist. Remove a site or search again."
            )
            return
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
            bg="#3a4568",
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
        tk.Label(
            meta,
            text=f"{video.site} · {video.channel}",
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

        tk.Button(
            meta,
            text="Blacklist site",
            command=lambda s=video.site: self.add_blacklist_domain(s),
            bg="#2a2f38",
            fg="#f1f3f4",
            activebackground="#3a4150",
            activeforeground="#ffffff",
            relief="flat",
            font=("Segoe UI", 8),
            cursor="hand2",
            padx=6,
            pady=2,
        ).pack(anchor="w", pady=(6, 0))

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
