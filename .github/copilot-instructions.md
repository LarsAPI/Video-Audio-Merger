# AI Coding Agent Instructions

## Project Overview
**Video-Audio Merger** is a Flask web service that combines audio files with video loops or static images using FFmpeg. The application features two distinct processing modes, video effects, and asynchronous job-based processing with real-time status tracking.

## Architecture & Key Patterns

### Core Processing Model
The app uses **job-based asynchronous processing**:
1. User uploads files via `/upload` endpoint → generates unique `file_id` (UUID)
2. Files saved to `/tmp/uploads` (cleanup after 24h)
3. Background thread spawned via `threading.Thread(daemon=True)` processes the merge
4. Status updates written to JSON file: `/tmp/output/{file_id}_status.json`
5. Frontend polls `/status/{job_id}` every 5 seconds for progress
6. Final output saved to `/tmp/output/{file_id}.mp4`

### Two Processing Modes

**Video Mode** (default):
- Accepts multiple video files → randomly shuffled into sequence
- Uses FFmpeg concat demuxer with list file `/tmp/uploads/concat_*.txt`
- Videos looped to match audio duration via clip sequence generation
- Function: `merge_video_audio()` [lines 920-1050]

**Image Mode** (toggle via UI):
- Single static image → extended to audio duration using `-loop 1 -t <duration>`
- Function: `merge_video_audio_from_image()` [lines 748-827]

### Video Effects System
Effects applied as FFmpeg `-vf` filters during concatenation/looping phase (before audio merge):
- Defined in `VIDEO_EFFECTS` dict (lines 33-40)
- Examples: `noise`, `vignette`, `hue`, `zoompan`, `gblur`, `eq`, `colorbalance`
- Applied to **both modes** (videos and images)
- Effect parameter always sanitized via `if effect in VIDEO_EFFECTS` checks

### FFmpeg Command Structure
Two-step pipeline for **both modes**:
1. **Encoding Phase**: Concatenate/loop videos OR create video from image, apply effects, encode H.264 video-only
   - Output: temporary video file (no audio)
   - Preset: `veryfast` with CRF 35 (lower quality/faster)
   - Profile: high/4.2 for compatibility
2. **Audio Merge Phase**: Copy video stream, merge AAC audio, use `-shortest` to trim to audio length
   - Output: final MP4 with both streams

**Key FFmpeg params** (consistent across modes):
- `-c:v libx264` (H.264), `-c:a aac` (audio codec)
- `-movflags +faststart` (enable streaming)
- `-maxrate 4M -bufsize 8M -g 250` (bitrate control)
- Timeouts: 7200s for encoding, 1800s for merge

## Critical Developer Workflows

### Local Development
```bash
# Without Docker
pip install flask gunicorn  # Required
# Requires system: ffmpeg, ffprobe
python app.py  # Runs on http://localhost:5000

# With Docker
docker-compose up  # Builds and runs on http://localhost:5001
```

### Adding New Video Effects
1. Add filter to `VIDEO_EFFECTS` dict (line 33): `'effect_name': 'ffmpeg_filter_string'`
2. Add UI option in HTML select (line 262)
3. Test with both modes using real files

### Status Tracking Flow
- Status file schema: `{status, progress, message, file_id, mode, effect, [video_count], timestamp}`
- Status values: `'processing'`, `'complete'`, `'error'`
- Cleanup: status files NOT auto-deleted (only uploaded source files deleted after 24h)

## File Organization
```
app.py                    # Monolithic Flask app (1268 lines)
Dockerfile                # Python 3.11 + FFmpeg
docker-compose.yml        # Umbrel-compatible setup (2GB mem limit)
```

No separate models, views, or config files—single-file architecture.

## Important Implementation Details

### Temporary File Cleanup
- **Upload sources** (`/tmp/uploads`) deleted automatically:
  - After successful merge (in `process_video_background()`)
  - On upload error (cleanup in exception handler)
  - On processing error (cleanup in background exception handler)
- **Status files** (`/tmp/output/*_status.json`) persisted for browser polling
- **Cleanup daemon** removes both folders' files older than 24h (every hour)

### Error Handling
- Subprocess errors logged with last 500 chars of stderr
- FFmpeg timeout (7200s) caught and reported as user-friendly error
- Partial cleanup on errors (removes temp files but not output)
- Missing files return 404 (download/status endpoints)

### Performance Considerations
- Gunicorn with **2 workers**, **600s timeout** (10 min) for long FFmpeg operations
- Expected times: videos ~20-30 min, images ~5-10 min (CRF 35)
- No streaming response; outputs complete MP4 only after full encoding
- Memory: 2GB limit in docker-compose (can hit on large 4K videos)

### Browser/Frontend Integration
- Single-page app with vanilla JavaScript
- File size validation client-side (500MB audio/video, 50MB image)
- Progress polling: `/status/{jobId}` every 5 seconds
- Download: `/download/{file_id}` triggers browser download

## Common Modification Points
- **Add file format support**: Update `accept` attributes in file inputs (lines 201, 208)
- **Change default effect**: Modify `effectSelect` option selected state
- **Adjust timeouts**: Update subprocess `timeout` parameter (currently 7200s encoding, 1800s merge)
- **Modify cleanup schedule**: Change `time.sleep(3600)` in `cleanup_old_files()` (line 1013)
- **Support environment variables**: Parse from `os.environ` (currently hardcoded in config lines 24-27)

## Testing Checklist
When modifying core logic:
1. ✓ Video mode: Test with 1, 2, and 3+ video files
2. ✓ Image mode: Verify static image extends to full audio duration
3. ✓ Effects: Test with both modes
4. ✓ Status polling: Confirm progress updates every 5s
5. ✓ File cleanup: Verify uploaded files deleted, status files persist post-completion
6. ✓ Error cases: Missing files, oversized uploads, FFmpeg failures
