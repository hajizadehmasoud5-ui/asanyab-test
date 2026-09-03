import hashlib
import os
import unittest

os.environ.setdefault("DB_NAME", "test")
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("DOCTOR_SESSION_SECRET", "s" * 64)
os.environ.setdefault("DOCTOR_LOGIN_CODE_HASH", hashlib.sha256(b"doctor-test-code").hexdigest())

import app_implant_patient as patient
from fastapi import HTTPException


class ImplantPatientApiUnitTests(unittest.TestCase):
    def test_patient_token_hash_is_sha256_only(self):
        token = "patient-token-example-abcdefghijklmnopqrstuvwxyz0123456789"
        digest = patient.token_hash(token)
        self.assertEqual(digest, hashlib.sha256(token.encode()).hexdigest())
        self.assertEqual(len(digest), 64)
        self.assertNotIn(token, digest)

    def test_more_info_requires_message(self):
        review = patient.DoctorPatientResponse(
            patient_response="پاسخ",
            more_info_required=True,
            more_info_message="",
            publish=False,
        )
        with self.assertRaises(HTTPException) as error:
            patient._validate_patient_response(review)
        self.assertEqual(error.exception.detail, "more_info_message_required")

    def test_publish_requires_patient_visible_content(self):
        review = patient.DoctorPatientResponse(publish=True)
        with self.assertRaises(HTTPException) as error:
            patient._validate_patient_response(review)
        self.assertEqual(error.exception.detail, "patient_response_required")

    def test_patient_token_shape_rejects_short_values(self):
        self.assertIsNone(patient.PATIENT_TOKEN_RE.fullmatch("short-token"))
        self.assertIsNotNone(patient.PATIENT_TOKEN_RE.fullmatch("A" * 43))


if __name__ == "__main__":
    unittest.main()
