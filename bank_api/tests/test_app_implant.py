import hashlib
import json
import os
import time
import unittest

os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("DOCTOR_SESSION_SECRET", "s" * 64)
os.environ.setdefault("DOCTOR_LOGIN_CODE_HASH", hashlib.sha256(b"doctor-test-code").hexdigest())

import app_implant as implant
from fastapi import HTTPException


class ImplantApiUnitTests(unittest.TestCase):
    def payload(self):
        return {
            "submission_key": "9c4ea0ac-a6db-451e-a01d-225bc0c55f69",
            "name": "بیمار تست",
            "mobile": "۰۹۱۲۱۲۳۴۵۶۷",
            "city": "اهواز",
            "problem": "دندان از دست رفته دارم",
            "missingCount": "۱ دندان",
            "jaws": ["upper"],
            "jawParts": {"upper": "سمت راست", "lower": ""},
            "teeth": ["16"],
            "medical": {"diabetes": True},
            "diseaseText": "دیابت کنترل‌شده",
            "medText": "متفورمین",
            "suggestedQuestions": ["آیا پیوند استخوان لازم است؟"],
            "question": "سؤال تست",
            "records": {"opg": "فایل انتخاب شد", "cbct": "ارسال نشده"},
            "photos": {"front": "فایل انتخاب شد"},
            "consent": True,
        }

    def test_payload_is_normalized(self):
        result = implant.validate_payload(json.dumps(self.payload(), ensure_ascii=False))
        self.assertEqual(result["mobile"], "09121234567")
        self.assertEqual(result["teeth"], ["16"])
        self.assertTrue(result["medical"]["diabetes"])

    def test_consent_is_required(self):
        payload = self.payload()
        payload["consent"] = False
        with self.assertRaises(HTTPException) as error:
            implant.validate_payload(json.dumps(payload))
        self.assertEqual(error.exception.detail, "consent_required")

    def test_file_magic_validation(self):
        self.assertEqual(implant.detect_file_type(b"\x89PNG\r\n\x1a\nrest", "opg"), ("image/png", ".png"))
        self.assertEqual(implant.detect_file_type(b"%PDF-1.7 rest", "cbct"), ("application/pdf", ".pdf"))
        with self.assertRaises(HTTPException):
            implant.detect_file_type(b"%PDF-1.7 rest", "front")

    def test_doctor_token_round_trip_and_expiry(self):
        token = implant.encode_token(int(time.time()) + 60)
        self.assertGreater(implant.decode_token(token)["exp"], int(time.time()))
        with self.assertRaises(HTTPException):
            implant.decode_token(token + "changed")
        with self.assertRaises(HTTPException):
            implant.decode_token(implant.encode_token(int(time.time()) - 1))


if __name__ == "__main__":
    unittest.main()
