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
) -> bytes:
    """Build a multi-month standard Option A Pavement workbook for unit tests (with >25-row capability)."""
    wb = openpyxl.Workbook()
    first = True
    for mon_abbr, row_list in rows_by_month.items():
        ws = wb.active if first else wb.create_sheet(mon_abbr)
        first = False
        ws.title = mon_abbr
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
        self.archive_dir = os.path.join(self.tmpdir.name, "opname_archive")
        self.orig_db = settings.DB_URL
        self.orig_opname_link = settings.OPNAME_EXCEL_SHARE_LINK
        self.orig_archive = settings.OPNAME_ARCHIVE_DIR
        settings.DB_URL = self.db_path
        settings.OPNAME_EXCEL_SHARE_LINK = "https://1drv.ms/x/s!TEST_OPNAME_LINK"
        settings.OPNAME_ARCHIVE_DIR = self.archive_dir
        main.session_ready_at = 0
        main.init_db()

    def tearDown(self):
        settings.DB_URL = self.orig_db
        settings.OPNAME_EXCEL_SHARE_LINK = self.orig_opname_link
        settings.OPNAME_ARCHIVE_DIR = self.orig_archive
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
        with patch("main._extract_image_bytes_from_message", return_value=xlsx_v1):
            main.process_message(
                {
                    "id": {"_serialized": "false_628111@c.us_XLSX1"},
                    "from": "628111@c.us",
                    "hasMedia": True,
                    "body": "",
                    "media": {"filename": "PV_W1_MIJ_2026.xlsx", "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
                    "_session": "default",
                }
            )
        mock_ensure.assert_called_once_with(settings.OPNAME_EXCEL_SHARE_LINK, 11, 2026)
        mock_replace.assert_called_once()
        slot_id_m1 = "XLS-2611-PV-W1-MIJ-M1"
        self.assertEqual(mock_replace.call_args[0][2], slot_id_m1)
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
                    "body": "",
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

        # 4) /arsip sends stored .xlsx back
        main.process_message(
            {"id": {"_serialized": "false_628111@c.us_ARS1"}, "from": "628111@c.us", "hasMedia": False, "body": f"/arsip {slot_id_m1}", "_session": "default"}
        )
        mock_send_doc.assert_called_once()
        self.assertEqual(mock_send_doc.call_args[0][2], "PV_W1_MIJ_2026.xlsx")

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

    @patch("main.replace_opname_slot_rows", return_value=(0, 1))
    @patch("main.ensure_monthly_opname_workbook", return_value=("DRV1", "ITM_NOV", "https://1drv.ms/x/NOV"))
    @patch("main.send_whatsapp_message")
    def test_roster_mismatch_asks_confirmation_then_commits_on_simpan(
        self,
        mock_send,
        mock_ensure,
        mock_replace,
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
                    "body": "",
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

    @patch("main.replace_opname_slot_rows", return_value=(0, 1))
    @patch("main.ensure_monthly_opname_workbook")
    @patch("main.send_whatsapp_message")
    def test_auto_monthly_rollover_creates_once_per_cycle_and_routes_cross_month_undo(
        self,
        mock_send,
        mock_ensure,
        mock_replace,
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
                        "body": "",
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


if __name__ == "__main__":
    unittest.main()
