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
import re
from datetime import datetime, timedelta
import threading
import time
from pathlib import Path
import zipfile
from io import BytesIO

app = Flask(__name__)

# Configuration
UPLOAD_FOLDER = '/tmp/uploads'
OUTPUT_FOLDER = '/tmp/output'
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB
CLEANUP_AGE_HOURS = 24

# Video effects mapping with categories
VIDEO_EFFECTS = {
    # No Effect
    'none': {'filter': None, 'category': 'none'},
    
    # STATISCHE EFFEKTE
    'vignette': {'filter': 'vignette=PI/5', 'category': 'static'},
    'noir': {'filter': 'eq=brightness=-0.1:contrast=1.2', 'category': 'static'},
    'warm': {'filter': 'colorbalance=rs=0.1:gs=-0.05:bs=-0.1', 'category': 'static'},
    'staub': {'filter': 'noise=alls=20:allf=t+u', 'category': 'static'},
    'blur': {'filter': 'gblur=sigma=2:steps=1', 'category': 'static'},
    
    # BEWEGTE EFFEKTE - Zoom & Pan
    'zoom_in': {'filter': 'zoompan=z=\'min(zoom+0.005,1.5)\':d=250:x=iw/2-(iw/zoom/2):y=ih/2-(ih/zoom/2)', 'category': 'animated'},
    'zoom_out': {'filter': 'zoompan=z=\'if(lte(zoom,1.0),1.5,max(1.001,zoom-0.005))\':d=1', 'category': 'animated'},
    'breathing': {'filter': 'zoompan=z=\'1+0.15*sin(2*PI*t)\':d=1:x=iw/2-(iw/zoom/2):y=ih/2-(ih/zoom/2)', 'category': 'animated'},
    'breathing_slow': {'filter': 'zoompan=z=\'1+0.1*sin(2*PI*t/3)\':d=1:x=iw/2-(iw/zoom/2):y=ih/2-(ih/zoom/2)', 'category': 'animated'},
    'ken_burns': {'filter': 'zoompan=z=\'min(max(zoom,pzoom)+0.0015,1.5)\':d=1:x=iw/2-(iw/zoom/2):y=ih/2-(ih/zoom/2)', 'category': 'animated'},
    'pan_right': {'filter': 'zoompan=z=1:x=\'x+5\':y=y:d=1', 'category': 'animated'},
    
    # BEWEGTE EFFEKTE - Rotation
    'rotate': {'filter': 'rotate=angle=2*PI*t/10:c=black', 'category': 'animated'},
    'rotate_slow': {'filter': 'rotate=angle=PI*t/20:c=black', 'category': 'animated'},
    'rotate_fast': {'filter': 'rotate=angle=4*PI*t:c=black', 'category': 'animated'},
    
    # BEWEGTE EFFEKTE - Farben
    'psychedelic': {'filter': 'hue=s=1.3:h=360*t*3', 'category': 'animated'},
    'psychedelic_slow': {'filter': 'hue=s=1.2:h=360*t', 'category': 'animated'},
    'rainbow': {'filter': 'hue=h=360*t*5:s=1.5', 'category': 'animated'},
    'color_wave': {'filter': 'hue=h=sin(2*PI*t*2)*180+180:s=1.3', 'category': 'animated'},
    'saturation_pulse': {'filter': 'hue=s=1+0.7*sin(2*PI*t*3)', 'category': 'animated'},
    'brightness_pulse': {'filter': 'eq=brightness=0.3*sin(2*PI*t*2)', 'category': 'animated'},
    
    # BEWEGTE EFFEKTE - Shake & Distortion
    'shake': {'filter': 'crop=in_w-abs(20*sin(t*20)):in_h-abs(20*sin(t*20))', 'category': 'animated'},
    'shake_soft': {'filter': 'crop=in_w-abs(10*sin(t*10)):in_h-abs(10*sin(t*10))', 'category': 'animated'},
    'earthquake': {'filter': 'crop=in_w-abs(50*sin(t*25)):in_h-abs(50*cos(t*25))', 'category': 'animated'},
    'vibrate': {'filter': 'crop=iw-abs(15*sin(t*100)):ih:abs(8*sin(t*100)):0', 'category': 'animated'},
    'wave_distort': {'filter': 'format=yuv420p,geq=lum=\'lum(X,Y+15*sin(X/10*2*PI+t*5))\'', 'category': 'animated'},
    'wave_horizontal': {'filter': 'format=yuv420p,geq=lum=\'lum(X+15*sin(Y/10*2*PI+t*5),Y)\'', 'category': 'animated'},
    'ripple': {'filter': 'format=yuv420p,geq=lum=\'lum(X+10*sin(hypot(X-W/2,Y-H/2)/20-t*3),Y+10*cos(hypot(X-W/2,Y-H/2)/20-t*3))\'', 'category': 'animated'},
    
    # BEWEGTE EFFEKTE - Glitch
    'rgb_glitch': {'filter': 'rgbashift=rh=15*sin(t*5):gh=-15*sin(t*5):bh=15*cos(t*5)', 'category': 'animated'},
    'rgb_glitch_fast': {'filter': 'rgbashift=rh=20*sin(t*10):gh=-20*sin(t*10):bh=20*cos(t*10)', 'category': 'animated'},
    'vhs_glitch': {'filter': 'rgbashift=rh=-8:gh=8,noise=alls=8:allf=t,eq=brightness=0.05*sin(t*2)', 'category': 'animated'},
    'datamosh': {'filter': 'noise=alls=20:allf=t,eq=contrast=1+0.3*sin(t*5)', 'category': 'animated'},
    'glitch_scan': {'filter': 'rgbashift=rh=30*sin(t*20):bv=30*sin(t*20)', 'category': 'animated'},
    
    # BEWEGTE EFFEKTE - Trails & Special
    'trails': {'filter': 'tmix=frames=5:weights=1 1 1 1 1', 'category': 'animated'},
    'trails_long': {'filter': 'tmix=frames=10:weights=1 1 1 1 1 1 1 1 1 1', 'category': 'animated'},
    'ghosting': {'filter': 'tmix=frames=3:weights=1 2 1', 'category': 'animated'},
    'stop_motion': {'filter': 'fps=8', 'category': 'animated'},
    'crt_flicker': {'filter': 'eq=brightness=0.1*sin(200*t):contrast=1+0.2*sin(100*t)', 'category': 'animated'},
    
    # NEUE: Partikel & Bewegte Overlays
    'dust_storm': {'filter': 'noise=alls=40:allf=t+u,hue=s=0.3+0.2*sin(t*3)', 'category': 'animated'},
    'snow': {'filter': 'noise=alls=60:allf=t+u,eq=contrast=1.2:brightness=0.1+0.05*sin(t*5)', 'category': 'animated'},
    'rain': {'filter': 'noise=alls=50:allf=t+u,format=yuv420p,geq=lum=\'lum(X,Y+30*sin(X/20+t*10))\'', 'category': 'animated'},
    'film_scratches': {'filter': 'noise=alls=80:allf=t+u,hue=s=0,eq=brightness=0.1*sin(t*20)', 'category': 'animated'},
    
    # KOMBINIERTE EFFEKTE
    'horror_glitch': {'filter': 'noise=alls=30:allf=t+u,rgbashift=rh=10*sin(t*10),eq=brightness=-0.2+0.1*sin(t*5)', 'category': 'combined'},
    'desert_heat': {'filter': 'hue=s=0.8,format=yuv420p,geq=lum=\'lum(X,Y+5*sin(X/10*2*PI+t*3))\'', 'category': 'combined'},
    'psychedelic_staub': {'filter': 'hue=h=360*t*3:s=1.4,noise=alls=25:allf=t+u', 'category': 'combined'},
    'western_dust': {'filter': 'colorbalance=rs=0.2:bs=-0.15,noise=alls=35:allf=t+u,vignette=PI/4,hue=s=1+0.3*sin(t*2)', 'category': 'combined'},
    'noir_grain': {'filter': 'eq=brightness=-0.1:contrast=1.3,noise=alls=40:allf=t+u', 'category': 'combined'},
    'vintage_breathing': {'filter': 'colorbalance=rs=0.15:bs=-0.1,zoompan=z=\'1+0.12*sin(2*PI*t*2)\':d=1,noise=alls=25:allf=t+u', 'category': 'combined'},
    'trippy_trails': {'filter': 'hue=h=360*t*4:s=1.5,tmix=frames=8:weights=1 1 1 1 1 1 1 1', 'category': 'combined'},
    'storm_chaos': {'filter': 'noise=alls=50:allf=t+u,rgbashift=rh=20*sin(t*10):gh=-20*sin(t*10),crop=in_w-abs(30*sin(t*15)):in_h-abs(30*sin(t*15)),eq=brightness=0.1*sin(t*8)', 'category': 'combined'},
    'acid_trip': {'filter': 'hue=h=360*t*5:s=1.6,format=yuv420p,geq=lum=\'lum(X+10*sin(Y/10*2*PI+t*8),Y+10*cos(X/10*2*PI+t*8))\'', 'category': 'combined'},
    'nightmare_vision': {'filter': 'eq=brightness=-0.3:contrast=1.5,hue=h=180+90*sin(t*2):s=0.5,noise=alls=35:allf=t+u,tmix=frames=4:weights=1 1 1 1', 'category': 'combined'},
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
        <p class="subtitle">Füge Audio zu deinem Video-Loop oder Standbild hinzu oder verbinde mehrere Audiodateien zu einer MP3</p>
        
        <div id="uploadForm">
            <div class="mode-selector">
                <button type="button" class="mode-btn active" id="videoModeBtn" onclick="switchMode('video')">
                    🎥 Video-Loops
                </button>
                <button type="button" class="mode-btn" id="imageModeBtn" onclick="switchMode('image')">
                    🖼️ Standbild
                </button>
                <button type="button" class="mode-btn" id="audioMergeModeBtn" onclick="switchMode('audio')">
                    🎧 Audios zusammenführen
                </button>
            </div>
            <div class="upload-section" id="audioSectionBox">
                <div class="upload-box" id="audioBox" onclick="document.getElementById('audioInput').click()">
                    <div class="upload-icon">🎵</div>
                    <div class="upload-label">Audio-Datei hochladen</div>
                    <div class="upload-hint">MP3, WAV, OGG, FLAC (max 500 MB)</div>
                    <div class="file-info" id="audioInfo"></div>
                    <input type="file" id="audioInput" name="audio" accept="audio/*">
                </div>
            </div>
            
            <div class="upload-section" id="audioMergeSectionBox" style="display: none;">
                <div class="upload-box" id="audioMergeBox" onclick="document.getElementById('audioMergeInput').click()">
                    <div class="upload-icon">🎧</div>
                    <div class="upload-label">Mehrere Audios hochladen</div>
                    <div class="upload-hint">MP3, WAV, OGG, FLAC (max 500 MB pro Datei)</div>
                    <div class="upload-hint" style="margin-top: 5px; font-weight: bold; color: #667eea;">
                        🎼 Mindestens 2 Audiodateien für die Zusammenführung
                    </div>
                    <div class="file-info" id="audioMergeInfo"></div>
                    <input type="file" id="audioMergeInput" name="audios" accept="audio/*" multiple>
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
            
            <div class="upload-section" id="imageSectionBox" style="display: none;">
                <div class="upload-box" id="imageBox" onclick="document.getElementById('imageInput').click()">
                    <div class="upload-icon">🖼️</div>
                    <div class="upload-label">Standbild hochladen</div>
                    <div class="upload-hint">JPG, PNG, GIF (max 50 MB)</div>
                    <div class="file-info" id="imageInfo"></div>
                    <input type="file" id="imageInput" name="image" accept="image/*">
                </div>
            </div>
            
            <div class="upload-section">
                <label style="display: block; font-weight: bold; color: #667eea; margin-bottom: 10px;">
                    ✨ Video-Effekt (Optional)
                </label>
                <select id="effectSelect" style="width: 100%; padding: 12px; border: 2px solid #667eea; border-radius: 8px; font-size: 1em; background: white; cursor: pointer;">
                    <option value="none">Kein Effekt</option>
                    
                    <optgroup label="━━━ STATISCHE EFFEKTE ━━━">
                        <option value="blur">🌫️ Blur</option>
                        <option value="staub">🌫️ Staub / Film Grain</option>
                        <option value="vignette">🎬 Vignette (Dunkle Ränder)</option>
                        <option value="noir">🖤 Noir / Film</option>
                        <option value="warm">🔥 Warm / Vintage</option>
                    </optgroup>
                    
                    <optgroup label="━━━ ZOOM & PAN ━━━">
                        <option value="zoom_in">🔍 Zoom-In</option>
                        <option value="zoom_out">🔍 Zoom-Out</option>
                        <option value="breathing">💨 Atmungs-Effekt</option>
                        <option value="breathing_slow">💨 Atmung (Langsam)</option>
                        <option value="ken_burns">🎞️ Ken Burns (3D Pan)</option>
                        <option value="pan_right">➡️ Pan Rechts</option>
                    </optgroup>
                    
                    <optgroup label="━━━ ROTATION ━━━">
                        <option value="rotate">🔄 Rotation</option>
                        <option value="rotate_slow">🔄 Rotation (Langsam)</option>
                        <option value="rotate_fast">🔄 Rotation (Schnell)</option>
                    </optgroup>
                    
                    <optgroup label="━━━ FARB-EFFEKTE ━━━">
                        <option value="psychedelic">🌈 Psychedelisch (Schnell)</option>
                        <option value="psychedelic_slow">🌈 Psychedelisch (Langsam)</option>
                        <option value="rainbow">🌅 Regenbogen-Welle</option>
                        <option value="color_wave">🌊 Farb-Welle</option>
                        <option value="saturation_pulse">📊 Sättigung-Puls</option>
                        <option value="brightness_pulse">💡 Helligkeits-Puls</option>
                    </optgroup>
                    
                    <optgroup label="━━━ SHAKE & DISTORTION ━━━">
                        <option value="shake">📺 Wackeln</option>
                        <option value="shake_soft">📺 Wackeln (Sanft)</option>
                        <option value="earthquake">⚠️ Erdbeben</option>
                        <option value="vibrate">〰️ Vibration</option>
                        <option value="wave_distort">〰️ Wellen (Vertikal)</option>
                        <option value="wave_horizontal">〰️ Wellen (Horizontal)</option>
                        <option value="ripple">〰️ Ripple-Effekt</option>
                    </optgroup>
                    
                    <optgroup label="━━━ GLITCH EFFEKTE ━━━">
                        <option value="rgb_glitch">📻 RGB Glitch</option>
                        <option value="rgb_glitch_fast">📻 RGB Glitch (Schnell)</option>
                        <option value="vhs_glitch">📼 VHS Glitch</option>
                        <option value="datamosh">🤖 Datamosh</option>
                        <option value="glitch_scan">📺 Glitch Scan</option>
                    </optgroup>
                    
                    <optgroup label="━━━ TRAILS & SPEZIAL ━━━">
                        <option value="trails">✨ Bewegungs-Trails</option>
                        <option value="trails_long">✨ Trails (Lang)</option>
                        <option value="ghosting">👻 Ghosting</option>
                        <option value="stop_motion">🎬 Stop Motion</option>
                        <option value="crt_flicker">📺 CRT Flicker</option>
                    </optgroup>
                    
                    <optgroup label="━━━ PARTIKEL & OVERLAYS ━━━">
                        <option value="dust_storm">🌪️ Staub-Sturm</option>
                        <option value="snow">❄️ Schnee</option>
                        <option value="rain">🌧️ Regen</option>
                        <option value="film_scratches">🎞️ Film-Kratzer</option>
                    </optgroup>
                    
                    <optgroup label="━━━ KOMBINIERTE EFFEKTE ━━━">
                        <option value="horror_glitch">👻 Horror Glitch</option>
                        <option value="desert_heat">🏜️ Wüsten-Hitze</option>
                        <option value="psychedelic_staub">🌈 Psycho-Staub</option>
                        <option value="western_dust">🤠 Western Dust</option>
                        <option value="noir_grain">🖤 Noir mit Grain</option>
                        <option value="vintage_breathing">🔄 Vintage Breathing</option>
                        <option value="trippy_trails">🌈 Trippy Trails</option>
                        <option value="storm_chaos">⚡ Sturm Chaos</option>
                        <option value="acid_trip">🎨 Acid Trip</option>
                        <option value="nightmare_vision">😱 Nightmare Vision</option>
                    </optgroup>
                </select>
                <div id="effectDescription" style="margin-top: 12px; padding: 12px; background: #f0f1ff; border-left: 4px solid #667eea; border-radius: 6px; font-size: 0.95em; color: #333; min-height: 40px; display: flex; align-items: center;">
                    Kein Effekt wird angewendet
                </div>
                <div style="margin-top: 8px; font-size: 0.85em; color: #666;">
                    Der Effekt wird über das gesamte Video gelegt
                </div>
            </div>
            
            <div id="trimFramesContainer" style="margin-top: 15px; display: none; padding: 12px; background: #f0f1ff; border-left: 4px solid #667eea; border-radius: 6px;">
                <div style="display: flex; align-items: center; gap: 10px;">
                    <label for="trimFramesInput" style="cursor: pointer; margin: 0; font-weight: 500; color: #333;">✂️ Frames vom Ende abschneiden (für Veo 3.1 Fix):</label>
                    <input type="number" id="trimFramesInput" value="7" min="0" max="100" style="width: 60px;" />
                </div>
                <div style="margin-top: 8px; font-size: 0.85em; color: #666;">
                    Entfernt die angegebenen Frames jedes Videos, um Loop-Fehlanpassungen zu beheben (Standard: 7)
                </div>
            </div>
            
            <button class="btn" id="submitBtn" disabled onclick="handleUpload()">Video erstellen</button>
        </div>
        
        <div id="result" class="result"></div>
        
        <div class="info-box">
            <h3>ℹ️ Hinweise</h3>
            <ul>
                <li><strong>Video-Loops:</strong> Werden automatisch geloopt bis zur Audio-Länge</li>
                <li>🎲 <strong>Mehrere Videos:</strong> Werden zufällig gemischt für mehr Abwechslung!</li>
                <li>🎧 <strong>Mehrere Audios:</strong> Werden zu einer einzelnen MP3 zusammengefügt</li>
                <li><strong>Standbild:</strong> Ein Bild wird für das gesamte Video verwendet</li>
                <li>✨ <strong>Effekte:</strong> Können mit Videos und Standbildern kombiniert werden</li>
                <li>Maximale Dateigröße: 500 MB (Audio/Video), 50 MB (Bild)</li>
                <li>Verarbeitung: Videos 20-30 Min, Standbilder 5-10 Min</li>
                <li>Dateien werden nach 24h automatisch gelöscht</li>
            </ul>
        </div>
    </div>

    <script>
        // Effect descriptions
        const effectDescriptions = {
            'none': 'Kein Effekt wird angewendet',
            'vignette': '🎨 Statisch - Dunkle Ränder für cinematischen Look',
            'noir': '🎨 Statisch - Klassischer Film-Noir Look',
            'warm': '🎨 Statisch - Warme Vintage-Farben',
            'staub': '🎨 Statisch - Film-Körnung und Staub',
            'blur': '🎨 Statisch - Weichzeichner-Effekt',
            'zoom_in': '🎭 Animiert - Schneller Zoom ins Bild (5x schneller)',
            'zoom_out': '🎭 Animiert - Schneller Zoom aus dem Bild (5x schneller)',
            'breathing': '🎭 Animiert - Schnell pulsierender Zoom (1 Zyklus/Sekunde)',
            'breathing_slow': '🎭 Animiert - Langsam pulsierender Zoom (alle 3 Sekunden)',
            'ken_burns': '🎭 Animiert - Klassischer Dokumentarfilm-Effekt',
            'pan_right': '🎭 Animiert - Schnelle Kamera-Bewegung nach rechts',
            'rotate': '🎭 Animiert - Kontinuierliche Rotation (1 Umdrehung/10 Sek)',
            'rotate_slow': '🎭 Animiert - Langsame Rotation (1 Umdrehung/20 Sek)',
            'rotate_fast': '🎭 Animiert - Schnelle Rotation (2 Umdrehungen/Sekunde)',
            'psychedelic': '🎭 Animiert - Schnelle Farbveränderungen (3x Geschwindigkeit)',
            'psychedelic_slow': '🎭 Animiert - Normale Psychedelic-Geschwindigkeit',
            'rainbow': '🎭 Animiert - Sehr schneller Regenbogen-Cycle (5x)',
            'color_wave': '🎭 Animiert - Schnelle wellenförmige Farbänderungen',
            'saturation_pulse': '🎭 Animiert - Schnell pulsierende Farbsättigung',
            'brightness_pulse': '🎭 Animiert - Schnell pulsierende Helligkeit',
            'shake': '🎭 Animiert - Schnelles Kamera-Wackeln (2x schneller)',
            'shake_soft': '🎭 Animiert - Sanftes Kamera-Wackeln',
            'earthquake': '🎭 Animiert - Sehr starkes Erdbeben-Wackeln',
            'vibrate': '🎭 Animiert - Extrem schnelles Vibrieren (100 Hz)',
            'wave_distort': '🎭 Animiert - Bewegte vertikale Wellen',
            'wave_horizontal': '🎭 Animiert - Bewegte horizontale Wellen',
            'ripple': '🎭 Animiert - Wasser-Ripple vom Zentrum',
            'rgb_glitch': '🎭 Animiert - Bewegte RGB-Kanal Verschiebung',
            'rgb_glitch_fast': '🎭 Animiert - Schnelle RGB-Kanal Verschiebung (2x)',
            'vhs_glitch': '🎭 Animiert - Bewegter VHS-Tape Effekt',
            'datamosh': '🎭 Animiert - Pulsierender Datamoshing Glitch',
            'glitch_scan': '🎭 Animiert - Schnelle Scan-Line Glitches',
            'trails': '🎭 Animiert - Motion Blur Trails (5 Frames)',
            'trails_long': '🎭 Animiert - Lange Motion Blur Trails (10 Frames)',
            'ghosting': '🎭 Animiert - Kurzer Geister-Effekt',
            'stop_motion': '🎭 Animiert - Stop-Motion Look (8 FPS)',
            'crt_flicker': '🎭 Animiert - Schnelles CRT-Monitor Flackern',
            'dust_storm': '🎭 Animiert - Bewegter Staubsturm (weht durch)',
            'snow': '🎭 Animiert - Fallender Schnee',
            'rain': '🎭 Animiert - Bewegter Regen',
            'film_scratches': '🎭 Animiert - Schnell bewegte Film-Kratzer',
            'horror_glitch': '🎨 Kombiniert - Bewegter Staub + Pulsierender Glitch + Dunkel',
            'desert_heat': '🎨 Kombiniert - Hitzeflimmern mit bewegten Wellen',
            'psychedelic_staub': '🎨 Kombiniert - Schnelle Farben + Bewegte Filmkörnung',
            'western_dust': '🎨 Kombiniert - Western-Farben + Bewegter Staub',
            'noir_grain': '🎨 Kombiniert - Film-Noir + Bewegte Körnung',
            'vintage_breathing': '🎨 Kombiniert - Vintage + Schneller Atmender Zoom + Staub',
            'trippy_trails': '🎨 Kombiniert - Sehr schnelle Psychedelic + Lange Trails',
            'storm_chaos': '🎨 Kombiniert - Extremer Staub + RGB-Glitch + Shake',
            'acid_trip': '🎨 Kombiniert - Extreme Farben + Spiralverzerrung',
            'nightmare_vision': '🎨 Kombiniert - Dunkel + Pulsierender Horror + Trails'
        };

        const audioInput = document.getElementById('audioInput');
        const audioMergeInput = document.getElementById('audioMergeInput');
        const videoInput = document.getElementById('videoInput');
        const audioBox = document.getElementById('audioBox');
        const audioMergeBox = document.getElementById('audioMergeBox');
        const videoBox = document.getElementById('videoBox');
        const audioInfo = document.getElementById('audioInfo');
        const audioMergeInfo = document.getElementById('audioMergeInfo');
        const videoInfo = document.getElementById('videoInfo');
        const submitBtn = document.getElementById('submitBtn');
        const resultDiv = document.getElementById('result');
        
        // Mode management
        const imageInput = document.getElementById('imageInput');
        const imageBox = document.getElementById('imageBox');
        const imageInfo = document.getElementById('imageInfo');
        const imageSectionBox = document.getElementById('imageSectionBox');
        const audioSectionBox = document.getElementById('audioSectionBox');
        const audioMergeSectionBox = document.getElementById('audioMergeSectionBox');
        const videoSectionBox = document.querySelector('[id="videoBox"]').closest('.upload-section');
        let currentMode = 'video';
        const trimFramesContainer = document.getElementById('trimFramesContainer');
        
        function switchMode(mode) {
            currentMode = mode;
            const videoModeBtn = document.getElementById('videoModeBtn');
            const imageModeBtn = document.getElementById('imageModeBtn');
            const audioMergeModeBtn = document.getElementById('audioMergeModeBtn');
            
            audioSectionBox.style.display = 'none';
            audioMergeSectionBox.style.display = 'none';
            videoSectionBox.style.display = 'none';
            imageSectionBox.style.display = 'none';
            audioInput.value = '';
            audioMergeInput.value = '';
            videoInput.value = '';
            imageInput.value = '';
            audioBox.classList.remove('has-file');
            audioMergeBox.classList.remove('has-file');
            videoBox.classList.remove('has-file');
            imageBox.classList.remove('has-file');
            audioInfo.textContent = '';
            audioMergeInfo.textContent = '';
            videoInfo.textContent = '';
            imageInfo.textContent = '';
            
            videoModeBtn.classList.remove('active');
            imageModeBtn.classList.remove('active');
            audioMergeModeBtn.classList.remove('active');
            trimFramesContainer.style.display = 'none';
            
            if (mode === 'video') {
                videoModeBtn.classList.add('active');
                audioSectionBox.style.display = 'block';
                videoSectionBox.style.display = 'block';
                trimFramesContainer.style.display = 'block';
                submitBtn.textContent = 'Video erstellen';
            } else if (mode === 'image') {
                imageModeBtn.classList.add('active');
                audioSectionBox.style.display = 'block';
                imageSectionBox.style.display = 'block';
                submitBtn.textContent = 'Video erstellen';
            } else {
                audioMergeModeBtn.classList.add('active');
                audioMergeSectionBox.style.display = 'block';
                submitBtn.textContent = 'Audios zusammenführen';
            }
            checkForm();
        }
        
        imageInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                const file = e.target.files[0];
                imageInfo.textContent = `✓ ${file.name} (${formatFileSize(file.size)})`;
                imageBox.classList.add('has-file');
            } else {
                imageBox.classList.remove('has-file');
            }
            checkForm();
        });
        
        function formatFileSize(bytes) {
            const k = 1024;
            const sizes = ['Bytes', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
        }
        
        function checkForm() {
            if (currentMode === 'video') {
                submitBtn.disabled = !(audioInput.files.length > 0 && videoInput.files.length > 0);
            } else if (currentMode === 'image') {
                submitBtn.disabled = !(audioInput.files.length > 0 && imageInput.files.length > 0);
            } else {
                submitBtn.disabled = !(audioMergeInput.files.length > 1);
            }
        }
        
        audioInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                const file = e.target.files[0];
                audioInfo.textContent = `✓ ${file.name} (${formatFileSize(file.size)})`;
                audioBox.classList.add('has-file');
            }
            checkForm();
        });
        
        audioMergeInput.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                const fileCount = e.target.files.length;
                const totalSize = Array.from(e.target.files).reduce((sum, file) => sum + file.size, 0);
                const fileNames = Array.from(e.target.files).map(f => f.name).join(', ');
                
                audioMergeInfo.innerHTML = `
                    ✓ ${fileCount} Audios ausgewählt<br>
                    <small style="color: #666;">${formatFileSize(totalSize)} gesamt</small><br>
                    <small style="color: #666; display: block; margin-top: 3px;">${fileNames}</small>
                `;
                audioMergeBox.classList.add('has-file');
            } else {
                audioMergeBox.classList.remove('has-file');
                audioMergeInfo.textContent = '';
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

        // Update effect description when selection changes
        const effectSelect = document.getElementById('effectSelect');
        const effectDescription = document.getElementById('effectDescription');
        
        effectSelect.addEventListener('change', (e) => {
            const selectedEffect = e.target.value;
            effectDescription.textContent = effectDescriptions[selectedEffect] || 'Unbekannter Effekt';
        });
        
        async function handleUpload() {
            const maxSize = 500 * 1024 * 1024;
            const maxImageSize = 50 * 1024 * 1024;
            
            const formData = new FormData();
            formData.append('mode', currentMode);
            
            let uploadDescription = '';
            let selectedEffect = document.getElementById('effectSelect').value;
            formData.append('effect', selectedEffect);
            
            // Add trim_frames option if in video mode
            if (currentMode === 'video') {
                const trimFramesInput = document.getElementById('trimFramesInput');
                formData.append('trim_frames', trimFramesInput.value);
            }
            
            if (currentMode === 'video') {
                if (audioInput.files.length === 0) {
                    showError('Audio-Datei benötigt');
                    return;
                }
                if (audioInput.files[0].size > maxSize) {
                    showError(`Audio-Datei zu groß: ${formatFileSize(audioInput.files[0].size)} (max 500 MB)`);
                    return;
                }
                formData.append('audio', audioInput.files[0]);
                
                for (let i = 0; i < videoInput.files.length; i++) {
                    if (videoInput.files[i].size > maxSize) {
                        showError(`Video ${i+1} zu groß: ${formatFileSize(videoInput.files[i].size)} (max 500 MB)`);
                        return;
                    }
                    formData.append('videos', videoInput.files[i]);
                }
                
                uploadDescription = `1 Audio + ${videoInput.files.length} Video${videoInput.files.length > 1 ? 's' : ''}`;
            } else if (currentMode === 'image') {
                if (audioInput.files.length === 0) {
                    showError('Audio-Datei benötigt');
                    return;
                }
                if (audioInput.files[0].size > maxSize) {
                    showError(`Audio-Datei zu groß: ${formatFileSize(audioInput.files[0].size)} (max 500 MB)`);
                    return;
                }
                if (imageInput.files.length === 0) {
                    showError('Standbild benötigt');
                    return;
                }
                if (imageInput.files[0].size > maxImageSize) {
                    showError(`Bild zu groß: ${formatFileSize(imageInput.files[0].size)} (max 50 MB)`);
                    return;
                }
                formData.append('audio', audioInput.files[0]);
                formData.append('image', imageInput.files[0]);
                uploadDescription = `1 Audio + 1 Standbild`;
            } else {
                if (audioMergeInput.files.length < 2) {
                    showError('Bitte mindestens 2 Audiodateien auswählen');
                    return;
                }
                for (let i = 0; i < audioMergeInput.files.length; i++) {
                    if (audioMergeInput.files[i].size > maxSize) {
                        showError(`Audio ${i+1} zu groß: ${formatFileSize(audioMergeInput.files[i].size)} (max 500 MB)`);
                        return;
                    }
                    formData.append('audios', audioMergeInput.files[i]);
                }
                uploadDescription = `${audioMergeInput.files.length} Audios zusammenführen`;
            }
            
            resultDiv.style.display = 'block';
            resultDiv.className = 'result loading';
            
            const effectText = (currentMode !== 'audio' && selectedEffect !== 'none') ? ` + ${selectedEffect} Effekt` : '';
            
            resultDiv.innerHTML = `
                <div class="spinner"></div>
                <div><strong>Dateien werden hochgeladen...</strong></div>
                <div style="margin-top: 10px;">
                    ${uploadDescription}${effectText}
                </div>
            `;
            
            submitBtn.disabled = true;
            
            try {
                const response = await fetch('/upload', {
                    method: 'POST',
                    body: formData
                });
                const result = await response.json();
                
                if (!result.success) {
                    showError(result.error || 'Upload fehlgeschlagen');
                    submitBtn.disabled = false;
                    return;
                }
                
                const jobId = result.job_id;
                console.log('Job ID:', jobId);
                
                let modeInfo = '';
                if (result.mode === 'image') {
                    modeInfo = '<div style="margin-top: 5px; color: #667eea; font-weight: bold;">🖼️ Standbild-Modus</div>';
                } else if (result.mode === 'audio') {
                    modeInfo = '<div style="margin-top: 5px; color: #667eea; font-weight: bold;">🎧 Audios werden zusammengeführt</div>';
                } else if (result.video_count) {
                    modeInfo = `<div style="margin-top: 5px; color: #667eea; font-weight: bold;">${result.video_count} Videos werden zufällig gemischt!</div>`;
                }
                
                const effectInfo = (result.effect && result.effect !== 'none' && result.mode !== 'audio')
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
                
                const pollInterval = setInterval(async () => {
                    try {
                        const statusResponse = await fetch(`/status/${jobId}`);
                        const statusData = await statusResponse.json();
                        
                        if (!statusData.success) {
                            clearInterval(pollInterval);
                            showError('Fehler beim Abrufen des Status');
                            submitBtn.disabled = false;
                            return;
                        }
                        
                        const statusMsg = document.getElementById('statusMessage');
                        const progressBar = document.getElementById('progressBar');
                        const progressText = document.getElementById('progressText');
                        
                        if (statusMsg) statusMsg.textContent = statusData.message;
                        if (progressBar) progressBar.style.width = statusData.progress + '%';
                        if (progressText) progressText.textContent = statusData.progress + '%';
                        
                        if (statusData.status === 'complete') {
                            clearInterval(pollInterval);
                            
                            let modeBadge = '';
                            if (statusData.mode === 'image') {
                                modeBadge = '<br><span style="color: #667eea;">🖼️ Standbild-Modus</span>';
                            } else if (statusData.mode === 'audio') {
                                modeBadge = '<br><span style="color: #667eea;">🎧 Audio-Merge erfolgreich</span>';
                            } else if (statusData.video_count) {
                                modeBadge = `<br><span style="color: #667eea;">🎲 ${statusData.video_count} Videos zufällig gemischt</span>`;
                            }
                            
                            const effectBadge = (statusData.effect && statusData.effect !== 'none' && statusData.mode !== 'audio')
                                ? `<br><span style="color: #764ba2;">✨ Mit ${statusData.effect} Effekt</span>`
                                : '';
                            
                            let downloadOptions = '';
                            if (statusData.has_tracklist) {
                                if (statusData.mode === 'audio') {
                                    downloadOptions = `
                                        <div style="margin-top: 15px; display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                                            <a href="/download/${statusData.file_id}" class="download-btn" download>
                                                📦 ZIP (Audio + Tracklist)
                                            </a>
                                            <a href="/download-audio/${statusData.file_id}" class="download-btn" download style="background: #17a2b8;">
                                                🎧 Nur MP3
                                            </a>
                                        </div>
                                        <div style="margin-top: 10px;">
                                            <a href="/download-tracklist/${statusData.file_id}" class="download-btn" download style="width: 100%; background: #6c757d;">
                                                📝 Nur Trackliste
                                            </a>
                                        </div>
                                    `;
                                } else {
                                    downloadOptions = `
                                        <div style="margin-top: 15px; display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                                            <a href="/download/${statusData.file_id}" class="download-btn" download>
                                                📦 ZIP (Video + Tracklist)
                                            </a>
                                            <a href="/download-video/${statusData.file_id}" class="download-btn" download style="background: #17a2b8;">
                                                🎬 Nur Video
                                            </a>
                                        </div>
                                        <div style="margin-top: 10px;">
                                            <a href="/download-tracklist/${statusData.file_id}" class="download-btn" download style="width: 100%; background: #6c757d;">
                                                📝 Nur Trackliste
                                            </a>
                                        </div>
                                    `;
                                }
                            } else {
                                const downloadLabel = statusData.mode === 'audio' ? '⬇️ MP3 herunterladen' : '⬇️ Video herunterladen';
                                downloadOptions = `
                                    <a href="/download/${statusData.file_id}" class="download-btn" download>
                                        ${downloadLabel}
                                    </a>
                                `;
                            }
                            
                            resultDiv.className = 'result success';
                            resultDiv.innerHTML = `
                                <div style="text-align: center;">
                                    <div style="font-size: 3em; margin-bottom: 10px;">✅</div>
                                    <div><strong>${statusData.mode === 'audio' ? 'Audios erfolgreich zusammengeführt!' : 'Video erfolgreich erstellt!'}</strong></div>
                                    <div style="margin: 10px 0;">
                                        Größe: ${statusData.size}<br>
                                        Dauer: ${statusData.duration}${modeBadge}${effectBadge}
                                    </div>
                                    ${downloadOptions}
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

def seconds_to_hhmmss(seconds):
    """Konvertiert Sekunden zu HH:MM:SS Format"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

def trim_video_frames(input_path, output_path, frames_to_trim=7):
    """
    Trim N frames from the end of a video file.
    
    Args:
        input_path: Path to the input video file
        output_path: Path to save the trimmed video file
        frames_to_trim: Number of frames to trim from the end (default: 7)
    
    Returns:
        True if successful, raises exception otherwise
    """
    try:
        # Get video framerate using ffprobe
        cmd_fps = [
            'ffprobe', '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=r_frame_rate',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            input_path
        ]
        result_fps = subprocess.run(cmd_fps, capture_output=True, text=True, timeout=30)
        fps_str = result_fps.stdout.strip()
        
        # Parse framerate (format: "30/1" or "29.97")
        if '/' in fps_str:
            num, denom = map(float, fps_str.split('/'))
            fps = num / denom
        else:
            fps = float(fps_str)
        
        print(f"Video FPS: {fps}")
        
        # Get original duration
        original_duration = get_video_duration(input_path)
        print(f"Original duration: {original_duration} seconds")
        
        # Calculate duration to trim
        trim_seconds = frames_to_trim / fps
        new_duration = original_duration - trim_seconds
        
        print(f"Trimming {frames_to_trim} frames (~{trim_seconds:.3f} seconds) from end")
        print(f"New duration: {new_duration} seconds")
        
        if new_duration <= 0:
            raise Exception(f"Video too short to trim {frames_to_trim} frames")
        
        # Use FFmpeg to trim the video (stream copy for speed)
        cmd_trim = [
            'ffmpeg', '-y',
            '-i', input_path,
            '-t', str(new_duration),
            '-c:v', 'copy',
            '-c:a', 'copy',
            output_path
        ]
        
        print(f"Running trim: {' '.join(cmd_trim[:8])}...")
        result = subprocess.run(cmd_trim, capture_output=True, text=True, timeout=600)
        
        if result.returncode != 0:
            print(f"FFmpeg trim stderr: {result.stderr[-500:]}")
            raise Exception(f"FFmpeg trim error: {result.stderr[-200:]}")
        
        print(f"Video trimmed successfully: {format_size(os.path.getsize(output_path))}")
        return True
        
    except Exception as e:
        print(f"Error trimming video: {e}")
        raise

def create_tracklist(audio_path, file_id, noise_threshold=-30, silence_duration=1):
    """
    Erstellt eine Trackliste basierend auf erkannten Liedwechseln
    Format: MM:SS - Song Name
    
    Args:
        audio_path: Pfad zur Audio-Datei
        file_id: Eindeutige ID für die Datei
        noise_threshold: Dezibel-Schwelle für Stille
        silence_duration: Mindestdauer der Stille
    
    Returns:
        Pfad zur erstellten TXT-Datei
    """
    try:
        print(f"[Tracklist] Creating tracklist for {file_id}")
        
        # FFmpeg Befehl zum Erkennen von Stille
        cmd = [
            'ffmpeg', '-i', audio_path,
            '-af', f'silencedetect=noise={noise_threshold}dB:d={silence_duration}',
            '-f', 'null', '-'
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300
        )
        
        # Parse silence detections
        stderr_output = result.stderr
        silence_starts = re.findall(r'silence_start: ([\d.]+)', stderr_output)
        silence_ends = re.findall(r'silence_end: ([\d.]+)', stderr_output)
        
        # Get audio duration
        audio_duration = get_video_duration(audio_path)
        
        # Create list of track start times
        track_times = []
        
        # First track starts at 0
        track_times.append(0.0)
        
        # Additional tracks start after each detected silence
        for i in range(len(silence_ends)):
            if i < len(silence_ends):
                start_time = float(silence_ends[i])
                # Only add if it's before the end of the audio
                if start_time < audio_duration:
                    track_times.append(start_time)
        
        # Remove duplicates and sort
        track_times = sorted(list(set(track_times)))
        
        print(f"[Tracklist] Detected {len(track_times)} tracks")
        
        # Create tracklist content
        tracklist_content = []
        
        for i, track_time in enumerate(track_times, 1):
            time_str = seconds_to_hhmmss(track_time)
            # Generic track name - users can edit manually
            song_name = f"Track {i}"
            tracklist_content.append(f"{time_str} - {song_name}")
        
        # Write to file
        tracklist_path = os.path.join(OUTPUT_FOLDER, f"{file_id}_tracklist.txt")
        with open(tracklist_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(tracklist_content))
        
        print(f"[Tracklist] Created: {tracklist_path}")
        print(f"[Tracklist] Total tracks: {len(track_times)}")
        return tracklist_path
        
    except Exception as e:
        print(f"[Tracklist] Error creating tracklist: {e}")
        import traceback
        print(traceback.format_exc())
        return None


def create_audio_tracklist(audio_paths, file_id):
    """Create a simple tracklist from multiple audio files by file order."""
    try:
        current_time = 0.0
        tracklist_content = []

        for idx, audio_path in enumerate(audio_paths, 1):
            duration = get_video_duration(audio_path)
            time_str = seconds_to_hhmmss(current_time)
            song_name = os.path.basename(audio_path)
            tracklist_content.append(f"{time_str} - {song_name}")
            current_time += duration

        tracklist_path = os.path.join(OUTPUT_FOLDER, f"{file_id}_tracklist.txt")
        with open(tracklist_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(tracklist_content))

        print(f"[Audio Tracklist] Created: {tracklist_path}")
        return tracklist_path
    except Exception as e:
        print(f"[Audio Tracklist] Error: {e}")
        import traceback
        print(traceback.format_exc())
        return None


def merge_audio_files(audio_paths, output_path, status_path=None):
    """Merge multiple audio files into a single MP3."""
    try:
        if status_path:
            update_status(status_path, 'processing', 15, 'Analysiere Audiodateien...')

        duration = sum(get_video_duration(path) for path in audio_paths)
        print(f"Total audio duration: {duration} seconds ({duration/60:.1f} minutes)")

        if status_path:
            update_status(status_path, 'processing', 30, 'Erstelle MP3...')

        cmd = ['ffmpeg', '-y']
        for path in audio_paths:
            cmd.extend(['-i', path])

        concat_inputs = ''.join(f'[{i}:a:0]' for i in range(len(audio_paths)))
        concat_filter = f'{concat_inputs}concat=n={len(audio_paths)}:v=0:a=1[out]'
        cmd.extend([
            '-filter_complex', concat_filter,
            '-map', '[out]',
            '-c:a', 'libmp3lame',
            '-b:a', '192k',
            '-ar', '44100',
            '-ac', '2',
            output_path
        ])

        print(f"Running: {' '.join(cmd[:10])}...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)

        if result.returncode != 0:
            print(f"FFmpeg merge stderr: {result.stderr[-500:]}")
            if os.path.exists(output_path):
                os.remove(output_path)
            raise Exception(f"FFmpeg audio merge error: {result.stderr[-200:]}")

        print(f"Audio merge completed: {output_path}")
        if status_path:
            update_status(status_path, 'processing', 70, 'MP3 wird finalisiert...')
        return True
    except subprocess.TimeoutExpired as e:
        print(f"FFmpeg timeout after {e.timeout} seconds")
        if os.path.exists(output_path):
            os.remove(output_path)
        raise Exception(f"Audio processing timeout - took longer than {e.timeout / 60:.0f} minutes")
    except Exception as e:
        print(f"Audio merge error: {e}")
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except:
                pass
        raise


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
        if effect != 'none' and effect in VIDEO_EFFECTS and VIDEO_EFFECTS[effect]['filter']:
            print(f"Applying video filter: {VIDEO_EFFECTS[effect]['filter']}")
            cmd_image_to_video.extend([
                '-vf', VIDEO_EFFECTS[effect]['filter']
            ])
        
        # Add encoding parameters
        cmd_image_to_video.extend([
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', '28',
            '-profile:v', 'high',
            '-level', '4.2',
            '-pix_fmt', 'yuv420p',
            '-maxrate', '10M',
            '-bufsize', '20M',
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
            timeout=7200
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

def merge_video_audio(audio_path, video_paths, output_path, status_path=None, effect='none', trim_frames=False):
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
        
        # Trim frames from end of videos if enabled
        if trim_frames > 0:
            print(f"Trimming {trim_frames} frames from end of videos...")
            if status_path:
                update_status(status_path, 'processing', 12, f'Schneide {trim_frames} Frames ab...')
            
            trimmed_video_paths = []
            for idx, vp in enumerate(video_paths):
                print(f"Trimming video {idx+1}/{len(video_paths)}: {vp}")
                # Create a trimmed version with _trimmed suffix
                base, ext = os.path.splitext(vp)
                trimmed_path = f"{base}_trimmed{ext}"
                try:
                    trim_video_frames(vp, trimmed_path, frames_to_trim=trim_frames)
                    # Replace original with trimmed version
                    os.remove(vp)
                    os.rename(trimmed_path, vp)
                    trimmed_video_paths.append(vp)
                    print(f"Video {idx+1} trimmed successfully")
                except Exception as e:
                    print(f"Warning: Failed to trim video {idx+1}: {e}")
                    # Continue with untrimmed video
                    trimmed_video_paths.append(vp)
            
            video_paths = trimmed_video_paths
        
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
        if effect != 'none' and effect in VIDEO_EFFECTS and VIDEO_EFFECTS[effect]['filter']:
            print(f"Applying video filter: {VIDEO_EFFECTS[effect]['filter']}")
            cmd_concat.extend([
                '-vf', VIDEO_EFFECTS[effect]['filter']
            ])
        
        # Add encoding parameters
        cmd_concat.extend([
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', '28',
            '-profile:v', 'high',
            '-level', '4.2',
            '-pix_fmt', 'yuv420p',
            '-maxrate', '10M',
            '-bufsize', '20M',
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
    audio_paths = []
    video_paths = []
    image_path = None
    
    try:
        print("=== UPLOAD START ===")
        
        mode = request.form.get('mode', 'video')  # 'video', 'image' or 'audio'
        print(f"Mode: {mode}")
        
        # Get selected effect
        effect = request.form.get('effect', 'none')
        if effect not in VIDEO_EFFECTS:
            effect = 'none'
        print(f"Selected effect: {effect}")
        
        # Get trim_frames option (only relevant in video mode)
        trim_frames = int(request.form.get('trim_frames', '7'))
        print(f"Trim frames count: {trim_frames}")
        
        # Generate unique ID
        file_id = str(uuid.uuid4())
        print(f"Generated file_id: {file_id}")
        
        if mode == 'audio':
            if 'audios' not in request.files:
                print("ERROR: Missing audio files")
                return jsonify({'success': False, 'error': 'Mindestens 2 Audiodateien benötigt'}), 400
            
            audio_files = request.files.getlist('audios')
            print(f"Audio files: {len(audio_files)} file(s)")
            if len(audio_files) < 2:
                print("ERROR: Not enough audio files")
                return jsonify({'success': False, 'error': 'Mindestens 2 Audiodateien benötigt'}), 400
            
            for idx, audio_file in enumerate(audio_files):
                if audio_file.filename == '':
                    continue
                audio_ext = os.path.splitext(audio_file.filename)[1] or '.mp3'
                path = os.path.join(UPLOAD_FOLDER, f"{file_id}_audio_{idx}{audio_ext}")
                print(f"Saving audio {idx+1}/{len(audio_files)}: {audio_file.filename}")
                audio_file.save(path)
                print(f"Audio {idx+1} saved: {os.path.getsize(path)} bytes")
                audio_paths.append(path)
            
            if len(audio_paths) < 2:
                print("ERROR: Not enough valid audio files")
                return jsonify({'success': False, 'error': 'Mindestens 2 gültige Audiodateien benötigt'}), 400
        else:
            if 'audio' not in request.files:
                print("ERROR: Missing audio file")
                return jsonify({'success': False, 'error': 'Audio-Datei benötigt'}), 400
            
            audio_file = request.files['audio']
            print(f"Audio file: {audio_file.filename}")
            if audio_file.filename == '':
                print("ERROR: Empty audio filename")
                return jsonify({'success': False, 'error': 'Leere Audio-Datei'}), 400
            
            audio_ext = os.path.splitext(audio_file.filename)[1] or '.mp3'
            audio_path = os.path.join(UPLOAD_FOLDER, f"{file_id}_audio{audio_ext}")
            print(f"Saving audio to: {audio_path}")
            audio_file.save(audio_path)
            print(f"Audio saved: {os.path.getsize(audio_path)} bytes")
        
            # Handle mode-specific files
        if mode == 'image':
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
        elif mode == 'video':
            if 'videos' not in request.files:
                print("ERROR: Missing video files")
                return jsonify({'success': False, 'error': 'Mindestens 1 Video benötigt'}), 400
            
            video_files = request.files.getlist('videos')
            print(f"Video files: {len(video_files)} file(s)")
            
            if len(video_files) == 0:
                print("ERROR: No video files")
                return jsonify({'success': False, 'error': 'Mindestens 1 Video benötigt'}), 400
            
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
        
        output_path = os.path.join(OUTPUT_FOLDER, f"{file_id}.{ 'mp3' if mode == 'audio' else 'mp4' }")
        
        # Create status file
        status_path = os.path.join(OUTPUT_FOLDER, f"{file_id}_status.json")
        status_data = {
            'status': 'processing',
            'progress': 0,
            'message': 'Upload erfolgreich - Verarbeitung startet...',
            'file_id': file_id,
            'mode': mode,
            'effect': effect,
            'trim_count': trim_frames if mode == 'video' else 0
        }
        
        if mode == 'video':
            status_data['video_count'] = len(video_paths)
        
        with open(status_path, 'w') as f:
            json.dump(status_data, f)
        
        # Start background processing
        if mode == 'image':
            mode_desc = 'Standbild'
        elif mode == 'audio':
            mode_desc = 'Audio-Zusammenführung'
        else:
            mode_desc = f"{len(video_paths)} video(s)"
        print(f"Starting background processing with {mode_desc} and '{effect}' effect...")
        
        thread = threading.Thread(
            target=process_video_background,
            args=(file_id, audio_path, audio_paths if mode == 'audio' else [], video_paths if mode == 'video' else None, image_path if mode == 'image' else None, output_path, status_path, effect, mode, trim_frames if mode == 'video' else False)
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

def process_video_background(file_id, audio_path, audio_paths, video_paths, image_path, output_path, status_path, effect='none', mode='video', trim_frames=False):
    """Background processing function"""
    try:
        if mode == 'image':
            mode_desc = "Standbild"
        elif mode == 'audio':
            mode_desc = "Audio-Zusammenführung"
        else:
            mode_desc = f"{len(video_paths)} video(s)"
        print(f"[Background] Starting merge for {file_id} with {mode_desc} and '{effect}' effect")
        
        # Update status: Starting
        effect_text = f' mit {effect} Effekt' if effect != 'none' else ''
        
        if mode == 'image':
            update_status(status_path, 'processing', 10, f'Standbild wird verarbeitet{effect_text}...')
            merge_video_audio_from_image(audio_path, image_path, output_path, status_path, effect)
        elif mode == 'audio':
            update_status(status_path, 'processing', 10, 'Analysiere Audiodateien...')
            merge_audio_files(audio_paths, output_path, status_path)
        else:
            update_status(status_path, 'processing', 10, f'Analysiere {len(video_paths)} Video(s){effect_text}...')
            merge_video_audio(audio_path, video_paths, output_path, status_path, effect, trim_frames)
        
        # Get file info
        file_size = os.path.getsize(output_path)
        duration = get_video_duration(output_path)
        
        # Create tracklist from original audio
        print("[Background] Creating tracklist...")
        update_status(status_path, 'processing', 90, 'Erstelle Trackliste...')
        if mode == 'audio':
            tracklist_path = create_audio_tracklist(audio_paths, file_id)
        else:
            tracklist_path = create_tracklist(audio_path, file_id)
        
        # Clean up input files
        print("[Background] Cleaning up input files...")
        if mode == 'audio':
            for ap in audio_paths:
                if os.path.exists(ap):
                    os.remove(ap)
        else:
            if os.path.exists(audio_path):
                os.remove(audio_path)
        
        if mode == 'video':
            for vp in video_paths:
                if os.path.exists(vp):
                    os.remove(vp)
        elif mode == 'image':
            if image_path and os.path.exists(image_path):
                os.remove(image_path)
        
        # Update status: Complete
        complete_data = {
            'file_id': file_id,
            'size': format_size(file_size),
            'duration': format_duration(duration),
            'file_size_bytes': file_size,
            'effect': effect,
            'mode': mode,
            'has_tracklist': tracklist_path is not None
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
            if mode == 'audio':
                for ap in audio_paths:
                    if os.path.exists(ap):
                        os.remove(ap)
            elif audio_path and os.path.exists(audio_path):
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
    """Download merged output and tracklist as ZIP"""
    try:
        mp4_path = os.path.join(OUTPUT_FOLDER, f"{file_id}.mp4")
        mp3_path = os.path.join(OUTPUT_FOLDER, f"{file_id}.mp3")
        tracklist_path = os.path.join(OUTPUT_FOLDER, f"{file_id}_tracklist.txt")

        file_path = mp3_path if os.path.exists(mp3_path) else mp4_path if os.path.exists(mp4_path) else None
        if not file_path:
            return "Datei nicht gefunden oder abgelaufen", 404

        has_tracklist = os.path.exists(tracklist_path)
        if has_tracklist:
            print(f"[Download] Creating ZIP for {file_id} with output and tracklist")
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                arcname = os.path.basename(file_path)
                zip_file.write(file_path, arcname=f"merged_{file_id}{os.path.splitext(file_path)[1]}")
                zip_file.write(tracklist_path, arcname=f"tracklist_{file_id}.txt")
            zip_buffer.seek(0)
            return send_file(
                zip_buffer,
                mimetype='application/zip',
                as_attachment=True,
                download_name=f'output_with_tracklist_{file_id}.zip'
            )

        mimetype = 'audio/mpeg' if file_path.endswith('.mp3') else 'video/mp4'
        download_name = f"merged_output_{file_id}{os.path.splitext(file_path)[1]}"
        return send_file(
            file_path,
            mimetype=mimetype,
            as_attachment=True,
            download_name=download_name
        )
    except Exception as e:
        print(f"Download error: {e}")
        return "Error downloading file", 500

@app.route('/download-audio/<file_id>')
def download_audio(file_id):
    """Download only the MP3 audio file"""
    try:
        audio_path = os.path.join(OUTPUT_FOLDER, f"{file_id}.mp3")
        if not os.path.exists(audio_path):
            return "Datei nicht gefunden oder abgelaufen", 404
        return send_file(
            audio_path,
            mimetype='audio/mpeg',
            as_attachment=True,
            download_name=f'merged_audio_{file_id}.mp3'
        )
    except Exception as e:
        print(f"Download error: {e}")
        return "Error downloading file", 500

@app.route('/download-video/<file_id>')
def download_video(file_id):
    """Download only the video file"""
    try:
        video_path = os.path.join(OUTPUT_FOLDER, f"{file_id}.mp4")
        
        if not os.path.exists(video_path):
            return "File not found or expired", 404
        
        return send_file(
            video_path,
            mimetype='video/mp4',
            as_attachment=True,
            download_name=f'merged_video_{file_id}.mp4'
        )
    except Exception as e:
        print(f"Download error: {e}")
        return "Error downloading file", 500

@app.route('/download-tracklist/<file_id>')
def download_tracklist(file_id):
    """Download only the tracklist file"""
    try:
        tracklist_path = os.path.join(OUTPUT_FOLDER, f"{file_id}_tracklist.txt")
        
        if not os.path.exists(tracklist_path):
            return "Tracklist not found", 404
        
        return send_file(
            tracklist_path,
            mimetype='text/plain',
            as_attachment=True,
            download_name=f'tracklist_{file_id}.txt'
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
