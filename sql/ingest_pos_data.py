import os
import csv
import json
import asyncio
from datetime import datetime, timezone
import asyncpg

CSV_PATH = "statement/Brigade_Bangalore_10_April_26 (1)bc6219c.csv"
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/retail_db")

async def main():
    print(f"Reading POS CSV from: {CSV_PATH}")
    if not os.path.exists(CSV_PATH):
        raise FileNotFoundError(f"POS CSV file not found at: {CSV_PATH}")
        
    transactions = {}
    
    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            invoice = row["invoice_number"]
            if not invoice:
                continue
                
            # Parse Date and Time
            # CSV has order_date in DD-MM-YYYY format and order_time in HH:MM:SS format
            date_str = row["order_date"]
            time_str = row["order_time"]
            
            # Combine Date and Time
            dt_str = f"{date_str} {time_str}"
            dt = datetime.strptime(dt_str, "%d-%m-%Y %H:%M:%S").replace(tzinfo=timezone.utc)
            
            sku = row["sku"]
            product_name = row["product_name"]
            qty = int(row["qty"] or 1)
            nmv = float(row["NMV"] or 0)
            total_amount = float(row["total_amount"] or 0)
            
            item_data = {
                "sku": sku,
                "product_name": product_name,
                "qty": qty,
                "price": nmv,
                "total_amount": total_amount
            }
            
            if invoice not in transactions:
                transactions[invoice] = {
                    "transaction_id": invoice,
                    "store_id": row["store_id"],
                    "timestamp": dt,
                    "amount": 0.0,
                    "items": [],
                    "payment_method": "CASH" if "CASH" in row.get("coupon_code", "") else "CARD"
                }
                
            transactions[invoice]["items"].append(item_data)
            transactions[invoice]["amount"] += total_amount

    # Convert dictionary to batch tuples
    insert_data = []
    for invoice, tx in transactions.items():
        insert_data.append((
            tx["transaction_id"],
            tx["store_id"],
            tx["timestamp"],
            round(tx["amount"], 2),
            json.dumps(tx["items"]),
            tx["payment_method"]
        ))
        
    print(f"Parsed {len(insert_data)} unique transactions from CSV.")
    
    # Establish connection
    print(f"Connecting to database at {DATABASE_URL}...")
    conn = await asyncpg.connect(DATABASE_URL)
    
    try:
        query = """
            INSERT INTO pos_transactions (transaction_id, store_id, timestamp, amount, items, payment_method)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6)
            ON CONFLICT (transaction_id) DO UPDATE 
            SET amount = EXCLUDED.amount, items = EXCLUDED.items, timestamp = EXCLUDED.timestamp;
        """
        await conn.executemany(query, insert_data)
        print("POS transactions successfully ingested into the database!")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
