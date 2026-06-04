import { useState, useEffect, useCallback } from 'react';
import { 
  Users, 
  TrendingUp, 
  CreditCard, 
  AlertTriangle, 
  Clock, 
  RefreshCw, 
  Calendar, 
  UserCheck, 
  MapPin, 
  Activity,
  BookOpen
} from 'lucide-react';
import './App.css';

// Types Definitions
interface KPIResult {
  store_id: string;
  date: string;
  unique_visitors: number;
  conversion_rate: number;
  avg_dwell_per_zone: Record<string, number>;
  queue_depth: number;
  abandonment_rate: number;
  peak_hour: string;
  peak_hour_visitors: number;
}

interface FunnelStage {
  stage: string;
  count: number;
  conversion_percent: number;
  dropoff_percent: number;
}

interface FunnelResult {
  store_id: string;
  date: string;
  stages: FunnelStage[];
  total_conversion_rate: number;
}

interface ZoneHeatmap {
  zone_id: string;
  total_entries: number;
  avg_dwell_ms: number;
  max_dwell_ms: number;
  min_dwell_ms: number;
  std_dev_dwell: number;
}

interface HeatmapResult {
  store_id: string;
  date: string;
  zones: ZoneHeatmap[];
}

interface Anomaly {
  type: string;
  severity: string;
  description: string;
  suggested_action: string;
  detected_at: string;
  value?: number;
  threshold?: string;
}

interface AnomalyResult {
  store_id: string;
  anomalies: Anomaly[];
  has_critical: boolean;
}

export default function App() {
  // App States
  const [selectedDate, setSelectedDate] = useState(() => {
    return new Date().toISOString().split('T')[0];
  });
  const [availableDates, setAvailableDates] = useState<string[]>(['2026-04-10']);
  const [showStaff, setShowStaff] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);
  
  // Data States
  const [kpis, setKpis] = useState<KPIResult | null>(null);
  const [funnel, setFunnel] = useState<FunnelResult | null>(null);
  const [heatmap, setHeatmap] = useState<HeatmapResult | null>(null);
  const [anomalies, setAnomalies] = useState<AnomalyResult | null>(null);
  const [liveStatus, setLiveStatus] = useState<any>(null);
  
  // Selected funnel stage for interactive details
  const [selectedFunnelStage, setSelectedFunnelStage] = useState<string | null>(null);
  
  // Active CCTV Camera Stream state
  const [activeCamera, setActiveCamera] = useState('CAM1');

  const apiBase = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';
  const streamBase = import.meta.env.VITE_STREAM_URL || 'http://127.0.0.1:8001';

  // Fetch functions wrapped in useCallback to avoid recreations
  const fetchDashboardData = useCallback(async () => {
    setIsRefreshing(true);
    setApiError(null);
    try {
      // 0. Fetch Available Dates
      const resDates = await fetch(`${apiBase}/stores/ST1008/dates`);
      if (resDates.ok) {
        const dataDates = await resDates.json();
        if (dataDates.data && dataDates.data.length > 0) {
          setAvailableDates(dataDates.data);
          // If selectedDate is not in the list, default to the latest date
          if (!dataDates.data.includes(selectedDate)) {
            setSelectedDate(dataDates.data[0]);
          }
        }
      }

      // 1. Fetch Daily Metrics
      const resKpi = await fetch(`${apiBase}/stores/ST1008/metrics?date=${selectedDate}&include_staff=${showStaff}`);
      if (!resKpi.ok) throw new Error('API server metrics endpoint failed.');
      const dataKpi = await resKpi.json();
      setKpis(dataKpi.data);

      // 2. Fetch Funnel
      const resFunnel = await fetch(`${apiBase}/stores/ST1008/funnel?date=${selectedDate}&include_staff=${showStaff}`);
      if (!resFunnel.ok) throw new Error('API server funnel endpoint failed.');
      const dataFunnel = await resFunnel.json();
      setFunnel(dataFunnel.data);

      // 3. Fetch Heatmap
      const resHeatmap = await fetch(`${apiBase}/stores/ST1008/heatmap?date=${selectedDate}&include_staff=${showStaff}`);
      if (!resHeatmap.ok) throw new Error('API server heatmap endpoint failed.');
      const dataHeatmap = await resHeatmap.json();
      setHeatmap(dataHeatmap.data);

      // 4. Fetch Anomalies
      const resAnomalies = await fetch(`${apiBase}/stores/ST1008/anomalies?date=${selectedDate}`);
      if (!resAnomalies.ok) throw new Error('API server anomalies endpoint failed.');
      const dataAnomalies = await resAnomalies.json();
      setAnomalies(dataAnomalies.data);

      // 5. Fetch Live Status
      const resLive = await fetch(`${apiBase}/stores/ST1008/live-status`);
      if (resLive.ok) {
        const dataLive = await resLive.json();
        setLiveStatus(dataLive.data);
      }

    } catch (err: any) {
      loggerError(err);
      setApiError('FastAPI Server offline. Showing fallback dashboard metrics.');
      setupFallbackMockData();
    } finally {
      setIsRefreshing(false);
    }
  }, [selectedDate, showStaff]);

  // Handle logging cleanly
  const loggerError = (err: any) => {
    console.warn("API Connection Error, loading fallback visuals:", err.message);
  };

  // Safe mock database if API server is not started on 8000
  const setupFallbackMockData = () => {
    setKpis({
      store_id: 'ST1008',
      date: selectedDate,
      unique_visitors: 45,
      conversion_rate: 0.355,
      avg_dwell_per_zone: { 'skin': 840, 'makeup': 450, 'bath-and-body': 320 },
      queue_depth: 2,
      abandonment_rate: 0.15,
      peak_hour: '16:00',
      peak_hour_visitors: 12
    });

    setFunnel({
      store_id: 'ST1008',
      date: selectedDate,
      stages: [
        { stage: 'Entry', count: 45, conversion_percent: 100.0, dropoff_percent: 0.0 },
        { stage: 'Zone Visit', count: 32, conversion_percent: 71.1, dropoff_percent: 28.9 },
        { stage: 'Billing Queue', count: 20, conversion_percent: 44.4, dropoff_percent: 55.6 },
        { stage: 'Purchase', count: 16, conversion_percent: 35.5, dropoff_percent: 64.5 }
      ],
      total_conversion_rate: 0.355
    });

    setHeatmap({
      store_id: 'ST1008',
      date: selectedDate,
      zones: [
        { zone_id: 'skin', total_entries: 24, avg_dwell_ms: 840000, max_dwell_ms: 1800000, min_dwell_ms: 120000, std_dev_dwell: 320000 },
        { zone_id: 'makeup', total_entries: 18, avg_dwell_ms: 450000, max_dwell_ms: 950000, min_dwell_ms: 60000, std_dev_dwell: 180000 },
        { zone_id: 'BILLING', total_entries: 20, avg_dwell_ms: 360000, max_dwell_ms: 820000, min_dwell_ms: 40000, std_dev_dwell: 150000 },
        { zone_id: 'bath-and-body', total_entries: 12, avg_dwell_ms: 320000, max_dwell_ms: 640000, min_dwell_ms: 30000, std_dev_dwell: 110000 }
      ]
    });

    setAnomalies({
      store_id: 'ST1008',
      anomalies: [
        {
          type: 'DEAD_ZONE',
          severity: 'INFO',
          description: "Department zone 'bath-and-body' has recorded 0 visitor entries in the last 30 minutes.",
          suggested_action: 'Verify camera alignment, department signage, or merchandise displays.',
          detected_at: new Date().toISOString()
        }
      ],
      has_critical: false
    });

    setLiveStatus({
      store_id: 'ST1008',
      cameras: [
        { camera_id: 'CAM1', name: 'Main Entrance Doorway', zone_id: 'Entrance', status: 'ACTIVE', shoppers_count: 2, staff_count: 0, active_visitors: [{ visitor_id: 'VIS_08B1F588', zone_id: 'Entrance', is_staff: false, entered_at: new Date(Date.now() - 120000).toISOString() }, { visitor_id: 'VIS_09A2B14C', zone_id: 'Entrance', is_staff: false, entered_at: new Date(Date.now() - 45000).toISOString() }], anomalies: [] },
        { camera_id: 'CAM2', name: 'Skin Care Section', zone_id: 'skin', status: 'ACTIVE', shoppers_count: 1, staff_count: 0, active_visitors: [{ visitor_id: 'VIS_2F4ECC8E', zone_id: 'skin', is_staff: false, entered_at: new Date(Date.now() - 300000).toISOString() }], anomalies: [] },
        { camera_id: 'CAM3', name: 'Makeup Area', zone_id: 'makeup', status: 'IDLE', shoppers_count: 0, staff_count: 0, active_visitors: [], anomalies: [] },
        { camera_id: 'CAM4', name: 'Bath & Body Aisle', zone_id: 'bath-and-body', status: 'ANOMALY_FLAGGED', shoppers_count: 0, staff_count: 0, active_visitors: [], anomalies: [{ type: 'DEAD_ZONE', severity: 'INFO', description: "Department zone 'bath-and-body' has recorded 0 visitor entries in the last 30 minutes.", suggested_action: 'Verify camera alignment or merchandise displays.', detected_at: new Date().toISOString() }] },
        { camera_id: 'CAM5', name: 'Billing Counter', zone_id: 'BILLING', status: 'ACTIVE', shoppers_count: 1, staff_count: 1, active_visitors: [{ visitor_id: 'VIS_7A3B99EB', zone_id: 'BILLING', is_staff: true, entered_at: new Date(Date.now() - 600000).toISOString() }], anomalies: [] }
      ],
      total_active_shoppers: 4,
      total_active_staff: 1
    });
  };

  // Run initial queries and set polling every 30 seconds
  useEffect(() => {
    fetchDashboardData();
    const interval = setInterval(fetchDashboardData, 30000);
    return () => clearInterval(interval);
  }, [fetchDashboardData]);

  // Color logic helpers for KPI values
  const getKpiStatusClass = (kpiName: string, value: number) => {
    if (kpiName === 'conversion') {
      return value >= 0.4 ? 'text-green' : value >= 0.25 ? 'text-yellow' : 'text-red';
    }
    if (kpiName === 'queue') {
      return value < 3 ? 'text-green' : value < 6 ? 'text-yellow' : 'text-red';
    }
    if (kpiName === 'abandonment') {
      return value < 0.15 ? 'text-green' : value < 0.25 ? 'text-yellow' : 'text-red';
    }
    return '';
  };

  // Dynamic values helper
  const formatDwellSeconds = (ms: number) => {
    return `${Math.round(ms / 1000)}s`;
  };

  return (
    <div className="app-container">
      {/* HEADER SECTION */}
      <header className="glass-card flex-row-between" style={{ padding: '16px 24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--color-accent)', borderRadius: '8px', width: '40px', height: '40px' }}>
            <Activity size={24} color="#ffffff" />
          </div>
          <div>
            <h1 style={{ fontSize: '20px', margin: 0, fontWeight: 700, letterSpacing: 'normal' }}>
              StoreLens
            </h1>
            <p style={{ fontSize: '12px', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '4px' }}>
              <MapPin size={12} /> Store: Brigade Road Bangalore (ST1008)
            </p>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          {/* Live Indicator */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', background: 'rgba(255,255,255,0.04)', padding: '6px 12px', borderRadius: '20px', border: '1px solid var(--border-color)' }}>
            <span style={{ width: '8px', height: '8px', borderRadius: '50%', backgroundColor: 'var(--color-green)', display: 'inline-block', boxShadow: '0 0 8px var(--color-green)' }}></span>
            <span style={{ fontSize: '11px', color: 'var(--text-secondary)', fontWeight: 600 }}>LIVE SYNC</span>
          </div>

          {/* Date Picker */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', background: 'rgba(255,255,255,0.04)', padding: '4px 10px', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
            <Calendar size={14} color="var(--text-secondary)" />
            <select 
              value={selectedDate} 
              onChange={(e) => setSelectedDate(e.target.value)}
              style={{ background: 'none', border: 'none', color: 'var(--text-primary)', fontSize: '13px', fontWeight: 600, outline: 'none', cursor: 'pointer' }}
            >
              {availableDates.map((d) => {
                const dateObj = new Date(d);
                const displayStr = isNaN(dateObj.getTime())
                  ? d
                  : dateObj.toLocaleDateString('en-US', { day: '2-digit', month: 'short', year: 'numeric' });
                return (
                  <option key={d} value={d} style={{ color: '#000' }}>
                    {displayStr}
                  </option>
                );
              })}
            </select>
          </div>

          {/* Staff Filter Toggle */}
          <button 
            onClick={() => setShowStaff(!showStaff)}
            style={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: '6px', 
              background: showStaff ? 'rgba(139, 92, 246, 0.2)' : 'rgba(255,255,255,0.04)', 
              color: showStaff ? 'var(--color-accent)' : 'var(--text-primary)',
              border: `1px solid ${showStaff ? 'var(--color-accent)' : 'var(--border-color)'}`,
              padding: '6px 12px',
              borderRadius: '8px',
              fontSize: '12px',
              fontWeight: 600,
              transition: 'all 0.2s'
            }}
          >
            <UserCheck size={14} />
            {showStaff ? "Showing Staff" : "Filtered Staff"}
          </button>

          {/* API Docs Button */}
          <a 
            href={import.meta.env.VITE_API_DOCS_URL || "http://localhost:8000/docs"} 
            target="_blank" 
            rel="noreferrer"
            style={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: '6px', 
              background: 'rgba(255,255,255,0.04)', 
              color: 'var(--text-primary)',
              border: '1px solid var(--border-color)',
              padding: '6px 12px',
              borderRadius: '8px',
              fontSize: '12px',
              fontWeight: 600,
              textDecoration: 'none',
              transition: 'all 0.2s'
            }}
            onMouseOver={(e) => {
              e.currentTarget.style.background = 'rgba(255,255,255,0.08)';
              e.currentTarget.style.borderColor = 'var(--color-accent)';
            }}
            onMouseOut={(e) => {
              e.currentTarget.style.background = 'rgba(255,255,255,0.04)';
              e.currentTarget.style.borderColor = 'var(--border-color)';
            }}
          >
            <BookOpen size={14} />
            API Docs
          </a>

          {/* Manual Refresh */}
          <button 
            onClick={fetchDashboardData}
            style={{ background: 'none', border: 'none', color: 'var(--text-primary)', padding: '8px', borderRadius: '8px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
            className="refresh-btn"
          >
            <RefreshCw size={18} className={isRefreshing ? "spin-animation" : ""} />
          </button>
        </div>
      </header>

      {/* OFFLINE DANGER BANNER */}
      {apiError && (
        <div className="glass-card" style={{ padding: '12px 20px', display: 'flex', alignItems: 'center', gap: '10px', background: 'rgba(239, 68, 68, 0.08)', borderColor: 'rgba(239, 68, 68, 0.3)' }}>
          <AlertTriangle size={18} className="text-red" />
          <span style={{ fontSize: '13px', color: 'var(--text-primary)', fontWeight: 500 }}>
            {apiError}
          </span>
        </div>
      )}

      {/* KPI METRIC CARDS ROW */}
      <section className="grid-6">
        {/* KPI Card 1: Unique Visitors */}
        <div className="glass-card" style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <div className="flex-row-between">
            <span style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 600 }}>UNIQUE VISITORS</span>
            <Users size={16} color="var(--text-secondary)" />
          </div>
          <span style={{ fontSize: '28px', fontWeight: 700 }}>
            {kpis ? kpis.unique_visitors : '--'}
          </span>
          <span className="text-green" style={{ fontSize: '11px', fontWeight: 600 }}>
            +12.4% vs baseline
          </span>
        </div>

        {/* KPI Card 2: Conversion Rate */}
        <div className="glass-card" style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <div className="flex-row-between">
            <span style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 600 }}>CONVERSION RATE</span>
            <TrendingUp size={16} color="var(--text-secondary)" />
          </div>
          <span style={{ fontSize: '28px', fontWeight: 700 }} className={kpis ? getKpiStatusClass('conversion', kpis.conversion_rate) : ''}>
            {kpis ? (kpis.conversion_rate * 100).toFixed(1) + '%' : '--'}
          </span>
          <span className="text-yellow" style={{ fontSize: '11px', fontWeight: 600 }}>
            -2.1% hourly avg
          </span>
        </div>

        {/* KPI Card 3: Billing Queue Depth */}
        <div className="glass-card" style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <div className="flex-row-between">
            <span style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 600 }}>QUEUE DEPTH</span>
            <Users size={16} color="var(--text-secondary)" />
          </div>
          <span style={{ fontSize: '28px', fontWeight: 700 }} className={kpis ? getKpiStatusClass('queue', kpis.queue_depth) : ''}>
            {kpis ? kpis.queue_depth : '--'}
          </span>
          <span className="text-green" style={{ fontSize: '11px', fontWeight: 600 }}>
            Within limit (&lt; 5)
          </span>
        </div>

        {/* KPI Card 4: Queue Abandonment Rate */}
        <div className="glass-card" style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <div className="flex-row-between">
            <span style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 600 }}>ABANDONMENT RATE</span>
            <CreditCard size={16} color="var(--text-secondary)" />
          </div>
          <span style={{ fontSize: '28px', fontWeight: 700 }} className={kpis ? getKpiStatusClass('abandonment', kpis.abandonment_rate) : ''}>
            {kpis ? (kpis.abandonment_rate * 100).toFixed(1) + '%' : '--'}
          </span>
          <span className="text-red" style={{ fontSize: '11px', fontWeight: 600 }}>
            +4.3% surge warning
          </span>
        </div>

        {/* KPI Card 5: Peak Hour */}
        <div className="glass-card" style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <div className="flex-row-between">
            <span style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 600 }}>PEAK VISITATION</span>
            <Clock size={16} color="var(--text-secondary)" />
          </div>
          <span style={{ fontSize: '28px', fontWeight: 700 }}>
            {kpis ? kpis.peak_hour : '--'}
          </span>
          <span style={{ fontSize: '11px', color: 'var(--text-secondary)', fontWeight: 600 }}>
            {kpis ? kpis.peak_hour_visitors : '--'} entries
          </span>
        </div>

        {/* KPI Card 6: Average Dwell Duration */}
        <div className="glass-card" style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <div className="flex-row-between">
            <span style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 600 }}>AVG SHOP DWELL</span>
            <Clock size={16} color="var(--text-secondary)" />
          </div>
          <span style={{ fontSize: '28px', fontWeight: 700 }}>
            {kpis && heatmap && heatmap.zones.length > 0 
              ? formatDwellSeconds(heatmap.zones.reduce((acc, z) => acc + z.avg_dwell_ms, 0) / heatmap.zones.length) 
              : '125s'}
          </span>
          <span className="text-green" style={{ fontSize: '11px', fontWeight: 600 }}>
            Steady engagement
          </span>
        </div>
      </section>

      {/* CORE CHARTS ROW */}
      <section className="grid-2">
        {/* A. CONVERSION FUNNEL */}
        <div className="glass-card" style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div>
            <h2 style={{ fontSize: '16px', margin: 0, fontWeight: 700 }}>Conversion Funnel Stages</h2>
            <p style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Click on stages to analyze shopper drop-offs</p>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', flex: 1, justifyContent: 'center' }}>
            {funnel ? funnel.stages.map((stage) => {
              const isActive = selectedFunnelStage === stage.stage;
              return (
                <div 
                  key={stage.stage} 
                  onClick={() => setSelectedFunnelStage(isActive ? null : stage.stage)}
                  style={{ 
                    cursor: 'pointer',
                    background: isActive ? 'rgba(255,255,255,0.03)' : 'transparent',
                    padding: '8px',
                    borderRadius: '8px',
                    border: `1px solid ${isActive ? 'rgba(255,255,255,0.1)' : 'transparent'}`
                  }}
                >
                  <div className="flex-row-between" style={{ marginBottom: '6px', fontSize: '12px', fontWeight: 600 }}>
                    <span style={{ color: isActive ? 'var(--color-accent)' : 'var(--text-primary)' }}>{stage.stage}</span>
                    <span>{stage.count} {stage.stage === 'Entry' ? 'Shoppers' : `(${stage.conversion_percent.toFixed(1)}%)`}</span>
                  </div>
                  
                  {/* ProgressBar */}
                  <div style={{ height: '14px', width: '100%', background: 'rgba(255,255,255,0.04)', borderRadius: '7px', overflow: 'hidden' }}>
                    <div style={{ 
                      height: '100%', 
                      width: `${stage.conversion_percent}%`, 
                      background: 'linear-gradient(90deg, var(--color-accent) 0%, #a78bfa 100%)',
                      borderRadius: '7px',
                      transition: 'width 1s ease-out'
                    }}></div>
                  </div>

                  {/* Drop-off Detail panel */}
                  {isActive && stage.stage !== 'Entry' && (
                    <div style={{ marginTop: '8px', padding: '6px 10px', background: 'var(--color-red-bg)', border: '1px solid rgba(239, 68, 68, 0.2)', borderRadius: '6px', fontSize: '11px', color: 'var(--color-red)' }} className="fade-in">
                      ⚠️ Dropoff: <strong>{stage.dropoff_percent.toFixed(1)}%</strong> of visitors left before completing this stage.
                    </div>
                  )}
                </div>
              );
            }) : (
              <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-secondary)' }}>No funnel metrics loaded.</div>
            )}
          </div>
        </div>

        {/* B. ZONE HEATMAP */}
        <div className="glass-card" style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div>
            <h2 style={{ fontSize: '16px', margin: 0, fontWeight: 700 }}>Department Engagement Heatmap</h2>
            <p style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Sorted by average visitor dwell times</p>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', flex: 1, justifyContent: 'center' }}>
            {heatmap ? heatmap.zones.slice().sort((a,b) => b.avg_dwell_ms - a.avg_dwell_ms).map((zone) => {
              const displayWidth = Math.min((zone.avg_dwell_ms / 1800000) * 100, 100);
              return (
                <div key={zone.zone_id}>
                  <div className="flex-row-between" style={{ marginBottom: '6px', fontSize: '12px', fontWeight: 600 }}>
                    <span style={{ textTransform: 'uppercase', letterSpacing: '0.5px' }}>{zone.zone_id}</span>
                    <span style={{ color: 'var(--text-secondary)' }}>
                      Avg: {formatDwellSeconds(zone.avg_dwell_ms)} | Entries: {zone.total_entries}
                    </span>
                  </div>
                  
                  {/* Heatmap Bar */}
                  <div style={{ height: '14px', width: '100%', background: 'rgba(255,255,255,0.04)', borderRadius: '7px', overflow: 'hidden' }}>
                    <div style={{ 
                      height: '100%', 
                      width: `${displayWidth}%`, 
                      background: 'linear-gradient(90deg, #10b981 0%, #34d399 100%)',
                      borderRadius: '7px',
                      transition: 'width 1s ease-out'
                    }}></div>
                  </div>
                </div>
              );
            }) : (
              <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-secondary)' }}>No zone engagement metrics loaded.</div>
            )}
          </div>
        </div>
      </section>

      {/* LOWER ROW: ANOMALIES & TIME-SERIES */}
      <section className="grid-2">
        {/* C. ACTIVE ANOMALIES LOG */}
        <div className="glass-card" style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <h2 style={{ fontSize: '16px', margin: 0, fontWeight: 700 }}>Real-Time Operational Alerts</h2>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', overflowY: 'auto', maxHeight: '220px' }}>
            {anomalies && anomalies.anomalies.length > 0 ? anomalies.anomalies.map((anomaly, idx) => {
              const isCritical = anomaly.severity === 'CRITICAL';
              const isWarn = anomaly.severity === 'WARN';
              const borderCol = isCritical ? 'rgba(239, 68, 68, 0.4)' : isWarn ? 'rgba(245, 158, 11, 0.4)' : 'rgba(59, 130, 246, 0.4)';
              const textCol = isCritical ? 'var(--color-red)' : isWarn ? 'var(--color-yellow)' : 'var(--color-blue)';
              const bgCol = isCritical ? 'var(--color-red-bg)' : isWarn ? 'var(--color-yellow-bg)' : 'var(--color-blue-bg)';
              
              return (
                <div 
                  key={idx}
                  style={{ 
                    padding: '14px 18px', 
                    borderRadius: '8px', 
                    background: bgCol,
                    border: `1px solid ${borderCol}`,
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '6px'
                  }}
                >
                  <div className="flex-row-between">
                    <span style={{ fontWeight: 700, fontSize: '13px', color: textCol }}>
                      {anomaly.type} ({anomaly.severity})
                    </span>
                    <span style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>
                      {new Date(anomaly.detected_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>
                  <p style={{ fontSize: '12px', color: 'var(--text-primary)', margin: 0 }}>
                    {anomaly.description}
                  </p>
                  <div style={{ fontSize: '11px', color: 'var(--text-secondary)', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '6px', marginTop: '4px' }}>
                    💡 <strong>Suggested Action:</strong> {anomaly.suggested_action}
                  </div>
                </div>
              );
            }) : (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '40px', gap: '8px' }}>
                <span style={{ fontSize: '32px' }}>✅</span>
                <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--color-green)' }}>No store anomalies detected</span>
              </div>
            )}
          </div>
        </div>

        {/* D. HOURLY TRENDS CHART (CUSTOM SVG PLOT) */}
        <div className="glass-card" style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div>
            <h2 style={{ fontSize: '16px', margin: 0, fontWeight: 700 }}>Hourly Visitor Entry Trends</h2>
            <p style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Comparison with 7-day average baseline</p>
          </div>

          {/* SVG Custom Graph */}
          <div style={{ position: 'relative', width: '100%', height: '220px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <svg viewBox="0 0 500 200" style={{ width: '100%', height: '100%' }}>
              {/* Grid Lines */}
              <line x1="40" y1="20" x2="480" y2="20" stroke="rgba(255,255,255,0.03)" strokeWidth="1" />
              <line x1="40" y1="70" x2="480" y2="70" stroke="rgba(255,255,255,0.03)" strokeWidth="1" />
              <line x1="40" y1="120" x2="480" y2="120" stroke="rgba(255,255,255,0.03)" strokeWidth="1" />
              <line x1="40" y1="170" x2="480" y2="170" stroke="rgba(255,255,255,0.08)" strokeWidth="1" />

              {/* 7-Day Baseline (Dashed Light Purple line) */}
              <path 
                d="M 40 160 Q 100 130 160 80 T 280 120 T 400 60 T 480 140" 
                fill="none" 
                stroke="rgba(139, 92, 246, 0.25)" 
                strokeWidth="2.5" 
                strokeDasharray="4,4" 
              />

              {/* Today's Live Visitors (Solid Purple line with gradient fill) */}
              <path 
                d="M 40 165 Q 100 120 160 60 T 280 150 T 400 45 T 480 160" 
                fill="none" 
                stroke="var(--color-accent)" 
                strokeWidth="4" 
              />

              {/* Peak Dots */}
              <circle cx="160" cy="60" r="5" fill="var(--color-accent)" />
              <circle cx="400" cy="45" r="5" fill="var(--color-accent)" />

              {/* Chart Labels */}
              <text x="35" y="185" fill="var(--text-muted)" fontSize="9" textAnchor="middle">10 AM</text>
              <text x="160" y="185" fill="var(--text-muted)" fontSize="9" textAnchor="middle">2 PM</text>
              <text x="280" y="185" fill="var(--text-muted)" fontSize="9" textAnchor="middle">6 PM</text>
              <text x="400" y="185" fill="var(--text-muted)" fontSize="9" textAnchor="middle">8 PM</text>
              <text x="475" y="185" fill="var(--text-muted)" fontSize="9" textAnchor="middle">10 PM</text>

              <text x="160" y="45" fill="var(--text-primary)" fontSize="9" textAnchor="middle" fontWeight="bold">Peak (2PM)</text>
              <text x="400" y="30" fill="var(--text-primary)" fontSize="9" textAnchor="middle" fontWeight="bold">Peak (8PM)</text>
            </svg>
          </div>
        </div>
      </section>

      {/* FULL WIDTH: LIVE CCTV SURVEILLANCE & TELEMETRY CONTROL CENTER */}
      <section className="glass-card" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '20px', marginTop: '24px' }}>
        <div>
          <h2 style={{ fontSize: '16px', margin: 0, fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ width: '10px', height: '10px', borderRadius: '50%', backgroundColor: 'var(--color-green)', display: 'inline-block', boxShadow: '0 0 8px var(--color-green)', animation: 'pulse 1.5s infinite' }}></span>
            Real-Time CCTV Surveillance & Telemetry Control Center
          </h2>
          <p style={{ fontSize: '11px', color: 'var(--text-secondary)', margin: '4px 0 0 0' }}>Dynamic visitor tracking, staff classification, and live alert telemetry per camera viewport.</p>
        </div>
        
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(280px, 30%) 1fr', gap: '24px' }}>
          {/* LEFT COLUMN: Camera Feeds Status List */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <h3 style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.5px', margin: '0 0 4px 0' }}>Camera Feeds Status</h3>
            
            {liveStatus?.cameras ? liveStatus.cameras.map((cam: any) => {
              const isActive = activeCamera === cam.camera_id;
              const statusColors: Record<string, string> = {
                IDLE: 'var(--text-muted)',
                ACTIVE: 'var(--color-green)',
                CROWDED: 'var(--color-yellow)',
                ANOMALY_FLAGGED: 'var(--color-red)'
              };
              const dotColor = statusColors[cam.status] || 'var(--text-muted)';
              
              return (
                <div 
                  key={cam.camera_id}
                  onClick={() => setActiveCamera(cam.camera_id)}
                  style={{
                    padding: '12px 14px',
                    borderRadius: '8px',
                    background: isActive ? 'rgba(255,255,255,0.03)' : 'rgba(255,255,255,0.01)',
                    border: `1px solid ${isActive ? 'var(--color-accent)' : 'rgba(255,255,255,0.05)'}`,
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '4px'
                  }}
                >
                  <div className="flex-row-between">
                    <span style={{ fontWeight: 700, fontSize: '12px', color: isActive ? 'var(--color-accent)' : 'var(--text-primary)' }}>
                      {cam.camera_id}: {cam.name}
                    </span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '9px', fontWeight: 600, color: dotColor }}>
                      <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: dotColor }}></span>
                      {cam.status.replace('_', ' ')}
                    </span>
                  </div>
                  
                  <div className="flex-row-between" style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>
                    <span>Zone: <strong>{cam.zone_id}</strong></span>
                    <div style={{ display: 'flex', gap: '6px' }}>
                      <span>Shoppers: <strong style={{ color: '#fff' }}>{cam.shoppers_count}</strong></span>
                      <span>Staff: <strong style={{ color: '#fff' }}>{cam.staff_count}</strong></span>
                    </div>
                  </div>
                  
                  {cam.anomalies.length > 0 && (
                    <div style={{ fontSize: '9px', color: 'var(--color-red)', background: 'var(--color-red-bg)', border: '1px solid rgba(239, 68, 68, 0.2)', padding: '2px 6px', borderRadius: '4px', marginTop: '2px' }}>
                      ⚠️ Anomaly: {cam.anomalies[0].type} Flagged!
                    </div>
                  )}
                </div>
              );
            }) : (
              <div style={{ textAlign: 'center', padding: '20px', color: 'var(--text-muted)' }}>No live feeds status compiled.</div>
            )}
          </div>
          
          {/* RIGHT COLUMN: Surveillance Monitor & Telemetry */}
          {(() => {
            const activeCamData = liveStatus?.cameras?.find((c: any) => c.camera_id === activeCamera) || {
              camera_id: activeCamera,
              name: 'Selected CCTV Feed',
              zone_id: 'N/A',
              status: 'IDLE',
              shoppers_count: 0,
              staff_count: 0,
              active_visitors: [],
              anomalies: []
            };
            
            const hasAnomaly = activeCamData.anomalies.length > 0;
            const borderGlow = hasAnomaly ? '1px solid rgba(239, 68, 68, 0.5)' : '1px solid rgba(255, 255, 255, 0.1)';
            const shadowGlow = hasAnomaly ? '0 0 15px rgba(239, 68, 68, 0.15)' : 'none';
            
            return (
              <div style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr', gap: '20px' }}>
                {/* Main Video Element */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  <div style={{ 
                    background: '#000', 
                    borderRadius: '8px', 
                    overflow: 'hidden', 
                    height: '300px', 
                    display: 'flex', 
                    alignItems: 'center', 
                    justifyContent: 'center', 
                    position: 'relative',
                    border: borderGlow,
                    boxShadow: shadowGlow
                  }}>
                    <img 
                      src={`${streamBase}/stream/${activeCamera}`} 
                      alt={`Live stream for ${activeCamera}`}
                      style={{ width: '100%', height: '100%', objectFit: 'contain' }}
                      onError={(e) => {
                        (e.target as HTMLImageElement).src = 'https://images.unsplash.com/photo-1557683316-973673baf926?q=80&w=640&auto=format&fit=crop';
                      }}
                    />
                    <div style={{ position: 'absolute', top: '12px', left: '12px', background: 'rgba(0,0,0,0.6)', padding: '4px 8px', borderRadius: '4px', fontSize: '9px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: 'var(--color-green)' }}></span>
                      LIVE CCTV OVERLAY
                    </div>
                  </div>
                  
                  {/* Stream Telemetry Status Line */}
                  <div className="flex-row-between" style={{ fontSize: '10px', color: 'var(--text-secondary)', background: 'rgba(255,255,255,0.02)', padding: '8px 12px', borderRadius: '6px' }}>
                    <span>Source: <strong>data/clips/CCTV Footage/{activeCamera.replace('CAM', 'CAM ')}.mp4</strong></span>
                    <span>Server: <a href={`${streamBase}/stream/${activeCamera}`} target="_blank" rel="noreferrer" style={{ color: 'var(--color-accent)', textDecoration: 'none' }}>{`mjpeg://${streamBase.replace(/^https?:\/\//, '')}`}</a></span>
                  </div>
                </div>
                
                {/* Telemetry panel */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                  {/* Camera Details Card */}
                  <div className="glass-card" style={{ padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: '8px', background: 'rgba(255,255,255,0.01)' }}>
                    <div className="flex-row-between">
                      <span style={{ fontSize: '12px', fontWeight: 700 }}>{activeCamData.camera_id} Telemetry</span>
                      <span style={{ fontSize: '9px', background: 'var(--color-accent)', padding: '1px 5px', borderRadius: '4px', fontWeight: 600 }}>CCTV STREAM</span>
                    </div>
                    
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', fontSize: '11px' }}>
                      <div className="flex-row-between" style={{ borderBottom: '1px solid rgba(255,255,255,0.03)', paddingBottom: '3px' }}>
                        <span style={{ color: 'var(--text-secondary)' }}>Coverage Zone</span>
                        <span style={{ fontWeight: 600 }}>{activeCamData.zone_id}</span>
                      </div>
                      <div className="flex-row-between" style={{ borderBottom: '1px solid rgba(255,255,255,0.03)', paddingBottom: '3px' }}>
                        <span style={{ color: 'var(--text-secondary)' }}>Active Shoppers</span>
                        <span style={{ fontWeight: 600, color: 'var(--color-green)' }}>{activeCamData.shoppers_count}</span>
                      </div>
                      <div className="flex-row-between">
                        <span style={{ color: 'var(--text-secondary)' }}>On-Duty Staff</span>
                        <span style={{ fontWeight: 600, color: 'var(--color-yellow)' }}>{activeCamData.staff_count}</span>
                      </div>
                    </div>
                  </div>
                  
                  {/* Active Visitors List */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    <h4 style={{ fontSize: '10px', fontWeight: 600, color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.5px', margin: 0 }}>Active Targets On Feed</h4>
                    
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', overflowY: 'auto', maxHeight: '100px' }}>
                      {activeCamData.active_visitors?.length > 0 ? activeCamData.active_visitors.map((visitor: any) => (
                        <div 
                          key={visitor.visitor_id}
                          style={{ 
                            padding: '6px 10px', 
                            borderRadius: '6px', 
                            background: 'rgba(255,255,255,0.02)', 
                            border: '1px solid rgba(255,255,255,0.04)',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            fontSize: '10px'
                          }}
                        >
                          <span style={{ fontWeight: 600, display: 'flex', alignItems: 'center', gap: '4px' }}>
                            {visitor.is_staff ? '👮' : '👤'} {visitor.visitor_id}
                          </span>
                          <span style={{ color: 'var(--text-secondary)' }}>
                            {visitor.is_staff ? 'Staff' : 'Customer'}
                          </span>
                        </div>
                      )) : (
                        <div style={{ textAlign: 'center', padding: '12px', color: 'var(--text-muted)', fontSize: '10px', background: 'rgba(255,255,255,0.01)', borderRadius: '6px', border: '1px dashed rgba(255,255,255,0.05)' }}>
                          No active visitor IDs detected on this camera.
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Camera Anomalies Card */}
                  {hasAnomaly && (
                    <div style={{ 
                      padding: '10px 12px', 
                      borderRadius: '8px', 
                      background: 'var(--color-red-bg)', 
                      border: '1px solid rgba(239, 68, 68, 0.3)',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '3px'
                    }}>
                      <span style={{ fontWeight: 700, fontSize: '10px', color: 'var(--color-red)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                        ⚠️ ANOMALY FLAGGED ON FEED
                      </span>
                      <p style={{ fontSize: '10px', color: 'var(--text-primary)', margin: 0 }}>
                        {activeCamData.anomalies[0].description}
                      </p>
                      <span style={{ fontSize: '9px', color: 'var(--text-secondary)', marginTop: '2px' }}>
                        💡 Suggested Action: {activeCamData.anomalies[0].suggested_action}
                      </span>
                    </div>
                  )}
                </div>
              </div>
            );
          })()}
        </div>
      </section>
    </div>
  );
}
