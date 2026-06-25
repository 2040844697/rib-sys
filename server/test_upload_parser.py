from __future__ import annotations

import unittest

from server.upload_parser import parse_multipart_upload


class UploadParserTests(unittest.TestCase):
    def test_parse_multipart_upload_without_cgi(self) -> None:
        boundary = "----ribsys-test-boundary"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="bucket"\r\n'
            "\r\n"
            "misc\r\n"
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="cover.png"\r\n'
            "Content-Type: image/png\r\n"
            "\r\n"
        ).encode("utf-8") + b"\x89PNGdemo\r\n" + f"--{boundary}--\r\n".encode("utf-8")

        bucket, filename, content_type, raw = parse_multipart_upload(
            f"multipart/form-data; boundary={boundary}",
            body,
        )

        self.assertEqual(bucket, "misc")
        self.assertEqual(filename, "cover.png")
        self.assertEqual(content_type, "image/png")
        self.assertEqual(raw, b"\x89PNGdemo")


if __name__ == "__main__":
    unittest.main()
