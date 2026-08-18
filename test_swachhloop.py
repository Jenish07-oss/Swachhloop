import unittest
from app import app
from seed_data import seed
from database import get_db

class TestNagarLoopPhase1(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        print("Seeding NagarLoop database...")
        seed()
        app.config['TESTING'] = True
        cls.client = app.test_client()

    def test_01_home_page(self):
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'NagarLoop', res.data)
        self.assertIn(b'loopTrack', res.data)
        self.assertIn(b'How It Works', res.data)

    def test_02_set_lang_toggle(self):
        # Switch to Gujarati
        res = self.client.post('/set-lang', data={'lang': 'gu'}, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        # Check Gujarati translation rendered
        self.assertIn('કચરો'.encode('utf-8'), res.data)
        
        # Switch back to English
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
        self.assertIn(b'Book a Pickup', res.data)

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
        self.assertIn(b'Invalid username or password', res.data)

    def test_07_logout(self):
        res = self.client.get('/logout', follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'You have been signed out.', res.data)

    def test_08_citizen_booking_page_and_submit(self):
        res = self.client.get('/book')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Book a Pickup', res.data)

        # Full booking post
        booking_data = {
            'household_id': '1',
            'lat': '23.0375',
            'lng': '72.5520',
            'stream_wet': 'on',
            'stream_dry': 'on',
            'stream_ewaste': 'on'
        }
        post_res = self.client.post('/book-pickup', data=booking_data, follow_redirects=True)
        self.assertEqual(post_res.status_code, 200)
        self.assertIn(b'Green Points earned', post_res.data)

    def test_09_my_pickups(self):
        res = self.client.get('/my-pickups')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'My Pickups', res.data)

    def test_10_impact_dashboard(self):
        res = self.client.get('/impact')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Impact Dashboard', res.data)
        self.assertIn(b'Green Points Balance', res.data)

    def test_11_manifest_view(self):
        res = self.client.get('/manifest/1')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Manifest', res.data)
        self.assertIn(b'data:image/png;base64', res.data)

    def test_12_admin_dashboard(self):
        res = self.client.get('/admin')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Municipal Command Center', res.data)

    def test_13_admin_dispatch(self):
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
        self.assertIn(b'--g: #1e7e5a;', res.data)

if __name__ == '__main__':
    unittest.main()
