from app.services.ffmpeg_service import process_video


def main() -> int:
    input_video = "test_input.mp4"
    output_video = "test_output.mp4"

    success = process_video(input_video, output_video)
    print("Video processing successful!" if success else "Video processing failed!")
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())