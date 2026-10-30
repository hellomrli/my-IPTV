import json
import tempfile
import unittest
from pathlib import Path

from scripts import build_playlists as bp
from scripts import sync_iptv as sync
from scripts.catchup_server import ChannelCatalog


PLAYLIST = '''#EXTM3U x-tvg-url="https://epg.test/epg.xml"
#EXTINF:-1 tvg-id="1" tvg-logo="logo.png" group-title="TV",Channel
http://gateway.test/123/index.m3u8?servicetype=1

#EXTINF:-1 tvg-id="1",Channel4K
http://gateway.test/456/index.m3u8?servicetype=1
#EXTINF:-1 tvg-id="2",External
https://external.test/live.m3u8
'''
CONFIG = {"base_url": "http://server.test:8081", "format": "ku9", "days_by_channel": {"Channel": 1}}


class BuildTests(unittest.TestCase):
    def test_only_allowlisted_variants_have_catchup(self):
        catchup, direct = bp.build_playlists(PLAYLIST, CONFIG)
        self.assertEqual(catchup.count('catchup="default"'), 1)
        self.assertIn('/catchup/123/${(b)yyyyMMddHHmmss}/${(e)yyyyMMddHHmmss}/index.m3u8', catchup)
        self.assertEqual(bp.channel_days(PLAYLIST, CONFIG), {"123": 1})
        self.assertIn('x-tvg-url="https://epg.test/epg.xml"', catchup)
        self.assertIn('tvg-id="1" tvg-logo="logo.png" group-title="TV"', catchup)
        self.assertEqual([entry.url for entry in sync.parse_m3u(catchup)[1]],
                         [entry.url for entry in sync.parse_m3u(PLAYLIST)[1]])
        self.assertIn("https://external.test/live.m3u8", direct)
        self.assertIn(f"{bp.DIRECT_BASE}/123/index.m3u8?servicetype=1", direct)

    def test_direct_operator_path_is_preserved(self):
        special = "http://cdnrrs.gx.chinamobile.com/PLTV/7777777G/7777777/224/123/index.m3u8?servicetype=1"
        playlist = PLAYLIST.replace("http://gateway.test/123/index.m3u8?servicetype=1", special)
        self.assertIn(special, bp.build_playlists(playlist, CONFIG)[1])

    def test_unix_placeholders_and_reverse_proxy_prefix(self):
        config = {**CONFIG, "base_url": "http://server.test/iptv/", "format": "unix"}
        catchup, _ = bp.build_playlists(PLAYLIST, config)
        self.assertIn("http://server.test/iptv/catchup/123/{utc}/{utcend}/index.m3u8", catchup)

    def test_output_is_idempotent_and_does_not_duplicate_attributes(self):
        first, _ = bp.build_playlists(PLAYLIST, CONFIG)
        second, _ = bp.build_playlists(first, CONFIG)
        self.assertEqual(first, second)

    def test_disabling_channel_removes_old_catchup_attributes(self):
        first, _ = bp.build_playlists(PLAYLIST, CONFIG)
        disabled = {**CONFIG, "days_by_channel": {}}
        result, _ = bp.build_playlists(first, disabled)
        self.assertNotIn('catchup=', result)
        self.assertNotIn('catchup-source=', result)

    def test_new_channel_id_follows_local_name_not_shared_epg_id(self):
        result, _ = bp.build_playlists(PLAYLIST.replace("/123/", "/999/"), CONFIG)
        self.assertIn("/catchup/999/", result)
        self.assertNotIn("/catchup/123/", result)
        self.assertNotIn("/catchup/456/", result)

    def test_keeps_channel_options_blank_lines_and_commas_in_attributes(self):
        playlist = PLAYLIST.replace('tvg-logo="logo.png"', 'tvg-logo="https://logo.test/a,b.png"')
        playlist = playlist.replace("http://gateway.test/123", "#EXTVLCOPT:http-user-agent=test\nhttp://gateway.test/123")
        catchup, direct = bp.build_playlists(playlist, CONFIG)
        self.assertIn('#EXTVLCOPT:http-user-agent=test', catchup)
        self.assertIn('#EXTVLCOPT:http-user-agent=test', direct)
        self.assertIn('tvg-logo="https://logo.test/a,b.png"', catchup)
        self.assertIn("\n\n#EXTINF:", catchup)

    def test_invalid_base_urls(self):
        for value in (None, [], "file:///etc/passwd", "http://user:pass@host", "http://", "http://host/?q=1", "http://host/#bad", 'http://host/"\n', "http://host:abc", "http://host:65536"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                bp.validate_base_url(value)

    def test_bad_retention_and_format_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            for value in (-1, 0, 8, True, "1"):
                path.write_text(json.dumps({**CONFIG, "days_by_channel": {"Channel": value}}))
                with self.subTest(value=value), self.assertRaises(ValueError):
                    bp.load_config(path)
            path.write_text(json.dumps({**CONFIG, "format": "unknown"}))
            with self.assertRaises(ValueError):
                bp.load_config(path)

    def test_empty_allowlist_disables_all_channels(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps({**CONFIG, "days_by_channel": {}}))
            config = bp.load_config(path)
            self.assertEqual(bp.channel_days(PLAYLIST, config), {})
            self.assertNotIn('catchup-source=', bp.build_playlists(PLAYLIST, config)[0])

    def test_configuration_requires_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            for config in ([], None, "invalid"):
                path.write_text(json.dumps(config))
                with self.subTest(config=config), self.assertRaises(ValueError):
                    bp.load_config(path)

    def test_committed_variants_match_generator(self):
        config = bp.load_config(bp.ROOT / "catchup.json")
        source = (bp.ROOT / "IPTV.m3u").read_text(encoding="utf-8")
        catchup, direct = bp.build_playlists(source, config)
        self.assertEqual((bp.ROOT / "IPTV-catchup.m3u").read_text(encoding="utf-8"), catchup)
        self.assertEqual((bp.ROOT / "gx.m3u").read_text(encoding="utf-8"), direct)
        self.assertEqual(len(sync.parse_m3u(catchup)[1]), len(sync.parse_m3u(source)[1]))
        for entry in sync.parse_m3u(catchup)[1]:
            if 'catchup-source=' in entry.extinf:
                self.assertIn(f"/catchup/{entry.channel_id}/", entry.extinf)


class SyncTests(unittest.TestCase):
    def test_sync_updates_catchup_id_without_changing_local_metadata(self):
        text, _ = bp.build_playlists(PLAYLIST, CONFIG)
        upstream = '#EXTM3U\n#EXTINF:-1,Channel\nhttp://upstream.test/999/index.m3u8\n'
        result, stats = sync.sync_playlist(text, upstream, add_missing=False)
        self.assertIn('http://gateway.test/999/index.m3u8?servicetype=1', result)
        self.assertIn('/catchup/999/', result)
        self.assertIn('tvg-logo="logo.png"', result)
        self.assertIn('tvg-id="1"', result)
        self.assertEqual(stats['updated'], 1)

    def test_added_channel_uses_first_recognizable_url(self):
        template = '#EXTM3U\n#EXTINF:-1,External\nhttps://external.test/live.m3u8\n' + PLAYLIST
        upstream = '#EXTM3U\n#EXTINF:-1,New\nhttp://upstream.test/999/index.m3u8\n'
        result, stats = sync.sync_playlist(template, upstream, add_missing=True)
        self.assertEqual(stats["added"], 1)
        self.assertIn('http://gateway.test/999/index.m3u8?servicetype=1', result)

    def test_channel_number_stays_before_name_when_no_attributes(self):
        result = sync.with_channel_number('#EXTINF:-1,Channel', 12)
        self.assertEqual(result, '#EXTINF:-1 tvg-chno="12",Channel')

    def test_channel_name_with_commas(self):
        extinf = '#EXTINF:-1 tvg-logo="https://host/a,b.png",News, International'
        self.assertEqual(sync.channel_name(extinf), 'News, International')

    def test_archive_metadata_url_can_contain_comma(self):
        extinf = '#EXTINF:-1 catchup-source="http://host/123/index.m3u8?a=1,2",News, International'
        self.assertEqual(sync.update_catchup_channel(extinf, "123", "456"),
                         extinf.replace('/123/', '/456/'))

    def test_sync_is_idempotent(self):
        first, _ = sync.sync_playlist(PLAYLIST, PLAYLIST, True)
        second, _ = sync.sync_playlist(first, PLAYLIST, True)
        self.assertEqual(first, second)


class CatalogTests(unittest.TestCase):
    def test_reloads_changed_channel_ids_and_retention(self):
        with tempfile.TemporaryDirectory() as tmp:
            playlist = Path(tmp) / "live.m3u"
            config = Path(tmp) / "config.json"
            playlist.write_text(PLAYLIST)
            config.write_text(json.dumps(CONFIG))
            catalog = ChannelCatalog(playlist, config)
            self.assertEqual(catalog.get("123"), 1)
            playlist.write_text(PLAYLIST.replace('/123/', '/123456/'))
            self.assertEqual(catalog.get("123456"), 1)
            self.assertEqual(catalog.get("123"), 0)
            config.write_text(json.dumps({**CONFIG, "days_by_channel": {"Channel": 7}}))
            self.assertEqual(catalog.get("123456"), 7)


if __name__ == "__main__":
    unittest.main()
