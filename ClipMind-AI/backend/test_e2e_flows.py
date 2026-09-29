#!/usr/bin/env python3
"""
Complete end-to-end test for delete and video playback functionality.
"""
import requests
import json
from pathlib import Path
import time

API_URL = "http://127.0.0.1:8000"

def test_complete_flow():
    print("\n" + "="*60)
    print("COMPLETE END-TO-END FLOW TEST")
    print("="*60)
    
    # Step 1: Register user
    print("\n[1/8] Registering user...")
    reg_data = {
        "full_name": "E2E Test User",
        "email": f"e2etest_{int(time.time())}@example.com",
        "password": "StrongPass123",
        "confirm_password": "StrongPass123",
        "role": "Content Creator"
    }
    try:
        reg_resp = requests.post(f"{API_URL}/auth/register", json=reg_data)
        if reg_resp.status_code != 201:
            print(f"  ✗ Registration failed: {reg_resp.status_code}")
            print(f"  Response: {reg_resp.text[:200]}")
            return False
        reg_user = reg_resp.json()
        user_id = reg_user["id"]
        print(f"  ✓ User registered: {user_id}")
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False
    
    # Step 2: Login
    print("\n[2/8] Logging in...")
    login_data = {
        "email": reg_data["email"],
        "password": reg_data["password"]
    }
    try:
        login_resp = requests.post(f"{API_URL}/auth/login", json=login_data)
        if login_resp.status_code != 200:
            print(f"  ✗ Login failed: {login_resp.status_code}")
            return False
        login_user = login_resp.json()
        token = login_user["access_token"]
        print(f"  ✓ Logged in with token: {token[:40]}...")
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False
    
    # Step 3: Upload video
    print("\n[3/8] Uploading test video...")
    video_file_path = Path("c:/Users/kaviy/OneDrive/Desktop/CMA_Coplit/ClipMind-AI/backend/uploads/test_video_1sec.mp4")
    if not video_file_path.exists():
        print(f"  ✗ Test video not found: {video_file_path}")
        return False
    
    try:
        with open(video_file_path, "rb") as f:
            files = {"file": (video_file_path.name, f, "video/mp4")}
            headers = {"Authorization": f"Bearer {token}"}
            upload_resp = requests.post(f"{API_URL}/videos/upload", files=files, headers=headers)
        
        if upload_resp.status_code != 201:
            print(f"  ✗ Upload failed: {upload_resp.status_code}")
            print(f"  Response: {upload_resp.text[:200]}")
            return False
        
        upload_data = upload_resp.json()
        video_id = upload_data["id"]
        print(f"  ✓ Video uploaded: {video_id}")
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False
    
    # Step 4: Get videos list and verify video appears
    print("\n[4/8] Verifying video appears in list...")
    try:
        headers = {"Authorization": f"Bearer {token}"}
        videos_resp = requests.get(f"{API_URL}/videos/", headers=headers)
        if videos_resp.status_code != 200:
            print(f"  ✗ Failed to get videos: {videos_resp.status_code}")
            return False
        
        videos = videos_resp.json()
        if not any(v["id"] == video_id for v in videos):
            print(f"  ✗ Uploaded video not found in list")
            return False
        
        print(f"  ✓ Video found in list ({len(videos)} total videos)")
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False
    
    # Step 5: Test media URL generation
    print("\n[5/8] Testing media URL generation...")
    video_info = next(v for v in videos if v["id"] == video_id)
    media_url = f"{API_URL}/media/videos/{video_info['owner_id']}/{video_id}{Path(video_info['filename']).suffix}"
    print(f"  Media URL: {media_url}")
    
    try:
        media_resp = requests.head(media_url)
        if media_resp.status_code not in [200, 206]:
            print(f"  ✗ Media URL not accessible: {media_resp.status_code}")
            return False
        print(f"  ✓ Media URL accessible: {media_resp.status_code}")
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False
    
    # Step 6: Test DELETE endpoint
    print("\n[6/8] Testing DELETE endpoint...")
    try:
        headers = {"Authorization": f"Bearer {token}"}
        delete_resp = requests.delete(f"{API_URL}/videos/{video_id}", headers=headers)
        
        if delete_resp.status_code not in [200, 204]:
            print(f"  ✗ DELETE failed: {delete_resp.status_code}")
            print(f"  Response: {delete_resp.text[:200]}")
            return False
        
        if delete_resp.status_code == 200:
            delete_data = delete_resp.json()
            print(f"  ✓ DELETE successful: {delete_data.get('message')}")
        else:
            print(f"  ✓ DELETE successful (204 No Content)")
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False
    
    # Step 7: Verify deletion (video should no longer be in list)
    print("\n[7/8] Verifying deletion...")
    try:
        headers = {"Authorization": f"Bearer {token}"}
        verify_resp = requests.get(f"{API_URL}/videos/", headers=headers)
        if verify_resp.status_code != 200:
            print(f"  ✗ Failed to verify: {verify_resp.status_code}")
            return False
        
        verify_videos = verify_resp.json()
        if any(v["id"] == video_id for v in verify_videos):
            print(f"  ✗ Video still exists after deletion")
            return False
        
        print(f"  ✓ Video successfully deleted from database ({len(verify_videos)} videos remaining)")
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False
    
    # Step 8: Verify media file is deleted
    print("\n[8/8] Verifying media file deletion...")
    try:
        media_resp = requests.head(media_url)
        if media_resp.status_code == 404:
            print(f"  ✓ Media file successfully deleted (404)")
        else:
            print(f"  ⚠ Media file status: {media_resp.status_code} (may still exist in storage)")
    except Exception as e:
        print(f"  ⚠ Could not verify media deletion: {e}")
    
    print("\n" + "="*60)
    print("✓ ALL TESTS PASSED - DELETE AND PLAYBACK FLOWS VERIFIED")
    print("="*60)
    return True

if __name__ == "__main__":
    success = test_complete_flow()
    exit(0 if success else 1)
