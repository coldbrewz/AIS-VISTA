import unittest
from services.llm import extract_json_str


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


if __name__ == "__main__":
    unittest.main()
