import json
import re
from functools import lru_cache
from itertools import islice, zip_longest
from urllib.request import Request, urlopen
from xml.etree import ElementTree


VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
CAROUSEL_LIMIT = 15


def feed_titles(channel_id):
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    with urlopen(url, timeout=6) as response:
        root = ElementTree.fromstring(response.read(512 * 1024))
    atom = "{http://www.w3.org/2005/Atom}"
    yt = "{http://www.youtube.com/xml/schemas/2015}"
    return {
        video_id: entry.findtext(atom + "title")
        for entry in root.findall(atom + "entry")
        if entry.findtext(yt + "channelId") == channel_id
        and (video_id := entry.findtext(yt + "videoId"))
        and VIDEO_ID.fullmatch(video_id)
    }


def channel_tab(channel_id, name):
    url = f"https://www.youtube.com/channel/{channel_id}/{name}"
    request = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US"})
    with urlopen(request, timeout=6) as response:
        html = response.read(4 * 1024 * 1024).decode("utf-8", errors="replace")
    match = re.search(r"\bvar ytInitialData\s*=\s*(\{)", html)
    if not match:
        raise ValueError("YouTube channel data is missing")
    data, _ = json.JSONDecoder().raw_decode(html, match.start(1))
    tabs = data.get("contents", {}).get("twoColumnBrowseResultsRenderer", {}).get("tabs")
    if tabs is None:
        raise ValueError("YouTube channel tabs are missing")
    for entry in tabs:
        tab = entry.get("tabRenderer", {})
        command = tab.get("endpoint", {}).get("commandMetadata", {}).get("webCommandMetadata", {})
        if command.get("url", "").rstrip("/").endswith(f"/{name}"):
            if not tab.get("selected"):
                raise ValueError(f"YouTube did not open the {name} tab")
            return tab.get("content", {}).get("richGridRenderer", {}).get("contents", [])
    return []


def tab_titles(channel_id, name):
    titles = {}
    for entry in channel_tab(channel_id, name):
        item = entry.get("richItemRenderer", {}).get("content", {})
        if name == "shorts":
            short = item.get("shortsLockupViewModel", {})
            command = short.get("onTap", {}).get("innertubeCommand", {})
            video_id = command.get("reelWatchEndpoint", {}).get("videoId")
            title = short.get("overlayMetadata", {}).get("primaryText", {}).get("content")
        else:
            video = item.get("lockupViewModel", {})
            video_id = video.get("contentId")
            metadata = video.get("metadata", {}).get("lockupMetadataViewModel", {})
            title = metadata.get("title", {}).get("content")
        if video_id and VIDEO_ID.fullmatch(video_id):
            titles[video_id] = title or "YouTube"
    return titles


@lru_cache(maxsize=1)
def channel_videos(channel_id, cache_window):
    uploads = tab_titles(channel_id, "videos")
    shorts = tab_titles(channel_id, "shorts")
    eligible = uploads | shorts
    if not eligible:
        return []
    try:
        feed = feed_titles(channel_id)
    except (OSError, ElementTree.ParseError):
        feed = {}

    # Use the mixed feed for ordering only. YouTube lists streams on a separate tab.
    videos = {
        video_id: title or eligible[video_id]
        for video_id, title in feed.items()
        if video_id in eligible
    }
    for pair in zip_longest(uploads, shorts):
        for video_id in pair:
            if video_id is not None:
                videos.setdefault(video_id, eligible[video_id])
    return [
        {"youtube_id": video_id, "title": title}
        for video_id, title in islice(videos.items(), CAROUSEL_LIMIT)
    ]
