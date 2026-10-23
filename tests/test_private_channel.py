import asyncio
import contextlib
import io
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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
        monitor.MESHCORE_CHANNEL_NAME = "RAO_MESHCORE"
        monitor.MESHCORE_CHANNEL_KEY_HEX = "7403f42915314f75bd44e4ed88b084aa"

    def tearDown(self):
        monitor.MESHCORE_CHANNEL_NAME = self.original_name
        monitor.MESHCORE_CHANNEL_KEY_HEX = self.original_key

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

    def test_no_public_channel_fallback_or_hardcoded_send(self):
        source = Path(monitor.__file__).read_text()
        self.assertNotIn("WEATHER_AUTO_SEND_CHANNEL", source)
        self.assertNotIn("TELEMETRY_AUTO_SEND_CHANNEL", source)
        self.assertNotIn("send_chan_msg(0", source)


if __name__ == "__main__":
    unittest.main()
