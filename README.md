# Video-Audio-Merger

Eine Flask-Web-Anwendung zum Kombinieren von Audio-Dateien mit Video-Loops oder statischen Bildern unter Verwendung von FFmpeg. Die Anwendung bietet zwei verschiedene Verarbeitungsmodi, Video-Effekte und asynchrone Job-basierte Verarbeitung mit Echtzeit-Status-Tracking.

## Features

- **Drei Verarbeitungsmodi**:
  - Video-Modus: Mehrere Videos zufällig in Sequenz schalten und mit Audio kombinieren
  - Image-Modus: Statisches Bild zur Audio-Länge erweitern
  - Audio-Merge-Modus: Mehrere Audio-Dateien sequentiell zusammenführen

- **Video-Effekte**: Über 100 verschiedene FFmpeg-basierte Effekte (Vignette, Noise, Zoom, etc.)
- **Konfigurierbares Frame-Trimming**: Entferne eine benutzerdefinierte Anzahl von Frames vom Ende jedes Videos (Standard: 7 für Veo 3.1 Kompatibilität)
- **Asynchrone Verarbeitung**: Job-basierte Hintergrundverarbeitung mit Echtzeit-Status-Updates
- **Datei-Upload**: Unterstützt große Dateien (bis 500 MB Video/Audio, 50 MB Bilder)
- **Docker-Unterstützung**: Einfache Bereitstellung mit Docker Compose
- **Automatische Bereinigung**: Temporäre Dateien werden nach 24 Stunden entfernt

## Installation

### Voraussetzungen

- Docker und Docker Compose
- Mindestens 2 GB RAM (empfohlen)
- FFmpeg (wird automatisch in Docker installiert)

### Lokale Entwicklung

```bash
# Repository klonen
git clone https://github.com/LarsAPI/Video-Audio-Merger.git
cd Video-Audio-Merger

# Mit Docker starten
docker-compose up -d

# Anwendung ist verfügbar unter http://localhost:5001
```

### Ohne Docker

```bash
# Systemabhängigkeiten installieren
sudo apt-get update
sudo apt-get install ffmpeg python3 python3-pip

# Python-Abhängigkeiten installieren
pip install flask gunicorn

# Anwendung starten
python app.py
# Verfügbar unter http://localhost:5000
```

## Verwendung

### Web-Interface

1. Öffne die Anwendung in deinem Browser
2. Wähle den gewünschten Modus:
   - **Video-Modus**: Lade Videos und Audio hoch
   - **Image-Modus**: Lade ein Bild und Audio hoch
   - **Audio-Merge-Modus**: Lade mehrere Audio-Dateien hoch

3. Wähle optional einen Video-Effekt aus der Dropdown-Liste
4. Im Video-Modus: Gib die Anzahl der zu entfernenden Frames ein (Standard: 7)
5. Klicke auf "Video erstellen"
6. Warte auf die Verarbeitung (Status wird alle 5 Sekunden aktualisiert)
7. Lade das fertige Video herunter

### API-Endpunkte

- `GET /`: Hauptseite mit Upload-Formular
- `POST /upload`: Dateien hochladen und Verarbeitung starten
- `GET /status/<job_id>`: Verarbeitungsstatus abrufen
- `GET /download/<file_id>`: Fertige Datei herunterladen
- `GET /health`: Healthcheck-Endpunkt

## Modi im Detail

### Video-Modus
- Akzeptiert mehrere Video-Dateien
- Videos werden zufällig in eine Sequenz geschaltet
- Automatische Loop-Erstellung zur Audio-Länge
- Optionales Frame-Trimming vom Ende jedes Videos
- Video-Effekte werden während der Konkatenation angewendet

### Image-Modus
- Akzeptiert eine einzelne Bild-Datei
- Bild wird zur Audio-Länge erweitert
- Gleiche Video-Effekte verfügbar wie im Video-Modus

### Audio-Merge-Modus
- Kombiniert 2+ Audio-Dateien sequentiell
- Ausgabe als MP3-Datei
- Keine Video-Verarbeitung

## Technische Details

### FFmpeg-Konfiguration
- **Video-Codec**: H.264 (libx264)
- **Audio-Codec**: AAC
- **Preset**: veryfast (schnellere Kodierung)
- **Profile**: high/4.2 (Kompatibilität)
- **Bitrate**: Max 4M, Buffer 8M, GOP 250 Frames
- **Streaming**: +faststart für Web-Playback

### Verarbeitungs-Pipeline
1. **Upload**: Dateien werden in `/tmp/uploads` gespeichert
2. **Trimming**: Frames vom Ende entfernen (Video-Modus)
3. **Konkatenation/Looping**: Videos kombinieren oder Bild erweitern
4. **Effekt-Anwendung**: FFmpeg-Filter während Kodierung
5. **Audio-Merge**: Video-Stream mit Audio kombinieren
6. **Ausgabe**: MP4-Datei in `/tmp/output`

### Leistungsdaten
- **Video-Modus**: ~20-30 Minuten für typische Videos
- **Image-Modus**: ~5-10 Minuten
- **Worker**: 2 Gunicorn-Worker
- **Timeout**: 10 Minuten pro Job
- **Speicherlimit**: 2 GB

### Sicherheit
- Dateigrößen-Limits (500MB Video/Audio, 50MB Bilder)
- Automatische Bereinigung temporärer Dateien
- Serverseitige Validierung von Eingaben

## Entwicklung

### Projekt-Struktur
```
app.py              # Monolithische Flask-Anwendung
Dockerfile          # Python 3.11 + FFmpeg
docker-compose.yml  # Umbrel-kompatibles Setup
README.md           # Diese Datei
```

### Neue Video-Effekte hinzufügen
1. Füge Filter zur `VIDEO_EFFECTS` Dict in `app.py` hinzu
2. Aktualisiere die HTML-Select-Option
3. Teste mit beiden Modi

### Code-Änderungen
- Alle Änderungen erfolgen in der einzelnen `app.py`-Datei
- Verwende `python -m py_compile app.py` für Syntax-Checks
- Teste mit kleinen Dateien für schnelle Iterationen

## Fehlerbehebung

### Häufige Probleme
- **FFmpeg-Fehler**: Stelle sicher, dass FFmpeg installiert ist
- **Speicherfehler**: Erhöhe RAM-Limit in docker-compose.yml
- **Timeout**: Lange Videos brauchen mehr Zeit
- **Dateigröße**: Überprüfe Upload-Limits

### Logs
```bash
# Docker-Logs anzeigen
docker-compose logs -f video-merger

# Container betreten
docker-compose exec video-merger bash
```

## Lizenz

Dieses Projekt ist Open-Source. Bitte beachte die FFmpeg-Lizenz für verwendete Bibliotheken.
