# 🚗 Accident Reconstruction Backend

AI-powered CCTV accident analysis system with Kestra workflow orchestration.

## 🎯 Features

- **Video Processing**: YOLO + ByteTrack for vehicle detection & tracking
- **Collision Detection**: Automatic collision analysis with severity assessment
- **Homography Calibration**: Map pixel coordinates to real-world positions
- **AI Analysis**: Google Gemini for detailed accident reports
- **PDF Generation**: Professional reports with collision screenshots
- **Audio Narration**: English + Hindi audio summaries (ElevenLabs)
- **Kestra Orchestration**: Full workflow automation

---

## 🚀 Quick Setup

### 1. Clone & Navigate
```bash
cd wemakedevs/accident-backend
```

### 2. Create Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip3 install -r requirements.txt
```

### 4. Create `.env` File
Create a `.env` file in the root directory:

```env
# Required
SECRET_KEY=your-secret-key-make-it-long-and-random-at-least-32-chars
DATABASE_URL=postgresql+asyncpg://username:password@your-neon-host/dbname?sslmode=require

# Cloudinary (for video/file uploads)
CLOUDINARY_CLOUD_NAME=your-cloud-name
CLOUDINARY_API_KEY=your-api-key
CLOUDINARY_API_SECRET=your-api-secret

# Optional
DEBUG=true
KESTRA_API_URL=http://localhost:8080/api/v1
```

### 5. Run Database Migrations
```bash
alembic upgrade head
```

### 6. Start the Server
```bash
python3 -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Server runs at: **http://localhost:8000**  
API Docs: **http://localhost:8000/docs**

---

## 🐳 Kestra Setup

### 1. Start Kestra
```bash
docker run -d --name kestra -p 8080:8080 --user=root \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v /tmp:/tmp \
  kestra/kestra:latest server local
```

Or if container exists:
```bash
docker start kestra
```

Open: **http://localhost:8080**

### 2. Add KV Store Keys
In Kestra UI: **Namespaces** → **accident.reconstruction** → **KV Store**

| Key | Value |
|-----|-------|
| `GEMINI_API_KEY` | Your Google Gemini API key |
| `CLOUDINARY_CLOUD_NAME` | Your Cloudinary cloud name |
| `CLOUDINARY_API_KEY` | Your Cloudinary API key |
| `CLOUDINARY_API_SECRET` | Your Cloudinary API secret |
| `ELEVENLABS_API_KEY` | Your ElevenLabs API key |

### 3. Import Workflow
1. Go to **Flows** → **Create**
2. Copy content from `kestra/workflows/accident-analysis.yaml`
3. Save

### 4. Run Workflow
Execute with inputs:
- `project_id`: Your project UUID
- `api_base_url`: `http://host.docker.internal:8000`
- `auth_token`: Your JWT token

---

## 🧪 API Testing Guide

### Health Check
```bash
curl http://localhost:8000/
```

### Signup
```bash
curl -X POST http://localhost:8000/api/v1/signup \
  -H "Content-Type: application/json" \
  -d '{"email": "test@test.com", "password": "password123", "full_name": "Test User"}'
```

### Login (Get Token)
```bash
curl -X POST http://localhost:8000/api/v1/login/access-token \
  -F "username=test@test.com" \
  -F "password=password123"
```
Save the `access_token` from response!

### Create Project
```bash
curl -X POST http://localhost:8000/api/v1/projects/ \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title": "Test Accident", "description": "Testing"}'
```

### Upload Video
```bash
curl -X POST "http://localhost:8000/api/v1/projects/PROJECT_ID/upload-video" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@/path/to/video.mp4"
```

### Start Processing
```bash
curl -X POST http://localhost:8000/api/v1/processing/start \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"project_id": "PROJECT_ID"}'
```

### Get Collisions
```bash
curl http://localhost:8000/api/v1/analysis/project/PROJECT_ID/collisions \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Kestra Status
```bash
curl http://localhost:8000/api/v1/kestra/project/PROJECT_ID/status \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## 📁 Project Structure

```
accident-backend/
├── src/
│   ├── api/
│   │   ├── routes/
│   │   │   ├── login_route.py      # Auth endpoints
│   │   │   ├── projects_route.py   # Project CRUD
│   │   │   ├── processing_route.py # Video processing
│   │   │   ├── analysis_route.py   # Collision analysis
│   │   │   ├── homography_route.py # Calibration
│   │   │   └── kestra_route.py     # Kestra integration
│   │   └── deps.py                 # Dependencies (auth, db)
│   ├── core/
│   │   ├── config.py               # Settings
│   │   ├── database.py             # DB connection
│   │   └── security.py             # JWT handling
│   ├── models/                     # SQLAlchemy models
│   ├── services/
│   │   ├── video_processor.py      # YOLO + ByteTrack
│   │   ├── collision_detector.py   # Collision analysis
│   │   └── homography_solver.py    # Calibration math
│   └── main.py                     # FastAPI app
├── kestra/
│   └── workflows/
│       └── accident-analysis.yaml  # Main Kestra workflow
├── alembic/                        # DB migrations
├── requirements.txt
└── .env                            # Environment variables
```

---

## 🎬 How PDF & Audio Generation Works (Kestra + Docker)

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        KESTRA WORKFLOW                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. Check Status ──► 2. Get Collisions ──► 3. Get Screenshot   │
│         │                    │                     │            │
│         ▼                    ▼                     ▼            │
│  ┌─────────────┐      ┌─────────────┐       ┌─────────────┐    │
│  │ HTTP Request│      │ HTTP Request│       │ HTTP Request│    │
│  │ to Backend  │      │ to Backend  │       │ to Backend  │    │
│  └─────────────┘      └─────────────┘       └─────────────┘    │
│                                                                 │
│  4. AI Analysis (Gemini API) ──► 5. Save to DB                 │
│         │                              │                        │
│         ▼                              ▼                        │
│  ┌─────────────┐              ┌─────────────┐                  │
│  │ HTTP Request│              │ HTTP Request│                  │
│  │ to Gemini   │              │ to Backend  │                  │
│  └─────────────┘              └─────────────┘                  │
│                                                                 │
│  6. Generate PDF ─────────► 7. Generate Audio                  │
│         │                          │                            │
│         ▼                          ▼                            │
│  ┌──────────────────┐      ┌──────────────────┐                │
│  │  DOCKER CONTAINER │      │  DOCKER CONTAINER │                │
│  │  python:3.11-slim │      │  python:3.11-slim │                │
│  │                   │      │                   │                │
│  │  • reportlab      │      │  • ElevenLabs API │                │
│  │  • pillow         │      │  • Gemini (Hindi) │                │
│  │  • cloudinary     │      │  • cloudinary     │                │
│  └────────┬─────────┘      └────────┬─────────┘                │
│           │                         │                           │
│           ▼                         ▼                           │
│     Upload to Cloudinary      Upload to Cloudinary              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### PDF Generation (Docker Container)

**What happens:**
1. Kestra spins up a fresh `python:3.11-slim` Docker container
2. Installs: `reportlab`, `pillow`, `cloudinary`, `requests`
3. Fetches collision screenshot from backend API
4. Generates professional PDF with:
   - Project metadata table
   - Collision screenshot image
   - AI analysis text (formatted)
   - Footer with timestamps
5. Uploads PDF to Cloudinary
6. Returns PDF URL to Kestra

**Key Code (from `accident-analysis.yaml`):**
```yaml
- id: generate_pdf
  type: io.kestra.plugin.scripts.python.Script
  containerImage: python:3.11-slim  # 🐳 Docker container!
  beforeCommands:
    - pip install reportlab pillow cloudinary kestra requests
  inputFiles:
    summary.txt: "{{json(outputs.ai_analysis.body)...}}"
  env:
    CLOUDINARY_CLOUD_NAME: "{{kv('CLOUDINARY_CLOUD_NAME')}}"
    # ... other env vars from KV Store
  script: |
    # Python code runs INSIDE the container
    from reportlab.platypus import SimpleDocTemplate, Paragraph...
    # Generate PDF, upload to Cloudinary
```

### Audio Generation (Docker Container)

**What happens:**
1. Kestra spins up another `python:3.11-slim` Docker container
2. Installs: `requests`, `cloudinary`
3. Takes AI summary text, cleans markdown formatting
4. **English Audio:**
   - Sends text to ElevenLabs API
   - Voice: `21m00Tcm4TlvDq8ikWAM` (Rachel)
   - Model: `eleven_monolingual_v1`
5. **Hindi Audio:**
   - First translates to Hindi using Gemini API
   - Sends Hindi text to ElevenLabs
   - Voice: `trxRCYtDC6qFREKq6Ek2` (Hindi voice)
   - Model: `eleven_multilingual_v2`
6. Uploads both MP3s to Cloudinary
7. Returns audio URLs to Kestra

**Key Code (from `accident-analysis.yaml`):**
```yaml
- id: generate_audio
  type: io.kestra.plugin.scripts.python.Script
  containerImage: python:3.11-slim  # 🐳 Another Docker container!
  beforeCommands:
    - pip install requests cloudinary kestra
  env:
    ELEVENLABS_API_KEY: "{{kv('ELEVENLABS_API_KEY')}}"
    GEMINI_API_KEY: "{{kv('GEMINI_API_KEY')}}"
  script: |
    # Call ElevenLabs TTS API
    response = requests.post(
        "https://api.elevenlabs.io/v1/text-to-speech/...",
        json={"text": english_text, "model_id": "eleven_monolingual_v1"}
    )
```

### Why Docker Containers?

| Benefit | Explanation |
|---------|-------------|
| **Isolation** | Each task runs in clean environment |
| **Dependencies** | Install any Python package without affecting host |
| **Reproducibility** | Same `python:3.11-slim` image every time |
| **Security** | Sandboxed execution |
| **Scalability** | Kestra can run multiple containers in parallel |

### Flow Summary

```
Kestra Workflow Execution:
│
├─► Step 1-5: HTTP Requests (lightweight, no containers)
│
├─► Step 6: generate_pdf
│   └─► Docker: python:3.11-slim
│       └─► pip install reportlab pillow cloudinary
│       └─► Run Python script
│       └─► Upload PDF → Cloudinary
│       └─► Container destroyed ✓
│
└─► Step 7: generate_audio
    └─► Docker: python:3.11-slim
        └─► pip install requests cloudinary
        └─► Call ElevenLabs API (English)
        └─► Call Gemini API (translate to Hindi)
        └─► Call ElevenLabs API (Hindi)
        └─► Upload MP3s → Cloudinary
        └─► Container destroyed ✓
```

---

## 🔧 Troubleshooting

### "No module named 'xyz'"
```bash
pip3 install xyz
```

### bcrypt/passlib error
```bash
pip3 install bcrypt==4.0.1
```

### Database tables don't exist
```bash
alembic upgrade head
```

### Kestra can't connect to backend
Use `http://host.docker.internal:8000` (not `localhost`)

---

## 📝 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/signup` | Create user |
| POST | `/api/v1/login/access-token` | Get JWT token |
| GET | `/api/v1/projects/` | List projects |
| POST | `/api/v1/projects/` | Create project |
| POST | `/api/v1/projects/{id}/upload-video` | Upload video |
| POST | `/api/v1/processing/start` | Start processing |
| GET | `/api/v1/processing/status/{run_id}` | Get status |
| GET | `/api/v1/analysis/project/{id}/collisions` | Get collisions |
| POST | `/api/v1/homography/project/{id}/session` | Create calibration |
| PUT | `/api/v1/homography/session/{id}/pairs` | Add points |
| POST | `/api/v1/homography/session/{id}/solve` | Solve matrix |
| GET | `/api/v1/kestra/project/{id}/status` | Kestra status |
| GET | `/api/v1/kestra/project/{id}/collision-data` | Collision data |
| POST | `/api/v1/kestra/project/{id}/save-summary` | Save AI summary |

---

## 🏆 Hackathon Tracks

- **Kestra Track**: Full workflow orchestration with AI analysis
- **Neon Track**: PostgreSQL database with async support

---

## 📄 License

MIT

