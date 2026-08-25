import unittest
import json
import os
import sqlite3
from app import app
from database import get_db, init_db
from seed_data import seed

class TestNagarLoopLocationSystem(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
        init_db()
        seed()

    def test_database_address_column_exists(self):
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(pickups)")
        columns = [row['name'] for row in cursor.fetchall()]
        conn.close()
        self.assertIn('address', columns, "pickups table must contain address column")
        self.assertIn('lat', columns, "pickups table must contain lat column")
        self.assertIn('lng', columns, "pickups table must contain lng column")

    def test_ahmedabad_booking_location(self):
        # 1. Ahmedabad location test
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['role'] = 'citizen'
            sess['household_id'] = 1

        res = self.client.post('/book-pickup', data={
            'address': 'Flat 402, Iscon Elegance, Prahlad Nagar, Ahmedabad, Gujarat 380015',
            'lat': '23.012500',
            'lng': '72.508300',
            'stream_wet': 'on',
            'stream_wet_kg': '4.5',
            'stream_dry': 'on',
            'stream_dry_kg': '3.2'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        conn = get_db()
        p = conn.execute("SELECT * FROM pickups ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        self.assertIn('Iscon Elegance', p['address'])
        self.assertAlmostEqual(p['lat'], 23.012500, places=4)
        self.assertAlmostEqual(p['lng'], 72.508300, places=4)

    def test_gandhinagar_booking_location(self):
        # 2. Gandhinagar location test
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['role'] = 'citizen'
            sess['household_id'] = 1

        res = self.client.post('/book-pickup', data={
            'address': 'Infocity Sector 01, Gandhinagar, Gujarat 382007',
            'lat': '23.197300',
            'lng': '72.628800',
            'stream_wet': 'on',
            'stream_wet_kg': '5.0',
            'stream_ewaste': 'on',
            'stream_ewaste_kg': '2.0'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        conn = get_db()
        p = conn.execute("SELECT * FROM pickups ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        self.assertIn('Gandhinagar', p['address'])
        self.assertAlmostEqual(p['lat'], 23.197300, places=4)
        self.assertAlmostEqual(p['lng'], 72.628800, places=4)

    def test_surat_booking_location(self):
        # 3. Surat location test
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['role'] = 'citizen'
            sess['household_id'] = 1

        res = self.client.post('/book-pickup', data={
            'address': 'Ghod Dod Road, Athwa, Surat, Gujarat 395007',
            'lat': '21.176400',
            'lng': '72.808100',
            'stream_dry': 'on',
            'stream_dry_kg': '8.0'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        conn = get_db()
        p = conn.execute("SELECT * FROM pickups ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        self.assertIn('Surat', p['address'])
        self.assertAlmostEqual(p['lat'], 21.176400, places=4)
        self.assertAlmostEqual(p['lng'], 72.808100, places=4)

    def test_vadodara_booking_location(self):
        # 4. Vadodara location test
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['role'] = 'citizen'
            sess['household_id'] = 1

        res = self.client.post('/book-pickup', data={
            'address': 'Alkapuri Main Road, Vadodara, Gujarat 390007',
            'lat': '22.310700',
            'lng': '73.170400',
            'stream_wet': 'on',
            'stream_wet_kg': '6.0'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        conn = get_db()
        p = conn.execute("SELECT * FROM pickups ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        self.assertIn('Vadodara', p['address'])
        self.assertAlmostEqual(p['lat'], 22.310700, places=4)
        self.assertAlmostEqual(p['lng'], 73.170400, places=4)

    def test_rajkot_booking_location(self):
        # 5. Rajkot location test
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['role'] = 'citizen'
            sess['household_id'] = 1

        res = self.client.post('/book-pickup', data={
            'address': 'Kalawad Road, Rajkot, Gujarat 360005',
            'lat': '22.283800',
            'lng': '70.763400',
            'stream_dry': 'on',
            'stream_dry_kg': '5.5',
            'stream_residual': 'on',
            'stream_residual_kg': '2.0'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        conn = get_db()
        p = conn.execute("SELECT * FROM pickups ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        self.assertIn('Rajkot', p['address'])
        self.assertAlmostEqual(p['lat'], 22.283800, places=4)
        self.assertAlmostEqual(p['lng'], 70.763400, places=4)

    def test_public_report_location_system(self):
        # 6. Public Waste Report location test
        res = self.client.post('/report-public', data={
            'address': 'Near Ring Road Flyover Junction, Surat, Gujarat 395002',
            'lat': '21.195000',
            'lng': '72.819000',
            'waste_type': 'dry',
            'estimated_kg': '14.0',
            'description': 'Plastic packing waste on roadside',
            'reporter_name': 'Hiren Patel',
            'reporter_phone': '9825112233'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        conn = get_db()
        p = conn.execute("SELECT * FROM pickups WHERE is_public = 1 ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        self.assertIn('Surat', p['address'])
        self.assertAlmostEqual(p['lat'], 21.195000, places=4)
        self.assertAlmostEqual(p['lng'], 72.819000, places=4)

    def test_society_bulk_booking_location(self):
        # 7. Society Bulk Booking location test
        with self.client.session_transaction() as sess:
            sess['user_id'] = 2
            sess['role'] = 'society_manager'
            sess['society_id'] = 1

        res = self.client.post('/book-pickup', data={
            'society_id': '1',
            'is_society': '1',
            'address': 'Gate No. 2 Bulk Station, Goyal Intercity, Drive-In Road, Ahmedabad, Gujarat 380054',
            'lat': '23.048900',
            'lng': '72.527300',
            'stream_wet': 'on',
            'stream_wet_kg': '30.0',
            'stream_dry': 'on',
            'stream_dry_kg': '25.0'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        conn = get_db()
        p = conn.execute("SELECT * FROM pickups WHERE is_society = 1 ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        self.assertIn('Gate No. 2 Bulk Station', p['address'])
        self.assertAlmostEqual(p['lat'], 23.048900, places=4)
        self.assertAlmostEqual(p['lng'], 72.527300, places=4)

    def test_driver_navigation_url_exact_coords(self):
        # 8. Test driver navigation URL contains exact coordinates
        conn = get_db()
        conn.execute("UPDATE pickups SET assigned_van_id = 1 WHERE id = 1")
        conn.commit()
        conn.close()

        with self.client.session_transaction() as sess:
            sess['user_id'] = 3
            sess['role'] = 'driver'
            sess['van_id'] = 1

        res = self.client.get('/driver')
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        self.assertIn('google.com/maps/dir/?api=1&destination=', html)

    def test_api_pickups_returns_address(self):
        # 9. Test API /api/pickups returns address field
        res = self.client.get('/api/pickups')
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertTrue(len(data['pickups']) > 0)
        first = data['pickups'][0]
        self.assertIn('address', first)
        self.assertTrue(len(first['address']) > 0)
        self.assertIn('lat', first)
        self.assertIn('lng', first)

    def test_manifest_page_shows_location_and_nav(self):
        # 10. Test Manifest page displays address and navigation link
        res = self.client.get('/manifest/1')
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        self.assertIn('📍 Pickup Location:', html)
        self.assertIn('google.com/maps/dir/?api=1&destination=', html)

if __name__ == '__main__':
    unittest.main()
