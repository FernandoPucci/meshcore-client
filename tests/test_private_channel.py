import asyncio
import contextlib
import io
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from meshcore import EventType

import meshcore_monitor as monitor


def result(event_type, payload):
    return SimpleNamespace(type=event_type, payload=payload)


class FakeCommands:
    def __init__(self, channels=None):
        self.channels = channels or {}
        self.sent = []

    async def get_channel(self, channel_idx):
        return self.channels.get(
            channel_idx,
            result(EventType.ERROR, {"reason": "not_found"}),
        )

    async def send_chan_msg(self, channel_idx, message):
        self.sent.append((channel_idx, message))
        return result(EventType.OK, {})


class FakeMeshCore:
    def __init__(self, channels=None):
        self.commands = FakeCommands(channels)


class PrivateChannelTests(unittest.TestCase):
    def setUp(self):
        self.original_name = monitor.MESHCORE_CHANNEL_NAME
        self.original_key = monitor.MESHCORE_CHANNEL_KEY_HEX
        self.original_bot_name = monitor.MY_NODE_NAME
        monitor.MESHCORE_CHANNEL_NAME = "RAO_MESHCORE"
        monitor.MESHCORE_CHANNEL_KEY_HEX = "7403f42915314f75bd44e4ed88b084aa"
        monitor.MY_NODE_NAME = "RAO-BOT"

    def tearDown(self):
        monitor.MESHCORE_CHANNEL_NAME = self.original_name
        monitor.MESHCORE_CHANNEL_KEY_HEX = self.original_key
        monitor.MY_NODE_NAME = self.original_bot_name

    def test_channel_key_requires_16_bytes(self):
        with self.assertRaises(ValueError):
            monitor.parse_channel_key("abcd")

    def test_resolves_exact_name_and_key_after_empty_slot(self):
        channels = {
            1: result(
                EventType.CHANNEL_INFO,
                {
                    "channel_name": "Public",
                    "channel_secret": bytes.fromhex("00" * 16),
                },
            ),
            3: result(
                EventType.CHANNEL_INFO,
                {
                    "channel_name": "RAO_MESHCORE",
                    "channel_secret": bytes.fromhex(monitor.MESHCORE_CHANNEL_KEY_HEX),
                },
            ),
        }

        channel_idx = asyncio.run(
            monitor.resolve_configured_channel(FakeMeshCore(channels), max_channels=5)
        )

        self.assertEqual(channel_idx, 3)

    def test_resolution_rejects_wrong_key(self):
        channels = {
            2: result(
                EventType.CHANNEL_INFO,
                {
                    "channel_name": "RAO_MESHCORE",
                    "channel_secret": bytes.fromhex("00" * 16),
                },
            ),
        }

        with self.assertRaisesRegex(RuntimeError, "was not found"):
            asyncio.run(
                monitor.resolve_configured_channel(FakeMeshCore(channels), max_channels=4)
            )

    def test_public_message_is_ignored(self):
        event = SimpleNamespace(
            payload={"channel_idx": 1, "text": "@[RAO-BOT] CLIMA"}
        )
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            asyncio.run(
                monitor.on_channel_message(
                    event,
                    FakeMeshCore(),
                    allowed_channel_idx=3,
                )
            )

        self.assertEqual(output.getvalue(), "")

    def test_weather_is_sent_to_resolved_channel(self):
        async def fake_weather():
            return {"weather": "ok"}

        meshcore = FakeMeshCore()
        with patch.object(monitor, "fetch_weather", new=fake_weather), patch.object(
            monitor,
            "format_weather_message",
            return_value="weather message",
        ):
            asyncio.run(monitor.send_weather_to_channel(meshcore, 3))

        self.assertEqual(meshcore.commands.sent, [(3, "weather message")])

    def test_greeting_uses_current_period_and_mentions_sender(self):
        cases = [
            (0, 0, "Bom dia ☀️, @PR2YZ"),
            (11, 59, "Bom dia ☀️, @PR2YZ"),
            (12, 0, "Boa tarde 🌤️, @PR2YZ"),
            (17, 59, "Boa tarde 🌤️, @PR2YZ"),
            (18, 0, "Boa noite 🌙, @PR2YZ"),
        ]

        for hour, minute, expected in cases:
            with self.subTest(hour=hour, minute=minute):
                now = datetime(
                    2026,
                    1,
                    1,
                    hour,
                    minute,
                    tzinfo=monitor.WEATHER_TIMEZONE,
                )
                self.assertEqual(
                    monitor.format_greeting_response("Boa noite", "PR2YZ", now),
                    expected,
                )

    def test_greeting_mention_corrects_requested_period(self):
        meshcore = FakeMeshCore()
        message = {
            "text": "PR2YZ: @[RAO-BOT 🤖] Boa Noite",
        }

        with patch.object(monitor, "datetime") as mocked_datetime:
            mocked_datetime.now.return_value = datetime(
                2026,
                1,
                1,
                9,
                tzinfo=monitor.WEATHER_TIMEZONE,
            )
            asyncio.run(
                monitor.handle_channel_mention(
                    meshcore,
                    3,
                    message["text"],
                    message=message,
                )
            )

        self.assertEqual(meshcore.commands.sent, [(3, "Bom dia ☀️, @PR2YZ")])

    def test_greeting_uses_sender_metadata_when_text_has_no_prefix(self):
        meshcore = FakeMeshCore()
        message = {
            "text": "@[RAO-BOT 🤖] bom dia",
            "sender_name": "PR2YZ",
        }

        with patch.object(monitor, "datetime") as mocked_datetime:
            mocked_datetime.now.return_value = datetime(
                2026,
                1,
                1,
                18,
                tzinfo=monitor.WEATHER_TIMEZONE,
            )
            asyncio.run(
                monitor.handle_channel_mention(
                    meshcore,
                    3,
                    message["text"],
                    message=message,
                )
            )

        self.assertEqual(meshcore.commands.sent, [(3, "Boa noite 🌙, @PR2YZ")])

    def test_hidden_version_aliases_return_version(self):
        query_time = datetime(
            2026,
            11,
            20,
            18,
            30,
            45,
            tzinfo=monitor.WEATHER_TIMEZONE,
        )
        for command in ("v", "ver", "version", "versao", "versão"):
            with self.subTest(command=command), patch.object(
                monitor,
                "get_app_version",
                return_value="20261120.141931",
            ), patch.object(monitor, "datetime") as mocked_datetime:
                mocked_datetime.now.return_value = query_time
                meshcore = FakeMeshCore()
                asyncio.run(
                    monitor.handle_channel_mention(
                        meshcore,
                        3,
                        f"PR2YZ: @[RAO-BOT 🤖] {command}",
                    )
                )

                self.assertEqual(
                    meshcore.commands.sent,
                    [
                        (
                            3,
                            "💻 Versão: 20261120.141931\r\n"
                            "Consultado em: 20/11/2026 18:30:45",
                        )
                    ],
                )

    def test_version_response_formats_query_timestamp(self):
        query_time = datetime(
            2026,
            11,
            20,
            9,
            5,
            7,
            tzinfo=monitor.WEATHER_TIMEZONE,
        )

        with patch.object(monitor, "get_app_version", return_value="20261120.141931"):
            self.assertEqual(
                monitor.format_version_response(query_time),
                "💻 Versão: 20261120.141931\r\n"
                "Consultado em: 20/11/2026 09:05:07",
            )

    def test_version_file_is_validated(self):
        with TemporaryDirectory() as directory:
            version_file = Path(directory) / "VERSION"
            with self.subTest("valid version"):
                version_file.write_text("20261120.141931\n", encoding="ascii")
                with patch.object(monitor, "VERSION_FILE", version_file):
                    self.assertEqual(monitor.get_app_version(), "20261120.141931")

            with self.subTest("invalid version"):
                version_file.write_text("manual-version\n", encoding="ascii")
                with patch.object(monitor, "VERSION_FILE", version_file):
                    self.assertEqual(monitor.get_app_version(), "invalida")

    def test_version_command_is_not_listed_in_help(self):
        meshcore = FakeMeshCore()

        asyncio.run(
            monitor.handle_channel_mention(
                meshcore,
                3,
                "@[RAO-BOT 🤖] AJUDA",
            )
        )

        self.assertNotIn("VERSION", meshcore.commands.sent[0][1])
        self.assertNotIn("VERSAO", meshcore.commands.sent[0][1])

    def test_ping_formats_signal_and_three_hops_per_line(self):
        result = {
            "success": True,
            "name": "PR2YZ",
            "rssi": -42,
            "snr": 12.5,
            "in_path_len": 6,
            "in_path_hash_len": 2,
            "in_path": "82695e1713a18abc44de91ff",
        }

        message = monitor.format_ping_response(result)

        self.assertEqual(
            message,
            "👂 PR2YZ: RX 📶 -42dBm/12,5dB\r\n"
            "🛣️ 6 saltos\r\n"
            "8269>5e17>13a1\r\n8abc>44de>91ff",
        )

    def test_ping_appends_ellipsis_when_over_maximum(self):
        result = {
            "success": True,
            "name": "PR2YZ",
            "rssi": -42,
            "snr": 12.5,
            "in_path_len": 12,
            "in_path_hash_len": 2,
            "in_path": "82695e1713a18abc44de91ff00112233445566778899aabb",
        }

        message = monitor.format_ping_response(result, max_length=80)

        self.assertLessEqual(len(message), 80)
        self.assertTrue(message.endswith("..."))

    def test_ping_formats_received_channel_signal(self):
        message = {
            "text": "PR2YZ: @[RAO-BOT 🤖] PING",
            "RSSI": -42,
            "SNR": 12.5,
            "path_len": 6,
            "path_hash_mode": 1,
            "path": "82695e1713a18abc44de91ff",
        }

        self.assertEqual(
            monitor.format_channel_ping_response(message),
            "👂 PR2YZ: RX 📶 -42dBm/12,5dB\r\n"
            "🛣️ 6 saltos\r\n"
            "8269>5e17>13a1\r\n8abc>44de>91ff",
        )

    def test_ping_mention_sends_formatted_response(self):
        meshcore = FakeMeshCore()
        message = {
            "text": "PR2YZ: @[RAO-BOT 🤖] PING",
            "RSSI": -42,
            "SNR": 12.5,
            "path_len": 3,
            "path_hash_mode": 1,
            "path": "82695e1713a1",
        }

        asyncio.run(
            monitor.handle_channel_mention(
                meshcore,
                3,
                message["text"],
                message=message,
            )
        )

        self.assertEqual(
            meshcore.commands.sent,
            [
                (
                    3,
                    "👂 PR2YZ: RX 📶 -42dBm/12,5dB\r\n"
                    "🛣️ 3 saltos\r\n"
                    "8269>5e17>13a1",
                )
            ],
        )

    def test_channel_ping_passes_received_message_metadata(self):
        meshcore = FakeMeshCore()
        message = {
            "channel_idx": 3,
            "text": "PR2YZ: @[RAO-BOT 🤖] PING",
            "RSSI": -42,
            "SNR": 12.5,
            "path_len": 3,
            "path_hash_mode": 1,
            "path": "82695e1713a1",
        }

        asyncio.run(
            monitor.on_channel_message(
                SimpleNamespace(payload=message),
                meshcore,
                allowed_channel_idx=3,
            )
        )

        self.assertEqual(
            meshcore.commands.sent[0][1],
            "👂 PR2YZ: RX 📶 -42dBm/12,5dB\r\n🛣️ 3 saltos\r\n8269>5e17>13a1",
        )

    def test_ping_uses_direct_for_zero_hops(self):
        result = {
            "success": True,
            "name": "PR2YZ",
            "rssi": -42,
            "snr": 12.5,
            "in_path_len": 0,
            "in_path_hash_len": 2,
            "in_path": "",
        }

        self.assertEqual(
            monitor.format_ping_response(result),
            "👂 PR2YZ: RX 📶 -42dBm/12,5dB\r\n🎯 Direto!",
        )

    def test_help_lists_ping_command(self):
        meshcore = FakeMeshCore()

        asyncio.run(
            monitor.handle_channel_mention(
                meshcore,
                3,
                "@[RAO-BOT 🤖] AJUDA",
            )
        )

        self.assertIn("-PING (sinal recebido)", meshcore.commands.sent[0][1])
        self.assertIn("-BOM DIA/BOA TARDE/BOA NOITE", meshcore.commands.sent[0][1])

    def test_no_public_channel_fallback_or_hardcoded_send(self):
        source = Path(monitor.__file__).read_text()
        self.assertNotIn("WEATHER_AUTO_SEND_CHANNEL", source)
        self.assertNotIn("TELEMETRY_AUTO_SEND_CHANNEL", source)
        self.assertNotIn("send_chan_msg(0", source)

    def test_disabled_telemetry_does_not_fetch_initial_status(self):
        with patch.object(monitor, "TELEMETRY_AUTO_SEND_ENABLED", False), patch.object(
            monitor,
            "check_all_repeaters_telemetry",
            new_callable=AsyncMock,
        ) as check_telemetry:
            asyncio.run(monitor.fetch_initial_telemetry_if_enabled(FakeMeshCore(), 3))

        check_telemetry.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
