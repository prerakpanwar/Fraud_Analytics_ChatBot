import pandas as pd
import mysql.connector
from datetime import datetime
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ✅ Ensure the file exists before processing
csv_file = "final_transactions.csv"
if not os.path.exists(csv_file):
    print(f"❌ Error: File {csv_file} not found!")
    exit(1)

# ✅ Load the 2019 transaction dataset
df = pd.read_csv(csv_file)

# ✅ Convert date columns to datetime format
df["trans_date_trans_time"] = pd.to_datetime(df["trans_date_trans_time"])

# ✅ Compute aggregated risk metrics per user
user_risk = (
    df.groupby("cc_num")
    .agg(
        total_transactions=("trans_num", "count"),
        total_fraud_transactions=("is_fraud", "sum"),
        avg_amt=("amt", "mean"),
        last_transaction_time=("trans_date_trans_time", "max"),
        last_transaction_location=("lat", "last"),  # Assuming last known location
    )
    .reset_index()
)

# ✅ Compute fraud rate
user_risk["fraud_rate"] = (
    user_risk["total_fraud_transactions"] / user_risk["total_transactions"]
)

# ✅ Compute risk score (Example: Fraud rate * 100)
user_risk["risk_score"] = user_risk["fraud_rate"] * 100

# ✅ MySQL Connection Setup with Error Handling
try:
    connection = mysql.connector.connect(
        host=os.getenv("DB_HOST", "mysql"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", "password"),
        database=os.getenv("DB_NAME", "kafka_data"),
        port=int(os.getenv("DB_PORT", "3306")),
    )
    cursor = connection.cursor()

    # ✅ Ensure `user_risk_profile` table exists
    create_table_query = """
    CREATE TABLE IF NOT EXISTS user_risk_profile (
        cc_num BIGINT PRIMARY KEY,
        total_transactions INT DEFAULT 0,
        total_fraud_transactions INT DEFAULT 0,
        fraud_rate FLOAT DEFAULT 0,
        avg_amt DECIMAL(10,2) DEFAULT 0,
        last_transaction_time DATETIME,
        last_transaction_location VARCHAR(255),
        risk_score FLOAT DEFAULT 0
    );
    """
    cursor.execute(create_table_query)
    connection.commit()
    print("✅ Checked/Created `user_risk_profile` table.")

    # ✅ Prepare Insert Query for Batch Processing
    query = """
        INSERT INTO user_risk_profile (cc_num, total_transactions, total_fraud_transactions, fraud_rate, 
                                       avg_amt, last_transaction_time, last_transaction_location, risk_score)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE 
        total_transactions = VALUES(total_transactions),
        total_fraud_transactions = VALUES(total_fraud_transactions),
        fraud_rate = VALUES(fraud_rate),
        avg_amt = VALUES(avg_amt),
        last_transaction_time = VALUES(last_transaction_time),
        last_transaction_location = VALUES(last_transaction_location),
        risk_score = VALUES(risk_score)
    """

    # ✅ Convert dataframe rows to tuples for batch insertion
    values = [
        (
            row["cc_num"],
            row["total_transactions"],
            row["total_fraud_transactions"],
            row["fraud_rate"],
            row["avg_amt"],
            row["last_transaction_time"],
            row["last_transaction_location"],
            row["risk_score"],
        )
        for _, row in user_risk.iterrows()
    ]

    # ✅ Batch Insert for Better Performance
    cursor.executemany(query, values)
    connection.commit()
    print(f"✅ Successfully stored {len(user_risk)} user risk profiles in MySQL!")

except mysql.connector.Error as err:
    print(f"❌ MySQL Error: {err}")

finally:
    # ✅ Close MySQL connection properly
    if cursor:
        cursor.close()
    if connection:
        connection.close()
    print("✅ MySQL connection closed.")
