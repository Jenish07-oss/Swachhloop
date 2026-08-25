import unittest
from app import app
from seed_data import seed
from database import get_db
from brand import calculate_green_points, format_pickup_code

class TestNagarLoopPhase2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        print("Seeding NagarLoop Phase 2 database...")
        seed()
        app.config['TESTING'] = True
        cls.client = app.test_client()

    def test_01_home_page(self):
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'NagarLoop', res.data)
        self.assertIn(b'id="loop"', res.data)
        self.assertIn(b'badges', res.data)
        self.assertIn(b'How It Works', res.data)
        self.assertNotIn(b'1 pt = \xe2\x82\xb91 tax credit', res.data)

    def test_02_set_lang_toggle(self):
        res = self.client.post('/set-lang', data={'lang': 'gu'}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn('કચરો'.encode('utf-8'), res.data)
        
        res = self.client.post('/set-lang', data={'lang': 'en'}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Book Pickup', res.data)

    def test_03_login_citizen_success(self):
        res = self.client.post('/login/citizen', data={
            'username': 'jenish',
            'password': 'jenish123'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Welcome back, Jenish Patel!', res.data)
        self.assertIn(b'Book a 4-Stream Collection', res.data)

    def test_04_login_driver_success(self):
        res = self.client.post('/login/driver', data={
            'username': 'vikram',
            'password': 'vikram123'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Driver Portal', res.data)
        self.assertIn(b'Vikram Thakor', res.data)

    def test_05_login_admin_success(self):
        res = self.client.post('/login/admin', data={
            'username': 'admin',
            'password': 'admin123'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Municipal Command Center', res.data)

    def test_06_login_invalid_password(self):
        res = self.client.post('/login/citizen', data={
            'username': 'jenish',
            'password': 'wrongpassword'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Invalid username', res.data)

    def test_07_logout(self):
        res = self.client.get('/logout', follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'You have been signed out.', res.data)

    def test_08_citizen_booking_page_and_submit(self):
        self.client.post('/login/citizen', data={'username': 'jenish', 'password': 'jenish123'})
        res_get = self.client.get('/book')
        self.assertEqual(res_get.status_code, 200)
        self.assertIn(b'Book', res_get.data)

        # Full booking post with Estimated KG
        booking_data = {
            'household_id': '1',
            'lat': '23.0375',
            'lng': '72.5520',
            'stream_wet': 'on',
            'stream_wet_kg': '4.2',
            'stream_dry': 'on',
            'stream_dry_kg': '3.5',
            'stream_ewaste': 'on',
            'stream_ewaste_kg': '1.2'
        }
        post_res = self.client.post('/book-pickup', data=booking_data, follow_redirects=True)
        self.assertEqual(post_res.status_code, 200)
        self.assertIn(b'Green Points', post_res.data)

    def test_09_my_pickups(self):
        self.client.post('/login/citizen', data={'username': 'jenish', 'password': 'jenish123'})
        res = self.client.get('/my-pickups')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'My Pickups', res.data)
        self.assertIn(b'NL-2026-', res.data)

    def test_10_impact_dashboard(self):
        self.client.post('/login/citizen', data={'username': 'jenish', 'password': 'jenish123'})
        res = self.client.get('/impact')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Impact Dashboard', res.data)
        self.assertIn(b'Green Points Balance', res.data)

    def test_11_manifest_view(self):
        res = self.client.get('/manifest/1')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Manifest', res.data)
        self.assertIn(b'NL-2026-00001', res.data)
        self.assertIn(b'data:image/png;base64', res.data)

    def test_12_admin_dashboard(self):
        self.client.post('/login/admin', data={'username': 'admin', 'password': 'admin123'})
        res = self.client.get('/admin')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Municipal Command Center', res.data)
        self.assertIn(b'Destination Facilities Capacity', res.data)

    def test_13_admin_dispatch(self):
        self.client.post('/login/admin', data={'username': 'admin', 'password': 'admin123'})
        res = self.client.get('/admin/dispatch')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Dispatch Center', res.data)

    def test_14_legal_and_help_pages(self):
        res_priv = self.client.get('/privacy')
        self.assertEqual(res_priv.status_code, 200)
        self.assertIn(b'Privacy Policy', res_priv.data)

        res_rew = self.client.get('/rewards')
        self.assertEqual(res_rew.status_code, 200)
        self.assertIn(b'Green Rewards', res_rew.data)

        res_help = self.client.get('/help')
        self.assertEqual(res_help.status_code, 200)
        self.assertIn(b'Frequently asked questions', res_help.data)
        self.assertIn(b'support@nagarloop.in', res_help.data)

    def test_15_public_leaderboard(self):
        res = self.client.get('/leaderboard')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Ward Green Champions', res.data)

    def test_16_css_static_file(self):
        res = self.client.get('/static/css/nl.css')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'--forest: #0C3B2E;', res.data)
        self.assertIn(b'--lime: #B5E048;', res.data)

    # ----------------------------------------------------
    # PHASE 2 SPECIFIC TEST SUITE
    # ----------------------------------------------------

    def test_17_registration_citizen(self):
        self.client.get('/logout')
        res = self.client.post('/register', data={
            'reg_type': 'citizen',
            'name': 'Pooja Barot',
            'phone': '9900000001',
            'address': 'Gulbai Tekra Axis',
            'password': 'password123'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Account registered successfully', res.data)

    def test_18_registration_society(self):
        self.client.get('/logout')
        res = self.client.post('/register', data={
            'reg_type': 'society',
            'society_name': 'Sterling City',
            'manager_name': 'Ketan Shah',
            'phone': '9900000002',
            'address': 'Bopal Road, Ahmedabad',
            'collection_point': 'Gate 1 Bin Storage',
            'password': 'password123'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Sterling City', res.data)
        self.assertIn(b'Society Dashboard', res.data)

    def test_19_society_dashboard_and_bulk_booking(self):
        self.client.post('/login/society_manager', data={'username': 'society', 'password': 'society123'})
        res = self.client.get('/society/dashboard')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Shivalik Heights', res.data)
        self.assertIn(b'Society Green Points', res.data)

        # Book bulk pickup
        res_book = self.client.post('/book-pickup', data={
            'society_id': '1',
            'is_society': '1',
            'stream_wet': 'on',
            'stream_wet_kg': '20.0',
            'stream_dry': 'on',
            'stream_dry_kg': '15.0'
        }, follow_redirects=True)
        self.assertEqual(res_book.status_code, 200)
        self.assertIn(b'Shivalik Heights', res_book.data)

    def test_20_public_waste_report(self):
        res = self.client.post('/report-public', data={
            'address': 'Near Mithakhali Underpass',
            'waste_type': 'dry',
            'estimated_kg': '15.0',
            'description': 'Dumped packaging cartons on footpath',
            'reporter_name': 'Civic Citizen',
            'reporter_phone': '9876543210'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Public waste report #NL-2026-', res.data)

    def test_21_proportional_points_formula(self):
        # Wet = 2/kg, Dry = 6/kg, E-Waste = 20/kg, Residual = 1/kg
        # score >= 80 -> 1.5x multiplier
        # 4.2 kg wet (8.4) + 3.5 kg dry (21.0) = 29.4 * 1.5 = 44.1 -> 44 points
        pts = calculate_green_points({'wet': 4.2, 'dry': 3.5}, bin_score=85, is_society=False)
        self.assertEqual(pts, 44)

        # Society below 5kg total -> 0 points
        soc_low = calculate_green_points({'wet': 2.0, 'dry': 1.0}, bin_score=90, is_society=True)
        self.assertEqual(soc_low, 0)

        # Public report -> 15 base (+5 if >= 10kg)
        pub_pts = calculate_green_points({'wet': 12.0}, is_public=True)
        self.assertEqual(pub_pts, 20)

    def test_22_driver_report_problem(self):
        self.client.post('/login/driver', data={'username': 'vikram', 'password': 'vikram123'})
        res = self.client.post('/api/driver/report-problem/1', json={
            'reason': 'Gate locked',
            'notes': 'Security stated resident is out of town'
        })
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()['success'])

        conn = get_db()
        p = conn.execute("SELECT status, problem_reason FROM pickups WHERE id = 1").fetchone()
        conn.close()
        self.assertEqual(p['status'], 'failed')
        self.assertEqual(p['problem_reason'], 'Gate locked')

    def test_23_admin_reschedule(self):
        self.client.post('/login/admin', data={'username': 'admin', 'password': 'admin123'})
        res = self.client.post('/api/admin/reschedule/1', json={
            'date': 'Tomorrow Morning',
            'window': '07:30 AM - 09:30 AM',
            'van_id': 1
        })
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()['success'])

        conn = get_db()
        p = conn.execute("SELECT status, rescheduled_date FROM pickups WHERE id = 1").fetchone()
        conn.close()
        self.assertEqual(p['status'], 'pending')
        self.assertEqual(p['rescheduled_date'], 'Tomorrow Morning')

    def test_24_filtered_leaderboard(self):
        res_soc = self.client.get('/leaderboard?period=this_month&category=societies')
        self.assertEqual(res_soc.status_code, 200)
        self.assertIn(b'Housing Societies', res_soc.data)

        res_week = self.client.get('/leaderboard?period=this_week&category=all')
        self.assertEqual(res_week.status_code, 200)
        self.assertIn(b'Individual Citizens', res_week.data)

    def test_25_route_recalculate_and_apply(self):
        self.client.post('/login/admin', data={'username': 'admin', 'password': 'admin123'})
        # 1. Recalculate route metrics with specific stops
        res_recalc = self.client.post('/api/route/recalculate', json={
            'van_id': 1,
            'stream_type': 'wet',
            'pickup_ids': [1, 2, 3]
        })
        self.assertEqual(res_recalc.status_code, 200)
        recalc_data = res_recalc.get_json()
        self.assertTrue(recalc_data['success'])
        self.assertGreater(recalc_data['naive_dist_km'], 0.0)
        self.assertGreater(recalc_data['custom_dist_km'], 0.0)

        # 2. Apply route batch
        res_apply = self.client.post('/api/route/apply', json={
            'van_id': 1,
            'stream_type': 'wet',
            'zone': '1',
            'pickup_ids': [1, 2, 3],
            'naive_dist': recalc_data['naive_dist_km'],
            'opt_dist': recalc_data['custom_dist_km'],
            'saved_pct': recalc_data['saved_pct']
        })
        self.assertEqual(res_apply.status_code, 200)
        apply_data = res_apply.get_json()
        self.assertTrue(apply_data['success'])
        self.assertIn('applied', apply_data['message'])

    def test_26_stream_zone_toggle_route_filters(self):
        self.client.post('/login/admin', data={'username': 'admin', 'password': 'admin123'})
        
        # Test stream=all
        res_all = self.client.get('/admin/route/1?stream=all&zone=all')
        self.assertEqual(res_all.status_code, 200)
        self.assertIn(b'All Streams', res_all.data)

        # Test stream=dry & zone=1
        res_dry = self.client.get('/admin/route/1?stream=dry&zone=1')
        self.assertEqual(res_dry.status_code, 200)
        self.assertIn(b'Dry Recyclables', res_dry.data)

        # Test zero stops edge case (zone=5 where no stops match)
        res_zero = self.client.get('/admin/route/1?stream=e_waste&zone=5')
        self.assertEqual(res_zero.status_code, 200)

    def test_27_sms_simulation_logs_on_admin(self):
        self.client.post('/login/admin', data={'username': 'admin', 'password': 'admin123'})
        res = self.client.get('/admin')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Notification Log / SMS Simulation', res.data)
        self.assertIn(b'SMS Engine Active', res.data)

    def test_28_zero_mixing_guarantee_present(self):
        # 1. Citizen report page
        self.client.post('/login/citizen', data={'username': 'jenish', 'password': 'jenish123'})
        res_citizen = self.client.get('/book')
        self.assertEqual(res_citizen.status_code, 200)
        self.assertIn(b'ZERO-MIXING', res_citizen.data)

        # 2. Public report page
        res_pub = self.client.get('/report-public')
        self.assertEqual(res_pub.status_code, 200)
        self.assertIn(b'ZERO-MIXING', res_pub.data)

        # 3. Driver portal
        self.client.post('/login/driver', data={'username': 'vikram', 'password': 'vikram123'})
        res_driver = self.client.get('/driver')
        self.assertEqual(res_driver.status_code, 200)
        self.assertIn(b'ZERO-MIXING', res_driver.data)

        # 4. Admin Command Center
        self.client.post('/login/admin', data={'username': 'admin', 'password': 'admin123'})
        res_admin = self.client.get('/admin')
        self.assertEqual(res_admin.status_code, 200)
        self.assertIn(b'ZERO-MIXING', res_admin.data)

    def test_29_driver_shift_lifecycle(self):
        # 1. Driver login
        self.client.post('/login/driver', data={'username': 'vikram', 'password': 'vikram123'})
        
        # 2. Start Shift
        res_start = self.client.post('/api/driver/start-shift')
        self.assertEqual(res_start.status_code, 200)
        data_start = res_start.get_json()
        self.assertTrue(data_start['success'])

        # 3. Check Driver portal reflects active shift
        res_portal = self.client.get('/driver')
        self.assertEqual(res_portal.status_code, 200)
        self.assertIn(b'SHIFT ACTIVE', res_portal.data)

        # 4. End Shift
        res_end = self.client.post('/api/driver/end-shift')
        self.assertEqual(res_end.status_code, 200)
        data_end = res_end.get_json()
        self.assertTrue(data_end['success'])
        self.assertIn('summary', data_end)

        # 5. Check Driver portal reflects summary & completed shift
        res_portal_end = self.client.get('/driver')
        self.assertEqual(res_portal_end.status_code, 200)
        self.assertIn(b'TODAY\'S SHIFT SUMMARY', res_portal_end.data)

    def test_30_driver_notify_nearby(self):
        self.client.post('/login/driver', data={'username': 'vikram', 'password': 'vikram123'})
        res = self.client.post('/api/driver/notify-nearby/1')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertIn('Citizen notified', data['message'])

    def test_31_sms_duplicate_prevention(self):
        from app import log_sms
        # First log
        id1 = log_sms('9876543210', 'Test notification', 'truck_nearby', pickup_id=99)
        # Duplicate log for same event & pickup
        id2 = log_sms('9876543210', 'Test notification duplicate', 'truck_nearby', pickup_id=99)
        self.assertEqual(id1, id2, "Duplicate notification should return existing ID without creating duplicate record")

    def test_32_admin_societies_management(self):
        self.client.post('/login/admin', data={'username': 'admin', 'password': 'admin123'})
        
        # 1. Societies Listing
        res_list = self.client.get('/admin/societies')
        self.assertEqual(res_list.status_code, 200)
        self.assertIn(b'Registered Housing Societies', res_list.data)
        self.assertIn(b'Shivalik Heights', res_list.data)
        self.assertIn(b'SOC-001', res_list.data)

        # 2. Society Detail View
        res_detail = self.client.get('/admin/societies/1')
        self.assertEqual(res_detail.status_code, 200)
        self.assertIn(b'Shivalik Heights', res_detail.data)
        self.assertIn(b'Green Points Balance', res_detail.data)
        self.assertIn(b'Segregated 4-Stream Breakdown', res_detail.data)

    def test_33_role_isolation_security(self):
        # 1. Citizen cannot access /driver or /admin
        self.client.post('/login/citizen', data={'username': 'jenish', 'password': 'jenish123'})
        res_c_drv = self.client.get('/driver', follow_redirects=False)
        self.assertIn(res_c_drv.status_code, [302, 403])
        res_c_adm = self.client.get('/admin', follow_redirects=False)
        self.assertIn(res_c_adm.status_code, [302, 403])

        # 2. Driver cannot access /admin or /admin/societies
        self.client.post('/login/driver', data={'username': 'vikram', 'password': 'vikram123'})
        res_d_adm = self.client.get('/admin', follow_redirects=False)
        self.assertIn(res_d_adm.status_code, [302, 403])
        res_d_soc = self.client.get('/admin/societies', follow_redirects=False)
        self.assertIn(res_d_soc.status_code, [302, 403])

        # 3. Society Manager cannot access /admin/societies
        self.client.post('/login/society_manager', data={'username': 'society', 'password': 'society123'})
        res_s_adm = self.client.get('/admin/societies', follow_redirects=False)
        self.assertIn(res_s_adm.status_code, [302, 403])

        # 4. Admin has access to all admin areas
        self.client.post('/login/admin', data={'username': 'admin', 'password': 'admin123'})
        res_a_dash = self.client.get('/admin')
        self.assertEqual(res_a_dash.status_code, 200)
        res_a_soc = self.client.get('/admin/societies')
        self.assertEqual(res_a_soc.status_code, 200)

    def test_34_society_data_privacy(self):
        # Society manager logged in -> accesses dashboard -> strictly restricted to own society
        self.client.post('/login/society_manager', data={'username': 'society', 'password': 'society123'})
        res = self.client.get('/society/dashboard?society_id=4')
        self.assertEqual(res.status_code, 200)
        # Should render Shivalik Heights (their own society, id 1), not Akshardham (id 4)
        self.assertIn(b'Shivalik Heights', res.data)

    def test_35_driver_report_collection_flow(self):
        self.client.post('/login/driver', data={'username': 'vikram', 'password': 'vikram123'})
        res = self.client.post('/api/status/2', json={'action': 'report_collection'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data.get('new_status'), 'collection_reported')

    def test_36_comprehensive_4way_role_matrix(self):
        # 1. Citizen cannot access Driver APIs or Admin APIs
        self.client.post('/login/citizen', data={'username': 'jenish', 'password': 'jenish123'})
        res_c1 = self.client.post('/api/driver/start-shift')
        self.assertEqual(res_c1.status_code, 403)
        res_c2 = self.client.post('/api/route/apply', json={'van_id': 1, 'pickup_ids': [1]})
        self.assertEqual(res_c2.status_code, 403)
        res_c3 = self.client.post('/api/admin/reschedule/1', json={'date': 'Tomorrow'})
        self.assertEqual(res_c3.status_code, 403)

        # 2. Driver cannot access Citizen private views or Admin APIs
        self.client.post('/login/driver', data={'username': 'vikram', 'password': 'vikram123'})
        res_d1 = self.client.get('/society/dashboard', follow_redirects=False)
        self.assertIn(res_d1.status_code, [302, 403])
        res_d2 = self.client.post('/api/route/apply', json={'van_id': 1, 'pickup_ids': [1]})
        self.assertEqual(res_d2.status_code, 403)

        # 3. Society Manager cannot access Driver APIs or Admin Command Center
        self.client.post('/login/society_manager', data={'username': 'society', 'password': 'society123'})
        res_s1 = self.client.get('/admin', follow_redirects=False)
        self.assertIn(res_s1.status_code, [302, 403])
        res_s2 = self.client.get('/driver', follow_redirects=False)
        self.assertIn(res_s2.status_code, [302, 403])
        res_s3 = self.client.post('/api/driver/start-shift')
        self.assertEqual(res_s3.status_code, 403)

        # 4. Unauthenticated guest blocked from protected routes
        self.client.get('/logout')
        res_g1 = self.client.get('/admin', follow_redirects=False)
        self.assertEqual(res_g1.status_code, 302)
        res_g2 = self.client.get('/driver', follow_redirects=False)
        self.assertEqual(res_g2.status_code, 302)
        res_g3 = self.client.post('/api/driver/start-shift')
        self.assertEqual(res_g3.status_code, 401)

    def test_37_admin_reports_page(self):
        self.client.post('/login/admin', data={'username': 'admin', 'password': 'admin123'})
        res = self.client.get('/admin/reports')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'MUNICIPAL CIRCULAR AUDIT REPORT', res.data)
        self.assertIn(b'Print Official Report', res.data)
        self.assertIn(b'CO2e Offset', res.data)

    def test_38_admin_export_csv(self):
        self.client.post('/login/admin', data={'username': 'admin', 'password': 'admin123'})
        res = self.client.get('/admin/export-csv')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get('Content-Type'), 'text/csv; charset=utf-8')
        self.assertIn(b'Pickup_ID,Reference_Code,Type,Entity_Name', res.data)
        self.assertIn(b'NL-2026-', res.data)

    def test_39_operational_rates_and_alerts(self):
        self.client.post('/login/admin', data={'username': 'admin', 'password': 'admin123'})
        res = self.client.get('/admin')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Success Rate', res.data)
        self.assertIn(b'Delivery Rate', res.data)
        self.assertIn(b'Operational Signals', res.data)
        self.assertIn(b'4-Stream Waste Recovery Volume', res.data)

    def test_40_co2e_estimate_accuracy(self):
        from brand import calculate_co2_impact
        # 10 kg wet (5 kg CO2e) + 10 kg dry (14 kg CO2e) + 10 kg ewaste (28 kg CO2e) + 10 kg residual (3 kg CO2e) = 50.0 kg CO2e
        co2 = calculate_co2_impact(wet_kg=10, dry_kg=10, ewaste_kg=10, residual_kg=10)
        self.assertEqual(co2, 50.0)

    def test_41_validate_indian_phone_unit(self):
        from app import validate_indian_phone
        # Valid Indian numbers starting with 6, 7, 8, 9
        self.assertEqual(validate_indian_phone("9825012345"), "9825012345")
        self.assertEqual(validate_indian_phone("+919825012345"), "9825012345")
        self.assertEqual(validate_indian_phone("91 98250 12345"), "9825012345")
        self.assertEqual(validate_indian_phone("09825012345"), "9825012345")
        self.assertEqual(validate_indian_phone("7878787878"), "7878787878")
        self.assertEqual(validate_indian_phone("6351234567"), "6351234567")
        self.assertEqual(validate_indian_phone("8989898989"), "8989898989")

        # Invalid numbers (starting with 1-5, wrong length, letters)
        self.assertIsNone(validate_indian_phone("1234567890"))
        self.assertIsNone(validate_indian_phone("5555555555"))
        self.assertIsNone(validate_indian_phone("98250123"))
        self.assertIsNone(validate_indian_phone("982501234567"))
        self.assertIsNone(validate_indian_phone("abcdefghij"))
        self.assertIsNone(validate_indian_phone(""))
        self.assertIsNone(validate_indian_phone(None))

    def test_42_register_with_invalid_phone_fails(self):
        res = self.client.post('/register', data={
            'reg_type': 'citizen',
            'name': 'Test Citizen',
            'phone': '1234567890',
            'password': 'password123',
            'address': 'Navrangpura'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Please enter a valid 10-digit Indian mobile number', res.data)

    def test_43_register_with_valid_indian_phone_success(self):
        res = self.client.post('/register', data={
            'reg_type': 'citizen',
            'name': 'Pooja Dave',
            'phone': '9898123456',
            'password': 'password123',
            'address': 'Vijay Cross Roads, Navrangpura'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Account registered successfully', res.data)

    def test_44_booking_blocked_when_ai_check_failed_or_missing(self):
        # Log in citizen
        self.client.post('/login/citizen', data={'username': 'jenish', 'password': 'jenish123'})
        
        # Test 1: Submit with failed AI check
        res_fail = self.client.post('/book-pickup', data={
            'household_id': 1,
            'stream_wet': 'on',
            'stream_wet_kg': '4.0',
            'address': 'Navrangpura, Ahmedabad',
            'lat': '23.0375',
            'lng': '72.5520',
            'ai_image_check': 'failed',
            'ai_confidence': '0.05'
        }, follow_redirects=True)
        self.assertEqual(res_fail.status_code, 200)
        self.assertIn(b'Booking blocked: A valid waste photo must be verified before booking', res_fail.data)

        # Test 2: Submit with unverified AI check (not_submitted)
        res_missing = self.client.post('/book-pickup', data={
            'household_id': 1,
            'stream_wet': 'on',
            'stream_wet_kg': '4.0',
            'address': 'Navrangpura, Ahmedabad',
            'lat': '23.0375',
            'lng': '72.5520',
            'ai_image_check': 'not_submitted',
            'ai_confidence': '0.0'
        }, follow_redirects=True)
        self.assertEqual(res_missing.status_code, 200)
        self.assertIn(b'Booking blocked: A valid waste photo must be verified before booking', res_missing.data)

        # Test 3: Submit with low confidence (below 0.30)
        res_low_conf = self.client.post('/book-pickup', data={
            'household_id': 1,
            'stream_wet': 'on',
            'stream_wet_kg': '4.0',
            'address': 'Navrangpura, Ahmedabad',
            'lat': '23.0375',
            'lng': '72.5520',
            'ai_image_check': 'passed',
            'ai_confidence': '0.10'
        }, follow_redirects=True)
        self.assertEqual(res_low_conf.status_code, 200)
        self.assertIn(b'Booking blocked: A valid waste photo must be verified before booking', res_low_conf.data)

    def test_45_booking_succeeds_only_when_ai_check_passed(self):
        self.client.post('/login/citizen', data={'username': 'jenish', 'password': 'jenish123'})
        
        res_pass = self.client.post('/book-pickup', data={
            'household_id': 1,
            'stream_wet': 'on',
            'stream_wet_kg': '4.0',
            'address': 'Navrangpura, Ahmedabad',
            'lat': '23.0375',
            'lng': '72.5520',
            'ai_image_check': 'passed',
            'ai_confidence': '0.85'
        }, follow_redirects=True)
        self.assertEqual(res_pass.status_code, 200)
        self.assertIn(b'booked successfully', res_pass.data)

if __name__ == '__main__':
    unittest.main()
