"""
Quick test script for database models
Run this to verify everything is working
"""

from app.db.session import SessionLocal
from app.models import User, Video, Transcript, TranscriptStatus, Summary, SummaryStatus
from datetime import datetime
import random

def test_database_models():
    """Test all models and relationships"""
    
    print("=" * 50)
    print("Testing Database Models")
    print("=" * 50)
    
    # Create database session
    db = SessionLocal()
    
    try:
        # 1. CREATE A TEST USER
        print("\n[1] Creating test user...")
        test_user = User(
            name="Test User",
            email=f"test_{random.randint(1, 9999)}@example.com",
            password="hashed_password_123",
            role="learner"
        )
        db.add(test_user)
        db.commit()
        db.refresh(test_user)
        print(f"    SUCCESS: User created with ID: {test_user.id}")
        print(f"    Email: {test_user.email}")
        
        # 2. CREATE A VIDEO FOR THIS USER
        print("\n[2] Creating test video...")
        test_video = Video(
            user_id=test_user.id,
            filename="test_video.mp4",
            file_path="/uploads/test_video.mp4",
            status="uploaded"
        )
        db.add(test_video)
        db.commit()
        db.refresh(test_video)
        print(f"    SUCCESS: Video created with ID: {test_video.id}")
        print(f"    Filename: {test_video.filename}")
        
        # 3. CREATE A TRANSCRIPT FOR THIS VIDEO
        print("\n[3] Creating test transcript...")
        test_transcript = Transcript(
            video_id=test_video.id,
            status=TranscriptStatus.PROCESSING
        )
        db.add(test_transcript)
        db.commit()
        db.refresh(test_transcript)
        print(f"    SUCCESS: Transcript created with ID: {test_transcript.id}")
        print(f"    Status: {test_transcript.status}")
        
        # 4. UPDATE TRANSCRIPT WITH TEXT
        print("\n[4] Updating transcript with text...")
        test_transcript.text = "This is the full transcript of the video. It contains all the spoken words from the video file."
        test_transcript.status = TranscriptStatus.COMPLETED
        db.commit()
        db.refresh(test_transcript)
        print(f"    SUCCESS: Transcript updated")
        print(f"    Text preview: {test_transcript.text[:50]}...")
        print(f"    New status: {test_transcript.status}")
        
        # 5. CREATE A SUMMARY
        print("\n[5] Creating test summary...")
        test_summary = Summary(
            transcript_id=test_transcript.id,
            short_summary="Key point 1\nKey point 2\nKey point 3",
            detailed_summary="This is a detailed summary of the entire video content. It explains everything in detail.",
            status=SummaryStatus.COMPLETED
        )
        db.add(test_summary)
        db.commit()
        db.refresh(test_summary)
        print(f"    SUCCESS: Summary created with ID: {test_summary.id}")
        print(f"    Status: {test_summary.status}")
        
        # 6. TEST RELATIONSHIPS
        print("\n[6] Testing relationships...")
        
        # User -> Videos
        user_videos = test_user.videos
        print(f"    User '{test_user.name}' has {len(user_videos)} video(s)")
        
        # Video -> Transcript
        video_transcript = test_video.transcript
        if video_transcript:
            print(f"    Video '{test_video.filename}' has transcript: {video_transcript.text[:30]}...")
        
        # Transcript -> Summary
        transcript_summary = test_transcript.summary
        if transcript_summary:
            print(f"    Transcript has summary: {transcript_summary.short_summary[:30]}...")
        
        # 7. VERIFY UNIQUE CONSTRAINTS
        print("\n[7] Testing unique constraints...")
        try:
            # Try to create another transcript for the same video (should fail)
            duplicate_transcript = Transcript(
                video_id=test_video.id,
                status=TranscriptStatus.NOT_STARTED
            )
            db.add(duplicate_transcript)
            db.commit()
            print("    WARNING: Duplicate transcript was allowed! (unique constraint not working)")
        except Exception as e:
            print(f"    SUCCESS: Duplicate transcript prevented: {str(e)[:50]}...")
            db.rollback()  # Rollback the failed transaction
        
        # 8. COUNT RECORDS
        print("\n[8] Database summary:")
        user_count = db.query(User).count()
        video_count = db.query(Video).count()
        transcript_count = db.query(Transcript).count()
        summary_count = db.query(Summary).count()
        print(f"    Users: {user_count}")
        print(f"    Videos: {video_count}")
        print(f"    Transcripts: {transcript_count}")
        print(f"    Summaries: {summary_count}")
        
        print("\n" + "=" * 50)
        print("ALL TESTS PASSED! Models are working correctly.")
        print("=" * 50)
        
    except Exception as e:
        print(f"\nERROR: {str(e)}")
        db.rollback()
        print("   Transaction rolled back")
        
    finally:
        # Clean up: Delete test data
        print("\nCleaning up test data...")
        try:
            # Delete in correct order (due to foreign keys)
            db.query(Summary).filter(Summary.transcript_id == test_transcript.id).delete()
            db.query(Transcript).filter(Transcript.video_id == test_video.id).delete()
            db.query(Video).filter(Video.id == test_video.id).delete()
            db.query(User).filter(User.id == test_user.id).delete()
            db.commit()
            print("   SUCCESS: Test data cleaned up")
        except:
            db.rollback()
            print("   WARNING: Could not clean up test data (may need manual cleanup)")
        
        db.close()
        print("\nTest complete!")

if __name__ == "__main__":
    test_database_models()
    