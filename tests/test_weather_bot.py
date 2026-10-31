import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from weather_bot import mock_hourly, summarize, build_message

class WeatherTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 31, 6, 0, tzinfo=ZoneInfo('Asia/Ho_Chi_Minh'))

    def test_rain(self):
        msg = build_message(summarize(mock_hourly(self.now, 'rain'), self.now), self.now, 'HCM', 50)
        self.assertIn('CẢNH BÁO', msg)
        self.assertIn('75%', msg)

    def test_clear(self):
        msg = build_message(summarize(mock_hourly(self.now, 'clear'), self.now), self.now, 'HCM', 50)
        self.assertIn('BẢN TIN', msg)

    def test_bad_data(self):
        with self.assertRaises(ValueError):
            summarize({'time': [], 'temperature_2m': [], 'precipitation_probability': []}, self.now)

if __name__ == '__main__':
    unittest.main()
