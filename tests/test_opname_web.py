import datetime
import io
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import openpyxl
from fastapi.testclient import TestClient
from PIL import Image

import main
from config import settings
from services.opname_catalog import PV_ITEMS
from services.opname_web import make_opname_token
from services.opname_xlsx import parse_standard_opname_xlsx


def _make_sample_pdf_bytes() -> bytes:
    im = Image.new("RGB", (400, 300), "white")
    buf = io.BytesIO()
    im.save(buf, format="PDF")
    return buf.getvalue()


def _make_sample_pv_xlsx_with_dims() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "NOV"
    ws.cell(7, 2, "Wilayah:")
    ws.cell(7, 4, "W1")
    ws.cell(7, 5, "Vendor:")
    ws.cell(7, 6, "MIJ")
    headers = [
        "No.", "Tanggal", "Minggu", "Kode Temuan",
        "STA / KM", "Jalur", "Lajur", "KODE", "Item / Keyword RAB",
        "P", "L", "T", "Jml", "Vol. Vendor", "Vol. Opname", "Satuan",
        "Baik", "Tdk Baik", "Keterangan",
    ]
    for i, h in enumerate(headers):
        ws.cell(10, 2 + i, h)
    ws.cell(11, 2, 1)
    ws.cell(11, 3, datetime.date(2026, 11, 10))
    ws.cell(11, 4, "M1")
    ws.cell(11, 5, "101126PV001")
    ws.cell(11, 6, "KM 45+200")
    ws.cell(11, 7, "A")
    ws.cell(11, 8, "L1")
    ws.cell(11, 10, "Permanen")
    ws.cell(11, 11, 4.0)
    ws.cell(11, 12, 1.0)
    ws.cell(11, 13, 0.05)
    ws.cell(11, 14, 1.0)
    ws.cell(11, 15, 0.2)
    ws.cell(11, 16, 0.2)
    ws.cell(11, 18, 1)
    ws.cell(11, 20, "Awal lapangan")
    ws.cell(12, 2, "TOTAL PEMERIKSAAN")

    ws_boq = wb.create_sheet("DAFTAR_BOQ")
    for idx_b, it in enumerate(PV_ITEMS, start=2):
        ws_boq.cell(idx_b, 1, it.keyword)
        ws_boq.cell(idx_b, 2, it.item_key)
        ws_boq.cell(idx_b, 3, it.uraian)
        ws_boq.cell(idx_b, 4, it.satuan)
    ws_boq.cell(1, 7, "PV")
    ws_boq.cell(2, 7, "W1")
    ws_boq.cell(3, 7, "MIJ")

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class OpnameWebTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "test_opname_web.db")
        self.orig_db = settings.DB_URL
        self.orig_opname_link = settings.OPNAME_EXCEL_SHARE_LINK
        self.orig_pub_url = settings.PUBLIC_BASE_URL
        self.orig_secret = settings.OPNAME_WEB_SECRET
        settings.DB_URL = self.db_path
        settings.OPNAME_EXCEL_SHARE_LINK = "https://1drv.ms/x/s!TEST_OPNAME_LINK"
        settings.PUBLIC_BASE_URL = "http://ais-vista.duckdns.org:5001"
        settings.OPNAME_WEB_SECRET = "unit-test-secret"
        main.session_ready_at = 0
        main.init_db()
        self.client = TestClient(main.app)

    def tearDown(self):
        settings.DB_URL = self.orig_db
        settings.OPNAME_EXCEL_SHARE_LINK = self.orig_opname_link
        settings.PUBLIC_BASE_URL = self.orig_pub_url
        settings.OPNAME_WEB_SECRET = self.orig_secret
        self.tmpdir.cleanup()

    def test_auth_guard_rejects_missing_or_invalid_tokens(self):
        dash_tok = make_opname_token("DASHBOARD")
        scan_tok = make_opname_token("SCAN-261126-ABCD")

        self.assertEqual(self.client.get("/opname").status_code, 403)
        self.assertEqual(self.client.get("/opname?token=wrong").status_code, 403)
        self.assertEqual(self.client.get("/api/opname/slots?token=wrong").status_code, 403)
        self.assertEqual(self.client.get("/review/SCAN-261126-ABCD").status_code, 403)
        self.assertEqual(self.client.get("/api/opname/review/SCAN-261126-ABCD?token=wrong").status_code, 403)
        self.assertEqual(self.client.get("/api/opname/media/SCAN-261126-ABCD?token=wrong").status_code, 403)
        self.assertEqual(
            self.client.post("/api/opname/review/SCAN-261126-ABCD/save?token=wrong", json={}).status_code,
            403,
        )

        # Valid dashboard token opens /opname and /api/opname/slots; record token rejected for /opname
        self.assertEqual(self.client.get(f"/opname?token={scan_tok}").status_code, 403)
        self.assertEqual(self.client.get(f"/opname?token={dash_tok}").status_code, 200)
        self.assertEqual(self.client.get(f"/api/opname/slots?token={dash_tok}").status_code, 200)

    @patch("main.download_file_from_onedrive")
    @patch("main.upload_file_to_onedrive")
    @patch("main.replace_opname_slot_rows", return_value=(0, 2))
    @patch("main.ensure_monthly_opname_workbook", return_value=("DRV1", "ITM_NOV", "https://1drv.ms/x/NOV"))
    @patch("main.extract_opname_form_ocr")
    @patch("main.send_whatsapp_document")
    @patch("main.send_whatsapp_message")
    def test_scan_to_web_review_edit_save_updates_excel_and_notifies_whatsapp(
        self,
        mock_send,
        mock_send_doc,
        mock_ocr,
        mock_ensure,
        mock_replace,
        mock_upload_arc,
        mock_dl_onedrive,
    ):
        pdf_bytes = _make_sample_pdf_bytes()
        mock_dl_onedrive.return_value = pdf_bytes
        mock_upload_arc.side_effect = [
            ("OD_SCAN_PDF", "https://1drv.ms/u/SCAN_PDF"),
            ("OD_OCR_XLS", "https://1drv.ms/u/OCR_XLS"),
            ("OD_EDITED_XLS", "https://1drv.ms/u/EDITED_XLS"),
        ]
        mock_ocr.return_value = (
            {
                "aset": "PV",
                "vendor": "MIJ",
                "wilayah": "W1",
                "minggu": "M3",
                "rows": [
                    {
                        "tanggal": "2026-11-18",
                        "kode_temuan": "181126PV001",
                        "wilayah": "W1",
                        "vendor": "MIJ",
                        "lokasi": "KM 45+200",
                        "jalur": "A",
                        "lajur": "L1",
                        "raw_item": "Permanen",
                        "p": 4.5,
                        "l": 1.2,
                        "t": 0.05,
                        "jml": None,
                        "vol_vendor": 0.27,
                        "vol_opname": 0.25,
                        "keterangan": "Revisi 0.25",
                        "handwritten_edited": True,
                    },
                    {
                        "tanggal": "2026-11-18",
                        "kode_temuan": "181126PV002",
                        "wilayah": "W1",
                        "vendor": "MIJ",
                        "lokasi": "KM 45+200",
                        "jalur": "A",
                        "lajur": "L1",
                        "raw_item": "Marka Putih",
                        "vol_vendor": 18.0,
                        "vol_opname": 18.0,
                        "handwritten_edited": False,
                    },
                ],
            },
            "",
        )

        with patch("main._extract_image_bytes_from_message", return_value=pdf_bytes):
            main.process_message(
                {
                    "id": {"_serialized": "false_628111@c.us_WEBSCAN1"},
                    "from": "628111@c.us",
                    "hasMedia": True,
                    "body": "Scan Opname PV M3",
                    "media": {"filename": "opname_signed.pdf", "mimetype": "application/pdf"},
                    "_session": "default",
                }
            )

        mock_replace.assert_not_called()
        preview_text = mock_send.call_args[0][1]
        scan_id = "SCAN-" + preview_text.split("SCAN-")[1].split("`")[0]
        scan_tok = make_opname_token(scan_id)
        expected_url = f"http://ais-vista.duckdns.org:5001/review/{scan_id}?token={scan_tok}"
        self.assertIn(expected_url, preview_text)

        # Render HTML page and verify anti-slop / responsive markers + row filter controls
        html_resp = self.client.get(f"/review/{scan_id}?token={scan_tok}")
        self.assertEqual(html_resp.status_code, 200)
        self.assertNotIn("\u2014", html_resp.text)
        self.assertIn('name="viewport"', html_resp.text)
        self.assertIn("Simpan ke DATA UNTUK VOL", html_resp.text)
        self.assertIn('id="rowFilterBar"', html_resp.text)
        self.assertIn('id="rowSearchInput"', html_resp.text)
        self.assertIn('id="rowItemFilter"', html_resp.text)
        self.assertIn('id="rowDateFilter"', html_resp.text)

        # JSON review endpoint returns OCR entries, catalog, and media URL
        api_resp = self.client.get(f"/api/opname/review/{scan_id}?token={scan_tok}")
        self.assertEqual(api_resp.status_code, 200)
        api_data = api_resp.json()
        self.assertEqual(api_data["aset"], "PV")
        self.assertEqual(api_data["minggu"], "M3")
        self.assertEqual(len(api_data["entries"]), 2)
        self.assertTrue(api_data["has_media"])
        self.assertTrue(len(api_data["boq_options"]) >= len(PV_ITEMS))

        # Media endpoint streams PDF page 0 as JPEG
        media_resp = self.client.get(f"/api/opname/media/{scan_id}?token={scan_tok}&page=0")
        self.assertEqual(media_resp.status_code, 200)
        self.assertEqual(media_resp.headers.get("X-PDF-Pages"), "1")
        self.assertEqual(media_resp.headers.get("content-type"), "image/jpeg")
        self.assertTrue(media_resp.content.startswith(b"\xff\xd8"))

        # Validation failure (zero volume + KM/Wilayah conflict) returns 422 without touching OneDrive
        bad_save = self.client.post(
            f"/api/opname/review/{scan_id}/save?token={scan_tok}",
            json={
                "aset": "PV",
                "wilayah": "W1",
                "vendor": "MIJ",
                "minggu": "M3",
                "entries": [
                    {
                        "tanggal": "2026-11-18",
                        "lokasi": "KM 72+500",
                        "item_key": api_data["entries"][0]["item_key"],
                        "volume": 0,
                    }
                ],
            },
        )
        self.assertEqual(bad_save.status_code, 422)
        self.assertGreaterEqual(len(bad_save.json()["errors"]), 2)
        mock_replace.assert_not_called()

        # Edit row 1 volume (0.25 -> 0.40), delete row 2, add Hotmix row (0.85) -> save
        mock_send.reset_mock()
        uploaded_blobs = []
        orig_side_effect = ("OD_EDITED_XLS", "https://1drv.ms/u/EDITED_XLS")

        def _capture_upload(data_bytes, filename, folder_path, content_type=""):
            uploaded_blobs.append((filename, data_bytes))
            return orig_side_effect

        with patch("main.upload_file_to_onedrive", side_effect=_capture_upload):
            save_resp = self.client.post(
                f"/api/opname/review/{scan_id}/save?token={scan_tok}",
                json={
                    "aset": "PV",
                    "wilayah": "W1",
                    "vendor": "MIJ",
                    "minggu": "M3",
                    "entries": [
                        {
                            "tanggal": "2026-11-18",
                            "kode_temuan": "181126PV001",
                            "lokasi": "KM 45+200",
                            "jalur": "A",
                            "lajur": "L1",
                            "item_key": api_data["entries"][0]["item_key"],
                            "p": 4.0,
                            "l": 2.0,
                            "t": 0.05,
                            "volume": 0.40,
                            "keterangan": "Revisi via Web",
                        },
                        {
                            "tanggal": "2026-11-18",
                            "kode_temuan": "181126PV003",
                            "lokasi": "KM 46+100",
                            "jalur": "B",
                            "lajur": "L2",
                            "item_key": "Hotmix",
                            "volume": 0.85,
                            "keterangan": "Tambahan baris web",
                        },
                    ],
                },
            )

        self.assertEqual(save_resp.status_code, 200)
        save_body = save_resp.json()
        self.assertTrue(save_body["ok"])
        self.assertTrue(save_body["whatsapp_notified"])

        # Regenerated .xlsx uploaded to OneDrive matches edited volumes
        self.assertEqual(len(uploaded_blobs), 1)
        parsed_regen = parse_standard_opname_xlsx(uploaded_blobs[0][1], filename=uploaded_blobs[0][0])
        self.assertTrue(parsed_regen.is_standard_form)
        self.assertEqual(len(parsed_regen.slots[0].entries), 2)
        self.assertAlmostEqual(parsed_regen.slots[0].entries[0]["volume"], 0.40)
        self.assertAlmostEqual(parsed_regen.slots[0].entries[1]["volume"], 0.85)

        # replace_opname_slot_rows committed edited rows to XLS-2611-PV-W1-MIJ-M3
        mock_replace.assert_called_once()
        self.assertEqual(mock_replace.call_args[0][2], "XLS-2611-PV-W1-MIJ-M3")
        excel_rows = mock_replace.call_args[0][3]
        self.assertEqual(len(excel_rows), 2)
        self.assertAlmostEqual(excel_rows[1][15], 0.85)

        # Pending marked CONFIRMED and WhatsApp notified
        conn = sqlite3.connect(self.db_path)
        pend_status = conn.execute(
            "SELECT status FROM opname_pending WHERE pending_id = ?", (scan_id,)
        ).fetchone()[0]
        slot_status = conn.execute(
            "SELECT status, minggu FROM opname_slots WHERE slot_id = ?", ("XLS-2611-PV-W1-MIJ-M3",)
        ).fetchone()
        conn.close()
        self.assertEqual(pend_status, "CONFIRMED")
        self.assertEqual(slot_status, ("ACTIVE", "M3"))
        mock_send.assert_called_once()
        self.assertEqual(mock_send.call_args[0][0], "628111@c.us")
        self.assertIn("Web Editor", mock_send.call_args[0][1])

    @patch("main.delete_opname_rows_by_id", return_value=1)
    @patch("main.upload_file_to_onedrive", return_value=("OD_XLS_NEW", "https://1drv.ms/u/XLS_NEW"))
    @patch("main.replace_opname_slot_rows", return_value=(0, 1))
    @patch("main.ensure_monthly_opname_workbook", return_value=("DRV1", "ITM_NOV", "https://1drv.ms/x/NOV"))
    @patch("main.send_whatsapp_message")
    def test_slot_list_reopen_lossless_edit_rename_and_undo(
        self,
        mock_send,
        mock_ensure,
        mock_replace,
        mock_upload_arc,
        mock_delete_rows,
    ):
        xlsx_bytes = _make_sample_pv_xlsx_with_dims()
        with patch("main._extract_image_bytes_from_message", return_value=xlsx_bytes):
            main.process_message(
                {
                    "id": {"_serialized": "false_628111@c.us_WEBDROP1"},
                    "from": "628111@c.us",
                    "hasMedia": True,
                    "body": "Opname",
                    "media": {"filename": "PV_W1_MIJ.xlsx", "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
                    "_session": "default",
                }
            )

        dash_tok = make_opname_token("DASHBOARD")
        list_resp = self.client.get(f"/api/opname/slots?token={dash_tok}&cycle=2026-11")
        self.assertEqual(list_resp.status_code, 200)
        list_data = list_resp.json()
        self.assertEqual(list_data["roster_progress"]["total"], 21)
        self.assertEqual(list_data["roster_progress"]["done"], 1)
        self.assertEqual(len(list_data["slots"]), 1)
        slot_id_m1 = "XLS-2611-PV-W1-MIJ-M1"
        self.assertEqual(list_data["slots"][0]["slot_id"], slot_id_m1)

        # Reopen M1 slot in web editor -> lossless dims and jalur_lajur preserved
        slot_tok = make_opname_token(slot_id_m1)
        rev_resp = self.client.get(f"/api/opname/review/{slot_id_m1}?token={slot_tok}")
        self.assertEqual(rev_resp.status_code, 200)
        rev_data = rev_resp.json()
        self.assertEqual(rev_data["record_type"], "SLOT")
        ent0 = rev_data["entries"][0]
        self.assertEqual(ent0["p"], 4.0)
        self.assertEqual(ent0["jalur_lajur"], "A L1")

        # Rename minggu from M1 -> M2 when saving -> deletes old M1 slot & creates M2 slot
        mock_replace.reset_mock()
        rename_resp = self.client.post(
            f"/api/opname/review/{slot_id_m1}/save?token={slot_tok}",
            json={
                "aset": "PV",
                "wilayah": "W1",
                "vendor": "MIJ",
                "minggu": "M2",
                "entries": [
                    {
                        "tanggal": "2026-11-10",
                        "kode_temuan": "101126PV001",
                        "lokasi": "KM 45+200",
                        "jalur": "A",
                        "lajur": "L1",
                        "item_key": ent0["item_key"],
                        "p": 5.0,
                        "l": 1.0,
                        "t": 0.05,
                        "jml": 1.0,
                        "volume": 0.25,
                    }
                ],
            },
        )
        self.assertEqual(rename_resp.status_code, 200)
        mock_delete_rows.assert_called_once_with(
            settings.OPNAME_EXCEL_SHARE_LINK,
            "TBL_LOG_PV",
            slot_id_m1,
            target_drive_item=("DRV1", "ITM_NOV"),
        )
        slot_id_m2 = "XLS-2611-PV-W1-MIJ-M2"
        self.assertEqual(mock_replace.call_args[0][2], slot_id_m2)

        conn = sqlite3.connect(self.db_path)
        m1_st = conn.execute("SELECT status FROM opname_slots WHERE slot_id = ?", (slot_id_m1,)).fetchone()[0]
        m2_st = conn.execute("SELECT status FROM opname_slots WHERE slot_id = ?", (slot_id_m2,)).fetchone()[0]
        conn.close()
        self.assertEqual(m1_st, "REPLACED")
        self.assertEqual(m2_st, "ACTIVE")

        # /undo on M2 voids both opname_entries and opname_slots and removes it from active list
        main.process_message(
            {"id": {"_serialized": "false_628111@c.us_UNDOWEB"}, "from": "628111@c.us", "hasMedia": False, "body": f"/undo {slot_id_m2}", "_session": "default"}
        )
        after_undo = self.client.get(f"/api/opname/slots?token={dash_tok}&cycle=2026-11").json()
        self.assertEqual(after_undo["slots"], [])
        self.assertEqual(after_undo["roster_progress"]["done"], 0)

    def test_console_root_and_guide_render_real_stats_without_aislop(self):
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO opname_pending (pending_id, kind, aset, payload_json, xlsx_path, source_path, warnings_text, status, created_at) VALUES (?, 'SCAN_OCR', 'PV', '[]', '{}', '{}', '', 'PENDING', ?)",
            ("SCAN-261126-HERO", today_str),
        )
        conn.execute(
            "INSERT INTO opname_slots (slot_id, cycle_key, aset, wilayah, vendor, minggu, payload_json, status, updated_at) VALUES (?, '2026-11', 'PV', 'W1', 'MIJ', 'M1', '{}', 'ACTIVE', ?)",
            ("XLS-2611-PV-W1-MIJ-M1", today_str),
        )
        conn.execute("INSERT INTO daily_updates (kode, date) VALUES (?, ?)", ("181126PV001", today_str))
        conn.execute("INSERT INTO daily_updates (kode, date) VALUES (?, ?)", ("181126DR002", today_str))
        conn.commit()
        conn.close()

        dash_tok = make_opname_token("DASHBOARD")
        root_resp = self.client.get("/")
        self.assertEqual(root_resp.status_code, 200)
        self.assertIn(f"/opname?token={dash_tok}", root_resp.text)
        self.assertIn("1 form", root_resp.text)
        self.assertIn("1 / 21", root_resp.text)
        self.assertIn("2 kode", root_resp.text)
        for slop_marker in ("#1e1b4b", "#4f46e5", "#7c3aed", "backdrop-filter", "\u2014", "outline: none"):
            self.assertNotIn(slop_marker, root_resp.text)

        guide_resp = self.client.get("/guide")
        self.assertEqual(guide_resp.status_code, 200)
        self.assertIn("docker compose -f docker-compose.arm.yml", guide_resp.text)
        self.assertIn("Scan Opname", guide_resp.text)
        for slop_marker in ("linear-gradient", "radial-gradient", "backdrop-filter", "\u2014", "outline: none"):
            self.assertNotIn(slop_marker, guide_resp.text)

    @patch("main.upload_file_to_onedrive", return_value=("OD_EDITED_AR", "https://1drv.ms/u/EDITED_AR"))
    @patch("main.replace_opname_slot_rows", return_value=(0, 2))
    @patch("main.ensure_monthly_opname_workbook", return_value=("DRV1", "ITM_NOV", "https://1drv.ms/x/NOV"))
    def test_review_ui_renders_ocr_banner_diffs_restore_and_save_excludes_removed(
        self,
        mock_ensure,
        mock_replace,
        mock_upload_arc,
    ):
        scan_id = "SCAN-261127-WEB1"
        slots_payload = [
            {
                "slot_id": "XLS-2611-PV-W1-MIJ-M3",
                "cycle_key": "2026-11",
                "cycle_month": 11,
                "cycle_year": 2026,
                "aset": "PV",
                "wilayah": "W1",
                "vendor": "MIJ",
                "minggu": "M3",
                "table_name": "TBL_LOG_PV",
                "entries": [
                    {
                        "tanggal": "2026-11-18",
                        "kode_temuan": "181126PV001",
                        "wilayah": "W1",
                        "vendor": "MIJ",
                        "lokasi": "KM 45+200",
                        "jalur_lajur": "A L1",
                        "item_key": "II.1",
                        "keyword": "Permanen",
                        "satuan": "m3",
                        "p": 5.4,
                        "l": 2.4,
                        "t": 0.07,
                        "vol_vendor": 1.025,
                        "vendor_p": 6.1,
                        "volume": 0.907,
                        "handwritten_edited": True,
                        "row_action": "",
                    },
                    {
                        "tanggal": "2026-11-18",
                        "kode_temuan": "181126PV002",
                        "wilayah": "W1",
                        "vendor": "MIJ",
                        "lokasi": "KM 45+300",
                        "jalur_lajur": "A L1",
                        "item_key": "II.2",
                        "keyword": "Salob",
                        "satuan": "m3",
                        "vol_vendor": 0.2,
                        "volume": 0.0,
                        "handwritten_edited": True,
                        "row_action": "REMOVED",
                    },
                    {
                        "tanggal": "2026-11-18",
                        "kode_temuan": "-",
                        "wilayah": "W1",
                        "vendor": "MIJ",
                        "lokasi": "KM 46+100",
                        "jalur_lajur": "B L1",
                        "item_key": "II.6",
                        "keyword": "Hotmix",
                        "satuan": "Ton",
                        "jml": 2.5,
                        "volume": 2.5,
                        "handwritten_edited": True,
                        "row_action": "ADDED",
                    },
                ],
            }
        ]
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO opname_pending (pending_id, kind, aset, payload_json, xlsx_path, source_path, warnings_text, status, created_at) VALUES (?, 'SCAN_OCR', 'PV', ?, '{}', '{}', '', 'PENDING', ?)",
            (scan_id, main.json.dumps(slots_payload), datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()
        conn.close()

        tok = make_opname_token(scan_id)
        html_resp = self.client.get(f"/review/{scan_id}?token={tok}")
        self.assertEqual(html_resp.status_code, 200)
        for marker in ('id="ocrReviewBanner"', "Revisi Tangan OCR", "Pulihkan Baris", "tag-added", "tag-removed", "diff-strip"):
            self.assertIn(marker, html_resp.text)

        all_removed_resp = self.client.post(
            f"/api/opname/review/{scan_id}/save?token={tok}",
            json={
                "aset": "PV",
                "wilayah": "W1",
                "vendor": "MIJ",
                "minggu": "M3",
                "entries": [
                    {
                        "tanggal": "2026-11-18",
                        "lokasi": "KM 45+300",
                        "item_key": "II.2",
                        "volume": 0,
                        "row_action": "REMOVED",
                    }
                ],
            },
        )
        self.assertEqual(all_removed_resp.status_code, 422)

        save_resp = self.client.post(
            f"/api/opname/review/{scan_id}/save?token={tok}",
            json={
                "aset": "PV",
                "wilayah": "W1",
                "vendor": "MIJ",
                "minggu": "M3",
                "entries": slots_payload[0]["entries"],
            },
        )
        self.assertEqual(save_resp.status_code, 200)
        mock_replace.assert_called_once()
        excel_rows = mock_replace.call_args[0][3]
        self.assertEqual(len(excel_rows), 2)
        self.assertEqual([r[8] for r in excel_rows], ["II.1", "II.6"])
