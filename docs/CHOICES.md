# ARCHITECTURAL TRADE-OFFS — StoreLens

This document outlines the major compromises, constraints, and engineering decisions made during the development of **StoreLens**.

---

## 1. Speed vs. Bounding Box Accuracy

* **Choices**: YOLOv8n (nano), YOLOv8m (medium), YOLOv8x (extra large).
* **Selection**: **YOLOv8n**
* **Rationale**: StoreLens must run at the edge (often on standard CPU hardware or low-power edge units). YOLOv8n achieves high throughput (above 15 FPS) on standard CPU threads, making the system highly accessible.
* **System Cost**: nano model can experience lower precision in highly crowded stores where shoppers overlap significantly.

---

## 2. Staff Classification: Spatial Heuristic vs. Deep Learning

* **Choices**: 
  1. Train a custom CNN uniform classifier model.
  2. Implement spatial geofencing and appearance heuristics.
* **Selection**: **Hybrid Heuristic + torchvision EfficientNet-B0 fallback**.
* **Rationale**: Custom uniform detectors require massive amounts of annotated company uniform data. StoreLens bypasses this by geofencing the checkout register counter (top 20% of the frame) and tracking stay duration (>10 frames). If a shopper remains behind the desk, they are classified as `is_staff = True`.
* **System Cost**: Potential false positives for tall customers standing near the registers, and false negatives for staff walking through product aisles.

---

## 3. Immediate Deduplication: Redis SET vs. PostgreSQL UNIQUE Constraint

* **Choices**:
  1. Let PostgreSQL handle deduplication via unique index constraints.
  2. Filter incoming events in Redis before hitting the database.
* **Selection**: **Redis SET checking (`SISMEMBER` + `SADD`)** as the primary filter, backed by PostgreSQL indexes.
* **Rationale**: Under heavy load, hitting PostgreSQL with duplicate events forces index scans and triggers transaction aborts. We offload this to Redis, achieving sub-millisecond deduplication checks.
* **System Cost**: Requires keeping a 24-hour event ID cache in Redis memory, but protects PostgreSQL from write bottlenecks.

---

## 4. Session Storage: In-Memory TTL vs. Persistent Tables

* **Choices**:
  1. Compute shopper sessions dynamically on every API request.
  2. Store sessions inside a dedicated PostgreSQL table updated via background tasks.
* **Selection**: **Dynamic PostgreSQL CTE query with Redis Cache-Aside**.
* **Rationale**: Dynamic computing ensures that the data is always mathematically accurate and eliminates complex background state synchronization. Redis caching prevents this from overloading the DB.
* **System Cost**: High database memory consumption during cache misses, but guarantees absolute mathematical consistency.
