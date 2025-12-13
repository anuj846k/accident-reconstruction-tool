# Accident Reconstruction Tool - Complete Guide

## 🎯 Why This Project Exists

### The Problem

After a car crash, people need answers:
- **When did it happen?** (exact time)
- **How fast were the cars going?**
- **Who was at fault?**
- **What exactly happened?**

**Currently, investigators:**
- Watch hours of video manually
- Write reports by hand
- Calculate speeds manually
- Take **days/weeks** to finish

### The Solution

This tool:
- Takes a **5-second crash video**
- Automatically finds **when the crash happened**
- Calculates **car speeds**
- Generates a **complete report** in **minutes**

---

## 📋 Step-by-Step Process

### Step 1: Upload Video

**What happens:**
- User uploads a 5-second dashcam/CCTV video
- System saves it to cloud storage

**Why:**
- Need the video to analyze

**Example:**
```
User: "Here's my crash video" → Uploads crash.mp4
System: "Got it! Saved to cloud"
```

---

### Step 2: Extract First Frame

**What happens:**
- System takes a screenshot from the first frame
- Saves it as an image

**Why:**
- Need a still image for calibration

**Example:**
```
System: "Taking screenshot of frame 1..."
Result: screenshot.jpg (shows the intersection/road)
```

---

### Step 3: Set Location

**What happens:**
- User finds the location on Google Maps
- System saves the GPS coordinates

**Why:**
- Need to know where the video was taken

**Example:**
```
User: "This happened at Main St & Oak Ave"
System: "Location saved: 37.7749°N, 122.4194°W"
```

---

### Step 4: Calibration (Homography) 🔑

**What happens:**
- User marks 4+ matching points: one on the video frame, the same point on the map
- System learns how video pixels map to real-world GPS

**Why:**
- Without this, you only have pixels, not real-world locations
- With this, you can convert pixels to GPS and calculate real speeds

**Example:**
```
User clicks on video: "This building corner" → Pixel (500, 300)
User clicks on map: "Same building corner" → GPS (37.7749°N, 122.4194°W)

System learns: "Pixel (500, 300) = GPS (37.7749°N, 122.4194°W)"

User does this 3 more times with different points.
System now knows how to convert ANY pixel → GPS location
```

**Visual Example:**
```
VIDEO FRAME (what camera sees):
┌─────────────────────────────┐
│  🏢 Building               │
│     ⬇️ Point A              │
│                            │
│  🚗 Car at (600, 400)       │  ← We want to know where this is in real world
│                            │
│  🏪 Store                  │
│     ⬇️ Point B              │
└─────────────────────────────┘

GOOGLE MAP (real world):
┌─────────────────────────────┐
│  🏢 Building                │
│     ⬇️ Point A (GPS)         │
│                            │
│  [Car's real location?]     │  ← System calculates this using matrix
│                            │
│  🏪 Store                   │
│     ⬇️ Point B (GPS)        │
└─────────────────────────────┘
```

**After calibration:**
- Car at pixel (600, 400) → System uses matrix → Car at GPS (37.7750°N, 122.4195°W)

---

### Step 5: Process Video

**What happens:**
- System runs **YOLO** to detect vehicles in each frame
- System runs **ByteTrack** to track each vehicle across frames (assigns IDs)
- System saves all detections to the database

**Why:**
- Need to know where each car is in every frame

**Example:**
```
Frame 1: Car detected at (600, 400) → Track ID #7
Frame 2: Car detected at (610, 405) → Still Track ID #7 (same car)
Frame 3: Car detected at (620, 410) → Still Track ID #7

Another car:
Frame 1: Car detected at (200, 300) → Track ID #14
Frame 2: Car detected at (190, 295) → Still Track ID #14
```

**Result:**
- Database has every car's position in every frame

---

### Step 6: Calculate Speeds

**What happens:**
- For each tracked vehicle:
  1. Get position in frame 10 (pixel coordinates)
  2. Convert pixel → GPS using the calibration matrix
  3. Get position in frame 20 (pixel coordinates)
  4. Convert pixel → GPS
  5. Calculate distance between GPS points
  6. Calculate speed: **distance ÷ time**

**Why:**
- Need real speeds for the report

**Example:**
```
Car #7:
- Frame 10: Pixel (600, 400) → GPS (37.7749°N, 122.4194°W)
- Frame 20: Pixel (650, 450) → GPS (37.7750°N, 122.4195°W)
- Distance: 0.1 miles
- Time: 0.33 seconds (10 frames ÷ 30 fps)
- Speed: 0.1 miles ÷ 0.33 seconds = 27 MPH
```

**Result:**
- Every car's speed at every moment

---

### Step 7: Detect Collision

**What happens:**
- System compares vehicles frame by frame:
  - Checks if bounding boxes overlap (IoU)
  - Checks distance between car centers
- If overlap is high and distance is low → **collision detected**
- System finds:
  - **First contact frame**
  - **Peak impact frame**
  - **Separation frame**

**Why:**
- Need to know exactly when the crash happened

**Example:**
```
Frame 49:
- Car #7 box: (600, 400, 100, 80)
- Car #14 box: (650, 420, 100, 80)
- Overlap: 30% (high!)
- Distance: 50 pixels (close!)
- Result: COLLISION DETECTED!

First contact: Frame 49
Peak impact: Frame 52
Separation: Frame 60
```

---

### Step 8: AI Analysis

**What happens:**
- System sends all data to **AWS Bedrock Claude** (AI)
- Claude analyzes:
  - Detection data
  - Speeds
  - Collision details
  - Weather (if available)
- Claude generates a **natural language report**

**Why:**
- Need a readable explanation, not just numbers

**Example:**
```
Claude receives:
- Car #7: 27 MPH
- Car #14: 25 MPH
- Collision at frame 49
- Location: Main St & Oak Ave

Claude generates:
"At 1.6 seconds into the video, Vehicle #7 traveling at 27 MPH 
collided with Vehicle #14 traveling at 25 MPH. The collision 
occurred at the intersection of Main St and Oak Ave. Vehicle #7 
appears to have been making a left turn when Vehicle #14, 
traveling straight, could not stop in time..."
```

---

### Step 9: Generate PDF Report

**What happens:**
- System creates a PDF with:
  - Screenshot of collision frame
  - Map showing vehicle paths
  - AI-generated narrative
  - Technical details (speeds, times, coordinates)

**Why:**
- Need a final document for insurance/legal use

**Example:**
```
PDF contains:
1. Cover page: "Accident Report - Main St & Oak Ave"
2. Collision screenshot (frame 49)
3. Map with car trajectories drawn
4. AI narrative (full story)
5. Technical appendix (speeds, times, GPS coordinates)
```

---

## 🔄 Complete Flow (Simple Version)

```
1. UPLOAD VIDEO
   ↓
2. EXTRACT FRAME (screenshot)
   ↓
3. SET LOCATION (Google Maps)
   ↓
4. CALIBRATE (mark 4+ points: video → map)
   ↓
5. PROCESS VIDEO (detect & track cars)
   ↓
6. CALCULATE SPEEDS (pixels → GPS → MPH)
   ↓
7. DETECT COLLISION (find when cars hit)
   ↓
8. AI ANALYSIS (Claude writes report)
   ↓
9. GENERATE PDF (final document)
```

---

## 📊 Why Each Step Matters

| Step | Why It's Needed |
|------|----------------|
| **Upload video** | Need the source material |
| **Extract frame** | Need image for calibration |
| **Set location** | Need to know where it happened |
| **Calibrate** | **Without this, can't calculate real speeds** |
| **Process video** | Need to find all cars in all frames |
| **Calculate speeds** | Need real speeds for report |
| **Detect collision** | Need exact moment of crash |
| **AI analysis** | Need readable explanation |
| **Generate PDF** | Need final document |

---

## 🌍 Real-World Example

**Scenario:** Two cars crash at an intersection

1. **Upload:** User uploads 5-second dashcam video
2. **Extract frame:** System takes screenshot of intersection
3. **Set location:** User finds "Main St & Oak Ave" on map
4. **Calibrate:** User marks 4 building corners (video → map)
5. **Process:** System finds Car #7 and Car #14 in every frame
6. **Calculate speeds:** Car #7 = 27 MPH, Car #14 = 25 MPH
7. **Detect collision:** Crash at frame 49 (1.6 seconds in)
8. **AI analysis:** Claude writes: "Car #7 turning left, Car #14 couldn't stop..."
9. **Generate PDF:** Final report ready for insurance

**Result:** Complete accident report in **5 minutes** instead of **5 hours**

---

## 🔑 Key Concepts Explained

### YOLO (You Only Look Once)
- AI model that detects objects in images/video
- Outputs: "There's a car at coordinates (x, y, width, height)"

### ByteTrack
- Tracking algorithm that follows the same vehicle across frames
- Assigns consistent IDs (e.g., Vehicle #7 stays #7 throughout)

### Bounding Box
- Rectangle around a detected object
- Format: (x, y, width, height) in pixels

### IoU (Intersection over Union)
- Measures how much two boxes overlap
- Range: 0 (no overlap) to 1 (perfect overlap)
- Used to detect collisions

### Homography
- Mathematical transformation that maps points from one view to another
- In this project: **video pixels → real-world GPS coordinates**
- Requires at least 4 point pairs to calculate

### Homography Matrix
- 3×3 matrix that performs the transformation
- Calculated from the point pairs you mark

### Kalman Filter
- Smoothing algorithm that reduces jitter in bounding boxes
- Makes speed calculations more stable

---

## 💡 Summary

**Problem:** Manual accident analysis is slow and expensive

**Solution:** Automate it with AI and computer vision

**Process:** Upload → Calibrate → Process → Analyze → Report

**Outcome:** Fast, accurate accident reports

---

## 🛠️ Original Project Tech Stack

### Frontend
- **React Router v7** - Web framework for the user interface
- **TypeScript** - Programming language (typed JavaScript)
- **Mantine UI** - Component library for buttons, forms, etc.
- **Vite** - Build tool for fast development
- **TanStack Query** - Data fetching and caching

### Backend
- **FastAPI** - Python web framework (creates REST APIs)
- **SQLAlchemy** - Database ORM (talks to PostgreSQL)
- **Pydantic** - Data validation
- **Python 3.11** - Programming language

### Video Processing
- **YOLOv8** - Object detection (finds cars in video)
- **ByteTrack** - Multi-object tracking (follows cars across frames)
- **Supervision** - Computer vision utilities
- **OpenCV** - Image/video processing
- **Kalman Filter** - Smoothing algorithm (reduces jitter)

### AI & Analysis
- **AWS Bedrock Claude Sonnet** - Large Language Model (writes reports)
- **Claude Agent Framework** - AI agent with tools (load_detections, compute_pair_metrics, etc.)

### Storage & Infrastructure
- **PostgreSQL** - Database (stores projects, detections, analysis)
- **AWS S3** - Cloud storage (stores videos, images, JSONL files)
- **Redis** - Message queue (for Celery tasks and SSE events)

### Background Processing
- **Celery** - Task queue system (runs video processing in background)
- **Redis** - Message broker (connects Celery workers)

### Report Generation
- **WeasyPrint** - PDF generation library
- **boto3** - AWS SDK (talks to S3 and Bedrock)

### Other Tools
- **Google Maps API** - For location search and map display
- **SSE (Server-Sent Events)** - Real-time streaming (shows Claude's thinking)
- **uv** - Python package manager

---

## 📦 What Each Technology Does

| Technology | Purpose |
|------------|---------|
| **React Router** | Creates the web interface users interact with |
| **FastAPI** | Handles API requests (upload video, start processing, etc.) |
| **YOLOv8** | Detects vehicles in video frames |
| **ByteTrack** | Tracks the same vehicle across multiple frames |
| **PostgreSQL** | Stores all data (projects, detections, analysis results) |
| **AWS S3** | Stores large files (videos, images, JSONL detection files) |
| **AWS Bedrock Claude** | AI that analyzes data and writes reports |
| **Celery** | Runs long tasks (video processing) without blocking the API |
| **Redis** | Queue system for Celery tasks |
| **WeasyPrint** | Creates PDF reports |
| **Google Maps API** | Shows map for location selection and homography calibration |

---

## 🏗️ Original Project Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    FRONTEND (React)                      │
│  - User uploads video                                    │
│  - Sets location on Google Maps                          │
│  - Marks calibration points                              │
│  - Views results and PDF                                 │
└──────────────────┬────────────────────────────────────────┘
                   │ HTTP Requests
                   ▼
┌─────────────────────────────────────────────────────────┐
│                  BACKEND (FastAPI)                        │
│  - Handles API requests                                  │
│  - Manages projects and users                            │
│  - Stores data in PostgreSQL                             │
│  - Sends tasks to Celery                                 │
└──────────────────┬────────────────────────────────────────┘
                   │
        ┌──────────┴──────────┐
        │                     │
        ▼                     ▼
┌──────────────┐    ┌──────────────────┐
│  PostgreSQL  │    │  Redis Queue     │
│  (Database)  │    │  (Task Queue)    │
└──────────────┘    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │  Celery Worker   │
                    │  - Processes video│
                    │  - Runs YOLO      │
                    │  - Calls Claude   │
                    │  - Generates PDF  │
                    └────────┬─────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   AWS S3     │    │ AWS Bedrock  │    │  PostgreSQL  │
│  (Storage)   │    │   Claude     │    │  (Results)   │
└──────────────┘    └──────────────┘    └──────────────┘
```

---

## 🔄 Data Flow in Original Project

1. **User uploads video** → FastAPI → Saves to AWS S3
2. **User sets location** → FastAPI → Saves to PostgreSQL
3. **User calibrates** → FastAPI → Calculates homography matrix → Saves to PostgreSQL
4. **User starts processing** → FastAPI → Sends task to Redis → Celery worker picks up
5. **Celery processes video** → Downloads from S3 → Runs YOLO + ByteTrack → Saves detections to PostgreSQL + JSONL to S3
6. **User starts AI analysis** → FastAPI → Sends task to Redis → Celery worker → Calls AWS Bedrock Claude → Streams results via SSE
7. **User generates PDF** → FastAPI → Sends task to Redis → Celery worker → Creates PDF → Uploads to S3 → Returns presigned URL

---

## 🎯 Our Implementation: Kestra Orchestration

We use **Kestra** instead of Celery for workflow orchestration.

### Why Kestra?

| Celery | Kestra |
|--------|--------|
| Python functions | YAML workflows |
| Needs Redis | No Redis needed |
| No built-in UI | Visual workflow UI |
| Manual AI integration | Built-in OpenAI plugin |

### Our Data Flow (with Kestra)

```
1. USER UPLOADS VIDEO
   ↓
   FastAPI → Cloudinary (storage)
   
2. USER STARTS ANALYSIS (triggers Kestra)
   ↓
   Kestra Workflow starts
   
3. KESTRA: Start Processing
   ↓
   Calls POST /api/v1/processing/start
   FastAPI runs YOLO + ByteTrack
   
4. KESTRA: Wait & Poll
   ↓
   Polls GET /api/v1/processing/status/{id}
   Until status = "completed"
   
5. KESTRA: Get Collision Data
   ↓
   Calls GET /api/v1/kestra/project/{id}/collision-data
   Gets collision details (IoU, severity, frames)
   
6. KESTRA: AI Analysis (OpenAI GPT-4)
   ↓
   Built-in OpenAI plugin summarizes collision
   Generates natural language report
   
7. KESTRA: Decision Making
   ↓
   If severity == "severe" → Priority alert
   If severity == "moderate" → Standard processing
   If severity == "minor" → Log for records
   
8. KESTRA: Save Summary
   ↓
   Calls POST /api/v1/kestra/project/{id}/save-summary
   Persists AI report to database
```

### Kestra Workflow Visual

```
┌─────────────────────────────────────────────────────────────┐
│                    KESTRA WORKFLOW UI                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐     │
│  │ Check   │ → │ Process │ → │ Get     │ → │ AI      │     │
│  │ Status  │   │ Video   │   │ Collisn │   │ Summary │     │
│  │ ✅      │   │ ✅      │   │ ✅      │   │ ✅      │     │
│  └─────────┘   └─────────┘   └─────────┘   └─────────┘     │
│                                              │              │
│                                              ▼              │
│                                       ┌─────────┐          │
│                                       │ Decide  │          │
│                                       │ Action  │          │
│                                       │ ✅      │          │
│                                       └────┬────┘          │
│                                            │               │
│                        ┌───────────────────┼────────────┐  │
│                        │                   │            │  │
│                        ▼                   ▼            ▼  │
│                   ┌────────┐         ┌────────┐   ┌────────┐
│                   │ SEVERE │         │MODERATE│   │ MINOR  │
│                   │ Alert! │         │ Normal │   │ Log    │
│                   └────────┘         └────────┘   └────────┘
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Hackathon Track: Kestra

This implementation satisfies:

✅ **"Best project using Kestra's built-in AI Agent to summarise data from other systems"**
- Uses Kestra's OpenAI plugin to summarize collision data
- Fetches data from our FastAPI (the "other system")

✅ **"Bonus: Agent makes decisions based on summarised data"**
- Severity-based decision making (severe → alert, moderate → normal, minor → log)

### Kestra Quick Start

```bash
# 1. Start Kestra
docker run --rm -it -p 8080:8080 kestra/kestra:latest server local

# 2. Open UI
open http://localhost:8080

# 3. Import workflow
# Copy kestra/workflows/accident-analysis.yaml

# 4. Add OpenAI secret
# Settings > Secrets > Add OPENAI_API_KEY

# 5. Run workflow with project_id
```

---

## 🚀 Oumi VLM (Hackathon Track - Demo Only)

We also implemented **Oumi VLM** for the Oumi hackathon track.

**Status:** ⚠️ Code preserved but NOT active (requires 18GB+ RAM)

The Oumi code is kept in:
- `src/services/oumi_vlm.py` - VLM inference
- `src/services/oumi_rl_finetuning.py` - RL fine-tuning
- `src/api/routes/vlm_analysis_route.py` - API endpoints (commented out)

**What it would do:**
1. Analyze collision frames with Vision-Language Model
2. Generate natural language descriptions
3. Fine-tune model with RLHF

**Why not active:**
- Qwen2-VL-2B requires ~18GB RAM
- Our hardware has 16GB
- Kept code for demo purposes

---

## 🎓 Learning Resources

- **YOLO:** https://github.com/ultralytics/ultralytics
- **ByteTrack:** https://github.com/ifzhang/ByteTrack
- **Homography:** https://docs.opencv.org/4.x/d9/dab/tutorial_homography.html
- **Kestra:** https://kestra.io/docs
- **OpenAI:** https://platform.openai.com/docs
- **FastAPI:** https://fastapi.tiangolo.com/

---

*This document explains the complete workflow of the accident reconstruction tool in simple terms.*

