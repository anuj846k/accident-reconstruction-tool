# 🧪 API Testing Guide - Accident Reconstruction System

This guide walks you through testing all API routes systematically to understand the complete flow.

---

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [Complete Flow Overview](#complete-flow-overview)
3. [Phase 1: Authentication](#phase-1-authentication)
4. [Phase 2: Project Setup](#phase-2-project-setup)
5. [Phase 3: Calibration (Optional but Important)](#phase-3-calibration)
6. [Phase 4: Video Processing](#phase-4-video-processing)
7. [Phase 5: Analysis & Results](#phase-5-analysis--results)
8. [Phase 6: Oumi VLM Analysis](#phase-6-oumi-vlm-analysis) ⚠️ *NOT IN USE*
9. [Phase 7: Kestra Workflow (Orchestration)](#phase-7-kestra-workflow)
10. [What's Left to Do](#whats-left-to-do)

---

## Prerequisites

### 1. Start the Server
```bash
cd accident-reconstruction-backend
source venv/bin/activate
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Open Swagger UI
Go to: **http://localhost:8000/docs**

### 3. Have a Test Video Ready
- Any video with cars/vehicles
- Can use a Cloudinary URL or upload via API

---

## Complete Flow Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        ACCIDENT RECONSTRUCTION FLOW                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  1. AUTH          →  Register/Login → Get JWT Token                    │
│                                                                         │
│  2. PROJECT       →  Create Project → Upload Video                     │
│                                                                         │
│  3. CALIBRATION   →  Create Session → Add 4+ Points → Solve Matrix    │
│      (optional)       (image pixel ↔ GPS coordinates)                  │
│                                                                         │
│  4. PROCESSING    →  Start Processing → YOLO Detection → ByteTrack    │
│                       → Speed Calculation (if calibrated)              │
│                                                                         │
│  5. ANALYSIS      →  Get Detections → Collision Analysis → AI Summary │
│                                                                         │
│  6. OUMI VLM      →  ⚠️ NOT IN USE (routes exist for hackathon track) │
│                                                                         │
│  7. KESTRA        →  Trigger Workflow → AI Summary → Decision → Save  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Authentication

### 1.1 Register a New User

```bash
curl -X POST http://localhost:8000/api/v1/signup \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "password123",
    "full_name": "Test User"
  }'
```

**Expected Response:**
```json
{
  "id": "uuid-here",
  "email": "test@example.com",
  "full_name": "Test User",
  "is_active": true
}
```

### 1.2 Login to Get Token

```bash
curl -X POST http://localhost:8000/api/v1/login/access-token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=test@example.com&password=password123"
```

**Expected Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6...",
  "token_type": "bearer"
}
```

**⚠️ IMPORTANT: Save this token! Use it in all subsequent requests.**

### 1.3 Test Token Validity

```bash
curl -X POST http://localhost:8000/api/v1/login/test-token \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

---

## Phase 2: Project Setup

### 2.1 Create a New Project

```bash
curl -X POST http://localhost:8000/api/v1/projects/ \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Accident Analysis",
    "description": "Testing the system"
  }'
```

**Expected Response:**
```json
{
  "id": "project-uuid-here",
  "name": "Test Accident Analysis",
  "description": "Testing the system",
  "status": "pending",
  "created_at": "2024-12-13T..."
}
```

**⚠️ SAVE THE PROJECT ID! You'll use it everywhere.**

### 2.2 List Your Projects

```bash
curl -X GET "http://localhost:8000/api/v1/projects/" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

### 2.3 Upload a Video

**Option A: Via API (file upload)**
```bash
curl -X POST "http://localhost:8000/api/v1/projects/PROJECT_ID/upload-video" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -F "file=@/path/to/your/video.mp4"
```

**Option B: Use Swagger UI**
1. Go to http://localhost:8000/docs
2. Find `POST /api/v1/projects/{project_id}/upload-video`
3. Click "Try it out"
4. Enter project_id and select video file
5. Execute

**Expected Response:**
```json
{
  "id": "media-asset-uuid",
  "project_id": "project-uuid",
  "uri": "https://res.cloudinary.com/...",
  "kind": "video",
  "filename": "video.mp4"
}
```

---

## Phase 3: Calibration

**Why Calibration?** Calibration enables:
- Real-world speed calculation (mph)
- GPS coordinate mapping
- Accurate distance measurements

### 3.1 Create/Get Calibration Session

```bash
curl -X POST "http://localhost:8000/api/v1/homography/project/PROJECT_ID/session" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

**Expected Response:**
```json
{
  "id": "session-uuid",
  "project_id": "project-uuid",
  "status": "draft",
  "pairs": [],
  "matrix": null
}
```

### 3.2 Add Calibration Points (Minimum 4)

You need 4+ corresponding points:
- **Image Point**: Normalized x,y (0.0 to 1.0) on video frame
- **GPS Point**: Latitude, Longitude from Google Maps

```bash
curl -X PUT "http://localhost:8000/api/v1/homography/session/SESSION_ID/pairs" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '[
    {"image_x_norm": 0.1, "image_y_norm": 0.2, "map_lat": 40.7128, "map_lng": -74.0060, "order_idx": 0},
    {"image_x_norm": 0.9, "image_y_norm": 0.2, "map_lat": 40.7129, "map_lng": -74.0055, "order_idx": 1},
    {"image_x_norm": 0.1, "image_y_norm": 0.8, "map_lat": 40.7125, "map_lng": -74.0060, "order_idx": 2},
    {"image_x_norm": 0.9, "image_y_norm": 0.8, "map_lat": 40.7126, "map_lng": -74.0055, "order_idx": 3}
  ]'
```

### 3.3 Solve Homography Matrix

```bash
curl -X POST "http://localhost:8000/api/v1/homography/session/SESSION_ID/solve" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

**Expected Response:**
```json
{
  "success": true,
  "matrix": [
    [1.234, 0.001, -0.5],
    [0.002, 1.567, -0.3],
    [0.0001, 0.0002, 1.0]
  ],
  "reprojection_error": 1.42e-14
}
```

**✅ Calibration Complete!** Now processing will calculate speeds.

---

## Phase 4: Video Processing

### 4.1 Start Processing

```bash
curl -X POST "http://localhost:8000/api/v1/processing/start" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{"project_id": "PROJECT_ID"}'
```

**Expected Response:**
```json
{
  "run_id": "run-uuid",
  "status": "started",
  "message": "Video processing started with calibration enabled (speed calculation active)..."
}
```

### 4.2 Check Processing Status

```bash
curl -X GET "http://localhost:8000/api/v1/processing/status/RUN_ID" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

**Response during processing:**
```json
{
  "run_id": "run-uuid",
  "status": "processing",
  "total_frames": null,
  "processed_frames": 0,
  "detection_count": 0
}
```

**Response when complete:**
```json
{
  "run_id": "run-uuid",
  "status": "completed",
  "total_frames": 602,
  "processed_frames": 602,
  "detection_count": 5656,
  "unique_tracks": 17
}
```

### 4.3 Get Processing Stats

```bash
curl -X GET "http://localhost:8000/api/v1/processing/project/PROJECT_ID/stats" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

---

## Phase 5: Analysis & Results

### 5.1 Get Detections

```bash
# All detections (limited)
curl -X GET "http://localhost:8000/api/v1/processing/project/PROJECT_ID/detections?limit=100" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"

# Detections for specific frame
curl -X GET "http://localhost:8000/api/v1/processing/project/PROJECT_ID/detections?frame_idx=50" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"

# Detections for specific track
curl -X GET "http://localhost:8000/api/v1/processing/project/PROJECT_ID/detections?track_id=1" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

**Expected Response:**
```json
{
  "project_id": "uuid",
  "total_count": 100,
  "detections": [
    {
      "id": "detection-uuid",
      "frame_idx": 0,
      "track_id": 1,
      "class_name": "car",
      "confidence": 0.95,
      "bbox_x": 100.5,
      "bbox_y": 200.3,
      "bbox_w": 150.0,
      "bbox_h": 80.0,
      "speed_mph": 25.5,      // ← Only if calibrated!
      "world_x": 40.7128,     // ← Only if calibrated!
      "world_y": -74.0060     // ← Only if calibrated!
    }
  ]
}
```

### 5.2 Get Unique Tracks

```bash
curl -X GET "http://localhost:8000/api/v1/processing/project/PROJECT_ID/tracks" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

### 5.3 Get Collision Data (via Kestra endpoint)

```bash
curl -X GET "http://localhost:8000/api/v1/kestra/project/PROJECT_ID/collision-data" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

**Expected Response:**
```json
{
  "project_id": "uuid",
  "has_collisions": true,
  "collision_count": 3,
  "top_collision": {
    "track_id_1": 5,
    "track_id_2": 8,
    "severity": "moderate",
    "max_iou": 0.4523,
    "duration_frames": 15,
    "first_contact_frame": 120,
    "peak_overlap_frame": 128
  },
  "all_collisions": [...]
}
```

---

## Phase 6: Oumi VLM Analysis

> ⚠️ **NOTE: FOR HACKATHON TRACK MENTION ONLY**
> 
> The Oumi VLM routes are implemented for the **Oumi hackathon track requirement** but are **NOT actively used** in the main workflow. The routes exist to demonstrate integration capability.
> 
> **DO NOT TEST these endpoints** - they require Oumi models which may not be installed/configured.

### Available Endpoints (Not for testing)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/vlm-analysis/analyze-collision` | VLM frame analysis (NOT IN USE) |
| POST | `/api/v1/vlm-analysis/fine-tune-with-rl` | RL fine-tuning (NOT IN USE) |

**Skip to Phase 7 (Kestra) for actual testing.**

---

## Phase 7: Kestra Workflow

### 7.1 Check Workflow Status

```bash
curl -X GET "http://localhost:8000/api/v1/kestra/project/PROJECT_ID/status" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

### 7.2 Trigger Analysis

```bash
curl -X POST "http://localhost:8000/api/v1/kestra/trigger-analysis" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  -d '{"project_id": "PROJECT_ID"}'
```

### 7.3 Get AI Summaries

```bash
curl -X GET "http://localhost:8000/api/v1/kestra/project/PROJECT_ID/summaries" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

### 7.4 Get Batch Processing Stats

```bash
curl -X GET "http://localhost:8000/api/v1/kestra/batch-stats" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE"
```

---

## 🔑 Quick Reference: All Endpoints

### Auth Routes
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/signup` | Register new user |
| POST | `/api/v1/login/access-token` | Login, get JWT |
| POST | `/api/v1/login/test-token` | Validate token |

### Project Routes
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/projects/` | Create project |
| GET | `/api/v1/projects/` | List projects |
| GET | `/api/v1/projects/{id}` | Get project |
| PATCH | `/api/v1/projects/{id}` | Update project |
| DELETE | `/api/v1/projects/{id}` | Delete project |
| POST | `/api/v1/projects/{id}/upload-video` | Upload video |

### Homography/Calibration Routes
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/homography/project/{id}/session` | Get/create session |
| PUT | `/api/v1/homography/session/{id}/pairs` | Update calibration points |
| POST | `/api/v1/homography/session/{id}/solve` | Solve matrix |
| GET | `/api/v1/homography/session/{id}/export` | Export data |

### Processing Routes
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/processing/start` | Start processing |
| GET | `/api/v1/processing/status/{run_id}` | Check status |
| GET | `/api/v1/processing/project/{id}/runs` | List runs |
| GET | `/api/v1/processing/project/{id}/detections` | Get detections |
| GET | `/api/v1/processing/project/{id}/tracks` | Get tracks |
| GET | `/api/v1/processing/project/{id}/stats` | Get stats |
| DELETE | `/api/v1/processing/project/{id}/detections` | Delete detections |

### Kestra Routes
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/kestra/trigger-analysis` | Trigger workflow |
| GET | `/api/v1/kestra/project/{id}/status` | Get workflow status |
| GET | `/api/v1/kestra/project/{id}/collision-data` | Get collision data |
| POST | `/api/v1/kestra/project/{id}/save-summary` | Save AI summary |
| GET | `/api/v1/kestra/project/{id}/summaries` | Get summaries |
| GET | `/api/v1/kestra/pending-projects` | Get pending projects |
| GET | `/api/v1/kestra/batch-stats` | Get batch stats |

### VLM Analysis Routes (⚠️ NOT IN USE - For Hackathon Track Only)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/vlm-analysis/analyze-collision` | Analyze with VLM (NOT IN USE) |
| POST | `/api/v1/vlm-analysis/fine-tune-with-rl` | RL fine-tuning (NOT IN USE) |

---

## 🧪 Complete Test Script

Save this as `test_flow.sh`:

```bash
#!/bin/bash

BASE_URL="http://localhost:8000/api/v1"
EMAIL="test@example.com"
PASSWORD="password123"

echo "=== 1. Register ==="
curl -X POST "$BASE_URL/signup" \
  -H "Content-Type: application/json" \
  -d "{\"email\": \"$EMAIL\", \"password\": \"$PASSWORD\", \"full_name\": \"Test\"}"

echo -e "\n\n=== 2. Login ==="
TOKEN=$(curl -s -X POST "$BASE_URL/login/access-token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=$EMAIL&password=$PASSWORD" | jq -r '.access_token')

echo "Token: $TOKEN"

echo -e "\n\n=== 3. Create Project ==="
PROJECT=$(curl -s -X POST "$BASE_URL/projects/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Test Project", "description": "Testing"}')

PROJECT_ID=$(echo $PROJECT | jq -r '.id')
echo "Project ID: $PROJECT_ID"

echo -e "\n\n=== 4. Create Calibration Session ==="
SESSION=$(curl -s -X POST "$BASE_URL/homography/project/$PROJECT_ID/session" \
  -H "Authorization: Bearer $TOKEN")

SESSION_ID=$(echo $SESSION | jq -r '.id')
echo "Session ID: $SESSION_ID"

# Continue with more tests...
```

---


