#!/usr/bin/env python3
"""
Video-Audio Merger Web Service
Standalone Flask app with FFmpeg
"""

from flask import Flask, request, send_file, render_template_string, jsonify
import os
import subprocess
import uuid
from datetime import datetime, timedelta
import threading
import time
from pathlib import Path

app = Flask(__name__)

# Configuration
UPLOAD_FOLDER = '/tmp/uploads'
OUTPUT_FOLDER = '/tmp/output'
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB
CLEANUP_AGE_HOURS = 24

# Create folders
Path(UPLOAD_FOLDER).mkdir(parents=True, exist_ok=True)
Path(OUTPUT_FOLDER).mkdir(parents=True, exist_ok=True)

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Video-Audio Merger</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .container {
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            max-width: 600px;
            width: 100%;
            padding: 40px;
        }
        h1 {
            color: #667eea;
            text-align: center;
            margin-bottom: 10px;
            font-size: 2em;
        }
        .subtitle {
            text-align: center;
            color: #666;
            margin-bottom: 30px;
        }
        .upload-section {
            margin: 20px 0;
        }
        .upload-box {
            border: 3px dashed #667eea;
            border-radius: 10px;
            padding: 30px;
            text-align: center;
            transition: all 0.3s;
            cursor: pointer;
            background: #f8f9ff;
        }
        .upload-box:hover {
            border-color: #764ba2;
            background: #f0f1ff;
        }
        .upload-box.has-file {
            border-color: #28a745;
            background: #e8f5e9;
        }
        .upload-icon {
            font-size: 3em;
            margin-bottom: 10px;
        }
        .upload-label {
            font-weight: bold;
            color: #667eea;
            margin-bottom: 5px;
        }
        .upload-hint {
            color: #999;
            font-size: 0.9em;
        }
        input[type="file"] {
            display: none;
        }
        .file-info {
            margin-top: 10px;
            color: #28a745;
            font-weight: bold;
        }
        .btn {
            width: 100%;
            padding: 15px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 10px;
            font-size: 1.1em;
            font-weight: bold;
            cursor: pointer;
            transition: transform 0.2s;
            margin-top: 20px;
        }
        .btn:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(0,0,0,0.2);
        }
        .btn:disabled {
            background: #ccc;
            cursor: not-allowed;
        }
        .result {
            margin-top: 20px;
            padding: 20px;
            border-radius: 10px;
            display: none;
        }
        .result.success {
            background: #d4edda;
            border: 1px solid #c3e6cb;
            color: #155724;
        }
        .result.error {
            background: #f8d7da;
            border: 1px solid #f5c6cb;
            color: #721c24;
        }
        .result.loading {
            background: #cce5ff;
            border: 1px solid #b8daff;
            color: #004085;
            text-align: center;
        }
        .spinner {
            border: 4px solid #f3f3f3;
            border-top: 4px solid #667eea;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
            margin: 20px auto;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        .download-btn {
            display: inline-block;
            margin-top: 15px;
            padding: 12px 30px;
            background: #28a745;
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-weight: bold;
        }
        .download-btn:hover {
            background: #218838;
        }
        .info-box {
            background: #e7f3ff;
            border-left: 4px solid #667eea;
            padding: 15px;
            margin-top: 20px;
            border-radius: 5px;
        }
        .info-box h3 {
            color: #667eea;
            margin-bottom: 10px;
        }
        .info-box ul {
            list-style: none;
            color: #555;
        }
        .info-box li {
            padding: 5px 0;
            padding-left: 20px;
            position: relative;
        }
        .info-box li:before {
            content: "•";
            position: absolute;
            left: 0;
            color: #667eea;
            font-weight: bold;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎬 Video-Audio Merger</h1>
        <p class="subtitle">Füge Audio zu deinem Video-Loop hinzu</p>
        
        <div id="uploadForm">
            <div class="upload-section">
                <div class="upload-box" id="audioBox" onclick="document.getElementById('audioInput').click()">
                    <div class="upload-icon">🎵</div>
                    <div class="upload-label">Audio-Datei hochladen</div>
                    <div class="upload-hint">MP3, WAV, OGG, FLAC (max 500 MB)</div>
                    <div class="file-info" id="audioInfo"></div>
                    <input type="file" id="audioInput" name="audio" accept="audio/*">
                </div>
            </div>
            
            <div class="upload-section">
                <div class="upload-box" id="videoBox" onclick="document.getElementById('videoInput').click()">
                    <div class="upload-icon">🎥</div>
                    <div class="upload-label">Video-Loop hochladen</div>
                    <div class="upload-hint">MP4, MOV, AVI, WebM (max 500 MB)</div>
                    <div class="file-info" id="videoInfo"></div>
                    <input type="file" id="videoInput" name="video" accept="video/*">
                </div>
            </div>
            
            <button class="btn" id="submitBtn" disabled onclick="handleUpload()">Video erstellen</button>
        </div>
        
        <div id="result" class="result"></div>
        
        <div class="info-box">
            <h3>ℹ️ Hinweise</h3>
            <ul>
                <li>Das Video wird automatisch geloopt bis zur Audio-Länge</li>
                <li>Maximale Dateigröße: 500 MB pro Datei</li>
                <li>Verarbeitung kann 1-5 Minuten dauern</li>
                <li>Dateien werden nach 24h automatisch gelöscht</li>
            </ul>
        </div>
    </div>

    <script>
        const audioInput = document.getElementById('audioInput');
        const videoInput = document.getElementById('videoInput');
        const audioBox = document.getElementById('audioBox');
        const videoBox = document.getElementById('videoBox');
        const audioInfo = document.getElementById('audioInfo');
        const videoInfo = document.getElementById('videoInfo');
        const submitBtn = document.getElementById('submitBtn');
        const resultDiv = document.getElementById('result');
        
        function formatFileSize(bytes) {
            const k = 1024;
            const sizes = ['Bytes', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
        }
        
        function checkForm() {
            submitBtn.disabled = !(audioInput.files.length > 0 && videoInput.files.length > 0);
        }
        
        audioInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                const file = e.target.files[0];
                audioInfo.textContent = `✓ ${file.name} (${formatFileSize(file.size)})`;
                audioBox.classList.add('has-file');
            }
            checkForm();
        });
        
        videoInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                const file = e.target.files[0];
                videoInfo.textContent = `✓ ${file.name} (${formatFileSize(file.size)})`;
                videoBox.classList.add('has-file');
            }
            checkForm();
        });
        
        async function handleUpload() {
            const maxSize = 500 * 1024 * 1024;
            
            if (audioInput.files[0].size > maxSize) {
                showError(`Audio-Datei zu groß: ${formatFileSize(audioInput.files[0].size)} (max 500 MB)`);
                return;
            }
            
            if (videoInput.files[0].size > maxSize) {
                showError(`Video-Datei zu groß: ${formatFileSize(videoInput.files[0].size)} (max 500 MB)`);
                return;
            }
            
            const formData = new FormData();
            formData.append('audio', audioInput.files[0]);
            formData.append('video', videoInput.files[0]);
            
            resultDiv.style.display = 'block';
            resultDiv.className = 'result loading';
            resultDiv.innerHTML = `
                <div class="spinner"></div>
                <div><strong>Video wird erstellt...</strong></div>
                <div style="margin-top: 10px;">Dies kann 1-5 Minuten dauern.</div>
            `;
            
            submitBtn.disabled = true;
            
            try {
                const response = await fetch('/upload', {
                    method: 'POST',
                    body: formData
                });
                
                const result = await response.json();
                
                if (result.success) {
                    resultDiv.className = 'result success';
                    resultDiv.innerHTML = `
                        <div style="text-align: center;">
                            <div style="font-size: 3em; margin-bottom: 10px;">✅</div>
                            <div><strong>Video erfolgreich erstellt!</strong></div>
                            <div style="margin: 10px 0;">
                                Größe: ${result.size}<br>
                                Dauer: ${result.duration}
                            </div>
                            <a href="/download/${result.file_id}" class="download-btn" download>
                                ⬇️ Video herunterladen
                            </a>
                        </div>
                    `;
                } else {
                    showError(result.error || 'Fehler beim Erstellen des Videos');
                }
            } catch (error) {
                showError(error.message);
            } finally {
                submitBtn.disabled = false;
            }
        }
        
        function showError(message) {
            resultDiv.style.display = 'block';
            resultDiv.className = 'result error';
            resultDiv.innerHTML = `
                <div style="text-align: center;">
                    <div style="font-size: 3em; margin-bottom: 10px;">❌</div>
                    <div><strong>Fehler</strong></div>
                    <div style="margin-top: 10px;">${message}</div>
                </div>
            `;
        }
    </script>
</body>
</html>
'''

def get_video_duration(file_path):
    """Get video duration using ffprobe"""
    try:
        result = subprocess.run([
            'ffprobe', '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            file_path
        ], capture_output=True, text=True, timeout=30)
        return float(result.stdout.strip())
    except Exception as e:
        print(f"Error getting duration: {e}")
        return 0

def format_duration(seconds):
    """Format seconds to readable time"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    if hours > 0:
        return f"{hours}h {minutes}min {secs}s"
    elif minutes > 0:
        return f"{minutes}min {secs}s"
    else:
        return f"{secs}s"

def format_size(bytes):
    """Format bytes to readable size"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes < 1024.0:
            return f"{bytes:.2f} {unit}"
        bytes /= 1024.0
    return f"{bytes:.2f} TB"

def merge_video_audio(audio_path, video_path, output_path):
    """Merge video and audio using FFmpeg - Optimized like n8n workflow"""
    try:
        # Get audio duration
        duration = get_video_duration(audio_path)
        print(f"Audio duration: {duration} seconds")
        
        # Get video duration
        video_duration = get_video_duration(video_path)
        print(f"Video duration: {video_duration} seconds")
        
        # Calculate loop count
        loop_count = int(duration / video_duration) + 1
        print(f"Loop count needed: {loop_count}")
        
        # Step 1: Create looped video (like your n8n workflow)
        temp_looped_video = os.path.join(UPLOAD_FOLDER, f"temp_looped_{os.path.basename(output_path)}")
        
        print("Step 1: Creating looped video...")
        cmd_loop = [
            'ffmpeg', '-y',
            '-stream_loop', str(loop_count - 1),
            '-i', video_path,
            '-t', str(duration),
            '-c:v', 'libx264',
            '-preset', 'medium',
            '-crf', '32',  # Höhere CRF = kleinere Datei (dein n8n nutzt 32)
            '-profile:v', 'high',
            '-level', '4.2',
            '-pix_fmt', 'yuv420p',
            '-maxrate', '5M',
            '-bufsize', '10M',
            '-g', '250',
            '-movflags', '+faststart',
            '-an',  # Kein Audio im ersten Schritt
            temp_looped_video
        ]
        
        print(f"Running: {' '.join(cmd_loop)}")
        result_loop = subprocess.run(
            cmd_loop,
            capture_output=True,
            text=True,
            timeout=3600
        )
        
        if result_loop.returncode != 0:
            print(f"FFmpeg loop stderr: {result_loop.stderr}")
            raise Exception(f"FFmpeg loop error: {result_loop.stderr}")
        
        print(f"Looped video created: {os.path.getsize(temp_looped_video)} bytes")
        
        # Step 2: Merge looped video with audio (like your n8n workflow)
        print("Step 2: Merging audio with looped video...")
        cmd_merge = [
            'ffmpeg', '-y',
            '-i', temp_looped_video,
            '-i', audio_path,
            '-c:v', 'copy',  # Video copy - kein Re-Encoding
            '-c:a', 'aac',
            '-b:a', '96k',  # Niedrigere Audio-Bitrate = kleinere Datei
            '-ar', '44100',
            '-map', '0:v:0',
            '-map', '1:a:0',
            '-shortest',
            '-movflags', '+faststart',
            output_path
        ]
        
        print(f"Running: {' '.join(cmd_merge)}")
        result_merge = subprocess.run(
            cmd_merge,
            capture_output=True,
            text=True,
            timeout=1800
        )
        
        if result_merge.returncode != 0:
            print(f"FFmpeg merge stderr: {result_merge.stderr}")
            # Cleanup temp file
            if os.path.exists(temp_looped_video):
                os.remove(temp_looped_video)
            raise Exception(f"FFmpeg merge error: {result_merge.stderr}")
        
        # Cleanup temp looped video
        if os.path.exists(temp_looped_video):
            os.remove(temp_looped_video)
            print("Cleaned up temporary looped video")
        
        print(f"FFmpeg completed successfully - Final size: {os.path.getsize(output_path)} bytes")
        return True
        
    except subprocess.TimeoutExpired:
        print("FFmpeg timeout - process took too long")
        # Cleanup on timeout
        if 'temp_looped_video' in locals() and os.path.exists(temp_looped_video):
            os.remove(temp_looped_video)
        raise Exception("Video processing timeout - file too large")
    except Exception as e:
        print(f"Merge error: {e}")
        # Cleanup on error
        if 'temp_looped_video' in locals() and os.path.exists(temp_looped_video):
            try:
                os.remove(temp_looped_video)
            except:
                pass
        raise

def cleanup_old_files():
    """Clean up files older than CLEANUP_AGE_HOURS"""
    while True:
        try:
            now = datetime.now()
            cutoff = now - timedelta(hours=CLEANUP_AGE_HOURS)
            
            for folder in [UPLOAD_FOLDER, OUTPUT_FOLDER]:
                for file_path in Path(folder).glob('*'):
                    if file_path.is_file():
                        file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                        if file_time < cutoff:
                            file_path.unlink()
                            print(f"Deleted old file: {file_path}")
        except Exception as e:
            print(f"Cleanup error: {e}")
        
        # Run every hour
        time.sleep(3600)

@app.route('/')
def index():
    """Show upload form"""
    return render_template_string(HTML_TEMPLATE)

@app.route('/upload', methods=['POST'])
def upload():
    """Handle file upload and merging"""
    audio_path = None
    video_path = None
    
    try:
        print("=== UPLOAD START ===")
        
        # Check files
        if 'audio' not in request.files or 'video' not in request.files:
            print("ERROR: Missing files in request")
            return jsonify({'success': False, 'error': 'Audio und Video benötigt'}), 400
        
        audio_file = request.files['audio']
        video_file = request.files['video']
        
        print(f"Audio file: {audio_file.filename}")
        print(f"Video file: {video_file.filename}")
        
        if audio_file.filename == '' or video_file.filename == '':
            print("ERROR: Empty filenames")
            return jsonify({'success': False, 'error': 'Leere Dateien'}), 400
        
        # Generate unique ID
        file_id = str(uuid.uuid4())
        print(f"Generated file_id: {file_id}")
        
        # Save uploaded files
        audio_ext = os.path.splitext(audio_file.filename)[1] or '.mp3'
        video_ext = os.path.splitext(video_file.filename)[1] or '.mp4'
        
        audio_path = os.path.join(UPLOAD_FOLDER, f"{file_id}_audio{audio_ext}")
        video_path = os.path.join(UPLOAD_FOLDER, f"{file_id}_video{video_ext}")
        output_path = os.path.join(OUTPUT_FOLDER, f"{file_id}.mp4")
        
        print(f"Saving audio to: {audio_path}")
        audio_file.save(audio_path)
        print(f"Audio saved: {os.path.getsize(audio_path)} bytes")
        
        print(f"Saving video to: {video_path}")
        video_file.save(video_path)
        print(f"Video saved: {os.path.getsize(video_path)} bytes")
        
        # Merge files
        print("Starting merge...")
        merge_video_audio(audio_path, video_path, output_path)
        print(f"Merge complete: {output_path}")
        
        # Get file info
        file_size = os.path.getsize(output_path)
        print(f"Output file size: {file_size} bytes")
        
        duration = get_video_duration(output_path)
        print(f"Output duration: {duration} seconds")
        
        # Clean up input files
        print("Cleaning up input files...")
        if os.path.exists(audio_path):
            os.remove(audio_path)
        if os.path.exists(video_path):
            os.remove(video_path)
        
        print("=== UPLOAD SUCCESS ===")
        return jsonify({
            'success': True,
            'file_id': file_id,
            'size': format_size(file_size),
            'duration': format_duration(duration)
        })
        
    except Exception as e:
        print(f"=== UPLOAD ERROR ===")
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {str(e)}")
        import traceback
        print(f"Traceback:\n{traceback.format_exc()}")
        
        # Cleanup on error
        try:
            if audio_path and os.path.exists(audio_path):
                os.remove(audio_path)
            if video_path and os.path.exists(video_path):
                os.remove(video_path)
        except:
            pass
        
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/download/<file_id>')
def download(file_id):
    """Download merged video"""
    try:
        file_path = os.path.join(OUTPUT_FOLDER, f"{file_id}.mp4")
        
        if not os.path.exists(file_path):
            return "File not found or expired", 404
        
        return send_file(
            file_path,
            mimetype='video/mp4',
            as_attachment=True,
            download_name=f'merged_video_{file_id}.mp4'
        )
    except Exception as e:
        print(f"Download error: {e}")
        return "Error downloading file", 500

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'service': 'video-audio-merger'})

if __name__ == '__main__':
    # Start cleanup thread
    cleanup_thread = threading.Thread(target=cleanup_old_files, daemon=True)
    cleanup_thread.start()
    
    # Start Flask app
    app.run(host='0.0.0.0', port=5000, debug=False)
