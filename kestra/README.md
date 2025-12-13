# Kestra Workflow Orchestration

This directory contains Kestra workflows for orchestrating the accident analysis pipeline.

## Overview

Kestra replaces Celery for workflow orchestration, providing:
- **Visual workflow monitoring**
- **Built-in AI Agent** (OpenAI plugin)
- **Decision making** based on collision severity
- **No Redis required**
- **Multiple trigger options** (user-triggered OR automated)

---

## 🎯 Two Use Cases

### Use Case 1: User-Triggered Analysis (Demo Flow)

```
USER clicks "Analyze" in your app
       │
       ▼
FRONTEND sends request to BACKEND
       │
       ▼
BACKEND triggers Kestra workflow (via API)
       │
       ▼
KESTRA runs all tasks:
  ① Check project status
  ② Start YOLO processing
  ③ Wait for completion
  ④ Get collision data
  ⑤ AI Summary (GPT-4)
  ⑥ Make severity decision
  ⑦ Save result
       │
       ▼
BACKEND receives result from Kestra
       │
       ▼
FRONTEND shows result to user
```

**When to use:** User wants to analyze a specific video on-demand.

---

### Use Case 2: Automated Batch Processing (Production Flow)

```
KESTRA triggers automatically (midnight every day)
       │
       ▼
KESTRA fetches all unprocessed projects
       │
       ▼
KESTRA loops through each project:
  ① Process video (YOLO)
  ② Detect collisions
  ③ AI Summary
  ④ Decide action:
     - SEVERE → Alert police 🚨
     - MODERATE → Add to daily report
     - MINOR → Log for statistics
       │
       ▼
KESTRA sends email report:
  "Daily Accident Report: 5 collisions detected"
       │
       ▼
Traffic department reads report next morning
```

**When to use:** City traffic department analyzing 100+ CCTV cameras daily without human involvement.

---

## Quick Start

### 1. Start Kestra (Docker)

```bash
# Start Kestra server
docker run --pull=always --rm -it \
  -p 8080:8080 \
  -v $(pwd)/kestra:/app/storage \
  kestra/kestra:latest server local
```

### 2. Open Kestra UI

Open http://localhost:8080 in your browser.

### 3. Configure Secrets

In Kestra UI, go to **Settings > Secrets** and add:

| Secret Name | Value |
|-------------|-------|
| `OPENAI_API_KEY` | Your OpenAI API key |

### 4. Import Workflows

In Kestra UI:
1. Go to **Flows**
2. Click **Create**
3. Paste the content from `workflows/accident-analysis.yaml`
4. Click **Save**

Repeat for `ai-summary-only.yaml` if needed.

### 5. Trigger Options

#### Option A: Manual (from Kestra UI)
1. Go to **Flows** > **accident-analysis-pipeline**
2. Click **Execute**
3. Fill in inputs (`project_id`, `auth_token`)
4. Click **Execute**

#### Option B: From Your App (Programmatic)
```python
# Your FastAPI backend triggers Kestra
import httpx

response = await httpx.post(
    "http://localhost:8080/api/v1/executions/accident.reconstruction/accident-analysis-pipeline",
    json={
        "inputs": {
            "project_id": "your-project-id",
            "auth_token": "your-jwt-token"
        }
    }
)
execution_id = response.json()["id"]
```

#### Option C: Scheduled (Automatic)
Already configured in workflow:
```yaml
triggers:
  - id: nightly_batch
    type: io.kestra.plugin.core.trigger.Schedule
    cron: "0 0 * * *"  # Runs at midnight every day
```

---

## Workflows

### 1. `accident-analysis.yaml` (Single Video Pipeline)

Complete workflow for **one video**:
1. Checks project status
2. Starts video processing if needed
3. Waits for processing to complete
4. Gets collision data
5. AI analyzes collisions (OpenAI GPT-4)
6. Makes decisions based on severity
7. Saves AI summary to database

**Use when:** User wants to analyze ONE video on-demand.

**Triggers:**
- Webhook (from your app)
- Manual (from Kestra UI)

---

### 2. `batch-processing.yaml` (Automated Batch)

Production workflow for **multiple videos**:
1. Fetches all unprocessed projects
2. Loops through each (3 concurrent)
3. Processes video (YOLO + ByteTrack)
4. Detects collisions
5. AI summarizes each
6. Makes severity decisions (alert for severe)
7. Sends daily email report

**Use when:** Automated CCTV monitoring (100+ cameras, no human involved).

**Triggers:**
- Scheduled (midnight every day)
- Manual (for testing)

---

### 3. `ai-summary-only.yaml` (Simplified)

Simplified workflow that:
1. Gets collision data
2. AI summarizes
3. Saves summary

**Use when:** Video is already processed, you just want AI analysis.

## API Endpoints (for Kestra)

Kestra calls these endpoints on your FastAPI backend:

### Single Video Analysis
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/kestra/project/{id}/status` | GET | Check workflow status |
| `/api/v1/kestra/project/{id}/collision-data` | GET | Get collision data for AI |
| `/api/v1/kestra/project/{id}/save-summary` | POST | Save AI summary |
| `/api/v1/processing/start` | POST | Start video processing |
| `/api/v1/processing/status/{run_id}` | GET | Check processing status |

### Batch Processing
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/kestra/pending-projects` | GET | Get all projects pending analysis |
| `/api/v1/kestra/batch-stats` | GET | Get batch processing statistics |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    KESTRA WORKFLOW                          │
│  (Visual orchestration, no code required)                   │
└──────────────────────┬──────────────────────────────────────┘
                       │
         ┌─────────────┼─────────────┐
         │             │             │
         ▼             ▼             ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  Your API    │ │   OpenAI     │ │   Decision   │
│  (FastAPI)   │ │   (GPT-4)    │ │   Engine     │
│              │ │              │ │              │
│ - Processing │ │ - Summarize  │ │ - Severity   │
│ - Collisions │ │ - Analyze    │ │ - Alerts     │
│ - Storage    │ │              │ │              │
└──────────────┘ └──────────────┘ └──────────────┘
```

## Hackathon Requirements

This implementation satisfies:

✅ **"Best project using Kestra's built-in AI Agent to summarise data from other systems"**
- Uses Kestra's OpenAI plugin to summarize collision data
- Fetches data from our API (other system)

✅ **"Bonus credit for enabling the agent to make decisions based on the summarised data"**
- `severity_decision` task takes different actions based on collision severity
- SEVERE → Priority alert
- MODERATE → Standard processing
- MINOR → Logged for records

## Troubleshooting

### "Connection refused" to API

If Kestra can't reach your API:
- Use `host.docker.internal` instead of `localhost` when running in Docker
- Or use your machine's actual IP address

### "Unauthorized" errors

Make sure:
1. Your JWT token is valid
2. Token is passed in the `auth_token` input
3. Token hasn't expired

### Workflow stuck

Check:
1. Kestra logs in the UI
2. Your FastAPI backend logs
3. Processing status endpoint

## Example Execution

```
Inputs:
  project_id: ccc646e8-34da-434b-bc6c-16334a34ba18
  auth_token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

Output:
  ╔════════════════════════════════════════════════════════════════╗
  ║                    WORKFLOW COMPLETE                          ║
  ╠════════════════════════════════════════════════════════════════╣
  ║  Project ID: ccc646e8-34da-434b-bc6c-16334a34ba18
  ║  Collisions Found: 1
  ║  AI Summary: Generated
  ║  Severity: moderate
  ╚════════════════════════════════════════════════════════════════╝
```

## Further Reading

- [Kestra Documentation](https://kestra.io/docs)
- [OpenAI Plugin](https://kestra.io/plugins/plugin-openai)
- [HTTP Plugin](https://kestra.io/plugins/plugin-core#http)

