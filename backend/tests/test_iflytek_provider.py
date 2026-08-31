from __future__ import annotations

import base64
import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from src.media.providers.iflytek import IflytekSpeechProvider


class FakeWebSocket:
    def __init__(self, messages: list[dict]) -> None:
        self.messages = [json.dumps(message, ensure_ascii=False) for message in messages]
        self.sent: list[dict] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def send(self, payload: str) -> None:
        self.sent.append(json.loads(payload))

    def recv(self, *, timeout: float):
        _ = timeout
        return self.messages.pop(0)


class IflytekProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = IflytekSpeechProvider(
            app_id="test-app",
            api_key="test-api-key",
            api_secret="test-api-secret",
        )

    def test_tts_decodes_audio_and_never_places_raw_secret_in_url(self) -> None:
        websocket = FakeWebSocket(
            [
                {
                    "code": 0,
                    "sid": "tts-sid",
                    "data": {
                        "audio": base64.b64encode(b"pcm-audio").decode("ascii"),
                        "status": 2,
                    },
                }
            ]
        )
        with patch("src.media.providers.iflytek.connect", return_value=websocket) as connect:
            result = self.provider.synthesize(
                text="刑法课堂测试。", voice="xiaoyan", audio_format="wav"
            )
        signed_url = connect.call_args.args[0]
        self.assertNotIn("test-api-key", signed_url)
        self.assertNotIn("test-api-secret", signed_url)
        self.assertEqual(result.audio, b"pcm-audio")
        self.assertEqual(result.provider_sid, "tts-sid")
        self.assertEqual(websocket.sent[0]["business"]["aue"], "raw")
        self.assertEqual(websocket.sent[0]["data"]["status"], 2)

    def test_iat_sends_first_and_final_frames_and_parses_words(self) -> None:
        websocket = FakeWebSocket(
            [
                {
                    "code": 0,
                    "sid": "iat-sid",
                    "data": {
                        "status": 2,
                        "result": {
                            "sn": 1,
                            "ls": True,
                            "ws": [
                                {"cw": [{"w": "罪刑法定"}]},
                                {"cw": [{"w": "原则。"}]},
                            ],
                        },
                    },
                }
            ]
        )
        with patch("src.media.providers.iflytek.connect", return_value=websocket):
            result = self.provider.transcribe(
                audio=b"\x00\x00" * 640,
                language="zh_cn",
                encoding="raw",
                sample_rate=16000,
            )
        self.assertEqual(result.transcript, "罪刑法定原则。")
        self.assertEqual(websocket.sent[0]["data"]["status"], 0)
        self.assertEqual(websocket.sent[-1], {"data": {"status": 2}})
        self.assertEqual(websocket.sent[0]["business"]["domain"], "iat")

    def test_tts_rejects_text_at_official_8000_byte_limit(self) -> None:
        with self.assertRaisesRegex(Exception, "iflytek_tts_text_length_invalid"):
            self.provider.synthesize(text="刑" * 2667)


class AsyncFakeWebSocket:
    def __init__(self, messages: list[dict]) -> None:
        self.messages = [json.dumps(message, ensure_ascii=False) for message in messages]
        self.sent: list[dict] = []
        self.closed = False

    async def send(self, payload: str) -> None:
        self.sent.append(json.loads(payload))

    async def recv(self, *, decode: bool = True):
        _ = decode
        return self.messages.pop(0)

    async def close(self, *, code: int = 1000) -> None:
        _ = code
        self.closed = True


class IflytekStreamingProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_streaming_iat_uses_wpgs_and_replaces_corrected_segments(self) -> None:
        provider = IflytekSpeechProvider(
            app_id="test-app",
            api_key="test-api-key",
            api_secret="test-api-secret",
        )
        websocket = AsyncFakeWebSocket(
            [
                {
                    "code": 0,
                    "sid": "iat-stream",
                    "data": {
                        "status": 1,
                        "result": {
                            "sn": 1,
                            "ls": False,
                            "pgs": "apd",
                            "ws": [{"cw": [{"w": "罪行"}]}],
                        },
                    },
                },
                {
                    "code": 0,
                    "sid": "iat-stream",
                    "data": {
                        "status": 2,
                        "result": {
                            "sn": 2,
                            "ls": True,
                            "pgs": "rpl",
                            "rg": [1, 1],
                            "ws": [{"cw": [{"w": "罪刑法定"}]}],
                        },
                    },
                },
            ]
        )
        with patch(
            "src.media.providers.iflytek.async_connect",
            new=AsyncMock(return_value=websocket),
        ):
            stream = provider.streaming_iat_session()
            await stream.start()
        await stream.send_audio(b"\x00\x00" * 640)
        first = await stream.receive()
        await stream.finish()
        final = await stream.receive()
        await stream.close()
        self.assertEqual(first["transcript"], "罪行")
        self.assertEqual(final["transcript"], "罪刑法定")
        self.assertTrue(final["final"])
        self.assertEqual(websocket.sent[0]["business"]["dwa"], "wpgs")
        self.assertEqual(websocket.sent[0]["business"]["eos"], 3000)
        self.assertNotIn("vad_eos", websocket.sent[0]["business"])
        self.assertEqual(websocket.sent[-1], {"data": {"status": 2}})
        self.assertTrue(websocket.closed)


if __name__ == "__main__":
    unittest.main()
