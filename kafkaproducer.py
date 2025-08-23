import csv
import time
from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable
import json
import logging

# Kafka settings
KAFKA_TOPIC = "transaction_data"
KAFKA_BROKER = "kafka:9092"

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_producer():
    retries = 10
    while retries > 0:
        try:
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BROKER,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )
            logger.info("✅ Connected to Kafka broker")
            return producer
        except NoBrokersAvailable:
            logger.warning("⏳ Waiting for Kafka broker to be ready...")
            time.sleep(5)
            retries -= 1
    raise Exception("❌ Failed to connect to Kafka broker after retries")


def stream_csv_data(file_path):
    producer = create_producer()
    total_rows = 0
    start_time = time.time()

    try:
        # First, count total records in CSV (excluding empty lines)
        with open(file_path, "r") as file:
            reader = csv.DictReader(file)
            total_records = sum(
                1 for row in reader if any(row.values())
            )  # Only count non-empty rows

        logger.info(f"📊 Found {total_records} valid records in {file_path}")

        # Debug: Let's also check with pandas for comparison
        try:
            import pandas as pd

            df = pd.read_csv(file_path)
            logger.info(f"🔍 Pandas confirms: {len(df)} records in CSV")
        except Exception as e:
            logger.warning(f"⚠️ Could not verify with pandas: {e}")

        # Now stream all records
        with open(file_path, "r") as file:
            reader = csv.DictReader(file)

            for row in reader:
                # Skip empty rows
                if not any(row.values()):
                    continue

                producer.send(KAFKA_TOPIC, row)
                producer.flush()
                total_rows += 1

                trans_id = row.get("trans_num", "N/A")
                logger.info(
                    f"📤 Streamed transaction #{total_rows}/{total_records} (ID: {trans_id})"
                )

                time.sleep(0.2)  # Simulate real-time delay

        producer.close()
        elapsed = time.time() - start_time
        logger.info("✅ Data streaming complete.")
        logger.info("Total records streamed: %s", total_rows)
        logger.info("⏱️ Time taken: %.2f seconds", elapsed)
        logger.info("Average throughput: %.2f records/second", total_rows / elapsed)

        # Exit gracefully to prevent container restart
        logger.info("🛑 Producer completed successfully. Exiting...")
        exit(0)

    except Exception as e:
        logger.error(f"❌ Error reading CSV or sending data to Kafka: {e}")
        producer.close()
        exit(1)


# Run the function with your CSV - automatically processes all records
stream_csv_data("final_transactions.csv")
