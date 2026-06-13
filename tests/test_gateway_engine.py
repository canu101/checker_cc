import unittest

from gateway_engine import GatewayEngine
from database import DatabaseManager


class GatewayEngineResponseTest(unittest.TestCase):
    def setUp(self):
        self.engine = GatewayEngine(DatabaseManager())

    def test_json_approved_status_is_classified_as_approved(self):
        result = self.engine.analyze_response('{"status":"approved","message":"000: Approved"}')

        self.assertEqual(result['category'], 'approved_charged')
        self.assertEqual(result['status_text'], 'APPROVED')

    def test_json_declined_status_is_classified_as_declined(self):
        result = self.engine.analyze_response('{"status":"declined","message":"000: Declined"}')

        self.assertEqual(result['category'], 'declined')
        self.assertEqual(result['status_text'], 'DECLINED')


if __name__ == '__main__':
    unittest.main()
