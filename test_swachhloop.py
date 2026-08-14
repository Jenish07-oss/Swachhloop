import unittest
from app import app
from seed_data import seed
from database import get_db

class TestSwachhLoop4R(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        print("Seeding database...")
        seed()
        cls.client = app.test_client()

    def test_01_citizen_home(self):
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'SwachhLoop', res.data)
        self.assertIn(b'Wet / Organic', res.data)
        self.assertIn(b'Dry Recyclables', res.data)
        self.assertIn(b'E-Waste', res.data)
        self.assertIn(b'Residual Combustibles', res.data)
        self.assertIn(b'Impact Ledger', res.data)

    def test_02_citizen_booking(self):
        data = {
            'household_id': '1',
            'lat': '23.0375',
            'lng': '72.5520',
            'stream_wet': 'on',
            'kg_wet': '4.0',
            'stream_dry': 'on',
            'kg_dry': '3.0'
        }
        res = self.client.post('/book-pickup', data=data, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Green Points', res.data)

    def test_03_my_pickups(self):
        res = self.client.get('/my-pickups')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'My 4R Pickups', res.data)
        self.assertIn(b'QR Manifest', res.data)

    def test_04_manifest_page(self):
        res = self.client.get('/manifest/1')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'SwachhLoop 4R Digital Manifest', res.data)
        self.assertIn(b'data:image/png;base64', res.data)
        self.assertIn(b'Segregated Streams', res.data)

    def test_05_admin_dashboard(self):
        res = self.client.get('/admin')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'4R Command Center', res.data)
        self.assertIn(b'Facility Demand Board', res.data)
        self.assertIn(b'KMeans Pickup Zones', res.data)

    def test_06_admin_route_optimization(self):
        res = self.client.get('/admin/route/1')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Route Optimization', res.data)
        self.assertIn(b'Distance Saved', res.data)
        self.assertIn(b'Nearest-neighbour estimate', res.data)

    def test_07_api_endpoints(self):
        # Pickups
        res = self.client.get('/api/pickups')
        self.assertEqual(res.status_code, 200)
        pickups = res.get_json()
        self.assertGreaterEqual(len(pickups), 40)
        self.assertIn('streams', pickups[0])

        # Vans
        res = self.client.get('/api/vans')
        self.assertEqual(res.status_code, 200)
        vans = res.get_json()
        self.assertEqual(len(vans), 3)

        # Facilities
        res = self.client.get('/api/facilities')
        self.assertEqual(res.status_code, 200)
        facilities = res.get_json()
        self.assertEqual(len(facilities), 4)

        # Zones (KMeans)
        res = self.client.get('/api/zones')
        self.assertEqual(res.status_code, 200)
        zones = res.get_json()
        self.assertEqual(len(zones['zones']), 5)

        # Demand
        res = self.client.get('/api/demand')
        self.assertEqual(res.status_code, 200)

        # Leaderboard
        res = self.client.get('/api/leaderboard')
        self.assertEqual(res.status_code, 200)
        self.assertIn('labels', res.get_json())

        # Impact
        res = self.client.get('/api/impact')
        self.assertEqual(res.status_code, 200)
        impact = res.get_json()
        self.assertGreater(impact['total_kg_diverted'], 0)

    def test_08_status_and_assignment(self):
        res = self.client.post('/api/assign', json={'pickup_id': 1, 'van_id': 2})
        self.assertEqual(res.status_code, 200)

        res = self.client.post('/api/status/1', json={'status': 'collected'})
        self.assertEqual(res.status_code, 200)

if __name__ == '__main__':
    unittest.main()
