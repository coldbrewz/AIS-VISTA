import base64
import datetime
import io
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import openpyxl
from PIL import Image

import main
from config import settings
from services.message_utils import (
    extract_kode_from_text,
    extract_media_metadata,
    extract_scan_opname_hint,
    resolve_billing_cycle,
)
from services.opname_catalog import PV_ITEMS
from services.opname_xlsx import build_prefilled_standard_xlsx, parse_standard_opname_xlsx


def _make_sample_pv_xlsx(
    rows_by_month: dict[str, list[dict]],
    preset_wil: str = "W1",
    preset_vend: str = "MIJ",
    use_header_meta: bool = True,
) -> bytes:
    """Build a multi-month standard Pavement workbook (header Wilayah/Vendor + ditto-capable columns)."""
    wb = openpyxl.Workbook()
    first = True
    for mon_abbr, row_list in rows_by_month.items():
        ws = wb.active if first else wb.create_sheet(mon_abbr)
        first = False
        ws.title = mon_abbr
        if use_header_meta:
            ws.cell(7, 2, "Wilayah:")
            ws.cell(7, 4, preset_wil)
            ws.cell(7, 5, "Vendor:")
            ws.cell(7, 6, preset_vend)
            headers = [
                "No.", "Tanggal", "Minggu", "Kode Temuan",
                "STA / KM", "Jalur", "Lajur", "KODE", "Item / Keyword RAB",
                "P", "L", "T", "Jml", "Vol. Vendor", "Vol. Opname", "Satuan",
                "Baik", "Tdk Baik", "Keterangan",
            ]
            for i, h in enumerate(headers):
                ws.cell(10, 2 + i, h)
            for idx, rec in enumerate(row_list, start=11):
                ws.cell(idx, 2, idx - 10)
                if "tanggal" in rec and rec["tanggal"] is not None:
                    ws.cell(idx, 3, rec["tanggal"])
                if "minggu" in rec and rec["minggu"] is not None:
                    ws.cell(idx, 4, rec["minggu"])
                if "kode_temuan" in rec and rec["kode_temuan"] is not None:
                    ws.cell(idx, 5, rec["kode_temuan"])
                if "lokasi" in rec and rec["lokasi"] is not None:
                    ws.cell(idx, 6, rec["lokasi"])
                if "jalur" in rec and rec["jalur"] is not None:
                    ws.cell(idx, 7, rec["jalur"])
                if "lajur" in rec and rec["lajur"] is not None:
                    ws.cell(idx, 8, rec["lajur"])
                ws.cell(idx, 10, rec["item"])
                if rec.get("p") is not None:
                    ws.cell(idx, 11, rec["p"])
                if rec.get("l") is not None:
                    ws.cell(idx, 12, rec["l"])
                if rec.get("t") is not None:
                    ws.cell(idx, 13, rec["t"])
                if rec.get("jml") is not None:
                    ws.cell(idx, 14, rec["jml"])
                if rec.get("vol_vendor") is not None:
                    ws.cell(idx, 15, rec["vol_vendor"])
                if rec.get("vol_opname") is not None:
                    ws.cell(idx, 16, rec["vol_opname"])
                ws.cell(idx, 18, 1)
                ws.cell(idx, 20, rec.get("ket", ""))
        else:
            headers = [
                "No.", "Tanggal", "Minggu", "Kode Temuan", "Wilayah", "Vendor",
                "STA / KM", "Jalur", "Lajur", "KODE", "Item / Keyword RAB",
                "P", "L", "T", "Jml", "Vol. Vendor", "Vol. Opname", "Satuan",
                "Baik", "Tdk Baik", "Keterangan",
            ]
            for i, h in enumerate(headers):
                ws.cell(10, 2 + i, h)
            for idx, rec in enumerate(row_list, start=11):
                ws.cell(idx, 2, idx - 10)
                ws.cell(idx, 3, rec["tanggal"])
                ws.cell(idx, 4, rec.get("minggu", "M1"))
                ws.cell(idx, 5, rec.get("kode_temuan", "-"))
                ws.cell(idx, 6, rec.get("wilayah", preset_wil))
                ws.cell(idx, 7, rec.get("vendor", preset_vend))
                ws.cell(idx, 8, rec["lokasi"])
                ws.cell(idx, 9, rec.get("jalur", "A"))
                ws.cell(idx, 10, rec.get("lajur", "L1"))
                ws.cell(idx, 12, rec["item"])
                if rec.get("p") is not None:
                    ws.cell(idx, 13, rec["p"])
                if rec.get("l") is not None:
                    ws.cell(idx, 14, rec["l"])
                if rec.get("t") is not None:
                    ws.cell(idx, 15, rec["t"])
                if rec.get("jml") is not None:
                    ws.cell(idx, 16, rec["jml"])
                if rec.get("vol_vendor") is not None:
                    ws.cell(idx, 17, rec["vol_vendor"])
                if rec.get("vol_opname") is not None:
                    ws.cell(idx, 18, rec["vol_opname"])
                ws.cell(idx, 20, 1)
                ws.cell(idx, 22, rec.get("ket", ""))
        tot_r = 11 + len(row_list)
        ws.cell(tot_r, 2, "TOTAL PEMERIKSAAN")

    ws_boq = wb.create_sheet("DAFTAR_BOQ")
    for idx_b, it in enumerate(PV_ITEMS, start=2):
        ws_boq.cell(idx_b, 1, it.keyword)
        ws_boq.cell(idx_b, 2, it.item_key)
        ws_boq.cell(idx_b, 3, it.uraian)
        ws_boq.cell(idx_b, 4, it.satuan)
    ws_boq.cell(1, 7, "PV")
    ws_boq.cell(2, 7, preset_wil)
    ws_boq.cell(3, 7, preset_vend)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _make_sample_pdf_bytes() -> bytes:
    im = Image.new("RGB", (400, 300), "white")
    buf = io.BytesIO()
    im.save(buf, format="PDF")
    return buf.getvalue()


class OpnameWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "test_vista.db")
        self.orig_db = settings.DB_URL
        self.orig_opname_link = settings.OPNAME_EXCEL_SHARE_LINK
        settings.DB_URL = self.db_path
        settings.OPNAME_EXCEL_SHARE_LINK = "https://1drv.ms/x/s!TEST_OPNAME_LINK"
        main.session_ready_at = 0
        main.init_db()

    def tearDown(self):
        settings.DB_URL = self.orig_db
        settings.OPNAME_EXCEL_SHARE_LINK = self.orig_opname_link
        self.tmpdir.cleanup()

    def test_trigger_separation_and_billing_cycle(self):
        self.assertIsNotNone(extract_kode_from_text("Kode: 191026PV001\nHotmix"))
        self.assertIsNone(extract_scan_opname_hint("Kode: 191026PV001\nHotmix"))
        self.assertEqual(
            extract_scan_opname_hint("Scan Opname PV W1 M2"),
            {"aset": "PV", "wilayah": "W1", "minggu": "M2"},
        )
        self.assertEqual(
            extract_media_metadata({"media": {"filename": "PV_W1_MIJ_2026.xlsx", "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}}),
            ("PV_W1_MIJ_2026.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        )
        self.assertEqual(resolve_billing_cycle(datetime.date(2026, 10, 25)), (10, 2026))
        self.assertEqual(resolve_billing_cycle(datetime.date(2026, 10, 26)), (11, 2026))
        self.assertEqual(resolve_billing_cycle(datetime.date(2026, 12, 26)), (1, 2027))

    def test_xlsx_parser_handles_over_25_rows_and_uncached_formulas(self):
        rows_30 = [
            {
                "tanggal": datetime.date(2026, 11, 2),
                "minggu": "M1",
                "lokasi": f"KM {28 + (i % 20)}+200",
                "item": "Permanen",
                "p": 4.0,
                "l": 1.0,
                "t": 0.05,
                # Leave vol_vendor & vol_opname None to test uncached P*L*T computation
            }
            for i in range(30)
        ]
        # Add 1 Marka Putih thermoplastic row with revised Vol. Opname
        rows_30.append(
            {
                "tanggal": datetime.date(2026, 11, 3),
                "minggu": "M1",
                "lokasi": "KM 45+200",
                "item": "Marka Putih",
                "vol_vendor": 20.0,
                "vol_opname": 18.5,
            }
        )
        xlsx_bytes = _make_sample_pv_xlsx({"NOV": rows_30})
        res = parse_standard_opname_xlsx(xlsx_bytes, filename="PV_W1_MIJ_2026.xlsx")
        self.assertTrue(res.is_standard_form)
        self.assertEqual(res.errors, [])
        self.assertEqual(res.roster_warnings, [])
        self.assertEqual(len(res.slots), 1)
        sl = res.slots[0]
        self.assertEqual(sl.slot_id, "XLS-2611-PV-W1-MIJ-M1")
        self.assertEqual(len(sl.entries), 31)
        self.assertAlmostEqual(sl.entries[0]["volume"], 0.2)
        self.assertAlmostEqual(sl.entries[-1]["volume"], 18.5)

    @patch("main.download_file_from_onedrive")
    @patch("main.upload_file_to_onedrive", return_value=("OD_ITM_XLS", "https://1drv.ms/u/ARC_XLS"))
    @patch("main.replace_opname_slot_rows", return_value=(0, 2))
    @patch("main.ensure_monthly_opname_workbook", return_value=("DRV1", "ITM_NOV", "https://1drv.ms/x/NOV"))
    @patch("main.send_whatsapp_document")
    @patch("main.send_whatsapp_message")
    def test_xlsx_drop_idempotent_revision_status_arsip_and_undo(
        self,
        mock_send,
        mock_send_doc,
        mock_ensure,
        mock_replace,
        mock_upload_arc,
        mock_dl_arc,
    ):
        # 1) Initial drop of M1 file
        xlsx_v1 = _make_sample_pv_xlsx(
            {
                "NOV": [
                    {"tanggal": datetime.date(2026, 11, 10), "minggu": "M1", "lokasi": "KM 45+200", "item": "Permanen", "vol_vendor": 0.27, "vol_opname": 0.27},
                    {"tanggal": datetime.date(2026, 11, 10), "minggu": "M1", "lokasi": "KM 45+200", "item": "Hotmix", "vol_opname": 0.62},
                ]
            }
        )
        mock_dl_arc.return_value = xlsx_v1
        with patch("main._extract_image_bytes_from_message", return_value=xlsx_v1):
            main.process_message(
                {
                    "id": {"_serialized": "false_628111@c.us_XLSX1"},
                    "from": "628111@c.us",
                    "hasMedia": True,
                    "body": "Opname",
                    "media": {"filename": "PV_W1_MIJ_2026.xlsx", "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
                    "_session": "default",
                }
            )
        mock_ensure.assert_called_once_with(settings.OPNAME_EXCEL_SHARE_LINK, 11, 2026)
        mock_upload_arc.assert_called_once()
        mock_replace.assert_called_once()
        slot_id_m1 = "XLS-2611-PV-W1-MIJ-M1"
        self.assertEqual(mock_replace.call_args[0][2], slot_id_m1)
        # Verify TBL_LOG_* row stores OneDrive link instead of local server path
        self.assertEqual(mock_replace.call_args[0][3][0][19], "https://1drv.ms/u/ARC_XLS")
        self.assertIn(slot_id_m1, mock_send.call_args[0][1])

        # 2) Revised M1 + new M2 in same workbook -> replaces M1 without double counting and adds M2
        mock_replace.reset_mock()
        mock_replace.side_effect = [(2, 1), (0, 1)]
        xlsx_v2 = _make_sample_pv_xlsx(
            {
                "NOV": [
                    {"tanggal": datetime.date(2026, 11, 10), "minggu": "M1", "lokasi": "KM 45+200", "item": "Permanen", "vol_vendor": 0.27, "vol_opname": 0.25},
                    {"tanggal": datetime.date(2026, 11, 17), "minggu": "M2", "lokasi": "KM 46+100", "item": "Marka Putih", "vol_opname": 18.0},
                ]
            }
        )
        with patch("main._extract_image_bytes_from_message", return_value=xlsx_v2):
            main.process_message(
                {
                    "id": {"_serialized": "false_628111@c.us_XLSX2"},
                    "from": "628111@c.us",
                    "hasMedia": True,
                    "body": "Opname PV",
                    "media": {"filename": "PV_W1_MIJ_2026.xlsx", "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
                    "_session": "default",
                }
            )
        self.assertEqual(mock_replace.call_count, 2)
        conn = sqlite3.connect(self.db_path)
        active_m1 = conn.execute("SELECT volume FROM opname_entries WHERE opname_id=? AND status='ACTIVE'", (slot_id_m1,)).fetchall()
        replaced_m1 = conn.execute("SELECT COUNT(*) FROM opname_entries WHERE opname_id=? AND status='REPLACED'", (slot_id_m1,)).fetchone()[0]
        conn.close()
        self.assertEqual(active_m1, [(0.25,)])
        self.assertEqual(replaced_m1, 2)

        # 3) /status opname shows M1, M2 active on PV | W1 | MIJ out of 21 slots
        mock_send.reset_mock()
        main.process_message(
            {"id": {"_serialized": "false_628111@c.us_STAT1"}, "from": "628111@c.us", "hasMedia": False, "body": "/status opname 2026-11", "_session": "default"}
        )
        stat_reply = mock_send.call_args[0][1]
        self.assertIn("21 Slot", stat_reply)
        self.assertIn("PV | W1 | MIJ : M1, M2", stat_reply)

        # 4) /arsip downloads from OneDrive item_id and sends document + OneDrive URL
        main.process_message(
            {"id": {"_serialized": "false_628111@c.us_ARS1"}, "from": "628111@c.us", "hasMedia": False, "body": f"/arsip {slot_id_m1}", "_session": "default"}
        )
        mock_dl_arc.assert_called_once_with("OD_ITM_XLS")
        mock_send_doc.assert_called_once()
        self.assertEqual(mock_send_doc.call_args[0][2], "PV_W1_MIJ_2026.xlsx")
        self.assertIn("https://1drv.ms/u/ARC_XLS", mock_send_doc.call_args[1]["caption"])

        # 5) /undo targets exact OneDrive workbook
        with patch("main.delete_opname_rows_by_id", return_value=1) as mock_del:
            main.process_message(
                {"id": {"_serialized": "false_628111@c.us_UNDO1"}, "from": "628111@c.us", "hasMedia": False, "body": f"/undo {slot_id_m1}", "_session": "default"}
            )
            mock_del.assert_called_once_with(
                settings.OPNAME_EXCEL_SHARE_LINK,
                "TBL_LOG_PV",
                slot_id_m1,
                target_drive_item=("DRV1", "ITM_NOV"),
            )

    @patch("main.upload_file_to_onedrive", return_value=("OD_ITM_MIS", "https://1drv.ms/u/ARC_MIS"))
    @patch("main.replace_opname_slot_rows", return_value=(0, 1))
    @patch("main.ensure_monthly_opname_workbook", return_value=("DRV1", "ITM_NOV", "https://1drv.ms/x/NOV"))
    @patch("main.send_whatsapp_message")
    def test_roster_mismatch_asks_confirmation_then_commits_on_simpan(
        self,
        mock_send,
        mock_ensure,
        mock_replace,
        mock_upload_arc,
    ):
        # Put MIJ (official W1 vendor) on W2 location -> bot must ask confirmation first!
        xlsx_mismatch = _make_sample_pv_xlsx(
            {
                "NOV": [
                    {"tanggal": datetime.date(2026, 11, 12), "minggu": "M2", "wilayah": "W2", "lokasi": "KM 72+500", "item": "Permanen", "vol_opname": 0.4}
                ]
            },
            preset_wil="W2",
            preset_vend="MIJ",
        )
        with patch("main._extract_image_bytes_from_message", return_value=xlsx_mismatch):
            main.process_message(
                {
                    "id": {"_serialized": "false_628111@c.us_MIS1"},
                    "from": "628111@c.us",
                    "hasMedia": True,
                    "body": "Opname",
                    "media": {"filename": "PV_W2_MIJ.xlsx", "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
                    "_session": "default",
                }
            )
        mock_replace.assert_not_called()
        reply = mock_send.call_args[0][1]
        self.assertIn("Butuh Konfirmasi Roster", reply)
        conf_id = reply.split("CONF-")[1].split(")")[0]
        conf_code = f"CONF-{conf_id}"

        # Confirm with /simpan CONF-... -> now writes to OneDrive silo
        mock_send.reset_mock()
        main.process_message(
            {"id": {"_serialized": "false_628111@c.us_SIMPCONF"}, "from": "628111@c.us", "hasMedia": False, "body": f"/simpan {conf_code}", "_session": "default"}
        )
        mock_replace.assert_called_once()
        self.assertIn("Opname Berhasil Dicatat", mock_send.call_args[0][1])

    @patch("main.upload_file_to_onedrive", return_value=("OD_ITM_SCAN", "https://1drv.ms/u/ARC_SCAN"))
    @patch("main.replace_opname_slot_rows", return_value=(0, 2))
    @patch("main.ensure_monthly_opname_workbook", return_value=("DRV1", "ITM_NOV", "https://1drv.ms/x/NOV"))
    @patch("main.extract_opname_form_ocr")
    @patch("main.send_whatsapp_document")
    @patch("main.send_whatsapp_message")
    def test_scan_opname_pdf_stages_ocr_returns_xlsx_and_commits_on_simpan(
        self,
        mock_send,
        mock_send_doc,
        mock_ocr,
        mock_ensure,
        mock_replace,
        mock_upload_arc,
    ):
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
                        "keterangan": "Tulisan tangan revisi 0.25",
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
        pdf_bytes = _make_sample_pdf_bytes()
        with patch("main._extract_image_bytes_from_message", return_value=pdf_bytes):
            main.process_message(
                {
                    "id": {"_serialized": "false_628111@c.us_SCAN1"},
                    "from": "628111@c.us",
                    "hasMedia": True,
                    "body": "Scan Opname PV M3",
                    "media": {"filename": "opname_signed.pdf", "mimetype": "application/pdf"},
                    "_session": "default",
                }
            )

        # Must stage ONLY (0 writes before /simpan) and reply with preview + pre-filled .xlsx
        mock_replace.assert_not_called()
        mock_ocr.assert_called_once()
        preview = mock_send.call_args[0][1]
        self.assertIn("Hasil Scan Opname", preview)
        self.assertIn("0.25 m3", preview)
        self.assertIn("✏️", preview)
        mock_send_doc.assert_called_once()
        returned_xlsx = mock_send_doc.call_args[0][1]
        parsed_back = parse_standard_opname_xlsx(returned_xlsx, filename=mock_send_doc.call_args[0][2])
        self.assertTrue(parsed_back.is_standard_form)
        self.assertEqual(len(parsed_back.slots[0].entries), 2)
        self.assertAlmostEqual(parsed_back.slots[0].entries[0]["volume"], 0.25)

        scan_code = "SCAN-" + preview.split("SCAN-")[1].split("`")[0]
        main.process_message(
            {"id": {"_serialized": "false_628111@c.us_SIMP1"}, "from": "628111@c.us", "hasMedia": False, "body": f"/simpan {scan_code}", "_session": "default"}
        )
        mock_replace.assert_called_once()
        self.assertEqual(mock_replace.call_args[0][2], "XLS-2611-PV-W1-MIJ-M3")

    @patch("main.upload_file_to_onedrive", return_value=("OD_ITM_DEC", "https://1drv.ms/u/ARC_DEC"))
    @patch("main.replace_opname_slot_rows", return_value=(0, 1))
    @patch("main.ensure_monthly_opname_workbook")
    @patch("main.send_whatsapp_message")
    def test_auto_monthly_rollover_creates_once_per_cycle_and_routes_cross_month_undo(
        self,
        mock_send,
        mock_ensure,
        mock_replace,
        mock_upload_arc,
    ):
        mock_ensure.side_effect = [
            ("DRV1", "ITM_DEC", "https://1drv.ms/x/DEC"),
            ("DRV1", "ITM_NOV", "https://1drv.ms/x/NOV"),
        ]
        # Cycle 2026-12 (Nov 26 + Dec 02) + late Cycle 2026-11 (Nov 24)
        xlsx_dec1 = _make_sample_pv_xlsx({"DES": [{"tanggal": datetime.date(2026, 11, 26), "minggu": "M1", "lokasi": "KM 45+200", "item": "Permanen", "vol_opname": 0.3}]})
        xlsx_dec2 = _make_sample_pv_xlsx({"DES": [{"tanggal": datetime.date(2026, 12, 2), "minggu": "M2", "lokasi": "KM 46+100", "item": "Permanen", "vol_opname": 0.4}]})
        xlsx_nov_late = _make_sample_pv_xlsx({"NOV": [{"tanggal": datetime.date(2026, 11, 24), "minggu": "M4", "lokasi": "KM 47+100", "item": "Permanen", "vol_opname": 0.2}]})

        for msg_id, raw_b in [("D1", xlsx_dec1), ("D2", xlsx_dec2), ("N4", xlsx_nov_late)]:
            with patch("main._extract_image_bytes_from_message", return_value=raw_b):
                main.process_message(
                    {
                        "id": {"_serialized": f"false_628111@c.us_{msg_id}"},
                        "from": "628111@c.us",
                        "hasMedia": True,
                        "body": "Upload Opname",
                        "media": {"filename": "PV_W1_MIJ_2026.xlsx", "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
                        "_session": "default",
                    }
                )

        self.assertEqual(mock_ensure.call_count, 2)
        self.assertEqual(mock_ensure.call_args_list[0][0][1:], (12, 2026))
        self.assertEqual(mock_ensure.call_args_list[1][0][1:], (11, 2026))
        self.assertEqual(mock_replace.call_args_list[0][1]["target_drive_item"], ("DRV1", "ITM_DEC"))
        self.assertEqual(mock_replace.call_args_list[1][1]["target_drive_item"], ("DRV1", "ITM_DEC"))
        self.assertEqual(mock_replace.call_args_list[2][1]["target_drive_item"], ("DRV1", "ITM_NOV"))

        with patch("main.delete_opname_rows_by_id", return_value=1) as mock_del:
            main.process_message(
                {"id": {"_serialized": "false_628111@c.us_UNDOLATE"}, "from": "628111@c.us", "hasMedia": False, "body": "/undo XLS-2611-PV-W1-MIJ-M4", "_session": "default"}
            )
            mock_del.assert_called_once_with(
                settings.OPNAME_EXCEL_SHARE_LINK,
                "TBL_LOG_PV",
                "XLS-2611-PV-W1-MIJ-M4",
                target_drive_item=("DRV1", "ITM_NOV"),
            )

    def test_xlsx_parser_supports_header_meta_and_ditto_rows(self):
        # Blank template (no G2/G3 presets on DAFTAR_BOQ, only header Row 7 Wilayah/Vendor + ditto continuation rows)
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "NOV"
        ws.cell(7, 2, "Wilayah:")
        ws.cell(7, 4, "W1")
        ws.cell(7, 5, "Vendor:")
        ws.cell(7, 6, "PT MIJ")
        headers = [
            "No.", "Tanggal", "Minggu", "Kode Temuan",
            "STA / KM", "Jalur", "Lajur", "KODE", "Item / Keyword RAB",
            "P", "L", "T", "Jml", "Vol. Vendor", "Vol. Opname", "Satuan",
            "Baik", "Tdk Baik", "Keterangan",
        ]
        for i, h in enumerate(headers):
            ws.cell(10, 2 + i, h)
        # Row 11: full location details
        ws.cell(11, 3, datetime.date(2026, 11, 20))
        ws.cell(11, 4, "M4")
        ws.cell(11, 5, "201126PV001")
        ws.cell(11, 6, "KM 45+200")
        ws.cell(11, 7, "A")
        ws.cell(11, 8, "L1")
        ws.cell(11, 10, "Permanen")
        ws.cell(11, 16, 0.25)
        # Row 12: same location -> blank Tanggal, Minggu, Kode Temuan, STA/KM, Jalur, Lajur
        ws.cell(12, 10, "Hotmix")
        ws.cell(12, 16, 0.58)
        # Row 13: same location, M5 week override
        ws.cell(13, 4, "M5")
        ws.cell(13, 10, "Marka Putih")
        ws.cell(13, 16, 18.0)

        ws_boq = wb.create_sheet("DAFTAR_BOQ")
        ws_boq.cell(1, 7, "PV")
        buf = io.BytesIO()
        wb.save(buf)

        res = parse_standard_opname_xlsx(buf.getvalue(), filename="01_STD_Opname_Pavement.xlsx")
        self.assertTrue(res.is_standard_form)
        self.assertEqual(res.errors, [])
        self.assertEqual(res.roster_warnings, [])
        self.assertEqual(len(res.slots), 2)
        m4_slot = [s for s in res.slots if s.minggu == "M4"][0]
        m5_slot = [s for s in res.slots if s.minggu == "M5"][0]
        self.assertEqual(m4_slot.slot_id, "XLS-2611-PV-W1-MIJ-M4")
        self.assertEqual(len(m4_slot.entries), 2)
        self.assertEqual(m4_slot.entries[1]["lokasi"], "KM 45+200")
        self.assertEqual(m4_slot.entries[1]["jalur_lajur"], "A L1")
        self.assertEqual(m4_slot.entries[1]["kode_temuan"], "201126PV001")
        self.assertEqual(m5_slot.entries[0]["lokasi"], "KM 45+200")

    def test_xlsx_without_opname_trigger_is_ignored(self):
        xlsx_bytes = _make_sample_pv_xlsx(
            {"NOV": [{"tanggal": datetime.date(2026, 11, 20), "minggu": "M4", "lokasi": "KM 45+200", "item": "Permanen", "vol_opname": 0.25}]}
        )
        with patch("main._extract_image_bytes_from_message", return_value=xlsx_bytes) as mock_dl, \
             patch("main.replace_opname_slot_rows") as mock_rep, \
             patch("main.upload_file_to_onedrive") as mock_up, \
             patch("main.send_whatsapp_message") as mock_send:
            # Group .xlsx without caption & direct chat .xlsx with unrelated caption
            main.process_message(
                {
                    "id": {"_serialized": "false_628111@g.us_SKIP1"},
                    "from": "628111@g.us",
                    "hasMedia": True,
                    "body": "",
                    "media": {"filename": "RAB_Revisi.xlsx", "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
                    "_session": "default",
                }
            )
            main.process_message(
                {
                    "id": {"_serialized": "false_628111@c.us_SKIP2"},
                    "from": "628111@c.us",
                    "hasMedia": True,
                    "body": "Jadwal minggu depan",
                    "media": {"filename": "PV_W1_MIJ_2026.xlsx", "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
                    "_session": "default",
                }
            )
        mock_dl.assert_not_called()
        mock_rep.assert_not_called()
        mock_up.assert_not_called()
        mock_send.assert_not_called()

    @patch("main.upload_file_to_onedrive", return_value=("OD_ITM_SCAN2", "https://1drv.ms/u/ARC_SCAN2"))
    @patch("main.ensure_monthly_opname_workbook", return_value=("DRV1", "ITM_NOV", "https://1drv.ms/x/NOV"))
    @patch("main.extract_opname_form_ocr")
    @patch("main.send_whatsapp_document")
    @patch("main.send_whatsapp_message")
    def test_scan_opname_auto_recalculates_from_handwritten_dimensions(
        self,
        mock_send,
        mock_send_doc,
        mock_ocr,
        mock_ensure,
        mock_upload_arc,
    ):
        mock_ocr.return_value = (
            {
                "aset": "PV",
                "vendor": "MIJ",
                "wilayah": "W1",
                "minggu": "M2",
                "rows": [
                    {
                        "tanggal": "2026-11-11",
                        "kode_temuan": "111126PV001",
                        "wilayah": "W1",
                        "vendor": "MIJ",
                        "lokasi": "KM 45+200",
                        "jalur": "A",
                        "lajur": "L1",
                        "raw_item": "Permanen",
                        "p": 15.0,
                        "l": 2.0,
                        "t": 0.05,
                        "jml": None,
                        "vol_vendor": 2.5,
                        "vol_opname": None,
                        "dimension_edited": True,
                        "handwritten_edited": True,
                    },
                    {
                        "tanggal": "2026-11-11",
                        "kode_temuan": "111126PV002",
                        "wilayah": "W1",
                        "vendor": "MIJ",
                        "lokasi": "KM 45+300",
                        "jalur": "A",
                        "lajur": "L1",
                        "raw_item": "Permanen",
                        "p": 15.0,
                        "l": 2.0,
                        "t": 0.05,
                        "jml": None,
                        "vol_vendor": 2.5,
                        "vol_opname": 1.4,
                        "dimension_edited": True,
                        "handwritten_edited": True,
                    },
                    {
                        "tanggal": "2026-11-11",
                        "kode_temuan": "111126PV003",
                        "wilayah": "W1",
                        "vendor": "MIJ",
                        "lokasi": "KM 45+400",
                        "jalur": "A",
                        "lajur": "L1",
                        "raw_item": "Permanen",
                        "p": 25.0,
                        "l": 2.0,
                        "t": None,
                        "jml": None,
                        "vol_vendor": 2.5,
                        "vol_opname": None,
                        "dimension_edited": False,
                        "handwritten_edited": False,
                    },
                    {
                        "tanggal": "2026-11-11",
                        "kode_temuan": "111126PV004",
                        "wilayah": "W1",
                        "vendor": "MIJ",
                        "lokasi": "KM 45+400",
                        "jalur": "A",
                        "lajur": "L1",
                        "raw_item": "Hotmix",
                        "p": 10.0,
                        "l": 2.0,
                        "t": 0.05,
                        "jml": None,
                        "vol_vendor": 2.3,
                        "vol_opname": None,
                        "dimension_edited": False,
                        "handwritten_edited": False,
                    },
                    {
                        "tanggal": "2026-11-11",
                        "kode_temuan": "111126PV005",
                        "wilayah": "W1",
                        "vendor": "MIJ",
                        "lokasi": "KM 31+120",
                        "jalur": "B",
                        "lajur": "L1",
                        "raw_item": "Hotmix",
                        "p": None,
                        "l": None,
                        "t": None,
                        "jml": 5.0,
                        "vol_vendor": 5.16,
                        "vol_opname": None,
                        "dimension_edited": True,
                        "handwritten_edited": True,
                    },
                    {
                        "tanggal": "2026-11-11",
                        "kode_temuan": "111126PV006",
                        "wilayah": "W1",
                        "vendor": "MIJ",
                        "lokasi": "Gorda Ramp Akses (Cikande)",
                        "jalur": "",
                        "lajur": "",
                        "raw_item": "Permanen",
                        "p": 6.1,
                        "l": 2.4,
                        "t": 0.07,
                        "jml": None,
                        "vol_vendor": 1.025,
                        "vol_opname": None,
                        "dimension_edited": True,
                        "handwritten_edited": True,
                    },
                ],
            },
            "",
        )
        pdf_bytes = _make_sample_pdf_bytes()
        with patch("main._extract_image_bytes_from_message", return_value=pdf_bytes):
            main.process_message(
                {
                    "id": {"_serialized": "false_628111@c.us_SCAN_DIM1"},
                    "from": "628111@c.us",
                    "hasMedia": True,
                    "body": "Scan Opname PV M2",
                    "media": {"filename": "opname_dim_edit.pdf", "mimetype": "application/pdf"},
                    "_session": "default",
                }
            )

        preview = mock_send.call_args[0][1]
        self.assertIn("1.5 m3", preview)
        self.assertIn("(auto P×L×T)", preview)
        self.assertIn("1.4 m3", preview)
        self.assertIn("2.5 m3", preview)
        self.assertIn("2.3 Ton", preview)
        self.assertIn("5 Ton", preview)
        self.assertIn("(auto)", preview)
        self.assertIn("cek revisi di web", preview)

        returned_xlsx = mock_send_doc.call_args[0][1]
        parsed_back = parse_standard_opname_xlsx(returned_xlsx, filename=mock_send_doc.call_args[0][2])
        self.assertTrue(parsed_back.is_standard_form)
        self.assertEqual(parsed_back.errors, [])
        entries = parsed_back.slots[0].entries
        self.assertEqual(len(entries), 6)
        self.assertAlmostEqual(entries[0]["volume"], 1.5)
        self.assertAlmostEqual(entries[1]["volume"], 1.4)
        self.assertAlmostEqual(entries[2]["volume"], 2.5)
        self.assertAlmostEqual(entries[3]["volume"], 2.3)
        self.assertAlmostEqual(entries[4]["volume"], 5.0)
        self.assertAlmostEqual(entries[5]["volume"], 1.025)

        conn = sqlite3.connect(self.db_path)
        payload_row = conn.execute("SELECT payload_json FROM opname_pending ORDER BY created_at DESC LIMIT 1").fetchone()
        conn.close()
        staged_entries = main.json.loads(payload_row[0])[0]["entries"]
        self.assertTrue(staged_entries[0]["handwritten_edited"])
        self.assertFalse(staged_entries[2]["handwritten_edited"])
        self.assertTrue(staged_entries[5]["handwritten_edited"])

    @patch("main.upload_file_to_onedrive", return_value=("OD_ITM_TYPO", "https://1drv.ms/u/ARC_TYPO"))
    @patch("main.ensure_monthly_opname_workbook", return_value=("DRV1", "ITM_AGT", "https://1drv.ms/x/AGT"))
    @patch("main.extract_opname_form_ocr")
    @patch("main.send_whatsapp_document")
    @patch("main.send_whatsapp_message")
    def test_scan_opname_warns_instead_of_rejecting_unknown_location_when_header_wilayah_present(
        self,
        mock_send,
        mock_send_doc,
        mock_ocr,
        mock_ensure,
        mock_upload_arc,
    ):
        mock_ocr.return_value = (
            {
                "aset": "PV",
                "vendor": "MIJ",
                "wilayah": "W1",
                "minggu": "M3",
                "rows": [
                    {
                        "tanggal": "2026-08-14",
                        "kode_temuan": "-",
                        "wilayah": "",
                        "vendor": "MIJ",
                        "lokasi": "STA Pintu Air Ramp Off",
                        "jalur": "",
                        "lajur": "",
                        "raw_item": "Salob",
                        "p": 0.5,
                        "l": 0.3,
                        "t": 0.05,
                        "jml": None,
                        "vol_vendor": 0.008,
                        "vol_opname": None,
                    }
                ],
            },
            "",
        )
        pdf_bytes = _make_sample_pdf_bytes()
        with patch("main._extract_image_bytes_from_message", return_value=pdf_bytes):
            main.process_message(
                {
                    "id": {"_serialized": "false_628111@c.us_SCAN_LOCWARN"},
                    "from": "628111@c.us",
                    "hasMedia": True,
                    "body": "Scan Opname PV M3",
                    "media": {"filename": "opname_m3.pdf", "mimetype": "application/pdf"},
                    "_session": "default",
                }
            )

        preview = mock_send.call_args[0][1]
        self.assertIn("Hasil Scan Opname", preview)
        self.assertIn("STA Pintu Air Ramp Off", preview)
        self.assertIn("memakai Wilayah header W1", preview)
        mock_send_doc.assert_called_once()

    @patch("main.upload_file_to_onedrive", return_value=("OD_ITM_ANCHOR", "https://1drv.ms/u/ARC_ANCHOR"))
    @patch("main.replace_opname_slot_rows", return_value=(0, 1))
    @patch("main.ensure_monthly_opname_workbook", return_value=("DRV1", "ITM_AGT", "https://1drv.ms/x/AGT"))
    @patch("main.extract_opname_form_ocr")
    @patch("main.send_whatsapp_document")
    @patch("main.send_whatsapp_message")
    def test_scan_opname_excel_anchored_merge_locks_location_and_records_vendor_dims(
        self,
        mock_send,
        mock_send_doc,
        mock_ocr,
        mock_ensure,
        mock_replace,
        mock_upload_arc,
    ):
        base_xlsx = _make_sample_pv_xlsx(
            {
                "AGT": [
                    {
                        "tanggal": datetime.date(2026, 8, 14),
                        "minggu": "M3",
                        "kode_temuan": "140826PV001",
                        "lokasi": "STA Ciujung Ramp Off",
                        "jalur": "A",
                        "lajur": "L1",
                        "item": "Permanen",
                        "p": 6.1,
                        "l": 2.4,
                        "t": 0.07,
                        "vol_vendor": 1.025,
                        "vol_opname": 1.025,
                    }
                ]
            }
        )
        with patch("main._extract_image_bytes_from_message", return_value=base_xlsx):
            main.process_message(
                {
                    "id": {"_serialized": "false_628111@c.us_BASEXLS1"},
                    "from": "628111@c.us",
                    "hasMedia": True,
                    "body": "Opname PV M3",
                    "media": {
                        "filename": "PV_W1_MIJ_2026.xlsx",
                        "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    },
                    "_session": "default",
                }
            )

        mock_send.reset_mock()
        mock_ocr.return_value = (
            {
                "aset": "PV",
                "vendor": "MIJ",
                "wilayah": "W1",
                "minggu": "M3",
                "rows": [
                    {
                        "tanggal": "2026-08-14",
                        "kode_temuan": "-",
                        "wilayah": "W1",
                        "vendor": "MIJ",
                        "lokasi": "STA Cijantung Ramp Off",
                        "jalur": "",
                        "lajur": "",
                        "raw_item": "Permanen",
                        "p": 5.4,
                        "l": 2.4,
                        "t": 0.07,
                        "jml": None,
                        "vol_vendor": 1.025,
                        "vol_opname": None,
                        "dimension_edited": True,
                        "handwritten_edited": True,
                    }
                ],
            },
            "",
        )
        pdf_bytes = _make_sample_pdf_bytes()
        with patch("main._extract_image_bytes_from_message", return_value=pdf_bytes):
            main.process_message(
                {
                    "id": {"_serialized": "false_628111@c.us_SCAN_ANCHOR1"},
                    "from": "628111@c.us",
                    "hasMedia": True,
                    "body": "Scan Opname PV M3",
                    "media": {"filename": "opname_anchor.pdf", "mimetype": "application/pdf"},
                    "_session": "default",
                }
            )

        preview = mock_send.call_args[0][1]
        self.assertIn("STA Ciujung Ramp Off", preview)
        self.assertIn("0.907 m3", preview)
        self.assertNotIn("Cijantung", preview)
        self.assertNotIn("memakai Wilayah header W1", preview)

        conn = sqlite3.connect(self.db_path)
        payload_row = conn.execute("SELECT payload_json FROM opname_pending ORDER BY created_at DESC LIMIT 1").fetchone()
        conn.close()
        staged_ent = main.json.loads(payload_row[0])[0]["entries"][0]
        self.assertEqual(staged_ent["lokasi"], "STA Ciujung Ramp Off")
        self.assertEqual(staged_ent["kode_temuan"], "140826PV001")
        self.assertEqual(staged_ent["jalur_lajur"], "A L1")
        self.assertAlmostEqual(staged_ent["vendor_p"], 6.1)
        self.assertTrue(staged_ent["anchored_from_excel"])
        self.assertAlmostEqual(staged_ent["p"], 5.4)
        self.assertAlmostEqual(staged_ent["volume"], 0.907)

    @patch("main.upload_file_to_onedrive", return_value=("OD_ITM_AR", "https://1drv.ms/u/ARC_AR"))
    @patch("main.replace_opname_slot_rows", return_value=(0, 2))
    @patch("main.ensure_monthly_opname_workbook", return_value=("DRV1", "ITM_AGT", "https://1drv.ms/x/AGT"))
    @patch("main.extract_opname_form_ocr")
    @patch("main.send_whatsapp_document")
    @patch("main.send_whatsapp_message")
    def test_scan_opname_added_removed_rekap_mismatch_and_simpan_excludes_removed(
        self,
        mock_send,
        mock_send_doc,
        mock_ocr,
        mock_ensure,
        mock_replace,
        mock_upload_arc,
    ):
        mock_ocr.return_value = (
            {
                "aset": "PV",
                "vendor": "MIJ",
                "wilayah": "W1",
                "minggu": "M3",
                "rows": [
                    {
                        "tanggal": "2026-08-14",
                        "lokasi": "KM 45+200",
                        "raw_item": "Permanen",
                        "vol_vendor": 1.0,
                        "vol_opname": 1.0,
                        "row_action": "",
                    },
                    {
                        "tanggal": "2026-08-14",
                        "lokasi": "KM 45+300",
                        "raw_item": "Salob",
                        "vol_vendor": 0.25,
                        "vol_opname": 0,
                        "row_action": "REMOVED",
                    },
                    {
                        "tanggal": "2026-08-14",
                        "lokasi": "KM 46+100",
                        "raw_item": "Hotmix",
                        "jml": 2.5,
                        "vol_opname": 2.5,
                        "row_action": "ADDED",
                    },
                ],
                "rekap_revisi": [{"raw_item": "Permanen", "vol_revisi": 2.5}],
            },
            "",
        )
        pdf_bytes = _make_sample_pdf_bytes()
        with patch("main._extract_image_bytes_from_message", return_value=pdf_bytes):
            main.process_message(
                {
                    "id": {"_serialized": "false_628111@c.us_SCAN_AR1"},
                    "from": "628111@c.us",
                    "hasMedia": True,
                    "body": "Scan Opname PV M3",
                    "media": {"filename": "opname_ar.pdf", "mimetype": "application/pdf"},
                    "_session": "default",
                }
            )

        preview = mock_send.call_args[0][1]
        self.assertIn("DIHAPUS / BATAL", preview)
        self.assertIn("(tambahan)", preview)
        self.assertIn("Vol. Revisi", preview)
        scan_id = "SCAN-" + preview.split("SCAN-")[1].split("`")[0]

        xlsx_bytes = mock_send_doc.call_args[0][1]
        parsed_xlsx = parse_standard_opname_xlsx(xlsx_bytes, filename=mock_send_doc.call_args[0][2])
        self.assertEqual(len(parsed_xlsx.slots[0].entries), 2)

        conn = sqlite3.connect(self.db_path)
        payload_row = conn.execute(
            "SELECT payload_json FROM opname_pending WHERE pending_id = ?", (scan_id,)
        ).fetchone()
        conn.close()
        staged_entries = main.json.loads(payload_row[0])[0]["entries"]
        self.assertEqual(len(staged_entries), 3)
        self.assertEqual(staged_entries[1]["row_action"], "REMOVED")
        self.assertEqual(staged_entries[2]["row_action"], "ADDED")

        mock_send.reset_mock()
        main.process_message(
            {
                "id": {"_serialized": "false_628111@c.us_SIMPAN_AR1"},
                "from": "628111@c.us",
                "hasMedia": False,
                "body": f"/simpan {scan_id}",
                "_session": "default",
            }
        )
        mock_replace.assert_called_once()
        committed_rows = mock_replace.call_args[0][3]
        self.assertEqual(len(committed_rows), 2)
        committed_keys = [r[8] for r in committed_rows]
        self.assertEqual(committed_keys, ["II.1", "II.6"])


if __name__ == "__main__":
    unittest.main()
