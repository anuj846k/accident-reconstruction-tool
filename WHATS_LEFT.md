# 🚧 What's Left to Complete - Hackathon Checklist

**Last Updated:** Dec 13, 2024  
**Deadline:** Dec 14, 2024 - 6 PM

---

## ✅ What's DONE

### Backend API (FastAPI)
- [x] Authentication (JWT, register, login)
- [x] Project CRUD operations
- [x] Video upload to Cloudinary
- [x] Database models & migrations
- [x] YOLO object detection
- [x] ByteTrack object tracking
- [x] Homography/Calibration system
- [x] Speed calculation (with calibration)
- [x] Collision detection algorithm
- [x] Oumi VLM integration routes
- [x] Oumi RL fine-tuning routes
- [x] Kestra API endpoints

### Kestra Workflow
- [x] Main workflow file (`accident-analysis.yaml`)
- [x] OpenAI AI summarization task
- [x] Decision making (Switch task)
- [x] Save results to database

---

## 🔴 What's LEFT

### Priority 1: Kestra Enhancement (HIGH - 3-4 hours)

**Add Screenshot & PDF Generation Tasks to Kestra**

The workflow needs two new Python script tasks:

#### Task 1: Screenshot Generation
```yaml
# Add to kestra/workflows/accident-analysis.yaml

- id: generate_screenshots
  type: io.kestra.plugin.scripts.python.Script
  description: "Generate collision screenshots using Python in Kestra"
  docker:
    image: python:3.9-slim
  beforeCommands:
    - pip install opencv-python-headless requests pillow numpy
  script: |
    import cv2
    import requests
    import numpy as np
    from PIL import Image
    import base64
    import json
    import os
    
    # Get collision data from previous task
    collision_data = json.loads('''{{ outputs.get_collisions.body | json }}''')
    video_url = "{{ outputs.check_status.body.video_url }}"
    
    # Download video
    response = requests.get(video_url, stream=True)
    with open('/tmp/video.mp4', 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    
    # Extract key frames
    cap = cv2.VideoCapture('/tmp/video.mp4')
    screenshots = []
    
    if collision_data.get('top_collision'):
        frames_to_capture = [
            collision_data['top_collision'].get('first_contact_frame', 0),
            collision_data['top_collision'].get('peak_overlap_frame', 0),
            collision_data['top_collision'].get('last_overlap_frame', 0)
        ]
        
        for frame_num in frames_to_capture:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
            ret, frame = cap.read()
            if ret:
                # Convert to base64
                _, buffer = cv2.imencode('.jpg', frame)
                img_base64 = base64.b64encode(buffer).decode('utf-8')
                screenshots.append({
                    'frame': frame_num,
                    'image_base64': img_base64
                })
    
    cap.release()
    
    # Output for next task
    print(json.dumps({'screenshots': screenshots, 'count': len(screenshots)}))
```

#### Task 2: PDF Report Generation
```yaml
- id: generate_pdf_report
  type: io.kestra.plugin.scripts.python.Script
  description: "Generate PDF report with collision analysis"
  docker:
    image: python:3.9-slim
  beforeCommands:
    - pip install reportlab pillow
  script: |
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import inch
    import json
    import base64
    from io import BytesIO
    from PIL import Image
    
    # Get data from previous tasks
    ai_summary = '''{{ outputs.ai_analysis.choices[0].message.content }}'''
    collision_data = json.loads('''{{ outputs.get_collisions.body | json }}''')
    project_id = "{{ inputs.project_id }}"
    
    # Create PDF
    pdf_path = f'/tmp/accident_report_{project_id[:8]}.pdf'
    c = canvas.Canvas(pdf_path, pagesize=letter)
    width, height = letter
    
    # Title
    c.setFont("Helvetica-Bold", 24)
    c.drawString(1*inch, height - 1*inch, "Accident Analysis Report")
    
    # Project Info
    c.setFont("Helvetica", 12)
    c.drawString(1*inch, height - 1.5*inch, f"Project ID: {project_id}")
    
    # Collision Summary
    c.setFont("Helvetica-Bold", 14)
    c.drawString(1*inch, height - 2*inch, "Collision Summary")
    
    c.setFont("Helvetica", 10)
    y_pos = height - 2.3*inch
    
    if collision_data.get('top_collision'):
        top = collision_data['top_collision']
        lines = [
            f"Severity: {top.get('severity', 'N/A')}",
            f"Vehicles: Track {top.get('track_id_1')} vs Track {top.get('track_id_2')}",
            f"Max Overlap (IoU): {top.get('max_iou', 0):.2%}",
            f"Duration: {top.get('duration_frames', 0)} frames",
        ]
        for line in lines:
            c.drawString(1*inch, y_pos, line)
            y_pos -= 0.2*inch
    
    # AI Analysis
    c.setFont("Helvetica-Bold", 14)
    c.drawString(1*inch, y_pos - 0.3*inch, "AI Analysis")
    
    c.setFont("Helvetica", 9)
    y_pos -= 0.6*inch
    
    # Wrap text
    for line in ai_summary.split('\n')[:30]:  # First 30 lines
        if y_pos < 1*inch:
            c.showPage()
            y_pos = height - 1*inch
        c.drawString(1*inch, y_pos, line[:90])  # Truncate long lines
        y_pos -= 0.15*inch
    
    c.save()
    
    # Read PDF and output as base64 for storage
    with open(pdf_path, 'rb') as f:
        pdf_base64 = base64.b64encode(f.read()).decode('utf-8')
    
    print(json.dumps({'pdf_path': pdf_path, 'pdf_base64': pdf_base64[:100] + '...'}))
```

---

### Priority 2: Frontend (HIGH - 6-8 hours)

#### 2.1 Basic Pages Needed
- [ ] **Login Page** - Form with email/password
- [ ] **Register Page** - Form with email/password/name
- [ ] **Dashboard** - List of projects with status
- [ ] **Project Detail** - Show processing results, collisions, AI summary
- [ ] **Upload Page** - Video upload form

#### 2.2 Calibration UI (4-5 hours)
- [ ] Split view: Video frame | Google Map
- [ ] Click on video → mark point
- [ ] Click on map → mark corresponding GPS
- [ ] Show 4+ point pairs
- [ ] "Solve" button to calculate matrix
- [ ] Show success/error status

#### 2.3 Suggested Tech Stack
```
Frontend/
├── app/
│   ├── routes/
│   │   ├── login.tsx
│   │   ├── register.tsx
│   │   ├── dashboard.tsx
│   │   ├── projects.$id.tsx
│   │   └── calibration.$id.tsx
│   ├── components/
│   │   ├── VideoPlayer.tsx
│   │   ├── CalibrationView.tsx
│   │   ├── CollisionTimeline.tsx
│   │   └── AISummaryCard.tsx
│   └── client/
│       └── api.ts (generated from OpenAPI)
```

---

### Priority 3: Testing & Polish (2 hours)

- [ ] End-to-end test: Register → Upload → Process → View Results
- [ ] Test Kestra workflow execution
- [ ] Test Oumi VLM analysis
- [ ] Fix any bugs found

---

### Priority 4: Deployment (2-3 hours)

#### Option A: Fly.io (Recommended)
```bash
# Backend
cd accident-reconstruction-backend
fly launch
fly deploy

# Kestra (Docker)
docker-compose up -d
```

#### Option B: Railway/Render
- Push to GitHub
- Connect to Railway/Render
- Set environment variables
- Deploy

---

### Priority 5: Demo Prep (1 hour)

- [ ] Record demo video (2-3 minutes)
- [ ] Prepare slides if needed
- [ ] Test on deployed version
- [ ] Prepare backup local demo

---

## 📅 Realistic Timeline

| Day | Time | Task | Hours |
|-----|------|------|-------|
| Dec 13 (Today) | Morning | Kestra screenshot/PDF tasks | 3 |
| Dec 13 | Afternoon | Frontend: Login, Dashboard | 4 |
| Dec 13 | Evening | Frontend: Project Detail | 3 |
| Dec 14 | Morning | Frontend: Calibration UI | 4 |
| Dec 14 | Afternoon | Testing + Bug fixes | 2 |
| Dec 14 | 4-5 PM | Deploy | 1 |
| Dec 14 | 5-6 PM | Demo prep | 1 |

**Total: ~18 hours** (Tight but doable!)

---

## 🎯 Minimum Viable Demo

If short on time, focus on:

1. ✅ Backend working (already done!)
2. ✅ Kestra workflow with OpenAI (already done!)
3. ⚠️ Basic frontend (login + dashboard + results view)
4. ⚠️ One successful end-to-end run

**Skip if needed:**
- Calibration UI (use API directly in demo)
- PDF generation (show AI summary in UI instead)
- Deployment (demo locally)
- Oumi VLM testing (routes exist for track mention only)

---

## 🏆 Hackathon Requirements Check

### Kestra Track
- [x] Use Kestra for orchestration
- [x] Use Kestra's AI Agent (OpenAI plugin)
- [x] Decision making (Switch task)
- [ ] Screenshot generation (Python script in Kestra) ← **TODO**
- [ ] PDF generation (Python script in Kestra) ← **TODO**

### Oumi Track (⚠️ FOR MENTION ONLY - NOT ACTIVELY USED)
- [x] Oumi VLM routes exist (for track requirement)
- [x] Frame analysis endpoint created
- [x] RL fine-tuning endpoint created
- ⚠️ **Note:** Routes exist but are NOT used in main workflow. Just for hackathon track mention.

---

## 💡 Tips for Teammate

1. **Start with Swagger UI** - Test all APIs at http://localhost:8000/docs
2. **Read TESTING_GUIDE.md** - Follow the complete flow
3. **Check terminal logs** - Backend logs show processing progress
4. **Use existing test video** - Any video with cars works

---

## 🔗 Key Files

| File | Purpose |
|------|---------|
| `src/main.py` | FastAPI app entry |
| `src/api/routes/` | All API endpoints |
| `src/services/video_processor.py` | YOLO + ByteTrack |
| `src/services/collision_analysis.py` | Collision detection |
| `src/services/oumi_vlm.py` | VLM analysis |
| `kestra/workflows/accident-analysis.yaml` | Kestra workflow |
| `.env` | Environment variables |
| `alembic/` | Database migrations |

---

Good luck! 🚀

