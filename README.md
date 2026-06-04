# StoreLens

A high-performance, edge-to-cloud **retail analytics system** that converts offline store CCTV video streams into real-time operational metrics, shopper conversion funnels, department heatmaps, and business anomaly alerts.

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.95+-009688?logo=fastapi&logoColor=white)
![YOLOv8](https://img.shields.io/badge/YOLOv8-Ultralytics-FF6F00?logo=yolo&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-4169E1?logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![License](https://img.shields.io/badge/License-MIT-green)

---

## What It Does

StoreLens processes CCTV footage in real-time using computer vision to:

1. **Detect & Track** people using YOLOv8 + ByteTrack
2. **Classify** each person as staff or shopper using positional + appearance heuristics
3. **Map** movements to store departments via polygonal geofences
4. **Detect** queue formations, wait times, and abandonment events
5. **Correlate** shopper behavior with POS transaction data
6. **Alert** on anomalies (e.g., sudden crowd surges, unusual empty zones)

All data is served through a **FastAPI REST API** and visualized on a **React dashboard** with live camera feeds.

---

## Key Features

- **Real-Time Person Detection** — YOLOv8 nano model with ByteTrack multi-object tracking
- **Polygonal Geofencing** — Shapely-based department boundary checks (PRODUCT_A, BILLING, etc.)
- **Staff Classification** — Hybrid heuristic using zone position, dwell time, and color uniformity
- **Queue Management** — Redis-backed live counter line tracking with wait duration and abandonment detection
- **Shopper Re-entry Detection** — Temporal window checks to avoid double-counting returning visitors
- **Group Entry Detection** — Identifies clusters of people entering together within a 3-frame window
- **Business Anomaly Engine** — Z-score and threshold-based alerting on visitor flow, conversions, and queue metrics
- **Live MJPEG Streaming** — Annotated camera feeds with bounding boxes, track IDs, and zone labels
- **Interactive Dashboard** — Dark-themed React UI with KPIs, funnels, heatmaps, alerts, and live feeds

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        CCTV Video Files                         │
│                  (CAM 1 → CAM 5 .mp4 files)                    │
└───────────────────────────┬──────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│                  Detection Pipeline (Python)                     │
│  ┌────────────┐  ┌──────────┐  ┌────────────┐  ┌────────────┐  │
│  │ YOLOv8     │→ │ByteTrack │→ │Zone Mapper │→ │Event       │  │
│  │ Inference  │  │Tracker   │  │(Shapely)   │  │Emitter     │  │
│  └────────────┘  └──────────┘  └────────────┘  └─────┬──────┘  │
│  ┌────────────┐  ┌──────────┐  ┌────────────┐        │         │
│  │Staff       │  │Queue     │  │Group       │        │         │
│  │Classifier  │  │Manager   │  │Detector    │        │         │
│  └────────────┘  └──────────┘  └────────────┘        │         │
└──────────────────────────────────────────────────────┬┘         │
                            │ HTTP POST /events/ingest │          │
                            ▼                          ▼          │
┌──────────────────────────────────────────────────────────────────┐
│                    FastAPI REST Server (:8000)                    │
│  Routes: /metrics, /funnel, /heatmap, /anomalies, /health       │
│  ┌──────────┐  ┌───────────┐  ┌──────────────────┐             │
│  │PostgreSQL│  │   Redis   │  │ Anomaly Engine   │             │
│  │  (Data)  │  │  (Cache)  │  │ (Z-score alerts) │             │
│  └──────────┘  └───────────┘  └──────────────────┘             │
└──────────────────────────┬──────────────────────────────────────┘
                            │ REST API
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│                   React Dashboard (:3000)                         │
│  KPI Cards │ Funnel │ Heatmap │ Alerts │ Live Camera Feeds       │
└──────────────────────────────────────────────────────────────────┘
```

---

## Repository Structure

```
storelens/
│
├── api/                              # FastAPI REST Server
│   ├── main.py                       # App bootstrap, CORS, middleware, exception handlers
│   ├── db.py                         # Asyncpg PostgreSQL connection pool
│   ├── cache.py                      # Redis async caching wrapper
│   ├── anomaly_engine.py             # Z-score business anomaly detection
│   └── routes/                       # API endpoint routers
│       ├── events.py                 #   POST /events/ingest — event ingestion
│       ├── metrics.py                #   GET /metrics — KPI dashboard data
│       ├── funnel.py                 #   GET /funnel — conversion funnel stages
│       ├── heatmap.py                #   GET /heatmap — department density map
│       ├── anomalies.py              #   GET /anomalies — active business alerts
│       └── health.py                 #   GET /health — system readiness check
│
├── detection/                        # Computer Vision Pipeline
│   ├── stream_server.py              # MJPEG streaming FastAPI server (:8001)
│   ├── pipeline.py                   # Core frame reader & detection orchestrator
│   ├── model_loader.py               # Lazy-loading YOLOv8 weights
│   ├── tracker.py                    # ByteTrack IOU multi-object tracker
│   ├── event_emitter.py              # Line-crossing & JSONL event writer
│   ├── zone_mapper.py                # Shapely polygon department checker
│   ├── staff_classifier.py           # Staff/shopper classification heuristics
│   ├── staff_classifier_enhanced.py  # Enhanced classifier with color uniformity
│   ├── reid.py                       # Shopper re-entry detection
│   ├── group_detector.py             # Temporal group entry detection
│   ├── queue_manager.py              # Redis queue depth controller
│   ├── schemas.py                    # Pydantic event validation schemas
│   └── ingest_events.py              # Batch event uploader to API
│
├── dashboard/                        # React Frontend (see dashboard/README.md)
│   ├── src/App.tsx                   # Main dashboard component
│   └── ...                           # Vite + React + TypeScript setup
│
├── tests/                            # Unit & integration tests
│   ├── conftest.py                   # Shared fixtures (FakeRedis, DB mocks)
│   ├── test_api.py                   # API endpoint tests
│   └── test_detection.py             # Detection pipeline tests
│
├── sql/                              # Database migrations
│   ├── 001_create_events.sql         # Events table schema
│   ├── 002_create_pos.sql            # POS transactions schema
│   ├── 003_create_sessions.sql       # Session tracking schema
│   └── ingest_pos_data.py            # POS data import script
│
├── data/clips/CCTV Footage/          # Video files (not tracked in git)
├── models/                           # ML model weights (not tracked in git)
├── docs/                             # Architecture documentation
│
├── launch.py                         # Single-file launcher for all services
├── requirements.txt                  # Python dependencies (full pipeline)
├── requirements_api.txt              # Python dependencies (API-only)
├── docker-compose.yml                # Docker orchestration
├── Dockerfile                        # API container build
├── Makefile                          # Convenience commands
├── init-db.sh                        # Database migration runner
├── .env.example                      # Environment variable template
└── .gitignore                        # Git exclusion rules
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Object Detection** | YOLOv8 (Ultralytics), PyTorch, OpenCV |
| **Object Tracking** | ByteTrack (IOU-based) |
| **Geofencing** | Shapely (polygon containment) |
| **REST API** | FastAPI, Uvicorn (ASGI) |
| **Database** | PostgreSQL 15 (asyncpg) |
| **Caching** | Redis 7 (redis.asyncio) |
| **Frontend** | React 19, TypeScript, Vite 8 |
| **Testing** | Pytest, pytest-asyncio, FakeRedis |
| **Orchestration** | Docker Compose |

---

## Quick Start

### Prerequisites

| Requirement | Version |
|---|---|
| Python | >= 3.11 |
| Node.js | >= 18.x |
| PostgreSQL | 15+ (or Docker) |
| Redis | 7+ (or Docker) |

### Option A — Run Everything with One Command

```bash
# 1. Clone the repo
git clone https://github.com/<your-username>/storelens.git
cd storelens

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate        # Linux/Mac
venv\Scripts\activate           # Windows

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Install dashboard dependencies
cd dashboard && npm install && cd ..

# 5. Copy environment config
cp .env.example .env
# Edit .env with your PostgreSQL and Redis connection strings

# 6. Start infrastructure (PostgreSQL + Redis)
docker compose up postgres redis -d

# 7. Run database migrations
bash init-db.sh

# 8. Launch all services with one command
python launch.py
```

This starts:
- **API Server** on `http://127.0.0.1:8000`
- **Stream Server** on `http://127.0.0.1:8001`
- **Dashboard** on `http://127.0.0.1:3000`

Press `Ctrl+C` to stop all services.

### Option B — Docker Compose (Full Stack)

```bash
docker compose up --build -d
docker compose exec api bash /app/init-db.sh
```

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/events/ingest` | Ingest detection events from the pipeline |
| `GET` | `/api/v1/metrics?store_id=STORE1&date=2024-01-15` | Dashboard KPIs (visitors, conversion, queue) |
| `GET` | `/api/v1/funnel?store_id=STORE1&date=2024-01-15` | Conversion funnel stages |
| `GET` | `/api/v1/heatmap?store_id=STORE1&date=2024-01-15` | Department visitor density |
| `GET` | `/api/v1/anomalies?store_id=STORE1` | Active anomaly alerts |
| `GET` | `/api/v1/health` | System health check (DB + Redis) |
| `GET` | `/docs` | Interactive Swagger API documentation |

---

## Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=detection --cov=api --cov-report=term -v

# Or use the Makefile
make test
```

---

## Environment Variables

Create a `.env` file in the project root (use `.env.example` as a template):

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://user:password@localhost:5432/retail_db` | PostgreSQL connection string |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection string |
| `LOG_LEVEL` | `info` | Logging verbosity (`debug`, `info`, `warn`, `error`) |
| `MODEL_PATH` | `models/yolov8n.pt` | Path to YOLOv8 model weights |
| `STORE_CONFIG_PATH` | `data/zones/stores.json` | Store zone configuration file |
| `API_PORT` | `8000` | REST API server port |

---

## License

MIT License — see [LICENSE](LICENSE) for details.
