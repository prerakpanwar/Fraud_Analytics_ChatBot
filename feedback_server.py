from flask import Flask, request, jsonify
import logging
import mysql.connector

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Database config (matches docker-compose)
DB_CONFIG = {
    "host": "mysql",
    "user": "root",
    "password": "password",
    "database": "kafka_data",
}


# ✅ GET request handler for email link
@app.route("/feedback", methods=["GET"])
def feedback_get():
    trans_num = request.args.get("trans_num")
    feedback = request.args.get("correct")

    if not trans_num or feedback not in {"0", "1"}:
        return "❌ Invalid request", 400

    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE fraud_predictions SET feedback = %s WHERE trans_num = %s",
            (int(feedback), trans_num),
        )
        conn.commit()
        cursor.close()
        conn.close()

        logging.info(f"✅ Feedback recorded for transaction {trans_num}: {feedback}")
        return f"✅ Thank you! Feedback recorded for transaction {trans_num}"
    except Exception as e:
        logging.error(f"❌ DB Error: {e}")
        return "❌ Database error", 500


# ✅ Optional: POST request (for future use if needed)
@app.route("/feedback", methods=["POST"])
def handle_feedback():
    data = request.get_json()
    trans_num = data.get("trans_num")
    feedback = data.get("feedback")

    if not trans_num or feedback not in {"0", "1"}:
        return jsonify({"status": "error", "message": "Invalid request"}), 400

    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE fraud_predictions SET feedback = %s WHERE trans_num = %s",
            (int(feedback), trans_num),
        )
        conn.commit()
        cursor.close()
        conn.close()

        logging.info(f"✅ Feedback recorded for transaction {trans_num}: {feedback}")
        return jsonify({"status": "success", "message": "Feedback recorded"})
    except Exception as e:
        logging.error(f"❌ DB Error: {e}")
        return jsonify({"status": "error", "message": "Database error"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
