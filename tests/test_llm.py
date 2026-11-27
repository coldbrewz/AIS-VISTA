import contextlib
import io
import json
import unittest
from unittest.mock import patch

from PIL import Image

from config import settings
from services.llm import _read_chat_completion_content, extract_json_str, extract_opname_form_ocr


def _tiny_jpeg_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), "white").save(buf, format="JPEG")
    return buf.getvalue()


class _FakeResponse:
    def __init__(self, status_code=200, headers=None, lines=None, json_data=None, text=""):
        self.status_code = status_code
        self.headers = headers or {}
        self._lines = lines or []
        self._json_data = json_data
        self.text = text

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def iter_lines(self, decode_unicode=True):
        for ln in self._lines:
            yield ln

    def json(self):
        return self._json_data


class _ChunkedFakeResponse(_FakeResponse):
    def __init__(self, status_code=200, headers=None, chunks=None, text=""):
        super().__init__(status_code=status_code, headers=headers, text=text)
        self._chunks = chunks or []

    def iter_content(self, chunk_size=4096):
        for chunk in self._chunks:
            yield chunk


class LLMJsonExtractTests(unittest.TestCase):
    def test_clean_json(self):
        text = '{"kode": "240523PV001", "sheet_name": "PV"}'
        self.assertEqual(extract_json_str(text), text)

    def test_json_in_markdown_code_fence(self):
        text = """```json
{"kode": "240523PV001", "sheet_name": "PV"}
```"""
        self.assertEqual(extract_json_str(text), '{"kode": "240523PV001", "sheet_name": "PV"}')

    def test_json_with_think_tags(self):
        text = """<think>
Analyzing the road image and caption...
Kode is 240523PV001.
</think>
```json
{
  "kode": "240523PV001",
  "sheet_name": "PV"
}
```"""
        expected = """{
  "kode": "240523PV001",
  "sheet_name": "PV"
}"""
        self.assertEqual(extract_json_str(text), expected)

    def test_json_with_extra_preamble_and_postamble(self):
        text = """Here is the extracted data:
{"kode": "240523PV001", "sheet_name": "PV"}
Hope this helps!"""
        self.assertEqual(extract_json_str(text), '{"kode": "240523PV001", "sheet_name": "PV"}')


class OpnameOCRStreamTests(unittest.TestCase):
    def setUp(self):
        self.orig_key = settings.VIKEY_API_KEY
        settings.VIKEY_API_KEY = "test-vikey-key"

    def tearDown(self):
        settings.VIKEY_API_KEY = self.orig_key

    @patch("services.llm.requests.post")
    def test_opname_ocr_parses_sse_stream_and_merges_multipage(self, mock_post):
        p1_payload = json.dumps(
            {
                "aset": "PV",
                "vendor": "MIJ",
                "wilayah": "W1",
                "minggu": "M5",
                "rows": [
                    {
                        "tanggal": "2026-08-23",
                        "raw_item": "Permanen",
                        "p": 4.3,
                        "l": 1.8,
                        "t": 0.16,
                        "vol_vendor": 1.238,
                        "vol_opname": None,
                    }
                ],
            }
        )
        mid = len(p1_payload) // 2
        sse_p1 = [
            f"data: {json.dumps({'choices': [{'delta': {'content': p1_payload[:mid]}}]})}",
            "",
            f"data: {json.dumps({'choices': [{'delta': {'content': p1_payload[mid:]}}]})}",
            "data: [DONE]",
        ]
        p2_payload = json.dumps({"rows": []})
        sse_p2 = [
            f"data: {json.dumps({'choices': [{'delta': {'content': p2_payload}}]})}",
            "data: [DONE]",
        ]
        mock_post.side_effect = [
            _FakeResponse(headers={"Content-Type": "text/event-stream; charset=utf-8"}, lines=sse_p1),
            _FakeResponse(headers={"Content-Type": "text/event-stream"}, lines=sse_p2),
        ]

        res, err = extract_opname_form_ocr([_tiny_jpeg_bytes(), _tiny_jpeg_bytes()], "PV", "Scan Opname PV M5", "II.1 Permanen")
        self.assertEqual(err, "")
        self.assertEqual(mock_post.call_count, 2)
        for call in mock_post.call_args_list:
            self.assertTrue(call.kwargs.get("stream"))
        self.assertEqual(res["aset"], "PV")
        self.assertEqual(res["vendor"], "MIJ")
        self.assertEqual(res["minggu"], "M5")
        self.assertEqual(len(res["rows"]), 1)
        self.assertEqual(res["rows"][0]["raw_item"], "Permanen")

    @patch("services.llm.requests.post")
    def test_opname_ocr_handles_plain_json_fallback(self, mock_post):
        mock_post.return_value = _FakeResponse(
            headers={"Content-Type": "application/json"},
            json_data={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "aset": "PV",
                                    "vendor": "MIJ",
                                    "wilayah": "W1",
                                    "minggu": "M5",
                                    "rows": [{"tanggal": "2026-08-23", "raw_item": "Hotmix", "vol_vendor": 5.07}],
                                }
                            )
                        }
                    }
                ]
            },
        )
        res, err = extract_opname_form_ocr([_tiny_jpeg_bytes()], "PV", "Scan Opname PV", "II.6 Hotmix")
        self.assertEqual(err, "")
        self.assertEqual(len(res["rows"]), 1)
        self.assertEqual(res["rows"][0]["vol_vendor"], 5.07)

    @patch("services.llm.requests.post")
    def test_opname_ocr_second_pass_applies_handwritten_corrections(self, mock_post):
        p1_payload = json.dumps(
            {
                "aset": "PV",
                "vendor": "MIJ",
                "wilayah": "W1",
                "minggu": "M3",
                "rows": [
                    {
                        "row_no": "108",
                        "tanggal": "2026-08-09",
                        "raw_item": "Permanen",
                        "p": 6.1,
                        "l": 2.4,
                        "t": 0.07,
                        "vol_vendor": 1.025,
                        "vol_opname": None,
                        "dimension_edited": True,
                        "handwritten_edited": True,
                    },
                    {
                        "row_no": "151",
                        "tanggal": "2026-08-15",
                        "raw_item": "Hotmix",
                        "p": None,
                        "l": None,
                        "t": None,
                        "jml": 5.16,
                        "vol_vendor": 5.16,
                        "vol_opname": None,
                        "dimension_edited": True,
                        "handwritten_edited": True,
                    },
                ],
            }
        )
        p2_payload = json.dumps(
            {
                "corrections": [
                    {
                        "row_index": 0,
                        "row_no": "108",
                        "field": "p",
                        "crossed_out_printed": 6.1,
                        "handwritten_replacement": "5,4",
                    },
                    {
                        "row_index": 1,
                        "row_no": "151",
                        "field": "jml",
                        "crossed_out_printed": 5.16,
                        "handwritten_replacement": 5.0,
                    },
                ]
            }
        )
        mock_post.side_effect = [
            _FakeResponse(
                headers={"Content-Type": "text/event-stream"},
                lines=[
                    f"data: {json.dumps({'choices': [{'delta': {'content': p1_payload}}]})}",
                    "data: [DONE]",
                ],
            ),
            _FakeResponse(
                headers={"Content-Type": "text/event-stream"},
                lines=[
                    f"data: {json.dumps({'choices': [{'delta': {'content': p2_payload}}]})}",
                    "data: [DONE]",
                ],
            ),
        ]

        res, err = extract_opname_form_ocr([_tiny_jpeg_bytes()], "PV", "Scan Opname PV M3", "II.1 Permanen\nII.6 Hotmix")
        self.assertEqual(err, "")
        self.assertEqual(mock_post.call_count, 2)
        self.assertAlmostEqual(res["rows"][0]["p"], 5.4)
        self.assertAlmostEqual(res["rows"][1]["jml"], 5.0)
        self.assertTrue(res["rows"][0]["dimension_edited"])
        self.assertTrue(res["rows"][1]["dimension_edited"])

    @patch("services.llm.requests.post")
    def test_opname_ocr_logs_before_pass1_and_pass2_requests(self, mock_post):
        p1_payload = json.dumps(
            {
                "aset": "PV",
                "vendor": "MIJ",
                "wilayah": "W1",
                "minggu": "M3",
                "rows": [
                    {
                        "row_no": "108",
                        "tanggal": "2026-08-09",
                        "raw_item": "Permanen",
                        "p": 6.1,
                        "l": 2.4,
                        "t": 0.07,
                        "vol_vendor": 1.025,
                        "vol_opname": None,
                        "dimension_edited": True,
                        "handwritten_edited": True,
                    }
                ],
            }
        )
        p2_payload = json.dumps(
            {
                "corrections": [
                    {
                        "row_index": 0,
                        "row_no": "108",
                        "field": "p",
                        "crossed_out_printed": 6.1,
                        "handwritten_replacement": "5,4",
                    }
                ]
            }
        )
        mock_post.side_effect = [
            _FakeResponse(
                headers={"Content-Type": "text/event-stream"},
                lines=[
                    f"data: {json.dumps({'choices': [{'delta': {'content': p1_payload}}]})}",
                    "data: [DONE]",
                ],
            ),
            _FakeResponse(
                headers={"Content-Type": "text/event-stream"},
                lines=[
                    f"data: {json.dumps({'choices': [{'delta': {'content': p2_payload}}]})}",
                    "data: [DONE]",
                ],
            ),
        ]

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            res, err = extract_opname_form_ocr([_tiny_jpeg_bytes()], "PV", "Scan Opname PV M3", "II.1 Permanen")

        self.assertEqual(err, "")
        self.assertAlmostEqual(res["rows"][0]["p"], 5.4)
        out = buf.getvalue()
        self.assertIn("[Opname OCR] Page 1/1 | sending Pass 1", out)
        self.assertIn("sending Pass 2", out)
        self.assertEqual(mock_post.call_args_list[0].kwargs.get("timeout"), (15, 75))
        self.assertEqual(mock_post.call_args_list[1].kwargs.get("timeout"), (15, 45))
        self.assertEqual(mock_post.call_args_list[0].kwargs["json"]["max_tokens"], 16384)
        self.assertEqual(mock_post.call_args_list[1].kwargs["json"]["max_tokens"], 6144)

    @patch("services.llm.requests.post")
    def test_opname_ocr_extracts_added_removed_rekap_revisi_and_pass2_skips_them(self, mock_post):
        p1_payload = json.dumps(
            {
                "aset": "PV",
                "vendor": "MIJ",
                "wilayah": "W1",
                "minggu": "M3",
                "rows": [
                    {
                        "row_no": "108",
                        "tanggal": "2026-08-09",
                        "raw_item": "Permanen",
                        "p": 6.1,
                        "l": 2.4,
                        "t": 0.07,
                        "vol_vendor": 1.025,
                        "vol_opname": None,
                        "dimension_edited": True,
                        "handwritten_edited": True,
                        "row_action": "",
                    },
                    {
                        "row_no": "109",
                        "tanggal": "2026-08-09",
                        "raw_item": "Salob",
                        "vol_vendor": 0.12,
                        "vol_opname": 0,
                        "handwritten_edited": True,
                        "row_action": "REMOVED",
                    },
                    {
                        "row_no": "+1",
                        "tanggal": "2026-08-10",
                        "raw_item": "Hotmix",
                        "jml": 2.5,
                        "vol_opname": 2.5,
                        "handwritten_edited": True,
                        "row_action": "ADDED",
                    },
                ],
                "rekap_revisi": [{"raw_item": "Permanen", "vol_revisi": 1.25}],
            }
        )
        p2_payload = json.dumps(
            {
                "corrections": [
                    {
                        "row_index": 0,
                        "row_no": "108",
                        "field": "p",
                        "crossed_out_printed": 6.1,
                        "handwritten_replacement": "5,4",
                    }
                ]
            }
        )
        mock_post.side_effect = [
            _FakeResponse(
                headers={"Content-Type": "text/event-stream"},
                lines=[
                    f"data: {json.dumps({'choices': [{'delta': {'content': p1_payload}}]})}",
                    "data: [DONE]",
                ],
            ),
            _FakeResponse(
                headers={"Content-Type": "text/event-stream"},
                lines=[
                    f"data: {json.dumps({'choices': [{'delta': {'content': p2_payload}}]})}",
                    "data: [DONE]",
                ],
            ),
        ]

        res, err = extract_opname_form_ocr([_tiny_jpeg_bytes()], "PV", "Scan Opname PV M3", "II.1 Permanen\nII.2 Salob\nII.6 Hotmix")
        self.assertEqual(err, "")
        self.assertEqual(mock_post.call_count, 2)
        pass2_prompt = mock_post.call_args_list[1].kwargs["json"]["messages"][0]["content"][0]["text"]
        self.assertIn('"108"', pass2_prompt)
        self.assertNotIn('"109"', pass2_prompt)
        self.assertNotIn('"+1"', pass2_prompt)
        self.assertAlmostEqual(res["rows"][0]["p"], 5.4)
        self.assertEqual(res["rows"][1]["row_action"], "REMOVED")
        self.assertEqual(res["rows"][2]["row_action"], "ADDED")
        self.assertEqual(res["rekap_revisi"], [{"raw_item": "Permanen", "vol_revisi": 1.25}])

    def test_read_chat_completion_content_aborts_sse_over_max_seconds(self):
        c1, c2 = '{"rows":', '[]}'
        sse_lines = [
            f"data: {json.dumps({'choices': [{'delta': {'content': c1}}]})}",
            f"data: {json.dumps({'choices': [{'delta': {'content': c2}}]})}",
            "data: [DONE]",
        ]
        fake_resp = _FakeResponse(
            headers={"Content-Type": "text/event-stream"},
            lines=sse_lines,
        )
        with patch("services.llm.time.monotonic", side_effect=[100.0, 101.0, 200.0]):
            with self.assertRaises(TimeoutError) as ctx:
                _read_chat_completion_content(fake_resp, max_seconds=45.0)
        self.assertIn("exceeded 45s total limit", str(ctx.exception))

    def test_read_chat_completion_content_aborts_non_sse_over_max_seconds(self):
        fake_resp = _ChunkedFakeResponse(
            headers={"Content-Type": "application/json"},
            chunks=[b" ", b'{"choices": []}'],
        )
        with patch("services.llm.time.monotonic", side_effect=[100.0, 101.0, 200.0]):
            with self.assertRaises(TimeoutError) as ctx:
                _read_chat_completion_content(fake_resp, max_seconds=90.0)
        self.assertIn("exceeded 90s total limit", str(ctx.exception))

    def test_read_chat_completion_content_reports_sample_on_blank_json_body(self):
        fake_resp = _ChunkedFakeResponse(
            headers={"Content-Type": "application/json"},
            chunks=[b" "],
        )
        with self.assertRaises(ValueError) as ctx:
            _read_chat_completion_content(fake_resp, max_seconds=90.0)
        msg = str(ctx.exception)
        self.assertIn("ctype=application/json", msg)
        self.assertIn("sample=' '", msg)

    @patch("services.llm.requests.post")
    def test_opname_ocr_skips_pass2_for_baik_check_and_verifies_lokasi_edit(self, mock_post):
        clean_payload = json.dumps(
            {
                "aset": "PV",
                "vendor": "MIJ",
                "wilayah": "W1",
                "opname_ke": "2",
                "minggu": "",
                "rows": [
                    {
                        "row_no": "1",
                        "tanggal": "2026-08-14",
                        "tanggal_temuan": "2026-08-02",
                        "lokasi": "KM 45+200",
                        "raw_item": "Permanen",
                        "vol_vendor": 1.0,
                        "vol_opname": None,
                        "hasil_baik": True,
                        "lokasi_edited": False,
                        "handwritten_edited": False,
                    }
                ],
            }
        )
        mock_post.return_value = _FakeResponse(
            headers={"Content-Type": "text/event-stream"},
            lines=[
                f"data: {json.dumps({'choices': [{'delta': {'content': clean_payload}}]})}",
                "data: [DONE]",
            ],
        )
        res_clean, err_clean = extract_opname_form_ocr([_tiny_jpeg_bytes()], "PV", "Scan Opname PV OP2", "II.1 Permanen")
        self.assertEqual(err_clean, "")
        self.assertEqual(mock_post.call_count, 1)
        self.assertEqual(res_clean["opname_ke"], "2")
        self.assertTrue(res_clean["rows"][0]["hasil_baik"])

        mock_post.reset_mock()
        p1_loc = json.dumps(
            {
                "aset": "PV",
                "vendor": "MIJ",
                "wilayah": "W1",
                "opname_ke": "3",
                "rows": [
                    {
                        "row_no": "2",
                        "tanggal": "2026-08-15",
                        "lokasi": "Gorda",
                        "raw_item": "Permanen",
                        "vol_vendor": 0.5,
                        "lokasi_edited": True,
                        "handwritten_edited": False,
                    }
                ],
            }
        )
        p2_loc = json.dumps(
            {
                "corrections": [
                    {
                        "row_index": 0,
                        "row_no": "2",
                        "field": "lokasi",
                        "crossed_out_printed": "Gorda",
                        "handwritten_replacement": "IC Cikupa",
                    }
                ]
            }
        )
        mock_post.side_effect = [
            _FakeResponse(
                headers={"Content-Type": "text/event-stream"},
                lines=[f"data: {json.dumps({'choices': [{'delta': {'content': p1_loc}}]})}", "data: [DONE]"],
            ),
            _FakeResponse(
                headers={"Content-Type": "text/event-stream"},
                lines=[f"data: {json.dumps({'choices': [{'delta': {'content': p2_loc}}]})}", "data: [DONE]"],
            ),
        ]
        res_loc, err_loc = extract_opname_form_ocr([_tiny_jpeg_bytes()], "PV", "Scan Opname PV OP3", "II.1 Permanen")
        self.assertEqual(err_loc, "")
        self.assertEqual(mock_post.call_count, 2)
        self.assertEqual(res_loc["rows"][0]["lokasi"], "IC Cikupa")
        self.assertTrue(res_loc["rows"][0]["lokasi_edited"])
        self.assertTrue(res_loc["rows"][0]["handwritten_edited"])


if __name__ == "__main__":
    unittest.main()
