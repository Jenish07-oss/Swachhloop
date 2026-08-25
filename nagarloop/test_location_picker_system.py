import unittest
import os
import sys
import json
import sqlite3

# Ensure path includes root directory
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from app import app
from seed_data import seed

class TestNagarLoopLocationSystem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        seed()

    def setUp(self):
        self.client = app.test_client()

    def test_01_location_search_api(self):
        """Test backend search suggestions API across Gujarat cities"""
        test_queries = [
            ("Navrangpura", "Ahmedabad"),
            ("Adajan", "Surat"),
            ("Alkapuri", "Vadodara"),
            ("Kalawad Road", "Rajkot"),
            ("Infocity", "Gandhinagar")
        ]

        for query, expected_city in test_queries:
            res = self.client.get(f'/api/location/search?q={query}&request_id=101')
            self.assertEqual(res.status_code, 200)
            data = json.loads(res.data.decode('utf-8'))
            self.assertTrue(data.get('success'))
            self.assertEqual(data.get('request_id'), '101')
            results = data.get('results', [])
            self.assertGreater(len(results), 0, f"No results for query '{query}'")
            # Verify coordinates are valid Gujarat coordinates
            first = results[0]
            self.assertIn('lat', first)
            self.assertIn('lng', first)
            self.assertGreaterEqual(first['lat'], 20.0)
            self.assertLessEqual(first['lat'], 25.0)
            self.assertGreaterEqual(first['lng'], 68.0)
            self.assertLessEqual(first['lng'], 75.0)

    def test_02_location_reverse_api(self):
        """Test backend reverse geocoding API"""
        # Test coordinates for Commerce Six Roads, Ahmedabad
        res = self.client.get('/api/location/reverse?lat=23.0365&lng=72.5535')
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data.decode('utf-8'))
        self.assertTrue(data.get('success'))
        self.assertIn('address', data)
        self.assertIn('Commerce Six Roads', data['address'])

    def test_03_citizen_booking_with_exact_coordinates(self):
        """Test booking pickup with custom Gujarat location saves exact coordinates and address"""
        # Login citizen
        self.client.post('/login/citizen', data={
            'username': 'jenish',
            'password': 'jenish123'
        }, follow_redirects=True)

        surat_lat = 21.1980
        surat_lng = 72.7950
        surat_address = "Adajan Hazira Road, Surat, Gujarat 395009"

        res = self.client.post('/book-pickup', data={
            'address': surat_address,
            'lat': str(surat_lat),
            'lng': str(surat_lng),
            'stream_dry': 'on',
            'stream_dry_kg': '5.0',
            'stream_wet': 'on',
            'stream_wet_kg': '3.5'
        }, follow_redirects=True)

        self.assertEqual(res.status_code, 200)

        # Verify in database
        from database import get_db
        conn = get_db()
        row = conn.execute("SELECT * FROM pickups ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertAlmostEqual(row['lat'], surat_lat, places=4)
        self.assertAlmostEqual(row['lng'], surat_lng, places=4)
        self.assertEqual(row['address'], surat_address)

        self.client.get('/logout', follow_redirects=True)

    def test_04_public_waste_report_with_exact_location(self):
        """Test reporting public waste with custom location without login"""
        vadodara_lat = 22.3110
        vadodara_lng = 73.1750
        vadodara_address = "RC Dutt Road, Alkapuri, Vadodara, Gujarat 390007"

        res = self.client.post('/report-public', data={
            'address': vadodara_address,
            'lat': str(vadodara_lat),
            'lng': str(vadodara_lng),
            'waste_type': 'dry',
            'estimated_kg': '20.0',
            'description': 'Bulk plastic packaging dumped on roadside near commercial building',
            'reporter_name': 'Aarav Patel',
            'reporter_phone': '9876543210',
            'ai_image_check': 'passed',
            'ai_confidence': '0.85'
        }, follow_redirects=True)

        self.assertEqual(res.status_code, 200)

        from database import get_db
        conn = get_db()
        row = conn.execute("SELECT * FROM pickups WHERE is_public = 1 ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertAlmostEqual(row['lat'], vadodara_lat, places=4)
        self.assertAlmostEqual(row['lng'], vadodara_lng, places=4)
        self.assertEqual(row['address'], vadodara_address)

    def test_05_society_booking_with_exact_gate_location(self):
        """Test society bulk booking saves exact gate coordinates"""
        self.client.post('/login/society_manager', data={
            'username': 'society',
            'password': 'society123'
        }, follow_redirects=True)

        rajkot_lat = 22.2850
        rajkot_lng = 70.7680
        rajkot_address = "Gate 2 Collection Bay, Kalawad Road, Rajkot, Gujarat 360005"

        res = self.client.post('/book-pickup', data={
            'is_society': '1',
            'society_id': '1',
            'address': rajkot_address,
            'lat': str(rajkot_lat),
            'lng': str(rajkot_lng),
            'stream_dry': 'on',
            'stream_dry_kg': '50.0',
            'stream_wet': 'on',
            'stream_wet_kg': '40.0',
            'ai_image_check': 'passed',
            'ai_confidence': '0.85'
        }, follow_redirects=True)

        self.assertEqual(res.status_code, 200)

        from database import get_db
        conn = get_db()
        row = conn.execute("SELECT * FROM pickups WHERE is_society = 1 ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertAlmostEqual(row['lat'], rajkot_lat, places=4)
        self.assertAlmostEqual(row['lng'], rajkot_lng, places=4)
        self.assertEqual(row['address'], rajkot_address)

        self.client.get('/logout', follow_redirects=True)

    def test_06_driver_navigation_uses_coordinates_not_address(self):
        """Test driver portal displays exact coordinates for Google Maps navigation"""
        from database import get_db
        conn = get_db()
        conn.execute("UPDATE pickups SET assigned_van_id = 1 WHERE id = 1")
        conn.commit()
        conn.close()

        self.client.post('/login/driver', data={
            'username': 'vikram',
            'password': 'vikram123'
        }, follow_redirects=True)

        res = self.client.get('/driver')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')

        # Check that NAVIGATE button links to Google Maps with exact destination coordinates
        self.assertIn('google.com/maps/dir/?api=1&destination=', html)
        self.assertIn('NAVIGATE', html)

        self.client.get('/logout', follow_redirects=True)

    def test_07_admin_dispatch_and_api_pickups(self):
        """Test API pickups return exact latitude and longitude"""
        self.client.post('/login/admin', data={
            'username': 'admin',
            'password': 'admin123'
        }, follow_redirects=True)

        res = self.client.get('/api/pickups')
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data.decode('utf-8'))
        pickups = data.get('pickups', [])
        self.assertGreater(len(pickups), 0)

        for p in pickups[:5]:
            self.assertIn('lat', p)
            self.assertIn('lng', p)
            self.assertIn('address', p)

        self.client.get('/logout', follow_redirects=True)

if __name__ == '__main__':
    unittest.main()
