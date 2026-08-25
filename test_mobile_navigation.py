import unittest
import os
import sys

# Ensure path includes root directory
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from app import app
from seed_data import seed

class TestNagarLoopMobileNavigation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        seed()

    def setUp(self):
        self.client = app.test_client()

    def test_01_public_guest_mobile_shell(self):
        """Test public/guest views contain mobile header, bottom nav, and drawer"""
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        html = res.data.decode('utf-8')
        self.assertIn('nl-mobile-header', html)
        self.assertIn('nl-mobile-bottom-nav', html)
        self.assertIn('nlMoreDrawer', html)
        self.assertIn('Citizen Login', html)
        self.assertIn('Society Manager Login', html)
        self.assertIn('Driver Login', html)
        self.assertIn('Municipal Admin Login', html)

    def test_02_citizen_login_and_mobile_navigation(self):
        """Test citizen login immediately renders full mobile navigation and all permitted sections"""
        res = self.client.post('/login/citizen', data={
            'username': 'jenish',
            'password': 'jenish123'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        # Check Home
        home_res = self.client.get('/')
        self.assertEqual(home_res.status_code, 200)
        h_html = home_res.data.decode('utf-8')
        self.assertIn('nl-mobile-bottom-nav', h_html)
        self.assertIn('nlMoreDrawer', h_html)
        self.assertIn('/book', h_html)
        self.assertIn('Pickups', h_html)
        self.assertIn('Impact', h_html)

        # Check Booking
        book_res = self.client.get('/book')
        self.assertEqual(book_res.status_code, 200)
        b_html = book_res.data.decode('utf-8')
        self.assertIn('stream-grid-2x2', b_html)
        self.assertIn('nl-mobile-sticky-action', b_html)

        # Check My Pickups
        pick_res = self.client.get('/my-pickups')
        self.assertEqual(pick_res.status_code, 200)

        # Check Impact
        imp_res = self.client.get('/impact')
        self.assertEqual(imp_res.status_code, 200)

        # Check Leaderboard
        board_res = self.client.get('/leaderboard')
        self.assertEqual(board_res.status_code, 200)

        # Check Logout
        logout_res = self.client.get('/logout', follow_redirects=True)
        self.assertEqual(logout_res.status_code, 200)

    def test_03_society_login_and_mobile_navigation(self):
        """Test society manager login renders dedicated society mobile navigation"""
        res = self.client.post('/login/society_manager', data={
            'username': 'society',
            'password': 'society123'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        dash_res = self.client.get('/society/dashboard')
        self.assertEqual(dash_res.status_code, 200)
        d_html = dash_res.data.decode('utf-8')
        self.assertIn('nl-mobile-bottom-nav', d_html)
        self.assertIn('Bulk Book', d_html)
        self.assertIn('nlMoreDrawer', d_html)

        bulk_res = self.client.get('/society/book')
        self.assertEqual(bulk_res.status_code, 200)

        self.client.get('/logout', follow_redirects=True)

    def test_04_driver_login_and_mobile_navigation(self):
        """Test driver login renders high-priority Next Stop and route mobile navigation"""
        res = self.client.post('/login/driver', data={
            'username': 'vikram',
            'password': 'vikram123'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        drv_res = self.client.get('/driver')
        self.assertEqual(drv_res.status_code, 200)
        d_html = drv_res.data.decode('utf-8')
        self.assertIn('nl-mobile-bottom-nav', d_html)
        self.assertIn('Today', d_html)
        self.assertIn('Route', d_html)
        self.assertIn('History', d_html)

        hist_res = self.client.get('/driver/history')
        self.assertEqual(hist_res.status_code, 200)

        self.client.get('/logout', follow_redirects=True)

    def test_05_admin_login_and_mobile_navigation(self):
        """Test admin login renders Command, Dispatch, and full More drawer"""
        res = self.client.post('/login/admin', data={
            'username': 'admin',
            'password': 'admin123'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)

        adm_res = self.client.get('/admin')
        self.assertEqual(adm_res.status_code, 200)
        a_html = adm_res.data.decode('utf-8')
        self.assertIn('nl-mobile-bottom-nav', a_html)
        self.assertIn('Command', a_html)
        self.assertIn('Dispatch', a_html)
        self.assertIn('Alerts', a_html)

        disp_res = self.client.get('/admin/dispatch')
        self.assertEqual(disp_res.status_code, 200)

        soc_res = self.client.get('/admin/societies')
        self.assertEqual(soc_res.status_code, 200)

        rep_res = self.client.get('/admin/reports')
        self.assertEqual(rep_res.status_code, 200)

        self.client.get('/logout', follow_redirects=True)

if __name__ == '__main__':
    unittest.main()
