import unittest

from services.message_utils import (
    extract_kode_from_text,
    extract_message_id,
    normalize_chat_id,
    resolve_reply_chat_id,
)


class MessageUtilsTests(unittest.TestCase):
    def test_extract_message_id_prefers_serialized_id(self):
        message = {
            "id": {
                "_serialized": "false_218880291143697@lid_AC8F4B56FB3DA0C9796526D19B57DDA5",
                "id": "AC8F4B56FB3DA0C9796526D19B57DDA5",
            }
        }

        self.assertEqual(
            extract_message_id(message),
            "false_218880291143697@lid_AC8F4B56FB3DA0C9796526D19B57DDA5",
        )

    def test_extract_message_id_reconstructs_from_raw_info(self):
        message = {
            "from": "218880291143697@lid",
            "fromMe": False,
            "_data": {
                "Info": {
                    "ID": "AC8F4B56FB3DA0C9796526D19B57DDA5",
                    "IsFromMe": False,
                }
            },
        }

        self.assertEqual(
            extract_message_id(message),
            "false_218880291143697@lid_AC8F4B56FB3DA0C9796526D19B57DDA5",
        )

    def test_resolve_reply_chat_id_prefers_phone_chat_over_lid(self):
        message = {
            "from": "218880291143697@lid",
            "_data": {"Info": {"Chat": "628123456789@s.whatsapp.net"}},
        }

        self.assertEqual(resolve_reply_chat_id(message), "628123456789@c.us")

    def test_normalize_chat_id_strips_device_suffix(self):
        self.assertEqual(normalize_chat_id("628123456789:12@s.whatsapp.net"), "628123456789@c.us")

    def test_extract_kode_from_text_supports_longer_suffixes(self):
        self.assertEqual(extract_kode_from_text("Kode:270707CA00001"), "270707CA00001")


if __name__ == "__main__":
    unittest.main()
