import requests

BASE_URL = "http://localhost:8000"

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
    resp = session.post(f"{BASE_URL}/user/leave", data={
        "date_str": leave_date,
        "start_time": "09:00",
        "end_time": "10:00"
    })
    print(f"Response: {resp.status_code} {resp.json()}")

if __name__ == "__main__":
    test_flow()
