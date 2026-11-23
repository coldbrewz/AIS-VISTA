import base64
import datetime
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import main
from config import settings
from services.message_utils import (
    extract_kode_from_text,
    extract_opname_trigger,
    parse_structured_opname_caption,
    resolve_billing_cycle,
)


TINY_JPG_B64 = base64.b64encode(b"\xff\xd8\xff\xe0MOCKJPEGDATA\xff\xd9").decode("utf-8")


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

    def test_trigger_separation_between_sla_and_opname(self):
        sla_text = "Kode: 191026PV001\nPerbaikan Hotmix"
        opn_kode_text = "Opname: 191026PV001\nLokasi: KM 45+200 A\nVendor: MIJ"
        opn_routine_text = "Opname: RM\nLokasi: KM 36+150 s/d KM 38+750 A\nVendor: KOPKAR"
        opn_trc_alias = "Opname: TRC\nLokasi: KM 32+000 A\nVendor: KOPKAR"

        self.assertIsNotNone(extract_kode_from_text(sla_text))
        self.assertIsNone(extract_opname_trigger(sla_text))

        self.assertIsNone(extract_kode_from_text(opn_kode_text))
        self.assertEqual(
            extract_opname_trigger(opn_kode_text),
            {"aset": "PV", "kode_temuan": "191026PV001"},
        )
        self.assertEqual(
            extract_opname_trigger(opn_routine_text),
            {"aset": "RM", "kode_temuan": ""},
        )
        self.assertEqual(
            extract_opname_trigger(opn_trc_alias),
            {"aset": "CA", "kode_temuan": ""},
        )

    def test_structured_caption_parser_pxlxt_and_status(self):
        caption = (
            "Opname: 191026FE003\n"
            "Lokasi: KM 75+800 A L1\n"
            "Vendor: KOPKAR\n"
            "Tanggal: 27-10-2026\n"
            "Item:\n"
            "- II.1: 4.5 x 1.2 x 0.05 m3\n"
            "- II.7: 10 Unit | Baru\n"
            "- III.6: 10 Unit | Eksisting\n"
        )
        parsed = parse_structured_opname_caption(caption)
        self.assertEqual(parsed["lokasi"], "KM 75+800 A L1")
        self.assertEqual(parsed["jalur_lajur"], "A L1")
        self.assertEqual(parsed["vendor"], "KOPKAR")
        self.assertEqual(parsed["tanggal"], "2026-10-27")
        self.assertEqual(len(parsed["items"]), 3)
        self.assertEqual(parsed["items"][0]["p"], 4.5)
        self.assertEqual(parsed["items"][0]["l"], 1.2)
        self.assertEqual(parsed["items"][0]["t"], 0.05)
        self.assertAlmostEqual(parsed["items"][0]["volume"], 0.27)
        self.assertEqual(parsed["items"][1]["material_status"], "Baru")
        self.assertEqual(parsed["items"][2]["material_status"], "Eksisting")

        # Multi-mode: colonless keyword, colonless item_key, and single-line Item without bullet
        colonless = parse_structured_opname_caption(
            "Opname: PV\nLokasi: KM 45+200 A\nVendor: MIJ\nItem:\n"
            "- Permanen 4.5 x 1.2 x 0.05 m3\n"
            "- II.6 0.62 ton\n"
            "- Pasang Tiang 2400 3 tiang\n"
        )
        self.assertEqual(colonless["unparsed_item_lines"], [])
        self.assertEqual(colonless["items"][0]["raw_item"], "Permanen")
        self.assertAlmostEqual(colonless["items"][0]["volume"], 0.27)
        self.assertEqual(colonless["items"][1]["raw_item"], "II.6")
        self.assertAlmostEqual(colonless["items"][1]["volume"], 0.62)
        self.assertEqual(colonless["items"][2]["raw_item"], "Pasang Tiang 2400")
        self.assertAlmostEqual(colonless["items"][2]["volume"], 3.0)

    def test_billing_cycle_26th_to_25th(self):
        self.assertEqual(resolve_billing_cycle(datetime.date(2026, 10, 25)), (10, 2026))
        self.assertEqual(resolve_billing_cycle(datetime.date(2026, 10, 26)), (11, 2026))
        self.assertEqual(resolve_billing_cycle(datetime.date(2026, 11, 25)), (11, 2026))
        self.assertEqual(resolve_billing_cycle(datetime.date(2026, 12, 26)), (1, 2027))

    @patch("main.send_whatsapp_message")
    def test_missing_photo_is_rejected_with_template(self, mock_send):
        msg = {
            "id": {"_serialized": "false_628111@c.us_NOPHOTO1"},
            "from": "628111@c.us",
            "hasMedia": False,
            "body": "Opname: 191026PV001\nLokasi: KM 45+200 A\nVendor: MIJ\nItem:\n- II.1: 4 x 1 x 0.05 m3",
            "_session": "default",
        }
        main.process_message(msg)
        mock_send.assert_called_once()
        reply_text = mock_send.call_args[0][1]
        self.assertIn("Opname Ditolak", reply_text)
        self.assertIn("Foto lapangan wajib", reply_text)

    @patch("main.send_whatsapp_message")
    def test_missing_vendor_is_rejected_never_defaulted(self, mock_send):
        msg = {
            "id": {"_serialized": "false_628111@c.us_NOVEND1"},
            "from": "628111@c.us",
            "hasMedia": True,
            "body": "Opname: 191026PV001\nLokasi: KM 45+200 A\nItem:\n- II.1: 4 x 1 x 0.05 m3",
            "_data": {"body": TINY_JPG_B64},
            "_session": "default",
        }
        main.process_message(msg)
        mock_send.assert_called_once()
        reply_text = mock_send.call_args[0][1]
        self.assertIn("Opname Ditolak", reply_text)
        self.assertIn("Vendor wajib diisi", reply_text)

    @patch("main.extract_opname_watermark_and_items")
    @patch("main.append_opname_rows")
    @patch("main.ensure_monthly_opname_workbook", return_value=("DRV1", "ITM_NOV", "https://1drv.ms/x/NOV"))
    @patch("main.upload_photo_to_onedrive", return_value="https://1drv.ms/i/MOCKPHOTO")
    @patch("main.send_whatsapp_message")
    def test_full_opname_flow_skips_llm_when_complete_and_supports_undo(
        self,
        mock_send,
        mock_upload,
        mock_ensure,
        mock_append,
        mock_llm,
    ):
        msg = {
            "id": {"_serialized": "false_628111@c.us_VALIDPV1"},
            "from": "628111@c.us",
            "hasMedia": True,
            "timestamp": 1761540000,
            "body": (
                "Opname: 191026PV001\n"
                "Lokasi: KM 45+200 A L1\n"
                "Vendor: MIJ\n"
                "Tanggal: 27-10-2026\n"
                "Item:\n"
                "- Permanen: 4.5 x 1.2 x 0.05 m3\n"
                "- Hotmix: 0.62 Ton\n"
            ),
            "_data": {"body": f"/9j/{TINY_JPG_B64[4:]}"},
            "_session": "default",
        }
        # Note base64 needs valid /9j/ header if using inline path
        with patch("main._extract_image_bytes_from_message", return_value=b"JPEG_BYTES"):
            main.process_message(msg)

        # Deterministic parse succeeded with explicit Tanggal -> 0 LLM calls!
        mock_llm.assert_not_called()
        mock_upload.assert_called_once()
        mock_ensure.assert_called_once_with(settings.OPNAME_EXCEL_SHARE_LINK, 11, 2026)
        mock_append.assert_called_once()
        self.assertEqual(mock_append.call_args[1]["target_drive_item"], ("DRV1", "ITM_NOV"))

        table_name = mock_append.call_args[0][1]
        rows = mock_append.call_args[0][2]
        self.assertEqual(table_name, "TBL_LOG_PV")
        self.assertEqual(len(rows), 2)
        opname_id = rows[0][0]
        self.assertTrue(opname_id.startswith("OPN-261027-"))
        self.assertEqual(rows[0][4], "W1")
        self.assertEqual(rows[0][7], "MIJ")
        self.assertEqual(rows[0][8], "II.1")
        self.assertEqual(rows[0][10], 4.5)
        self.assertEqual(rows[1][8], "II.6")
        self.assertEqual(rows[1][15], 0.62)

        # Verify SQLite persistence and /rekap opname
        conn = sqlite3.connect(self.db_path)
        count = conn.execute("SELECT COUNT(*) FROM opname_entries WHERE status='ACTIVE'").fetchone()[0]
        conn.close()
        self.assertEqual(count, 2)

        mock_send.reset_mock()
        main.process_message(
            {
                "id": {"_serialized": "false_628111@c.us_REKAP1"},
                "from": "628111@c.us",
                "hasMedia": False,
                "body": "/rekap opname 2026-10-27",
                "_session": "default",
            }
        )
        self.assertIn("W1", mock_send.call_args[0][1])
        self.assertIn("PV", mock_send.call_args[0][1])

        # Verify /undo removes rows from exact workbook and voids SQLite
        mock_send.reset_mock()
        with patch("main.delete_opname_rows_by_id", return_value=2) as mock_del:
            main.process_message(
                {
                    "id": {"_serialized": "false_628111@c.us_UNDO1"},
                    "from": "628111@c.us",
                    "hasMedia": False,
                    "body": f"/undo {opname_id}",
                    "_session": "default",
                }
            )
            mock_del.assert_called_once_with(
                settings.OPNAME_EXCEL_SHARE_LINK,
                "TBL_LOG_PV",
                opname_id,
                target_drive_item=("DRV1", "ITM_NOV"),
            )

        conn = sqlite3.connect(self.db_path)
        active_after = conn.execute("SELECT COUNT(*) FROM opname_entries WHERE status='ACTIVE'").fetchone()[0]
        conn.close()
        self.assertEqual(active_after, 0)

    @patch("main.extract_opname_watermark_and_items")
    @patch("main.append_opname_rows")
    @patch("main.ensure_monthly_opname_workbook")
    @patch("main.upload_photo_to_onedrive", return_value="https://1drv.ms/i/MOCKPHOTO")
    @patch("main.send_whatsapp_message")
    def test_auto_monthly_rollover_creates_once_per_cycle_and_routes_cross_month_undo(
        self,
        mock_send,
        mock_upload,
        mock_ensure,
        mock_append,
        mock_llm,
    ):
        mock_ensure.side_effect = [
            ("DRV1", "ITM_DEC", "https://1drv.ms/x/DEC"),
            ("DRV1", "ITM_NOV", "https://1drv.ms/x/NOV"),
        ]
        with patch("main._extract_image_bytes_from_message", return_value=b"JPEG_BYTES"):
            # 1) 26-11-2026 enters cycle 2026-12 -> creates DEC workbook once
            main.process_message(
                {
                    "id": {"_serialized": "false_628111@c.us_DEC1"},
                    "from": "628111@c.us",
                    "hasMedia": True,
                    "timestamp": 1764120000,
                    "body": "Opname: 261126PV001\nLokasi: KM 45+200 A L1\nVendor: MIJ\nTanggal: 26-11-2026\nItem:\n- Permanen: 4.5 x 1.2 x 0.05 m3\n",
                    "_session": "default",
                }
            )
            # 2) 02-12-2026 stays in cycle 2026-12 -> hits SQLite cache (no extra create call)
            main.process_message(
                {
                    "id": {"_serialized": "false_628111@c.us_DEC2"},
                    "from": "628111@c.us",
                    "hasMedia": True,
                    "timestamp": 1764640000,
                    "body": "Opname: 021226PV002\nLokasi: KM 46+100 A L1\nVendor: MIJ\nTanggal: 02-12-2026\nItem:\n- Permanen: 3.0 x 1.0 x 0.05 m3\n",
                    "_session": "default",
                }
            )
            # 3) Late 24-11-2026 entry belongs to cycle 2026-11 -> creates/opens NOV workbook
            main.process_message(
                {
                    "id": {"_serialized": "false_628111@c.us_NOVLATE"},
                    "from": "628111@c.us",
                    "hasMedia": True,
                    "timestamp": 1764640100,
                    "body": "Opname: 241126PV003\nLokasi: KM 47+100 B L1\nVendor: MIJ\nTanggal: 24-11-2026\nItem:\n- Permanen: 2.0 x 1.0 x 0.05 m3\n",
                    "_session": "default",
                }
            )

        self.assertEqual(mock_ensure.call_count, 2, msg=f"replies={[c[0][1] for c in mock_send.call_args_list]}")
        self.assertEqual(mock_ensure.call_args_list[0][0][1:], (12, 2026))
        self.assertEqual(mock_ensure.call_args_list[1][0][1:], (11, 2026))

        self.assertEqual(mock_append.call_args_list[0][1]["target_drive_item"], ("DRV1", "ITM_DEC"))
        self.assertEqual(mock_append.call_args_list[1][1]["target_drive_item"], ("DRV1", "ITM_DEC"))
        self.assertEqual(mock_append.call_args_list[2][1]["target_drive_item"], ("DRV1", "ITM_NOV"))
        late_nov_id = mock_append.call_args_list[2][0][2][0][0]

        with patch("main.delete_opname_rows_by_id", return_value=1) as mock_del:
            main.process_message(
                {
                    "id": {"_serialized": "false_628111@c.us_UNDOLATE"},
                    "from": "628111@c.us",
                    "hasMedia": False,
                    "body": f"/undo {late_nov_id}",
                    "_session": "default",
                }
            )
            mock_del.assert_called_once_with(
                settings.OPNAME_EXCEL_SHARE_LINK,
                "TBL_LOG_PV",
                late_nov_id,
                target_drive_item=("DRV1", "ITM_NOV"),
            )

    @patch("main.send_whatsapp_message")
    def test_format_command_replies_with_cheat_sheet(self, mock_send):
        main.process_message(
            {
                "id": {"_serialized": "false_628111@c.us_FMT1"},
                "from": "628111@c.us",
                "hasMedia": False,
                "body": "/format GR",
                "_session": "default",
            }
        )
        mock_send.assert_called_once()
        self.assertIn("TEMPLATE OPNAME GR", mock_send.call_args[0][1])


if __name__ == "__main__":
    unittest.main()
