import datetime
import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch

import openpyxl
from fastapi.testclient import TestClient

import main
from config import settings
from services.opname_catalog import PV_ITEMS, check_roster_pairing, normalize_vendor
from services.opname_roster import (
    ROSTER_CONFIG_FILENAME,
    ROSTER_CONFIG_FOLDER,
    ensure_roster_tables,
    export_roster_payload,
    get_active_roster,
    pull_roster_from_onedrive,
)
from services.opname_web import make_opname_token
from services.opname_xlsx import parse_standard_opname_xlsx


def _make_xlsx_with_vendor(vendor_name: str) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "NOV"
    ws.cell(7, 2, "Wilayah:")
    ws.cell(7, 4, "W1")
    ws.cell(7, 5, "Vendor:")
    ws.cell(7, 6, vendor_name)
    headers = [
        "No.", "Tanggal", "Minggu", "Kode Temuan",
        "STA / KM", "Jalur", "Lajur", "KODE", "Item / Keyword RAB",
        "P", "L", "T", "Jml", "Vol. Vendor", "Vol. Opname", "Satuan",
        "Baik", "Tdk Baik", "Keterangan",
    ]
    for i, h in enumerate(headers):
        ws.cell(10, 2 + i, h)
    ws.cell(11, 2, 1)
    ws.cell(11, 3, datetime.date(2026, 11, 12))
    ws.cell(11, 4, "M2")
    ws.cell(11, 5, "121126PV001")
    ws.cell(11, 6, "KM 45+200")
    ws.cell(11, 10, "Permanen")
    ws.cell(11, 16, 0.35)
    ws.cell(12, 2, "TOTAL PEMERIKSAAN")

    ws_boq = wb.create_sheet("DAFTAR_BOQ")
    for idx_b, it in enumerate(PV_ITEMS, start=2):
        ws_boq.cell(idx_b, 1, it.keyword)
        ws_boq.cell(idx_b, 2, it.item_key)
        ws_boq.cell(idx_b, 3, it.uraian)
        ws_boq.cell(idx_b, 4, it.satuan)
    ws_boq.cell(1, 7, "PV")
    ws_boq.cell(2, 7, "W1")
    ws_boq.cell(3, 7, vendor_name)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class OpnameRosterTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "test_roster.db")
        self.orig_db = settings.DB_URL
        self.orig_opname_link = settings.OPNAME_EXCEL_SHARE_LINK
        self.orig_secret = settings.OPNAME_WEB_SECRET
        settings.DB_URL = self.db_path
        settings.OPNAME_EXCEL_SHARE_LINK = "https://1drv.ms/x/s!TEST_OPNAME_LINK"
        settings.OPNAME_WEB_SECRET = "roster-test-secret"
        main.session_ready_at = 0
        main.init_db()
        self.client = TestClient(main.app)
        self.dash_tok = make_opname_token("DASHBOARD")

    def tearDown(self):
        settings.DB_URL = self.orig_db
        settings.OPNAME_EXCEL_SHARE_LINK = self.orig_opname_link
        settings.OPNAME_WEB_SECRET = self.orig_secret
        self.tmpdir.cleanup()

    def test_auth_guard_for_all_roster_endpoints(self):
        self.assertEqual(self.client.get("/api/opname/roster").status_code, 403)
        self.assertEqual(self.client.post("/api/opname/roster/slot?token=bad", json={}).status_code, 403)
        self.assertEqual(self.client.post("/api/opname/roster/slot/toggle?token=bad", json={}).status_code, 403)
        self.assertEqual(self.client.post("/api/opname/roster/vendor/toggle?token=bad", json={}).status_code, 403)
        self.assertEqual(self.client.get("/api/opname/roster/export?token=bad").status_code, 403)
        self.assertEqual(self.client.post("/api/opname/roster/import?token=bad", json={}).status_code, 403)
        self.assertEqual(self.client.post("/api/opname/roster/sync-onedrive?token=bad").status_code, 403)

    @patch("main.upload_private_file_to_onedrive", return_value="OD_CFG_1")
    def test_add_new_vendor_slot_immediately_recognized_everywhere(self, mock_up_cfg):
        # Before adding, PT KARYA MANDIRI is rejected
        ok_before, _, _ = normalize_vendor("PT Karya Mandiri", "PV")
        self.assertFalse(ok_before)

        resp = self.client.post(
            f"/api/opname/roster/slot?token={self.dash_tok}",
            json={
                "vendor": "KARYA",
                "aliases": "PT KARYA MANDIRI, KARYA MANDIRI",
                "aset": "PV",
                "wilayah": "W1",
            },
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["ok"])
        self.assertTrue(body["onedrive_synced"])
        mock_up_cfg.assert_called_once()
        self.assertEqual(mock_up_cfg.call_args[0][1], ROSTER_CONFIG_FILENAME)
        self.assertEqual(mock_up_cfg.call_args[0][2], ROSTER_CONFIG_FOLDER)

        # Immediately accepted by catalog, roster pairing, and XLSX parser
        self.assertEqual(normalize_vendor("PT Karya Mandiri", "PV")[:2], (True, "KARYA"))
        self.assertEqual(check_roster_pairing("PV", "KARYA", "W1"), (True, ""))
        parsed = parse_standard_opname_xlsx(_make_xlsx_with_vendor("PT Karya Mandiri"), filename="PV_W1_KARYA.xlsx")
        self.assertEqual(parsed.errors, [])
        self.assertEqual(parsed.roster_warnings, [])
        self.assertEqual(parsed.slots[0].slot_id, "XLS-2611-PV-W1-KARYA-M2")

    @patch("main.upload_private_file_to_onedrive", return_value="OD_CFG_2")
    @patch("main.upload_file_to_onedrive", return_value=("OD_ITM", "https://1drv.ms/u/ARC_MIJ"))
    @patch("main.replace_opname_slot_rows", return_value=(0, 1))
    @patch("main.ensure_monthly_opname_workbook", return_value=("DRV1", "ITM_NOV", "https://1drv.ms/x/NOV"))
    @patch("main.send_whatsapp_message")
    def test_terminate_vendor_updates_counts_without_breaking_history(
        self,
        mock_send,
        mock_ensure,
        mock_replace,
        mock_upload_arc,
        mock_up_cfg,
    ):
        # 1) Commit historical MIJ slot while MIJ is active
        xlsx_mij = _make_xlsx_with_vendor("MIJ")
        with patch("main._extract_image_bytes_from_message", return_value=xlsx_mij):
            main.process_message(
                {
                    "id": {"_serialized": "false_628111@c.us_HISTMIJ"},
                    "from": "628111@c.us",
                    "hasMedia": True,
                    "body": "Opname",
                    "media": {"filename": "PV_W1_MIJ.xlsx", "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
                    "_session": "default",
                }
            )

        # 2) Terminate PV / MIJ / W1 in roster
        tog = self.client.post(
            f"/api/opname/roster/slot/toggle?token={self.dash_tok}",
            json={"aset": "PV", "vendor": "MIJ", "wilayah": "W1", "active": False},
        )
        self.assertEqual(tog.status_code, 200)
        self.assertEqual(len(get_active_roster(self.db_path)), 20)

        # /api/opname/slots total reflects 20 active slots (and MIJ past slot won't inflate active roster done count)
        slots_resp = self.client.get(f"/api/opname/slots?token={self.dash_tok}&cycle=2026-11").json()
        self.assertEqual(slots_resp["roster_progress"]["total"], 20)

        # /status opname uses dynamic 20-slot list
        mock_send.reset_mock()
        main.process_message(
            {"id": {"_serialized": "false_628111@c.us_STAT20"}, "from": "628111@c.us", "hasMedia": False, "body": "/status opname 2026-11", "_session": "default"}
        )
        stat_text = mock_send.call_args[0][1]
        self.assertIn("20 Slot", stat_text)
        self.assertNotIn("PV | W1 | MIJ", stat_text)

        # Historical MIJ slot still reopens cleanly in web editor
        hist_id = "XLS-2611-PV-W1-MIJ-M2"
        rev = self.client.get(f"/api/opname/review/{hist_id}?token={make_opname_token(hist_id)}")
        self.assertEqual(rev.status_code, 200)
        self.assertEqual(rev.json()["vendor"], "MIJ")

    @patch("main.upload_private_file_to_onedrive", return_value="OD_CFG_3")
    def test_vps_migration_json_export_import_and_onedrive_auto_restore(self, mock_up_cfg):
        # Customize DB 1: add KARYA and deactivate PV/MIJ/W1
        self.client.post(
            f"/api/opname/roster/slot?token={self.dash_tok}",
            json={"vendor": "KARYA", "aliases": "PT KARYA MANDIRI", "aset": "PV", "wilayah": "W1"},
        )
        self.client.post(
            f"/api/opname/roster/slot/toggle?token={self.dash_tok}",
            json={"aset": "PV", "vendor": "MIJ", "wilayah": "W1", "active": False},
        )
        exp_resp = self.client.get(f"/api/opname/roster/export?token={self.dash_tok}")
        self.assertEqual(exp_resp.status_code, 200)
        exported_bytes = exp_resp.content
        exported_obj = json.loads(exported_bytes.decode("utf-8"))

        # Path A: Simulate brand-new VPS DB importing JSON manually via API
        with tempfile.TemporaryDirectory() as vps2_dir:
            vps2_db = os.path.join(vps2_dir, "vps2.db")
            settings.DB_URL = vps2_db
            main.init_db()
            imp_resp = self.client.post(
                f"/api/opname/roster/import?token={self.dash_tok}",
                json=exported_obj,
            )
            self.assertEqual(imp_resp.status_code, 200)
            roster_vps2 = set(get_active_roster(vps2_db))
            self.assertIn(("PV", "KARYA", "W1"), roster_vps2)
            self.assertNotIn(("PV", "MIJ", "W1"), roster_vps2)

        # Path B: Simulate brand-new VPS DB auto-restoring from OneDrive on boot
        with tempfile.TemporaryDirectory() as vps3_dir:
            vps3_db = os.path.join(vps3_dir, "vps3.db")
            ensure_roster_tables(vps3_db)
            restored, _ = pull_roster_from_onedrive(
                vps3_db,
                lambda folder, fname: exported_bytes,
                only_if_unmodified=True,
            )
            self.assertTrue(restored)
            roster_vps3 = set(get_active_roster(vps3_db))
            self.assertIn(("PV", "KARYA", "W1"), roster_vps3)
            self.assertNotIn(("PV", "MIJ", "W1"), roster_vps3)

            # Once local changes are made on VPS 3, auto-restore must NOT overwrite them
            settings.DB_URL = vps3_db
            self.client.post(
                f"/api/opname/roster/slot?token={self.dash_tok}",
                json={"vendor": "BARU", "aset": "DR", "wilayah": "W2"},
            )
            skipped, _ = pull_roster_from_onedrive(
                vps3_db,
                lambda folder, fname: exported_bytes,
                only_if_unmodified=True,
            )
            self.assertFalse(skipped)
            self.assertIn(("DR", "BARU", "W2"), set(get_active_roster(vps3_db)))
