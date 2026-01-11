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
    """Merge video and audio using FFmpeg"""
    try:
        # Get audio duration
        duration = get_video_duration(audio_path)
        
        # FFmpeg command
        cmd = [
            'ffmpeg', '-y',
            '-stream_loop', '-1', '-i', video_path,
            '-i', audio_path,
            '-t', str(duration),
            '-c:v', 'libx264', '-preset', 'medium', '-crf', '23',
            '-c:a', 'aac', '-b:a', '192k',
            '-pix_fmt', 'yuv420p',
            '-movflags', '+faststart',
            '-shortest',
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        
        if result.returncode != 0:
            raise Exception(f"FFmpeg error: {result.stderr}")
        
        return True
    except Exception as e:
        print(f"Merge error: {e}")
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
    try:
        # Check files
        if 'audio' not in request.files or 'video' not in request.files:
            return jsonify({'success': False, 'error': 'Audio und Video benötigt'}), 400
        
        audio_file = request.files['audio']
        video_file = request.files['video']
        
        if audio_file.filename == '' or video_file.filename == '':
            return jsonify({'success': False, 'error': 'Leere Dateien'}), 400
        
        # Generate unique ID
        file_id = str(uuid.uuid4())
        
        # Save uploaded files
        audio_ext = os.path.splitext(audio_file.filename)[1]
        video_ext = os.path.splitext(video_file.filename)[1]
        
        audio_path = os.path.join(UPLOAD_FOLDER, f"{file_id}_audio{audio_ext}")
        video_path = os.path.join(UPLOAD_FOLDER, f"{file_id}_video{video_ext}")
        output_path = os.path.join(OUTPUT_FOLDER, f"{file_id}.mp4")
        
        audio_file.save(audio_path)
        video_file.save(video_path)
        
        # Merge files
        merge_video_audio(audio_path, video_path, output_path)
        
        # Get file info
        file_size = os.path.getsize(output_path)
        duration = get_video_duration(output_path)
        
        # Clean up input files
        os.remove(audio_path)
        os.remove(video_path)
        
        return jsonify({
            'success': True,
            'file_id': file_id,
            'size': format_size(file_size),
            'duration': format_duration(duration)
        })
        
    except Exception as e:
        print(f"Upload error: {e}")
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
