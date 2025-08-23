from flask import Flask, request, jsonify
import logging
from rag_chatbot import FraudAnalystChatbot
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Initialize the chatbot
chatbot = FraudAnalystChatbot()


@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint."""
    return jsonify({"status": "healthy", "service": "fraud-analyst-chatbot"})


@app.route("/query", methods=["POST"])
def process_query():
    """Process a natural language query and return fraud analysis results."""
    try:
        data = request.get_json()

        if not data or "query" not in data:
            return jsonify({"error": "Missing 'query' field"}), 400

        query = data["query"]

        # Check if API key is provided
        api_key = data.get("api_key") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            return jsonify({"error": "OpenAI API key required"}), 400

        # Setup LLM if not already done
        if not chatbot.llm:
            if not chatbot.setup_llm(api_key):
                return jsonify({"error": "Failed to setup AI model"}), 500

        # Process the query
        result = chatbot.process_query(query)

        if result["success"]:
            # Convert DataFrame to JSON for API response
            results_json = (
                result["results"].to_dict("records")
                if not result["results"].empty
                else []
            )

            return jsonify(
                {
                    "success": True,
                    "query": query,
                    "sql_query": result["sql_query"],
                    "explanation": result["explanation"],
                    "results": results_json,
                    "record_count": result["record_count"],
                }
            )
        else:
            return jsonify({"success": False, "error": result["error"]}), 500

    except Exception as e:
        logging.error(f"Error processing query: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/sample-queries", methods=["GET"])
def get_sample_queries():
    """Get sample queries for demonstration."""
    return jsonify({"queries": chatbot.get_sample_queries()})


@app.route("/setup", methods=["POST"])
def setup_ai():
    """Setup the AI model with API key."""
    try:
        data = request.get_json()
        api_key = data.get("api_key") or os.getenv("OPENAI_API_KEY")

        if not api_key:
            return jsonify({"error": "OpenAI API key required"}), 400

        if chatbot.setup_llm(api_key):
            return jsonify({"success": True, "message": "AI setup successful"})
        else:
            return jsonify({"error": "Failed to setup AI model"}), 500

    except Exception as e:
        logging.error(f"Error setting up AI: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
