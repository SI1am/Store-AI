# StoreLens Dashboard — Real-Time Retail Analytics UI

The **StoreLens Dashboard** is a live analytics frontend for StoreLens. Built with **React 19**, **TypeScript**, and **Vite**, it provides real-time visibility into store operations — shopper counts, conversion funnels, department heatmaps, anomaly alerts, and live camera feeds with annotated detection overlays.

---

## Features

| Feature | Description |
|---|---|
| **Live KPI Cards** | Unique visitors, conversion rate, queue depth, abandonment rate — all auto-refreshing every 5 seconds. |
| **Conversion Funnel** | Interactive stage-by-stage funnel from Entry → Department → Billing → Purchase, with drop-off percentages. |
| **Department Heatmap** | Color-coded grid showing visitor density per zone (e.g., PRODUCT_A, PRODUCT_B, BILLING). |
| **Anomaly Alerts** | Real-time alert feed with severity badges (critical/warning/info) for unusual activity patterns. |
| **Live Camera Feeds** | MJPEG streams from 5 CCTV cameras with YOLO-detected bounding boxes, track IDs, and staff labels rendered live. |
| **Staff vs. Shopper Split** | Separate counts distinguishing store employees from customers using appearance + positional heuristics. |
| **API Documentation Link** | One-click access to the backend Swagger/OpenAPI docs. |

---

## Tech Stack

- **Framework**: [React 19](https://react.dev/) with TypeScript
- **Build Tool**: [Vite 8](https://vite.dev/)
- **Icons**: [Lucide React](https://lucide.dev/)
- **Styling**: Vanilla CSS with CSS custom properties (dark theme)
- **State Management**: React `useState` + `useEffect` polling

---

## Prerequisites

- **Node.js** >= 18.x
- **npm** >= 9.x
- A running **Backend API** server at `http://127.0.0.1:8000` (see the [Backend README](../README.md))
- A running **Stream Server** at `http://127.0.0.1:8001` for live camera feeds

---

## Getting Started

### 1. Install Dependencies

```bash
cd dashboard
npm install
```

### 2. Start the Dev Server

```bash
npm run dev
```

The dashboard will open at **http://127.0.0.1:3000**.

### 3. Build for Production (Optional)

```bash
npm run build
npm run preview
```

---

## Backend Connection

The dashboard connects to the following backend endpoints (configured in `src/App.tsx`):

| Service | URL | Purpose |
|---|---|---|
| **REST API** | `http://127.0.0.1:8000/api/v1/` | KPIs, funnel, heatmap, anomalies |
| **Stream Server** | `http://127.0.0.1:8001/stream/{cam_id}` | Live MJPEG camera feeds |
| **Swagger Docs** | `http://127.0.0.1:8000/docs` | Interactive API documentation |

> **Note**: If the backend is running on a different host/port, update the fetch URLs in `src/App.tsx`.

---

## Project Structure

```
dashboard/
├── public/                   # Static assets
├── src/
│   ├── App.tsx               # Main application component (all views + data fetching)
│   ├── App.css               # Component-specific styles
│   ├── index.css             # Global styles & CSS custom properties
│   ├── main.tsx              # React DOM entry point
│   └── assets/               # Image assets
├── index.html                # HTML entry point
├── package.json              # Dependencies & scripts
├── vite.config.ts            # Vite configuration (port 3000)
├── tsconfig.json             # TypeScript base config
├── tsconfig.app.json         # App-specific TS config
├── tsconfig.node.json        # Node-specific TS config
└── eslint.config.js          # ESLint configuration
```

---

## Available Scripts

| Command | Description |
|---|---|
| `npm run dev` | Start Vite dev server with HMR on port 3000 |
| `npm run build` | Type-check and build for production |
| `npm run preview` | Preview the production build locally |
| `npm run lint` | Run ESLint checks |

---

## Design

The dashboard uses a **dark theme** with a modern glassmorphism aesthetic:
- Background gradients with frosted glass card effects
- Vibrant accent colors for KPI indicators
- Smooth micro-animations on hover and data refresh
- Responsive grid layout adapting to different screen sizes

---

## License

This project is part of StoreLens. See the root [README](../README.md) for full project details.
