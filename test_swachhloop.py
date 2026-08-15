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
        self.assertIn(b'Impact', res.data)

    def test_02_citizen_booking_without_kg(self):
        # Booking without any citizen KG input (Pure stream selection)
        data = {
            'household_id': '1',
            'lat': '23.0375',
            'lng': '72.5520',
            'stream_wet': 'on',
            'stream_dry': 'on'
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
        self.assertIn(b'Manifest', res.data)
        self.assertIn(b'data:image/png;base64', res.data)
        self.assertIn(b'Segregated Streams', res.data)

    def test_05_admin_dashboard(self):
        res = self.client.get('/admin')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Municipal Command Center', res.data)
        self.assertIn(b'Facility Demand Board', res.data)
        self.assertIn(b'FILTERS', res.data)

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

        # Set to pending then report collection
        conn = get_db()
        conn.execute("UPDATE pickups SET status = 'pending' WHERE id = 1")
        conn.commit()
        conn.close()

        res = self.client.post('/api/status/1', json={'action': 'report_collection'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['new_status'], 'collection_reported')

    def test_09_citizen_impact(self):
        res = self.client.get('/impact')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Your 4R Impact Dashboard', res.data)
        self.assertIn(b'Estimated Waste Diverted', res.data)

    def test_10_demo_reset_and_route_apply(self):
        res = self.client.post('/api/route/apply', json={'van_id': 1, 'pickup_ids': [1, 2, 3]})
        self.assertEqual(res.status_code, 200)

        res = self.client.post('/api/reset-demo')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()['success'])

    def test_11_route_recalculate(self):
        res = self.client.post('/api/route/recalculate', json={
            'van_id': 1,
            'stream_type': 'wet',
            'pickup_ids': [1, 5, 2]
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertIn('custom_dist_km', data)
        self.assertIn('saved_pct', data)

    def test_12_dispatch_center(self):
        res = self.client.get('/admin/dispatch?van_id=1')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Dispatch Center', res.data)
        self.assertIn(b'Route Stops Sequence', res.data)

    def test_13_route_deliver(self):
        # Set pickups 1, 2 to collected first
        conn = get_db()
        conn.execute("UPDATE pickups SET status = 'collected' WHERE id IN (1, 2)")
        conn.commit()
        conn.close()

        res = self.client.post('/api/route/deliver', json={'pickup_ids': [1, 2]})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()['success'])

    def test_14_safe_status_lifecycle_and_reopen(self):
        # 1. Reset demo
        self.client.post('/api/reset-demo')
        
        conn = get_db()
        pending_pickup = conn.execute("SELECT id FROM pickups WHERE status = 'pending' LIMIT 1").fetchone()
        conn.close()
        pid = pending_pickup['id']
        
        # 2. Report collection from pending
        res = self.client.post(f'/api/status/{pid}', json={'action': 'report_collection'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['new_status'], 'collection_reported')

        # 3. Duplicate report collection must fail server validation
        res_dup = self.client.post(f'/api/status/{pid}', json={'action': 'report_collection'})
        self.assertEqual(res_dup.status_code, 400)

        # 4. Reopen pickup back to pending
        res_reopen = self.client.post(f'/api/status/{pid}', json={'action': 'reopen_pickup'})
        self.assertEqual(res_reopen.status_code, 200)
        self.assertEqual(res_reopen.get_json()['new_status'], 'pending')

        # 5. Report collection again -> citizen confirm -> mark delivered
        self.client.post(f'/api/status/{pid}', json={'action': 'report_collection'})
        self.client.post(f'/api/citizen/verify/{pid}', json={'action': 'confirm'})
        res_del = self.client.post(f'/api/status/{pid}', json={'action': 'mark_delivered'})
        self.assertEqual(res_del.status_code, 200)
        self.assertEqual(res_del.get_json()['new_status'], 'delivered')

        # 6. Verify audit logs in database
        conn = get_db()
        logs = conn.execute("SELECT * FROM audit_logs WHERE pickup_id = ? ORDER BY id ASC", (pid,)).fetchall()
        conn.close()
        self.assertGreaterEqual(len(logs), 4)

    def test_15_collection_verification_and_dispute_workflow(self):
        # 1. Reset demo
        self.client.post('/api/reset-demo')
        
        conn = get_db()
        pending_pickup = conn.execute("SELECT id FROM pickups WHERE status = 'pending' LIMIT 1").fetchone()
        conn.close()
        pid = pending_pickup['id']

        # 2. Operator reports collection -> collection_reported
        res_op = self.client.post(f'/api/status/{pid}', json={'action': 'report_collection'})
        self.assertEqual(res_op.status_code, 200)
        self.assertEqual(res_op.get_json()['new_status'], 'collection_reported')

        # 3. Citizen disputes -> disputed
        res_disp = self.client.post(f'/api/citizen/verify/{pid}', json={'action': 'dispute'})
        self.assertEqual(res_disp.status_code, 200)
        self.assertEqual(res_disp.get_json()['new_status'], 'disputed')

        # 4. Admin reviews dispute and returns to pending -> pending
        res_reopen = self.client.post(f'/api/status/{pid}', json={'action': 'admin_reopen'})
        self.assertEqual(res_reopen.status_code, 200)
        self.assertEqual(res_reopen.get_json()['new_status'], 'pending')

        # 5. Operator reports collection again -> collection_reported
        res_op2 = self.client.post(f'/api/status/{pid}', json={'action': 'report_collection'})
        self.assertEqual(res_op2.status_code, 200)
        self.assertEqual(res_op2.get_json()['new_status'], 'collection_reported')

        # 6. Citizen confirms -> collected
        res_conf = self.client.post(f'/api/citizen/verify/{pid}', json={'action': 'confirm'})
        self.assertEqual(res_conf.status_code, 200)
        self.assertEqual(res_conf.get_json()['new_status'], 'collected')

        # 7. Deliver -> delivered
        res_del = self.client.post(f'/api/status/{pid}', json={'action': 'mark_delivered'})
        self.assertEqual(res_del.status_code, 200)
        self.assertEqual(res_del.get_json()['new_status'], 'delivered')

        # 8. Check audit trail
        conn = get_db()
        logs = conn.execute("SELECT * FROM audit_logs WHERE pickup_id = ? ORDER BY id ASC", (pid,)).fetchall()
        conn.close()
        self.assertGreaterEqual(len(logs), 5)

if __name__ == '__main__':
    unittest.main()
