from backend.app.services.ffmpeg_service import process_video


input_video = "test_input.mp4"
output_video = "test_output.mp4"

success = process_video(input_video, output_video)

if success:
    print("Video processing successful!")
else:
    print("Video processing failed!")