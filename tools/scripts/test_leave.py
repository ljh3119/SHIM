import sys
try:
    import requests
except ImportError:
    print("[ERROR] 'requests' package is required to run this integration test.")
    print("Please install development dependencies using: pip install -r requirements-dev.txt")
    sys.exit(1)


import os
BASE_URL = os.getenv("SHIM_BASE_URL", "http://localhost:9090")

def test_flow():
    session = requests.Session()
    
    # 1. Login
    print("Logging in...")
    resp = session.post(f"{BASE_URL}/login", data={"user_id": "admin", "password": "0000"}, allow_redirects=False)
    if resp.status_code != 302:
        print(f"Login failed: {resp.status_code} {resp.text}")
        return
    print("Login successful.")

    # 2. Apply for leave (as admin, which is allowed but usually admin is redirected to /admin/dashboard)
    # However, admin can still call /user/leave if authenticated.
    print("Applying for leave...")
    # Today is 2026-05-12 (Tuesday)
    leave_date = "2026-05-13" # Wednesday
    resp = session.post(f"{BASE_URL}/api/user/leave", data={
        "date_str": leave_date,
        "start_time": "09:00",
        "end_time": "10:00"
    })
    print(f"Response: {resp.status_code} {resp.json()}")

if __name__ == "__main__":
    test_flow()
