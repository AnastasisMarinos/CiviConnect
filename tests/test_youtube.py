import unittest
from unittest.mock import patch

from civiconnect import youtube


class YouTubeCarouselTests(unittest.TestCase):
    def test_mixed_feed_only_shows_eligible_uploads_and_fills_with_shorts(self):
        uploads = {"upload00001": "Regular upload", "upload00002": "Older upload"}
        shorts = {"shorts00001": "Short"}
        feed = {
            "stream00001": "Live now",
            "stream00002": "Upcoming event",
            "stream00003": "Replay",
            "upload00001": "Latest upload",
        }
        with (
            patch.object(youtube, "tab_titles", side_effect=[uploads, shorts]) as tabs,
            patch.object(youtube, "feed_titles", return_value=feed),
        ):
            rows = youtube.channel_videos.__wrapped__("test-channel", 0)

        self.assertEqual([call.args[1] for call in tabs.call_args_list], ["videos", "shorts"])
        self.assertEqual(rows, [
            {"youtube_id": "upload00001", "title": "Latest upload"},
            {"youtube_id": "shorts00001", "title": "Short"},
            {"youtube_id": "upload00002", "title": "Older upload"},
        ])
