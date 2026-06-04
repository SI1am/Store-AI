import pytest
from datetime import datetime, date
import uuid
import json

def test_health_endpoint(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    res_data = response.json()
    assert "status" in res_data
    assert "components" in res_data
    # In tests health is degraded or unhealthy because postgres pool connect is bypassed, but it resolves to 200
    assert len(res_data["components"]) == 3

def test_events_ingestion_validation(client):
    # Let's test invalid event schemas: confidence out of bounds
    invalid_event = {
        "events": [
            {
                "event_id": str(uuid.uuid4()),
                "store_id": "S001",
                "camera_id": "CAM_A",
                "visitor_id": "VIS_abc123xyz789",
                "event_type": "ENTRY",
                "timestamp": "2024-01-15T10:30:15Z",
                "confidence": 1.5,  # Invalid (> 1.0)
            }
        ]
    }
    response = client.post("/api/v1/events/ingest", json=invalid_event)
    assert response.status_code == 422  # Unprocessable Entity
    
    # Test valid schema but missing required fields
    incomplete_event = {
        "events": [
            {
                "event_id": str(uuid.uuid4()),
                "store_id": "S001"
            }
        ]
    }
    response = client.post("/api/v1/events/ingest", json=incomplete_event)
    assert response.status_code == 422

def test_metrics_caching_and_zero_visitors(client, mock_redis):
    # Empty store Metrics check
    response = client.get("/api/v1/stores/S999/metrics")
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "ok"
    metrics = res_data["data"]
    assert metrics["store_id"] == "S999"
    assert metrics["unique_visitors"] == 0
    assert metrics["conversion_rate"] == 0.0
    assert metrics["queue_depth"] == 0
    assert metrics["abandonment_rate"] == 0.0
    
    # Caching check: Key metrics:S999:today should exist in Redis now
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    cache_key = f"metrics:S999:{today_str}:False"
    
    import asyncio
    assert asyncio.run(mock_redis.exists(cache_key)) == 1
    
    # Fetching metrics a second time should trigger Cache HIT
    response_cached = client.get("/api/v1/stores/S999/metrics")
    assert response_cached.status_code == 200
    assert response_cached.json()["meta"]["cached"] is True

def test_funnel_computations(client):
    response = client.get("/api/v1/stores/S001/funnel")
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "ok"
    funnel = res_data["data"]
    assert funnel["store_id"] == "S001"
    assert len(funnel["stages"]) == 4
    
    # Check funnel stages in chronological order
    stages = [s["stage"] for s in funnel["stages"]]
    assert stages == ["Entry", "Zone Visit", "Billing Queue", "Purchase"]

def test_heatmap_dwell_times(client):
    response = client.get("/api/v1/stores/S001/heatmap")
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "ok"
    assert "zones" in res_data["data"]

def test_realtime_anomalies(client):
    response = client.get("/api/v1/stores/S001/anomalies")
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "ok"
    assert "anomalies" in res_data["data"]
    assert res_data["data"]["has_critical"] is False
