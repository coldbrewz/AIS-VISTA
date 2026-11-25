import io
import os
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import openpyxl
from fastapi.testclient import TestClient

os.environ.setdefault("WAHA_API_KEY", "test-waha-key")
os.environ.setdefault("VIKEY_API_KEY", "test-vikey-key")
os.environ.setdefault("EXCEL_SHARE_LINK", "https://1drv.ms/x/s!dummy_sla")
os.environ.setdefault("OPNAME_EXCEL_SHARE_LINK", "https://1drv.ms/x/s!dummy_opname")

import main  # noqa: E402
from services.tagihan_generator import generate_tagihan_workbook, parse_tagihan_cycle  # noqa: E402


def _build_synthetic_mc_template_bytes() -> bytes:
    """Create a minimal realistic Tagihan MC workbook covering PML PV W1, PML RMB W1, and REKAP sheets."""
    wb = openpyxl.Workbook()
    ws_p1 = wb.active
    ws_p1.title = "REKAP PILAR 1 PEMEL"
    ws_p1["W8"] = "='REKAP INC PPN'!X8"
    ws_p1["V8"] = 1000
    ws_p1["F8"] = 100000
    ws_p1["X8"] = "=V8+W8"
    ws_p1["Y8"] = "=X8/F8"
    ws_p1["Z8"] = "=1-Y8"
    ws_p1["W9"] = "='REKAP INC PPN'!X9"
    ws_p1["W29"] = "=SUM(W8:W28)"

    ws_inc = wb.create_sheet("REKAP INC PPN")
    ws_inc["X8"] = "='PML RMB W1'!N25"
    ws_inc["X9"] = "='PML PV W1'!R25"

    # PML PV W1: unit_col=D, unit_price=I, annual=J, prev_qty=K, input=Q, price=R, bobot=S, cum_qty=T, cum_price=U, cum_bobot=V
    ws_pv = wb.create_sheet("PML PV W1")
    ws_pv["G8"] = "Qty"
    ws_pv["I8"] = "Harga Satuan"
    ws_pv["Q8"] = "Volume"
    ws_pv["T8"] = "Volume"
    ws_pv["K8"] = "Volume"
    ws_pv["J21"] = 1000000
    # Row 12: II.1 Permanen @ 100,000
    ws_pv["A12"] = "II.1"
    ws_pv["B12"] = "Rekondisi Perkerasan Jalan Beton (Permanen)"
    ws_pv["D12"] = "m3"
    ws_pv["I12"] = 100000
    ws_pv["K12"] = 2
    ws_pv["Q12"] = 999  # stale placeholder to verify clearing / overwrite
    ws_pv["R12"] = "=Q12*I12"
    ws_pv["S12"] = "=R12/$J$21*100"
    ws_pv["T12"] = "=K12+Q12"
    ws_pv["U12"] = "=T12*I12"
    ws_pv["V12"] = "=U12/$J$21*100"
    # Row 13: II.6 Hotmix @ 200,000 (should zero out when absent from LOG_PV)
    ws_pv["A13"] = "II.6"
    ws_pv["B13"] = "Pekerjaan Pengaspalan Manual Hotmix"
    ws_pv["D13"] = "Ton"
    ws_pv["I13"] = 200000
    ws_pv["K13"] = 0
    ws_pv["Q13"] = 5
    ws_pv["R13"] = "=Q13*I13"
    ws_pv["S13"] = "=R13/$J$21*100"
    ws_pv["T13"] = "=K13+Q13"
    ws_pv["U13"] = "=T13*I13"
    ws_pv["V13"] = "=U13/$J$21*100"
    # Footer rows
    ws_pv["A20"], ws_pv["B20"], ws_pv["R20"], ws_pv["S20"], ws_pv["U20"], ws_pv["V20"] = (
        "A", "Total Nilai Perbulan", "=SUM(R10:R19)", "=SUM(S10:S19)", "=SUM(U10:U19)", "=SUM(V10:V19)"
    )
    ws_pv["A21"], ws_pv["B21"], ws_pv["J21"] = ("B", "Total Nilai Pertahun", 1000000)
    ws_pv["A22"], ws_pv["B22"], ws_pv["R22"], ws_pv["U22"] = ("C", "Dasar Pengenaan Pajak (DPP)", "=R20*11/12", "=U20*11/12")
    ws_pv["A23"], ws_pv["B23"], ws_pv["R23"], ws_pv["U23"] = ("D", "PPN 12%", "=R22*0.12", "=U22*0.12")
    ws_pv["A25"], ws_pv["B25"], ws_pv["R25"], ws_pv["U25"] = ("E", "Grand Total", "=R20+R23", "=U20+U23")

    # PML RMB W1: unit_col=C, unit_price=H, annual=I, prev_qty=J, input=M, price=N, bobot=O, cum_qty=P, cum_price=Q, cum_bobot=R
    ws_rmb = wb.create_sheet("PML RMB W1")
    ws_rmb["H8"] = "Harga Satuan"
    ws_rmb["J8"] = "Volume"
    ws_rmb["M8"] = "Volume"
    ws_rmb["P8"] = "Volume"
    ws_rmb["I21"] = 500000
    ws_rmb["A10"] = "I.1"
    ws_rmb["B10"] = "Penggantian Daun Rambu Aluminium Uk. 60 x 60 cm"
    ws_rmb["C10"] = "Bh"
    ws_rmb["H10"] = 50000
    ws_rmb["J10"] = 1
    ws_rmb["M10"] = 0
    ws_rmb["N10"] = "=M10*H10"
    ws_rmb["O10"] = "=N10/$I$21*100"
    ws_rmb["P10"] = "=J10+M10"
    ws_rmb["Q10"] = "=P10*H10"
    ws_rmb["R10"] = "=Q10/$I$21*100"
    ws_rmb["A20"], ws_rmb["B20"], ws_rmb["N20"] = ("A", "Total Nilai Perbulan", "=SUM(N10:N19)")
    ws_rmb["A21"], ws_rmb["B21"], ws_rmb["I21"] = ("B", "Total Nilai Pertahun", 500000)
    ws_rmb["A22"], ws_rmb["B22"], ws_rmb["N22"] = ("C", "Dasar Pengenaan Pajak (DPP)", "=N20*11/12")
    ws_rmb["A23"], ws_rmb["B23"], ws_rmb["N23"] = ("D", "PPN 12%", "=N22*0.12")
    ws_rmb["A25"], ws_rmb["B25"], ws_rmb["N25"] = ("E", "Grand Total", "=N20+N23")

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _build_synthetic_vista_silo_bytes() -> bytes:
    """Create a DATA_UNTUK_VOL silo workbook with cached numbers and uncalculated dimension formulas."""
    wb = openpyxl.Workbook()
    ws_pv = wb.active
    ws_pv.title = "LOG_PV"
    headers = [
        "Opname_ID", "Kode_Temuan", "Tanggal", "Aset", "Wilayah", "Lokasi", "Jalur_Lajur",
        "Vendor", "Item_Key", "Uraian_BOQ", "P", "L", "T", "Jumlah", "Volume_Calc", "Volume", "Satuan",
    ]
    ws_pv.append(headers)
    # Row written via Graph API formula (cached Volume None -> fallback P*L*T = 2*1.5*0.5 = 1.5 m3)
    ws_pv.append([
        "XLS-2611-PV-W1-MIJ-M1", "-", "2026-11-10", "PV", "W1", "KM 45+200", "A / L1",
        "PT MIJ", "II.1", "Rekondisi Perkerasan Jalan Beton (Permanen)", 2.0, 1.5, 0.5, None,
        "=PRODUCT(K2:N2)", "=[@[Volume_Calc]]", "m3",
    ])
    # Direct numeric row (2.5 m3) -> total II.1 = 4.0 m3
    ws_pv.append([
        "XLS-2611-PV-W1-MIJ-M2", "-", "2026-11-12", "PV", "W1", "KM 46+100", "A / L2",
        "PT MIJ", "II.1", "Rekondisi Perkerasan Jalan Beton (Permanen)", None, None, None, None,
        "", 2.5, "m3",
    ])

    ws_sg = wb.create_sheet("LOG_SG")
    ws_sg.append(headers)
    ws_sg.append([
        "XLS-2611-SG-W1-ATLA-M1", "-", "2026-11-15", "SG", "W1", "KM 50+000", "B",
        "PT ATLA", "I.1-60X60", "Penggantian Daun Rambu Aluminium Uk. 60 x 60 cm", None, None, None, 3,
        "", 3, "Bh",
    ])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class TagihanGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.orig_db = main.settings.DB_URL
        self.orig_opname_link = main.settings.OPNAME_EXCEL_SHARE_LINK
        self.orig_tmpl_link = main.settings.TAGIHAN_TEMPLATE_SHARE_LINK
        self.orig_auto = main.settings.OPNAME_AUTO_MONTHLY
        self.orig_enabled = main.settings.OPNAME_ENABLED

        main.settings.DB_URL = os.path.join(self.tmpdir.name, "test_vista.db")
        main.settings.OPNAME_EXCEL_SHARE_LINK = "https://1drv.ms/x/s!opname_test"
        main.settings.TAGIHAN_TEMPLATE_SHARE_LINK = ""
        main.settings.OPNAME_AUTO_MONTHLY = True
        main.settings.OPNAME_ENABLED = True
        main.init_db()
        self.client = TestClient(main.app)

    def tearDown(self):
        main.settings.DB_URL = self.orig_db
        main.settings.OPNAME_EXCEL_SHARE_LINK = self.orig_opname_link
        main.settings.TAGIHAN_TEMPLATE_SHARE_LINK = self.orig_tmpl_link
        main.settings.OPNAME_AUTO_MONTHLY = self.orig_auto
        main.settings.OPNAME_ENABLED = self.orig_enabled
        self.tmpdir.cleanup()

    def test_parse_tagihan_cycle(self):
        self.assertEqual(parse_tagihan_cycle("/tagihan 2026-11"), (11, 2026))
        self.assertEqual(parse_tagihan_cycle("/tagihan oktober 2026"), (10, 2026))
        self.assertEqual(
            parse_tagihan_cycle("/tagihan", template_filename="MC-11 MENCARI VOLUME 2026.xlsx"),
            (11, 2026),
        )

    def test_generate_tagihan_workbook_patches_inputs_and_rekap_caches(self):
        vista_bytes = _build_synthetic_vista_silo_bytes()
        tmpl_bytes = _build_synthetic_mc_template_bytes()

        res = generate_tagihan_workbook(vista_bytes, tmpl_bytes, cycle_month=11, cycle_year=2026)
        self.assertEqual(res["warnings"], [])
        self.assertEqual(res["output_filename"], "MC-11_TAGIHAN_NOVEMBER_2026.xlsx")

        # II.1: 4.0 * 100,000 = 400,000 subtotal -> DPP 400,000*11/12 -> PPN 12% = 44,000 -> GT = 444,000
        # I.1: 3 * 50,000 = 150,000 subtotal -> GT = 166,500
        self.assertAlmostEqual(res["grand_totals"]["PML PV W1"], 444000.0, places=2)
        self.assertAlmostEqual(res["grand_totals"]["PML RMB W1"], 166500.0, places=2)

        wb_val = openpyxl.load_workbook(io.BytesIO(res["output_bytes"]), data_only=True)
        wb_fml = openpyxl.load_workbook(io.BytesIO(res["output_bytes"]), data_only=False)
        try:
            self.assertEqual(wb_val["PML PV W1"]["Q12"].value, 4)
            self.assertIsNone(wb_val["PML PV W1"]["Q13"].value)  # stale row cleared
            self.assertEqual(wb_fml["PML PV W1"]["R12"].value, "=Q12*I12")
            self.assertAlmostEqual(wb_val["PML PV W1"]["R25"].value, 444000.0, places=2)
            self.assertAlmostEqual(wb_val["REKAP INC PPN"]["X8"].value, 166500.0, places=2)
            self.assertAlmostEqual(wb_val["REKAP PILAR 1 PEMEL"]["W8"].value, 166500.0, places=2)
            self.assertAlmostEqual(wb_val["REKAP PILAR 1 PEMEL"]["W9"].value, 444000.0, places=2)
        finally:
            wb_val.close()
            wb_fml.close()

        with zipfile.ZipFile(io.BytesIO(res["output_bytes"]), "r") as zf:
            self.assertIn('fullCalcOnLoad="1"', zf.read("xl/workbook.xml").decode("utf-8"))

    def test_whatsapp_tagihan_with_attachment_and_cached_reuse(self):
        tmpl_bytes = _build_synthetic_mc_template_bytes()
        vista_bytes = _build_synthetic_vista_silo_bytes()
        uploaded_docs = []
        sent_docs = []
        sent_texts = []

        def fake_upload(data_bytes, filename, folder_path, content_type="application/octet-stream"):
            item_id = f"ITEM_{len(uploaded_docs) + 1}"
            uploaded_docs.append((item_id, filename, folder_path, data_bytes))
            return item_id, f"https://1drv.ms/x/{item_id}"

        def fake_download(item_id, drive_id=""):
            if item_id == "SILO_NOV_ID":
                return vista_bytes
            for u_id, _fn, _fld, data in uploaded_docs:
                if u_id == item_id:
                    return data
            raise KeyError(item_id)

        with patch("main.download_whatsapp_media", return_value=tmpl_bytes), \
             patch("main.ensure_monthly_opname_workbook", return_value=("DRV1", "SILO_NOV_ID", "https://1drv.ms/x/silo")), \
             patch("main.download_file_from_onedrive", side_effect=fake_download), \
             patch("main.upload_file_to_onedrive", side_effect=fake_upload), \
             patch("main.send_whatsapp_document", side_effect=lambda *a, **kw: sent_docs.append((a, kw))), \
             patch("main.send_whatsapp_message", side_effect=lambda *a, **kw: sent_texts.append((a, kw))):

            # 1. Group message sending MC-11 template with `/tagihan` caption
            resp1 = self.client.post(
                "/webhook",
                json={
                    "event": "message",
                    "session": "default",
                    "payload": {
                        "id": "MSG_TAG_1",
                        "from": "628123456@g.us",
                        "participant": "628111222@c.us",
                        "body": "/tagihan",
                        "hasMedia": True,
                        "media": {
                            "url": "http://waha:3000/api/files/mc11.xlsx",
                            "filename": "MC-11 MENCARI VOLUME 2026.xlsx",
                            "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        },
                    },
                },
            )
            self.assertEqual(resp1.status_code, 200)
            self.assertEqual(len(sent_docs), 1)
            self.assertEqual(sent_docs[0][0][2], "MC-11_TAGIHAN_NOVEMBER_2026.xlsx")
            self.assertIn("Tagihan MC Selesai", sent_docs[0][1]["caption"])
            self.assertIn("610,500.00", sent_docs[0][1]["caption"])
            self.assertEqual(len(uploaded_docs), 2)  # template cached + generated output uploaded

            # 2. Text-only `/tagihan 2026-11` reuses the cached template from OneDrive
            resp2 = self.client.post(
                "/webhook",
                json={
                    "event": "message",
                    "session": "default",
                    "payload": {
                        "id": "MSG_TAG_2",
                        "from": "628123456@g.us",
                        "participant": "628111222@c.us",
                        "body": "/tagihan 2026-11",
                        "hasMedia": False,
                    },
                },
            )
            self.assertEqual(resp2.status_code, 200)
            self.assertEqual(len(sent_docs), 2)
            self.assertEqual(sent_docs[1][0][2], "MC-11_TAGIHAN_NOVEMBER_2026.xlsx")

    def test_whatsapp_tagihan_without_template_shows_instructions(self):
        sent_texts = []
        with patch("main.send_whatsapp_message", side_effect=lambda *a, **kw: sent_texts.append(a[1])):
            resp = self.client.post(
                "/webhook",
                json={
                    "event": "message",
                    "session": "default",
                    "payload": {
                        "id": "MSG_TAG_NONE",
                        "from": "628123456@c.us",
                        "body": "/tagihan 2026-11",
                        "hasMedia": False,
                    },
                },
            )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(any("Kirim file template `MC" in txt for txt in sent_texts))
