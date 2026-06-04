import os
import json
import urllib.request

EVENTS_PATH = "data/clips/events_real.jsonl"
INGEST_URL = "http://localhost:8000/api/v1/events/ingest"

def main():
    print(f"Reading events from: {EVENTS_PATH}")
    if not os.path.exists(EVENTS_PATH):
        raise FileNotFoundError(f"Events file not found at: {EVENTS_PATH}")
        
    events = []
    with open(EVENTS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                events.append(json.loads(line.strip()))
                
    total_events = len(events)
    print(f"Loaded {total_events} shopper events.")
    
    if total_events == 0:
        print("No events found to ingest.")
        return
        
    # Batch events in chunks of 200 to respect the 500 max limit in schema
    batch_size = 200
    for i in range(0, total_events, batch_size):
        chunk = events[i:i+batch_size]
        payload = {"events": chunk}
        
        # Prepare request
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            INGEST_URL,
            data=data_bytes,
            headers={
                "Content-Type": "application/json",
                "X-Trace-ID": f"INGEST_REAL_{i//batch_size}"
            },
            method="POST"
        )
        
        print(f"Ingesting batch {i//batch_size + 1} ({len(chunk)} events)...")
        try:
            with urllib.request.urlopen(req) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                print(f"Success: Ingested {resp_data['data']['ingested']} events.")
        except Exception as e:
            print(f"Error ingesting batch: {e}")
            if hasattr(e, 'read'):
                print("Error Details:", e.read().decode("utf-8"))
            raise e

    print("All real events successfully ingested!")

if __name__ == "__main__":
    main()
