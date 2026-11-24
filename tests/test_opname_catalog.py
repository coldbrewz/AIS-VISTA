import unittest

from services.opname_catalog import (
    ASSET_TO_TABLE,
    IC_AKSES_WILAYAH,
    OFFICIAL_VENDOR_ROSTER,
    VALID_OPNAME_ASSETS,
    check_roster_pairing,
    get_boq_menu_for_asset,
    normalize_asset_code,
    normalize_vendor,
    resolve_boq_item,
    resolve_rumput_segment,
    resolve_wilayah,
)


class OpnameCatalogTests(unittest.TestCase):
    def test_wilayah_km_boundaries(self):
        self.assertEqual(resolve_wilayah("KM 26+035 A")[:2], (True, "W1"))
        self.assertEqual(resolve_wilayah("KM 59+999 B L1")[:2], (True, "W1"))
        self.assertEqual(resolve_wilayah("KM 60+000 A")[:2], (True, "W2"))
        self.assertEqual(resolve_wilayah("KM 98+200 Median")[:2], (True, "W2"))

        # Range midpoint resolution
        self.assertEqual(resolve_wilayah("KM 36+150 s/d KM 38+750 A")[:2], (True, "W1"))
        self.assertEqual(resolve_wilayah("KM 73+700 s/d KM 77+350 B")[:2], (True, "W2"))

        # Out-of-bounds and contradictory hints rejected
        ok_low, _, _, _ = resolve_wilayah("KM 25+900 A")
        ok_high, _, _, _ = resolve_wilayah("KM 99+100 B")
        ok_mismatch, _, _, msg_mismatch = resolve_wilayah("KM 45+200 W2")
        self.assertFalse(ok_low)
        self.assertFalse(ok_high)
        self.assertFalse(ok_mismatch)
        self.assertIn("tidak konsisten", msg_mismatch.lower())

    def test_all_legend_ic_akses_names_resolve_correctly(self):
        expected_w1 = [
            "0.1 BITUNG",
            "1.1 CIKUPA 1",
            "1.10 CIKUPA 2",
            "1.2 BALTIM",
            "1.3 BALBAR",
            "1.31 CIKANDE",
            "1.4 CIUJUNG",
            "RA 43",
        ]
        expected_w2 = [
            "2.5 SERTIM",
            "2.6 SERBAR Ramp OFF",
            "2.7 CILTIM",
            "2.8 CILBAR",
            "2.9 MERAK",
            "Petak Papat",
            "RA 68",
        ]
        for loc in expected_w1:
            ok, wil, _, err = resolve_wilayah(loc)
            self.assertTrue(ok, f"Failed for {loc}: {err}")
            self.assertEqual(wil, "W1", loc)
        for loc in expected_w2:
            ok, wil, _, err = resolve_wilayah(loc)
            self.assertTrue(ok, f"Failed for {loc}: {err}")
            self.assertEqual(wil, "W2", loc)
        self.assertGreater(len(IC_AKSES_WILAYAH), 20)

    def test_strict_vendor_validation_never_defaults(self):
        ok_empty, v_empty, _ = normalize_vendor("", "PV")
        ok_unknown, v_unknown, _ = normalize_vendor("PT RANDOM JAYA", "PV")
        self.assertFalse(ok_empty)
        self.assertIsNone(v_empty)
        self.assertFalse(ok_unknown)
        self.assertIsNone(v_unknown)

        ok_mij, v_mij, _ = normalize_vendor("PT Mustika Ifra Jaya", "PV")
        ok_danu, v_danu, _ = normalize_vendor("Danudian", "PV")
        ok_kopkar, v_kopkar, _ = normalize_vendor("kopkar", "RM")
        self.assertEqual((ok_mij, v_mij), (True, "MIJ"))
        self.assertEqual((ok_danu, v_danu), (True, "DANU"))
        self.assertEqual((ok_kopkar, v_kopkar), (True, "KOPKAR"))

    def test_asset_routing_and_aliases(self):
        self.assertEqual(normalize_asset_code("TRC"), "CA")
        self.assertEqual(normalize_asset_code("pv"), "PV")
        for aset in VALID_OPNAME_ASSETS:
            sheet, table, grp = ASSET_TO_TABLE[aset]
            self.assertTrue(sheet.startswith("LOG_"))
            self.assertTrue(table.startswith("TBL_LOG_"))
            self.assertTrue(grp)

    def test_boq_keyword_and_rumput_segment_resolution(self):
        # Field keyword resolution (no Roman code needed on site)
        for aset, phrase, expected_key in [
            ("PV", "Permanen", "II.1"),
            ("PV", "Salob", "II.2"),
            ("PV", "Hotmix", "II.6"),
            ("PV", "Sealant 1cm", "III.1"),
            ("SG", "Panel PVC", "I.15-PVC"),
            ("SG", "Stiker A", "I.15-STIKER"),
            ("GR", "Bongkar Beam", "II.1"),
            ("GR", "Pasang Beam", "II.8-PASANG"),
            ("GR", "Pengadaan Tiang 2400", "II.17-MAT"),
            ("WR", "Tensioning", "III.35"),
            ("LC", "Pangkas >30cm", "III.10b"),
            ("CA", "Mandor", "II.1"),
            ("DR", "Keruk Saluran Terbuka", "I.12"),
            ("DR", "Bekisting", "II.19-BEKISTING"),
            ("FE", "Pengadaan Panel 5cm", "II.7"),
            ("FE", "Pasang Panel 5cm", "III.6"),
        ]:
            it, err = resolve_boq_item(aset, phrase, "KM 45+200", "W1")
            self.assertEqual(err, "", f"Failed keyword {aset}:{phrase}: {err}")
            self.assertEqual(it.item_key, expected_key, f"{aset}:{phrase}")

        # Duplicate raw code I.15 in SG still asks for keyword, while Code + Keyword resolves cleanly
        dup_sg, err_sg = resolve_boq_item("SG", "I.15")
        self.assertIsNone(dup_sg)
        self.assertIn("Panel PVC", err_sg)
        combo_pvc, err_combo = resolve_boq_item("SG", "I.15 Panel PVC")
        self.assertEqual(err_combo, "")
        self.assertEqual(combo_pvc.item_key, "I.15-PVC")
        combo_gr, err_gr = resolve_boq_item("GR", "II.8 Pasang Beam")
        self.assertEqual(err_gr, "")
        self.assertEqual(combo_gr.item_key, "II.8-PASANG")
        combo_pv, err_pv = resolve_boq_item("PV", "II.1 - Permanen")
        self.assertEqual(err_pv, "")
        self.assertEqual(combo_pv.item_key, "II.1")

        # Verify every asset's non-RM-segment keywords are unique (no ambiguity)
        for aset in VALID_OPNAME_ASSETS:
            if aset == "RM":
                continue
            kws = [it.keyword.lower() for it in get_boq_menu_for_asset(aset)]
            self.assertEqual(len(kws), len(set(kws)), f"Duplicate keyword in {aset}")

        # Rumput KM range maps deterministically to segment key
        rm_seg, rm_err = resolve_rumput_segment("W1", "KM 36+150 s/d KM 38+750 A", "Rumput")
        self.assertEqual(rm_err, "")
        self.assertEqual(rm_seg.item_key, "RM.P1.W1.36150")

        rm_ic, rm_ic_err = resolve_rumput_segment("W2", "2.6 SERBAR", "Rumput Interchange")
        self.assertEqual(rm_ic_err, "")
        self.assertEqual(rm_ic.item_key, "RM.IC.SERBAR")

    def test_official_roster_and_new_vendor_aliases(self):
        self.assertEqual(len(OFFICIAL_VENDOR_ROSTER), 21)
        self.assertEqual(normalize_vendor("PT DM", "PV"), (True, "DANU", ""))
        self.assertEqual(normalize_vendor("PT WILFANISTA", "PV"), (True, "WILFA", ""))
        self.assertEqual(normalize_vendor("PT CAKRA", "WR"), (True, "CSP", ""))

        ok_match, msg_ok = check_roster_pairing("PV", "MIJ", "W1")
        self.assertTrue(ok_match)
        self.assertEqual(msg_ok, "")

        ok_mismatch, msg_bad = check_roster_pairing("PV", "MIJ", "W2")
        self.assertFalse(ok_mismatch)
        self.assertIn("W1", msg_bad)


if __name__ == "__main__":
    unittest.main()
