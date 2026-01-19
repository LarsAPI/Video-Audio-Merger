#!/usr/bin/env python3
"""
Video-Audio Merger Web Service
Standalone Flask app with FFmpeg
"""

from flask import Flask, request, send_file, render_template_string, jsonify
import os
import subprocess
import uuid
import json
import random
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

# Video effects mapping
VIDEO_EFFECTS = {
    'none': None,
    'staub': 'noise=alls=20:allf=t+u',
    'vignette': 'vignette=PI/5',
    'psychedelic': 'hue=s=1.2:h=10*sin(t*0.1)',
    'zoom': 'zoompan=z=\'zoom+0.001\':d=250',
    'glitch': 'gblur=sigma=2:steps=1',
    'noir': 'eq=brightness=-0.1:contrast=1.2',
    'warm': 'colorbalance=rs=0.1:gs=-0.05:bs=-0.1'
}

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
        .mode-selector {
            display: flex;
            gap: 10px;
            margin-bottom: 30px;
            background: #f0f1ff;
            padding: 10px;
            border-radius: 10px;
        }
        .mode-btn {
            flex: 1;
            padding: 15px;
            border: 2px solid #667eea;
            background: white;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.3s;
            font-weight: bold;
            color: #667eea;
        }
        .mode-btn:hover {
            background: #f8f9ff;
        }
        .mode-btn.active {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-color: #764ba2;
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
        <p class="subtitle">Füge Audio zu deinem Video-Loop oder Standbild hinzu</p>
        
        <div id="uploadForm">
            <div class="mode-selector">
                <button type="button" class="mode-btn active" id="videoModeBtn" onclick="switchMode('video')">
                    🎥 Video-Loops
                </button>
                <button type="button" class="mode-btn" id="imageModeBtn" onclick="switchMode('image')">
                    🖼️ Standbild
                </button>
            </div>
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
                    <div class="upload-label">Video-Loops hochladen</div>
                    <div class="upload-hint">MP4, MOV, AVI, WebM (max 500 MB pro Datei)</div>
                    <div class="upload-hint" style="margin-top: 5px; font-weight: bold; color: #667eea;">
                        📹 Mehrere Videos = Zufällige Abwechslung!
                    </div>
                    <div class="file-info" id="videoInfo"></div>
                    <input type="file" id="videoInput" name="video" accept="video/*" multiple>
                </div>
            </div>
            
            <div class="upload-section">
                <label style="display: block; font-weight: bold; color: #667eea; margin-bottom: 10px;">
                    ✨ Video-Effekt (Optional)
                </label>
                <select id="effectSelect" style="width: 100%; padding: 12px; border: 2px solid #667eea; border-radius: 8px; font-size: 1em; background: white; cursor: pointer;">
                    <option value="none">Kein Effekt</option>
                    <option value="staub">🌫️ Staub / Film Grain</option>
                    <option value="vignette">🎬 Vignette (Dunkle Ränder)</option>
                    <option value="psychedelic">🌈 Psychedelisch</option>
                    <option value="zoom">🔍 Langsamer Zoom</option>
                    <option value="glitch">⚡ Glitch / Blur</option>
                    <option value="noir">🖤 Noir / Film</option>
                    <option value="warm">🔥 Warm / Vintage</option>
                </select>
                <div style="margin-top: 8px; font-size: 0.85em; color: #666;">
                    Der Effekt wird über das gesamte Video gelegt
                </div>
            </div>
            
            <button class="btn" id="submitBtn" disabled onclick="handleUpload()">Video erstellen</button>
        </div>
        
        <div id="result" class="result"></div>
        
        <div class="info-box">
            <h3>ℹ️ Hinweise</h3>
            <ul>
                <li>Das Video wird automatisch geloopt bis zur Audio-Länge</li>
                <li>🎲 <strong>Mehrere Videos:</strong> Werden zufällig gemischt für mehr Abwechslung!</li>
                <li>Maximale Dateigröße: 500 MB pro Datei</li>
                <li>Verarbeitung kann 20-30 Minuten dauern (je nach Audio-Länge)</li>
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
                const fileCount = e.target.files.length;
                const totalSize = Array.from(e.target.files).reduce((sum, file) => sum + file.size, 0);
                const fileNames = Array.from(e.target.files).map(f => f.name).join(', ');
                
                videoInfo.innerHTML = `
                    ✓ ${fileCount} Video${fileCount > 1 ? 's' : ''} ausgewählt<br>
                    <small style="color: #666;">${formatFileSize(totalSize)} gesamt</small><br>
                    <small style="color: #666; display: block; margin-top: 3px;">${fileNames}</small>
                `;
                videoBox.classList.add('has-file');
            }
            checkForm();
        });
        
        async function handleUpload() {
            const maxSize = 500 * 1024 * 1024;
            const maxImageSize = 50 * 1024 * 1024;
            
            if (audioInput.files[0].size > maxSize) {
                showError(`Audio-Datei zu groß: ${formatFileSize(audioInput.files[0].size)} (max 500 MB)`);
                return;
            }
            
            const formData = new FormData();
            formData.append('audio', audioInput.files[0]);
            formData.append('mode', currentMode);
            
            let uploadDescription = '';
            
            if (currentMode === 'video') {
                // Video mode - check all videos
                for (let i = 0; i < videoInput.files.length; i++) {
                    if (videoInput.files[i].size > maxSize) {
                        showError(`Video ${i+1} zu groß: ${formatFileSize(videoInput.files[i].size)} (max 500 MB)`);
                        return;
                    }
                }
                
                // Append all video files
                for (let i = 0; i < videoInput.files.length; i++) {
                    formData.append('videos', videoInput.files[i]);
                }
                
                uploadDescription = `1 Audio + ${videoInput.files.length} Video${videoInput.files.length > 1 ? 's' : ''}`;
            } else {
                // Image mode - check image
                if (imageInput.files[0].size > maxImageSize) {
                    showError(`Bild zu groß: ${formatFileSize(imageInput.files[0].size)} (max 50 MB)`);
                    return;
                }
                
                formData.append('image', imageInput.files[0]);
                uploadDescription = `1 Audio + 1 Standbild`;
            }
            
            // Append selected effect
            const selectedEffect = document.getElementById('effectSelect').value;
            formData.append('effect', selectedEffect);
            
            resultDiv.style.display = 'block';
            resultDiv.className = 'result loading';
            
            const effectText = selectedEffect !== 'none' ? ` + ${selectedEffect} Effekt` : '';
            
            resultDiv.innerHTML = `
                <div class="spinner"></div>
                <div><strong>Dateien werden hochgeladen...</strong></div>
                <div style="margin-top: 10px;">
                    ${uploadDescription}${effectText}
                </div>
            `;
            
            submitBtn.disabled = true;
            
            try {
                // Upload files
                const response = await fetch('/upload', {
                    method: 'POST',
                    body: formData
                });
                
                const result = await response.json();
                
                if (!result.success) {
                    showError(result.error || 'Upload fehlgeschlagen');
                    return;
                }
                
                // Start status polling
                const jobId = result.job_id;
                console.log('Job ID:', jobId);
                
                let modeInfo = '';
                if (result.mode === 'image') {
                    modeInfo = '<div style="margin-top: 5px; color: #667eea; font-weight: bold;">🖼️ Standbild-Modus</div>';
                } else if (result.video_count) {
                    modeInfo = `<div style="margin-top: 5px; color: #667eea; font-weight: bold;">${result.video_count} Videos werden zufällig gemischt!</div>`;
                }
                
                const effectInfo = result.effect && result.effect !== 'none' 
                    ? `<div style="margin-top: 5px; color: #764ba2;">✨ Effekt: ${result.effect}</div>` 
                    : '';
                
                resultDiv.innerHTML = `
                    <div class="spinner"></div>
                    <div><strong>Upload erfolgreich!</strong></div>
                    ${modeInfo}
                    ${effectInfo}
                    <div id="statusMessage" style="margin-top: 10px;">Verarbeitung startet...</div>
                    <div style="margin-top: 15px; background: #e0e0e0; border-radius: 10px; height: 20px; overflow: hidden;">
                        <div id="progressBar" style="background: linear-gradient(90deg, #667eea, #764ba2); height: 100%; width: 0%; transition: width 0.3s;"></div>
                    </div>
                    <div id="progressText" style="margin-top: 5px; font-size: 0.9em; color: #666;">0%</div>
                `;
                
                // Poll status every 5 seconds
                const pollInterval = setInterval(async () => {
                    try {
                        const statusResponse = await fetch(`/status/${jobId}`);
                        const statusData = await statusResponse.json();
                        
                        if (!statusData.success) {
                            clearInterval(pollInterval);
                            showError('Fehler beim Abrufen des Status');
                            return;
                        }
                        
                        // Update UI
                        const statusMsg = document.getElementById('statusMessage');
                        const progressBar = document.getElementById('progressBar');
                        const progressText = document.getElementById('progressText');
                        
                        if (statusMsg) statusMsg.textContent = statusData.message;
                        if (progressBar) progressBar.style.width = statusData.progress + '%';
                        if (progressText) progressText.textContent = statusData.progress + '%';
                        
                        // Check if complete
                        if (statusData.status === 'complete') {
                            clearInterval(pollInterval);
                            
                            let modeBadge = '';
                            if (statusData.mode === 'image') {
                                modeBadge = '<br><span style="color: #667eea;">🖼️ Standbild-Modus</span>';
                            } else if (statusData.video_count) {
                                modeBadge = `<br><span style="color: #667eea;">🎲 ${statusData.video_count} Videos zufällig gemischt</span>`;
                            }
                            
                            const effectBadge = statusData.effect && statusData.effect !== 'none'
                                ? `<br><span style="color: #764ba2;">✨ Mit ${statusData.effect} Effekt</span>`
                                : '';
                            
                            resultDiv.className = 'result success';
                            resultDiv.innerHTML = `
                                <div style="text-align: center;">
                                    <div style="font-size: 3em; margin-bottom: 10px;">✅</div>
                                    <div><strong>Video erfolgreich erstellt!</strong></div>
                                    <div style="margin: 10px 0;">
                                        Größe: ${statusData.size}<br>
                                        Dauer: ${statusData.duration}${modeBadge}${effectBadge}
                                    </div>
                                    <a href="/download/${statusData.file_id}" class="download-btn" download>
                                        ⬇️ Video herunterladen
                                    </a>
                                </div>
                            `;
                            submitBtn.disabled = false;
                        } else if (statusData.status === 'error') {
                            clearInterval(pollInterval);
                            showError(statusData.message);
                            submitBtn.disabled = false;
                        }
                        
                    } catch (error) {
                        console.error('Status poll error:', error);
                    }
                }, 5000); // Poll every 5 seconds
                
            } catch (error) {
                showError(error.message);
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

def merge_video_audio_from_image(audio_path, image_path, output_path, status_path=None, effect='none'):
    """Create video from static image with audio and optional effects"""
    try:
        # Get audio duration
        duration = get_video_duration(audio_path)
        print(f"Audio duration: {duration} seconds ({duration/60:.1f} minutes)")
        print(f"Creating video from image: {image_path}")
        
        if effect != 'none':
            print(f"Applying effect: {effect}")
        
        if status_path:
            effect_text = f' + {effect} Effekt' if effect != 'none' else ''
            update_status(status_path, 'processing', 20, f'Erstelle Video aus Standbild{effect_text}...')
        
        temp_video = os.path.join(UPLOAD_FOLDER, f"temp_image_video_{os.path.basename(output_path)}")
        
        print("Step 1: Creating video from image...")
        start_time = time.time()
        
        # Build FFmpeg command
        cmd_image_to_video = [
            'ffmpeg', '-y',
            '-loop', '1',
            '-i', image_path,
            '-t', str(duration)
        ]
        
        # Add video filter if effect is selected
        if effect != 'none' and effect in VIDEO_EFFECTS and VIDEO_EFFECTS[effect]:
            print(f"Applying video filter: {VIDEO_EFFECTS[effect]}")
            cmd_image_to_video.extend([
                '-vf', VIDEO_EFFECTS[effect]
            ])
        
        # Add encoding parameters
        cmd_image_to_video.extend([
            '-c:v', 'libx264',
            '-preset', 'veryfast',
            '-crf', '35',
            '-profile:v', 'high',
            '-level', '4.2',
            '-pix_fmt', 'yuv420p',
            '-maxrate', '4M',
            '-bufsize', '8M',
            '-g', '250',
            '-movflags', '+faststart',
            '-threads', '0',
            temp_video
        ])
        
        print(f"Running: {' '.join(cmd_image_to_video[:10])}...")
        
        if status_path:
            est_minutes = int((duration / 300))  # Images are faster to encode
            update_status(status_path, 'processing', 30, f'Video-Encoding läuft... (~{est_minutes} Min)')
        
        result_video = subprocess.run(
            cmd_image_to_video,
            capture_output=True,
            text=True,
            timeout=3600
        )
        
        encoding_time = time.time() - start_time
        print(f"Video creation completed in {encoding_time/60:.1f} minutes")
        
        if result_video.returncode != 0:
            print(f"FFmpeg stderr: {result_video.stderr[-500:]}")
            raise Exception(f"FFmpeg error: {result_video.stderr[-200:]}")
        
        video_size = os.path.getsize(temp_video)
        print(f"Video created: {format_size(video_size)}")
        
        if status_path:
            update_status(status_path, 'processing', 80, 'Audio wird hinzugefügt...')
        
        # Step 2: Merge with audio
        print("Step 2: Merging audio with video...")
        cmd_merge = [
            'ffmpeg', '-y',
            '-i', temp_video,
            '-i', audio_path,
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-b:a', '96k',
            '-ar', '44100',
            '-map', '0:v:0',
            '-map', '1:a:0',
            '-shortest',
            '-movflags', '+faststart',
            output_path
        ]
        
        print(f"Running: {' '.join(cmd_merge[:10])}...")
        
        result_merge = subprocess.run(
            cmd_merge,
            capture_output=True,
            text=True,
            timeout=1800
        )
        
        if result_merge.returncode != 0:
            print(f"FFmpeg merge stderr: {result_merge.stderr[-500:]}")
            if os.path.exists(temp_video):
                os.remove(temp_video)
            raise Exception(f"FFmpeg merge error: {result_merge.stderr[-200:]}")
        
        # Cleanup
        if os.path.exists(temp_video):
            os.remove(temp_video)
            print("Cleaned up temporary video")
        
        final_size = os.path.getsize(output_path)
        total_time = time.time() - start_time
        print(f"=== IMAGE VIDEO COMPLETE ===")
        print(f"Final file size: {format_size(final_size)}")
        print(f"Total processing time: {total_time/60:.1f} minutes")
        if effect != 'none':
            print(f"Applied effect: {effect}")
        
        if status_path:
            update_status(status_path, 'processing', 95, 'Finalisierung...')
        
        return True
        
    except subprocess.TimeoutExpired as e:
        print(f"FFmpeg timeout after {e.timeout} seconds")
        if 'temp_video' in locals() and os.path.exists(temp_video):
            os.remove(temp_video)
        raise Exception(f"Video processing timeout - took longer than {e.timeout/60:.0f} minutes")
    except Exception as e:
        print(f"Image merge error: {e}")
        if 'temp_video' in locals() and os.path.exists(temp_video):
            try:
                os.remove(temp_video)
            except:
                pass
        raise
    """Merge video and audio - with random video mixing and optional effects"""
    import random
    
    try:
        # Get audio duration
        duration = get_video_duration(audio_path)
        print(f"Audio duration: {duration} seconds ({duration/60:.1f} minutes)")
        
        # Handle single or multiple videos
        if isinstance(video_paths, str):
            video_paths = [video_paths]
        
        print(f"Processing with {len(video_paths)} video file(s)")
        if effect != 'none':
            print(f"Applying effect: {effect}")
        
        # Get duration of each video
        video_durations = []
        for idx, vp in enumerate(video_paths):
            vd = get_video_duration(vp)
            video_durations.append(vd)
            print(f"Video {idx+1} duration: {vd} seconds")
        
        if status_path:
            effect_text = f' + {effect} Effekt' if effect != 'none' else ''
            update_status(status_path, 'processing', 15, f'{len(video_paths)} Video(s) werden analysiert{effect_text}...')
        
        # Calculate clips needed
        avg_video_duration = sum(video_durations) / len(video_durations)
        total_clips_needed = int(duration / avg_video_duration) + len(video_paths)
        
        print(f"Average video duration: {avg_video_duration:.2f} seconds")
        print(f"Total clips needed: ~{total_clips_needed}")
        
        if status_path:
            update_status(status_path, 'processing', 20, f'Erstelle zufällige Video-Sequenz ({total_clips_needed} Clips)...')
        
        # Create paths
        concat_list_path = os.path.join(UPLOAD_FOLDER, f"concat_{os.path.basename(output_path)}.txt")
        temp_looped_video = os.path.join(UPLOAD_FOLDER, f"temp_looped_{os.path.basename(output_path)}")
        
        # Generate random sequence
        print("Generating random video sequence...")
        current_time = 0
        clip_sequence = []
        
        while current_time < duration:
            video_idx = random.randint(0, len(video_paths) - 1)
            clip_sequence.append(video_idx)
            current_time += video_durations[video_idx]
        
        print(f"Generated sequence with {len(clip_sequence)} clips")
        print(f"Video distribution: {[clip_sequence.count(i) for i in range(len(video_paths))]}")
        
        # Create FFmpeg concat file
        with open(concat_list_path, 'w') as f:
            for video_idx in clip_sequence:
                video_path_escaped = video_paths[video_idx].replace("'", "'\\''")
                f.write(f"file '{video_path_escaped}'\n")
        
        print(f"Concat list created: {concat_list_path}")
        
        if status_path:
            est_minutes = int((duration / 200))
            effect_note = f' ({effect} Effekt)' if effect != 'none' else ''
            update_status(status_path, 'processing', 25, f'Video-Encoding läuft{effect_note}... (~{est_minutes} Min)')
        
        # Step 1: Concatenate videos with optional effect
        print("Step 1: Creating concatenated video with optional effect...")
        start_time = time.time()
        
        # Build FFmpeg command with optional video filter
        cmd_concat = [
            'ffmpeg', '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', concat_list_path,
            '-t', str(duration)
        ]
        
        # Add video filter if effect is selected
        if effect != 'none' and effect in VIDEO_EFFECTS and VIDEO_EFFECTS[effect]:
            print(f"Applying video filter: {VIDEO_EFFECTS[effect]}")
            cmd_concat.extend([
                '-vf', VIDEO_EFFECTS[effect]
            ])
        
        # Add encoding parameters
        cmd_concat.extend([
            '-c:v', 'libx264',
            '-preset', 'veryfast',
            '-crf', '35',
            '-profile:v', 'high',
            '-level', '4.2',
            '-pix_fmt', 'yuv420p',
            '-maxrate', '4M',
            '-bufsize', '8M',
            '-g', '250',
            '-movflags', '+faststart',
            '-an',
            '-threads', '0',
            temp_looped_video
        ])
        
        print(f"Running: {' '.join(cmd_concat[:10])}...")
        
        result_concat = subprocess.run(
            cmd_concat,
            capture_output=True,
            text=True,
            timeout=7200
        )
        
        encoding_time = time.time() - start_time
        print(f"Concatenation completed in {encoding_time/60:.1f} minutes")
        
        if result_concat.returncode != 0:
            print(f"FFmpeg concat stderr: {result_concat.stderr[-500:]}")
            if os.path.exists(concat_list_path):
                os.remove(concat_list_path)
            raise Exception(f"FFmpeg concat error: {result_concat.stderr[-200:]}")
        
        # Remove concat list
        if os.path.exists(concat_list_path):
            os.remove(concat_list_path)
        
        concat_size = os.path.getsize(temp_looped_video)
        print(f"Concatenated video created: {format_size(concat_size)}")
        
        if status_path:
            update_status(status_path, 'processing', 80, 'Audio wird hinzugefügt...')
        
        # Step 2: Merge with audio
        print("Step 2: Merging audio with video...")
        cmd_merge = [
            'ffmpeg', '-y',
            '-i', temp_looped_video,
            '-i', audio_path,
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-b:a', '96k',
            '-ar', '44100',
            '-map', '0:v:0',
            '-map', '1:a:0',
            '-shortest',
            '-movflags', '+faststart',
            output_path
        ]
        
        print(f"Running: {' '.join(cmd_merge[:10])}...")
        
        result_merge = subprocess.run(
            cmd_merge,
            capture_output=True,
            text=True,
            timeout=1800
        )
        
        if result_merge.returncode != 0:
            print(f"FFmpeg merge stderr: {result_merge.stderr[-500:]}")
            if os.path.exists(temp_looped_video):
                os.remove(temp_looped_video)
            raise Exception(f"FFmpeg merge error: {result_merge.stderr[-200:]}")
        
        # Cleanup
        if os.path.exists(temp_looped_video):
            os.remove(temp_looped_video)
            print("Cleaned up temporary video")
        
        final_size = os.path.getsize(output_path)
        total_time = time.time() - start_time
        print(f"=== MERGE COMPLETE ===")
        print(f"Final file size: {format_size(final_size)}")
        print(f"Total processing time: {total_time/60:.1f} minutes")
        print(f"Used {len(clip_sequence)} clips from {len(video_paths)} video(s)")
        if effect != 'none':
            print(f"Applied effect: {effect}")
        
        if status_path:
            update_status(status_path, 'processing', 95, 'Finalisierung...')
        
        return True
        
    except subprocess.TimeoutExpired as e:
        print(f"FFmpeg timeout after {e.timeout} seconds")
        if 'temp_looped_video' in locals() and os.path.exists(temp_looped_video):
            os.remove(temp_looped_video)
        if 'concat_list_path' in locals() and os.path.exists(concat_list_path):
            os.remove(concat_list_path)
        raise Exception(f"Video processing timeout - took longer than {e.timeout/60:.0f} minutes")
    except Exception as e:
        print(f"Merge error: {e}")
        if 'temp_looped_video' in locals() and os.path.exists(temp_looped_video):
            try:
                os.remove(temp_looped_video)
            except:
                pass
        if 'concat_list_path' in locals() and os.path.exists(concat_list_path):
            try:
                os.remove(concat_list_path)
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
    """Handle file upload and start background processing"""
    audio_path = None
    video_paths = []
    image_path = None
    
    try:
        print("=== UPLOAD START ===")
        
        # Check audio file
        if 'audio' not in request.files:
            print("ERROR: Missing audio file")
            return jsonify({'success': False, 'error': 'Audio-Datei benötigt'}), 400
        
        audio_file = request.files['audio']
        mode = request.form.get('mode', 'video')  # 'video' or 'image'
        
        print(f"Mode: {mode}")
        print(f"Audio file: {audio_file.filename}")
        
        if audio_file.filename == '':
            print("ERROR: Empty audio filename")
            return jsonify({'success': False, 'error': 'Leere Audio-Datei'}), 400
        
        # Get selected effect
        effect = request.form.get('effect', 'none')
        if effect not in VIDEO_EFFECTS:
            effect = 'none'
        print(f"Selected effect: {effect}")
        
        # Generate unique ID
        file_id = str(uuid.uuid4())
        print(f"Generated file_id: {file_id}")
        
        # Save audio file
        audio_ext = os.path.splitext(audio_file.filename)[1] or '.mp3'
        audio_path = os.path.join(UPLOAD_FOLDER, f"{file_id}_audio{audio_ext}")
        
        print(f"Saving audio to: {audio_path}")
        audio_file.save(audio_path)
        print(f"Audio saved: {os.path.getsize(audio_path)} bytes")
        
        # Handle mode-specific files
        if mode == 'image':
            # Image mode - single image
            if 'image' not in request.files:
                print("ERROR: Missing image file")
                return jsonify({'success': False, 'error': 'Standbild benötigt'}), 400
            
            image_file = request.files['image']
            if image_file.filename == '':
                print("ERROR: Empty image filename")
                return jsonify({'success': False, 'error': 'Leeres Standbild'}), 400
            
            image_ext = os.path.splitext(image_file.filename)[1] or '.jpg'
            image_path = os.path.join(UPLOAD_FOLDER, f"{file_id}_image{image_ext}")
            
            print(f"Saving image: {image_file.filename}")
            image_file.save(image_path)
            print(f"Image saved: {os.path.getsize(image_path)} bytes")
            
        else:
            # Video mode - multiple videos
            if 'videos' not in request.files:
                print("ERROR: Missing video files")
                return jsonify({'success': False, 'error': 'Mindestens 1 Video benötigt'}), 400
            
            video_files = request.files.getlist('videos')
            print(f"Video files: {len(video_files)} file(s)")
            
            if len(video_files) == 0:
                print("ERROR: No video files")
                return jsonify({'success': False, 'error': 'Mindestens 1 Video benötigt'}), 400
            
            # Save all video files
            for idx, video_file in enumerate(video_files):
                if video_file.filename == '':
                    continue
                    
                video_ext = os.path.splitext(video_file.filename)[1] or '.mp4'
                video_path = os.path.join(UPLOAD_FOLDER, f"{file_id}_video_{idx}{video_ext}")
                
                print(f"Saving video {idx+1}/{len(video_files)}: {video_file.filename}")
                video_file.save(video_path)
                print(f"Video {idx+1} saved: {os.path.getsize(video_path)} bytes")
                
                video_paths.append(video_path)
            
            if len(video_paths) == 0:
                print("ERROR: No valid video files")
                return jsonify({'success': False, 'error': 'Keine gültigen Video-Dateien'}), 400
        
        output_path = os.path.join(OUTPUT_FOLDER, f"{file_id}.mp4")
        
        # Create status file
        status_path = os.path.join(OUTPUT_FOLDER, f"{file_id}_status.json")
        status_data = {
            'status': 'processing',
            'progress': 0,
            'message': 'Upload erfolgreich - Verarbeitung startet...',
            'file_id': file_id,
            'mode': mode,
            'effect': effect
        }
        
        if mode == 'video':
            status_data['video_count'] = len(video_paths)
        
        with open(status_path, 'w') as f:
            json.dump(status_data, f)
        
        # Start background processing
        mode_desc = f"Standbild" if mode == 'image' else f"{len(video_paths)} video(s)"
        print(f"Starting background processing with {mode_desc} and '{effect}' effect...")
        
        thread = threading.Thread(
            target=process_video_background,
            args=(file_id, audio_path, video_paths if mode == 'video' else None, 
                  image_path if mode == 'image' else None, output_path, status_path, effect, mode)
        )
        thread.daemon = True
        thread.start()
        
        print(f"=== UPLOAD ACCEPTED - Processing {mode_desc} in background ===")
        
        # Return immediately with job_id
        response_data = {
            'success': True,
            'job_id': file_id,
            'mode': mode,
            'effect': effect,
            'message': f'Upload erfolgreich'
        }
        
        if mode == 'video':
            response_data['video_count'] = len(video_paths)
        
        return jsonify(response_data)
        
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
            for vp in video_paths:
                if os.path.exists(vp):
                    os.remove(vp)
            if image_path and os.path.exists(image_path):
                os.remove(image_path)
        except:
            pass
        
        return jsonify({'success': False, 'error': str(e)}), 500

def process_video_background(file_id, audio_path, video_paths, image_path, output_path, status_path, effect='none', mode='video'):
    """Background processing function"""
    try:
        mode_desc = "Standbild" if mode == 'image' else f"{len(video_paths)} video(s)"
        print(f"[Background] Starting merge for {file_id} with {mode_desc} and '{effect}' effect")
        
        # Update status: Starting
        effect_text = f' mit {effect} Effekt' if effect != 'none' else ''
        
        if mode == 'image':
            update_status(status_path, 'processing', 10, f'Standbild wird verarbeitet{effect_text}...')
            # Create video from image
            merge_video_audio_from_image(audio_path, image_path, output_path, status_path, effect)
        else:
            update_status(status_path, 'processing', 10, f'Analysiere {len(video_paths)} Video(s){effect_text}...')
            # Merge videos
            merge_video_audio(audio_path, video_paths, output_path, status_path, effect)
        
        # Get file info
        file_size = os.path.getsize(output_path)
        duration = get_video_duration(output_path)
        
        # Clean up input files
        print("[Background] Cleaning up input files...")
        if os.path.exists(audio_path):
            os.remove(audio_path)
        
        if mode == 'video':
            for vp in video_paths:
                if os.path.exists(vp):
                    os.remove(vp)
        else:
            if image_path and os.path.exists(image_path):
                os.remove(image_path)
        
        # Update status: Complete
        complete_data = {
            'file_id': file_id,
            'size': format_size(file_size),
            'duration': format_duration(duration),
            'file_size_bytes': file_size,
            'effect': effect,
            'mode': mode
        }
        
        if mode == 'video':
            complete_data['video_count'] = len(video_paths)
        
        update_status(status_path, 'complete', 100, 'Video erfolgreich erstellt!', complete_data)
        
        print(f"[Background] === PROCESSING COMPLETE for {file_id} ===")
        
    except Exception as e:
        print(f"[Background] Error processing {file_id}: {e}")
        import traceback
        print(f"[Background] Traceback:\n{traceback.format_exc()}")
        
        # Update status: Error
        update_status(status_path, 'error', 0, f'Fehler: {str(e)}')
        
        # Cleanup on error
        try:
            if audio_path and os.path.exists(audio_path):
                os.remove(audio_path)
            if mode == 'video' and video_paths:
                for vp in video_paths:
                    if os.path.exists(vp):
                        os.remove(vp)
            if mode == 'image' and image_path and os.path.exists(image_path):
                os.remove(image_path)
        except:
            pass

def update_status(status_path, status, progress, message, data=None):
    """Update status file"""
    try:
        status_data = {
            'status': status,
            'progress': progress,
            'message': message,
            'timestamp': datetime.now().isoformat()
        }
        if data:
            status_data.update(data)
        
        with open(status_path, 'w') as f:
            json.dump(status_data, f)
    except Exception as e:
        print(f"Error updating status: {e}")

@app.route('/status/<job_id>')
def get_status(job_id):
    """Get processing status"""
    try:
        status_path = os.path.join(OUTPUT_FOLDER, f"{job_id}_status.json")
        
        if not os.path.exists(status_path):
            return jsonify({
                'success': False,
                'error': 'Job not found'
            }), 404
        
        with open(status_path, 'r') as f:
            status_data = json.load(f)
        
        return jsonify({
            'success': True,
            **status_data
        })
        
    except Exception as e:
        print(f"Status check error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

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
