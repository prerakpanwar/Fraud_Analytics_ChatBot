import os
import json
import logging
import mysql.connector
import pandas as pd
from typing import List, Dict, Any, Optional
from datetime import datetime
import streamlit as st
from dotenv import load_dotenv

# LangChain imports
from langchain.chat_models import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FraudAnalystChatbot:
    """
    RAG-based chatbot for fraud analysis that converts natural language to SQL
    and provides intelligent explanations of fraud patterns.
    """

    def __init__(self):
        """Initialize the chatbot with database connection and LLM setup."""
        self.db_config = {
            "host": os.getenv("DB_HOST", "mysql"),
            "user": os.getenv("DB_USER", "root"),
            "password": os.getenv("DB_PASSWORD", "password"),
            "database": os.getenv("DB_NAME", "kafka_data"),
            "port": int(
                os.getenv("DB_PORT", "3306")
            ),  # Fixed: Use 3306 for container, 3307 for external
        }

        # Initialize LLM (will be set up when API key is provided)
        self.llm = None
        self.api_key = None

        # Database schema knowledge
        self.schema_info = """
        Database: kafka_data
        Table: fraud_predictions
        Columns:
        - trans_num (VARCHAR(50), PRIMARY KEY) - Transaction number
        - probability (FLOAT) - ML model prediction (0-1)
        - is_fraud (TINYINT(1)) - Fraud classification (0=legitimate, 1=fraud)
        - full_json (JSON) - Complete transaction data including amount, cc_num, etc.
        - feedback (TINYINT(1)) - User feedback on prediction (0=incorrect, 1=correct, NULL=no feedback)
        
        IMPORTANT: Transaction details are stored in the full_json JSON field. You MUST use JSON_EXTRACT() to access them:
        - Amount: JSON_EXTRACT(full_json, '$.amt')
        - Credit Card: JSON_EXTRACT(full_json, '$.cc_num')
        - Merchant: JSON_EXTRACT(full_json, '$.merchant')
        - Category: JSON_EXTRACT(full_json, '$.category')
        - Gender: JSON_EXTRACT(full_json, '$.gender')
        - Age: JSON_EXTRACT(full_json, '$.age')
        
        Examples:
        - SELECT AVG(JSON_EXTRACT(full_json, '$.amt')) FROM fraud_predictions WHERE is_fraud = 1;
        - SELECT COUNT(*) FROM fraud_predictions WHERE is_fraud = 1;
        - SELECT trans_num, probability, JSON_EXTRACT(full_json, '$.amt') as amount FROM fraud_predictions WHERE is_fraud = 1 ORDER BY probability DESC LIMIT 10;
        - SELECT trans_num, JSON_EXTRACT(full_json, '$.amt') as amount, JSON_EXTRACT(full_json, '$.merchant') as merchant FROM fraud_predictions WHERE is_fraud = 1;
        - SELECT COUNT(*) as total_fraud FROM fraud_predictions WHERE is_fraud = 1;
        - SELECT COUNT(*) as total_legitimate FROM fraud_predictions WHERE is_fraud = 0;
        """

    def setup_llm(self, api_key: str):
        """Setup the language model with OpenAI API key."""
        try:
            os.environ["OPENAI_API_KEY"] = api_key
            self.llm = ChatOpenAI(
                model_name="gpt-3.5-turbo", temperature=0.1, max_tokens=1000
            )
            self.api_key = api_key  # Store the API key for re-initialization
            logger.info("✅ LLM setup successful")
            return True
        except Exception as e:
            logger.error(f"❌ LLM setup failed: {e}")
            return False

    def get_database_connection(self):
        """Get MySQL database connection."""
        try:
            connection = mysql.connector.connect(**self.db_config)
            return connection
        except Exception as e:
            logger.error(f"❌ Database connection failed: {e}")
            # Log more details for debugging
            logger.error(f"❌ Connection config: {self.db_config}")
            return None

    def ensure_llm_ready(self):
        """Ensure LLM is ready, reinitialize if needed."""
        if not self.llm and self.api_key:
            logger.info("🔄 Reinitializing LLM...")
            self.setup_llm(self.api_key)

    def natural_language_to_sql(self, query: str) -> str:
        """Convert natural language query to SQL using LLM."""
        self.ensure_llm_ready()
        if not self.llm:
            logger.error("❌ LLM not available for SQL generation")
            return None

        logger.info(f"🔍 Converting query to SQL: {query}")

        prompt_template = PromptTemplate(
            input_variables=["query", "schema"],
            template="""
            You are a SQL expert. Convert the following natural language query to SQL.
            
            Database Schema:
            {schema}
            
            Natural Language Query: {query}
            
            MANDATORY RULES - VIOLATION WILL CAUSE ERRORS:
            - For ANY amount-related query: use JSON_EXTRACT(full_json, '$.amt') NEVER 'amount'
            - For ANY credit card query: use JSON_EXTRACT(full_json, '$.cc_num') NEVER 'cc_num'
            - For ANY merchant query: use JSON_EXTRACT(full_json, '$.merchant') NEVER 'merchant'
            - For ANY category query: use JSON_EXTRACT(full_json, '$.category') NEVER 'category'
            - For fraud: use is_fraud = 1 (integer, not TRUE)
            - For legitimate: use is_fraud = 0 (integer, not FALSE)
            - Transaction ID: use 'trans_num' (not transaction_id, not id)
            - For probability queries: use 'probability' column directly (it exists as a column)
            - For average probability: use AVG(probability) FROM fraud_predictions
            - For amount comparisons: use JSON_EXTRACT(full_json, '$.amt') > value
            
            VALID COLUMNS ONLY: trans_num, probability, is_fraud, full_json, feedback
            
            EXAMPLES:
            - "What's the average fraud probability?" → SELECT AVG(probability) FROM fraud_predictions
            - "Show me fraudulent transactions with amounts above $100" → SELECT * FROM fraud_predictions WHERE is_fraud = 1 AND JSON_EXTRACT(full_json, '$.amt') > 100
            - "Count all transactions" → SELECT COUNT(*) FROM fraud_predictions
            - "Show me high-value transactions" → SELECT * FROM fraud_predictions WHERE JSON_EXTRACT(full_json, '$.amt') > 100
            
            Generate ONLY the SQL query. No explanations, no comments.
            """,
        )

        try:
            logger.info("🔄 Calling LLM for SQL generation...")
            chain = LLMChain(llm=self.llm, prompt=prompt_template)
            sql_query = chain.run(query=query, schema=self.schema_info)
            sql_query = sql_query.strip()

            logger.info(f"🔍 Raw SQL from LLM: {sql_query}")

            # Post-process to fix common errors
            sql_query = self._fix_common_sql_errors(sql_query)

            logger.info(f"✅ Final SQL: {sql_query}")
            return sql_query
        except Exception as e:
            logger.error(f"❌ SQL conversion failed: {e}")
            logger.error(f"❌ Error type: {type(e).__name__}")

            # Try fallback
            logger.info("🔄 Trying fallback SQL generation...")
            fallback_sql = self._simple_sql_fallback(query)
            if fallback_sql:
                logger.info(f"✅ Fallback SQL: {fallback_sql}")
                return fallback_sql
            else:
                logger.error("❌ No fallback available")
                return None

    def _simple_sql_fallback(self, query: str) -> str:
        """Simple fallback SQL generation for common queries."""
        query_lower = query.lower()

        # Simple pattern matching for common queries
        if "average" in query_lower and "probability" in query_lower:
            return "SELECT AVG(probability) FROM fraud_predictions"
        elif (
            "average" in query_lower
            and "fraud" in query_lower
            and "probability" in query_lower
        ):
            return "SELECT AVG(probability) FROM fraud_predictions WHERE is_fraud = 1"
        elif "probability" in query_lower and "above" in query_lower:
            # Extract number from query
            import re

            numbers = re.findall(r"\d+\.?\d*", query)
            if numbers:
                threshold = float(numbers[0])
                return f"SELECT COUNT(*) FROM fraud_predictions WHERE probability > {threshold}"
            else:
                return "SELECT COUNT(*) FROM fraud_predictions WHERE probability > 0.8"
        elif "top" in query_lower and "fraud" in query_lower:
            return "SELECT trans_num, probability FROM fraud_predictions WHERE is_fraud = 1 ORDER BY probability DESC LIMIT 10"
        elif "count" in query_lower and "fraud" in query_lower:
            return "SELECT COUNT(*) FROM fraud_predictions WHERE is_fraud = 1"
        elif "total" in query_lower and "transaction" in query_lower:
            return "SELECT COUNT(*) FROM fraud_predictions"
        elif "amount" in query_lower and "fraud" in query_lower:
            return "SELECT AVG(JSON_EXTRACT(full_json, '$.amt')) FROM fraud_predictions WHERE is_fraud = 1"
        elif "amount" in query_lower and "average" in query_lower:
            return "SELECT AVG(JSON_EXTRACT(full_json, '$.amt')) FROM fraud_predictions"
        # New patterns for failing queries
        elif (
            "amount" in query_lower
            and "above" in query_lower
            and ("$" in query or "100" in query)
        ):
            return "SELECT * FROM fraud_predictions WHERE JSON_EXTRACT(full_json, '$.amt') > 100"
        elif (
            "fraudulent" in query_lower
            and "amount" in query_lower
            and "above" in query_lower
        ):
            return "SELECT * FROM fraud_predictions WHERE is_fraud = 1 AND JSON_EXTRACT(full_json, '$.amt') > 100"
        elif "high-value" in query_lower or "expensive" in query_lower:
            return "SELECT * FROM fraud_predictions WHERE JSON_EXTRACT(full_json, '$.amt') > 100 ORDER BY JSON_EXTRACT(full_json, '$.amt') DESC"
        elif "probability" in query_lower and "distribution" in query_lower:
            return "SELECT probability, COUNT(*) FROM fraud_predictions GROUP BY probability ORDER BY probability DESC"

        return None

    def _fix_common_sql_errors(self, sql_query: str) -> str:
        """Fix common SQL errors that the AI might generate."""
        import re

        # Only replace standalone words, not those already in JSON_EXTRACT
        if "JSON_EXTRACT" not in sql_query:
            # Replace amount only if not already in JSON_EXTRACT
            sql_query = re.sub(
                r"\bamount\b", "JSON_EXTRACT(full_json, '$.amt')", sql_query
            )
            sql_query = re.sub(
                r"\bcc_num\b", "JSON_EXTRACT(full_json, '$.cc_num')", sql_query
            )
            sql_query = re.sub(
                r"\bmerchant\b", "JSON_EXTRACT(full_json, '$.merchant')", sql_query
            )
            sql_query = re.sub(
                r"\bcategory\b", "JSON_EXTRACT(full_json, '$.category')", sql_query
            )

        # These are always safe to replace
        sql_query = sql_query.replace("transaction_id", "trans_num")
        sql_query = sql_query.replace("is_fraud = TRUE", "is_fraud = 1")
        sql_query = sql_query.replace("is_fraud = FALSE", "is_fraud = 0")
        sql_query = sql_query.replace("is_fraud = true", "is_fraud = 1")
        sql_query = sql_query.replace("is_fraud = false", "is_fraud = 0")

        return sql_query

    def test_simple_query(self) -> bool:
        """Test a simple query to verify database connectivity."""
        try:
            connection = self.get_database_connection()
            if not connection:
                return False

            cursor = connection.cursor()
            cursor.execute("SELECT COUNT(*) FROM fraud_predictions")
            result = cursor.fetchone()
            cursor.close()
            connection.close()

            logger.info(f"✅ Simple query test passed: {result[0]} records")
            return True
        except Exception as e:
            logger.error(f"❌ Simple query test failed: {e}")
            return False

    def execute_sql_query(self, sql_query: str) -> pd.DataFrame:
        """Execute SQL query and return results as DataFrame."""
        connection = self.get_database_connection()
        if not connection:
            logger.error("❌ Cannot establish database connection")
            return None

        try:
            logger.info(f"🔍 Executing SQL: {sql_query}")

            # Test the connection first
            cursor = connection.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            logger.info("✅ Database connection test passed")

            # Execute the actual query
            df = pd.read_sql(sql_query, connection)
            connection.close()
            logger.info(f"✅ SQL executed successfully, returned {len(df)} rows")
            return df

        except Exception as e:
            logger.error(f"❌ SQL execution failed: {e}")
            logger.error(f"❌ SQL query was: {sql_query}")
            logger.error(f"❌ Error type: {type(e).__name__}")

            # Try to get more specific error information
            try:
                cursor = connection.cursor()
                cursor.execute("SHOW TABLES")
                tables = cursor.fetchall()
                logger.info(f"✅ Available tables: {tables}")
                cursor.close()
            except Exception as table_error:
                logger.error(f"❌ Cannot check tables: {table_error}")

            connection.close()
            return None

    def generate_fraud_explanation(self, query: str, results: pd.DataFrame) -> str:
        """Generate intelligent explanation of fraud analysis results."""
        if not self.llm or results is None or results.empty:
            return "No data found for analysis."

        # Convert results to readable format
        results_summary = results.head(10).to_string()

        # Extract key statistics from results to prevent hallucination
        key_stats = self._extract_key_statistics(results, query)

        prompt_template = PromptTemplate(
            input_variables=["query", "results", "schema", "key_stats"],
            template="""
            You are a fraud analyst expert. Analyze the following fraud detection results and provide insights.
            
            User Query: {query}
            Database Schema: {schema}
            Query Results:
            {results}
            
            IMPORTANT: Use ONLY these verified statistics in your response:
            {key_stats}
            
            CRITICAL RULES:
            1. NEVER invent or estimate percentages - use ONLY the actual numbers from the results
            2. If the results show a fraud rate, use that exact percentage
            3. If calculating percentages, use: (fraud_count / total_count) * 100
            4. For fraud rate queries, the correct rate is typically 0.5-1.0%, NOT 50%+
            5. If you see a percentage > 10%, it's likely wrong - double-check the calculation
            
            Provide a clear, professional explanation of the fraud analysis results. Include:
            1. Key findings and patterns (using actual numbers)
            2. Risk factors identified
            3. Recommendations for fraud prevention
            4. Any unusual patterns or anomalies
            
            Keep the response concise but informative.
            """,
        )

        try:
            chain = LLMChain(llm=self.llm, prompt=prompt_template)
            explanation = chain.run(
                query=query,
                results=results_summary,
                schema=self.schema_info,
                key_stats=key_stats,
            )
            return explanation
        except Exception as e:
            logger.error(f"❌ Explanation generation failed: {e}")
            return f"Analysis completed. Found {len(results)} records."

    def _extract_key_statistics(self, results: pd.DataFrame, query: str) -> str:
        """Extract key statistics from results to prevent LLM hallucination."""
        stats = []

        try:
            # Check if this is a fraud rate query
            if any(
                word in query.lower()
                for word in ["fraud rate", "percentage", "percent"]
            ):
                if len(results) == 1 and len(results.columns) == 1:
                    value = results.iloc[0, 0]
                    if isinstance(value, (int, float)):
                        if value < 1.0:
                            stats.append(
                                f"Fraud rate: {value:.2f}% (this is the correct percentage)"
                            )
                        else:
                            stats.append(
                                f"Calculated value: {value} (verify this is reasonable)"
                            )

            # Check if this is a count query
            elif any(word in query.lower() for word in ["count", "how many", "number"]):
                if len(results) == 1 and len(results.columns) == 1:
                    value = results.iloc[0, 0]
                    stats.append(f"Count: {value:,} records")

            # Check if this is a probability query
            elif any(word in query.lower() for word in ["probability", "prob", "avg"]):
                if len(results) == 1 and len(results.columns) == 1:
                    value = results.iloc[0, 0]
                    if isinstance(value, (int, float)):
                        stats.append(f"Average probability: {value:.3f}")

            # For complex results, provide summary
            else:
                stats.append(f"Total records: {len(results)}")
                if not results.empty:
                    stats.append(f"Columns: {list(results.columns)}")
                    if len(results) <= 5:
                        stats.append(f"Sample data: {results.to_string()}")

        except Exception as e:
            stats.append(f"Error extracting stats: {e}")

        return "\n".join(stats) if stats else "No specific statistics extracted"

    def process_query(self, query: str) -> Dict[str, Any]:
        """Process a natural language query and return comprehensive results."""
        try:
            # Step 1: Convert to SQL
            sql_query = self.natural_language_to_sql(query)
            if not sql_query:
                return {
                    "success": False,
                    "error": "Failed to generate SQL query",
                    "sql_query": None,
                }

            # Step 2: Execute SQL
            results = self.execute_sql_query(sql_query)
            if results is None:
                return {
                    "success": False,
                    "error": "Failed to execute SQL query",
                    "sql_query": sql_query,
                }

            # Step 3: Generate explanation
            explanation = self.generate_fraud_explanation(query, results)

            return {
                "success": True,
                "sql_query": sql_query,
                "results": results,
                "explanation": explanation,
                "record_count": len(results),
            }

        except Exception as e:
            logger.error(f"❌ Query processing failed: {e}")
            return {"success": False, "error": str(e), "sql_query": None}

    def get_sample_queries(self) -> List[str]:
        """Get sample queries for demonstration."""
        return [
            "How many fraudulent transactions are in the database?",
            "What's the total number of transactions?",
            "How many legitimate transactions are there?",
            "Count all transactions",
            "Display the first 10 transactions",
            "Show me all transactions",
            "List all fraudulent transaction",
            "Display the transactions where user has given feedback",
        ]


# Streamlit Interface
def main():
    st.set_page_config(
        page_title="🕵️ Fraud Analyst Chatbot", page_icon="🕵️", layout="wide"
    )

    st.title("🕵️ Fraud Analyst Chatbot")
    st.markdown("**AI-Powered Fraud Analysis with Natural Language Queries**")

    # Initialize session state variables - this is the key fix
    if "chatbot" not in st.session_state:
        st.session_state.chatbot = FraudAnalystChatbot()
    if "ai_setup" not in st.session_state:
        st.session_state.ai_setup = False
    if "api_key" not in st.session_state:
        st.session_state.api_key = ""
    if "ai_setup_time" not in st.session_state:
        st.session_state.ai_setup_time = ""
    if "last_query" not in st.session_state:
        st.session_state.last_query = ""
    if "last_result" not in st.session_state:
        st.session_state.last_result = None
    if "setup_clicked" not in st.session_state:
        st.session_state.setup_clicked = False

    chatbot = st.session_state.chatbot

    # Sidebar for configuration
    with st.sidebar:
        st.header("🔧 Configuration")

        # API Key input
        api_key = st.text_input(
            "OpenAI API Key",
            type="password",
            value=st.session_state.api_key,
            help="Enter your OpenAI API key to enable AI features",
        )

        # Setup AI button
        if api_key and st.button("Setup AI"):
            st.session_state.setup_clicked = True
            st.session_state.api_key = api_key

            with st.spinner("Setting up AI..."):
                if chatbot.setup_llm(api_key):
                    st.session_state.ai_setup = True
                    st.session_state.ai_setup_time = datetime.now().strftime("%H:%M:%S")
                    st.success("✅ AI setup successful!")
                else:
                    st.session_state.ai_setup = False
                    st.error("❌ AI setup failed")

        # Show AI status - this should persist
        if st.session_state.ai_setup:
            st.success("✅ AI is ready to use!")

            if st.session_state.ai_setup_time:
                st.caption(f"Setup at: {st.session_state.ai_setup_time}")

            # Auto-recover if LLM is lost
            if not chatbot.llm and st.session_state.api_key:
                st.info("🔄 Reconnecting to AI...")
                if chatbot.setup_llm(st.session_state.api_key):
                    st.success("✅ AI reconnected!")
                else:
                    st.error("❌ AI reconnection failed")

            if chatbot.llm:
                st.info("🤖 LLM: Connected")
            else:
                st.warning("🤖 LLM: Not connected")

        # Test database connection
        if st.button("🔍 Test Database Connection"):
            with st.spinner("Testing database..."):
                connection = chatbot.get_database_connection()
                if connection:
                    try:
                        cursor = connection.cursor()
                        cursor.execute("SELECT COUNT(*) FROM fraud_predictions")
                        count = cursor.fetchone()[0]
                        cursor.close()
                        connection.close()
                        st.success(f"✅ Database connected! {count:,} records found")
                    except Exception as e:
                        st.error(f"❌ Database test failed: {e}")
                else:
                    st.error("❌ Cannot connect to database")

        # Sample queries
        st.header("💡 Sample Queries")
        sample_queries = chatbot.get_sample_queries()
        for query in sample_queries:
            if st.button(query, key=f"sample_{hash(query)}"):
                st.session_state.last_query = query

    # Main chat interface
    col1, col2 = st.columns([1, 1])

    with col1:
        st.header("💬 Ask Questions")

        # Query input
        user_query = st.text_input(
            "Enter your fraud analysis question:",
            value=st.session_state.last_query,
            placeholder="e.g., Show me the top 10 fraudulent transactions",
        )

        # Analyze button
        if st.button("🔍 Analyze", type="primary"):
            if not user_query:
                st.warning("Please enter a question")
            elif not st.session_state.ai_setup:
                st.warning("Please setup OpenAI API key in the sidebar")
            else:
                # Ensure AI is still connected
                if not chatbot.llm and st.session_state.api_key:
                    st.info("🔄 Reconnecting to AI...")
                    if not chatbot.setup_llm(st.session_state.api_key):
                        st.error(
                            "❌ AI reconnection failed. Please try setting up AI again."
                        )
                        return

                with st.spinner("Analyzing fraud data..."):
                    result = chatbot.process_query(user_query)

                    if result["success"]:
                        st.session_state.last_result = result
                        st.session_state.last_query = user_query
                        st.success("✅ Analysis complete!")
                    else:
                        st.error(f"❌ Analysis failed: {result['error']}")
                        if "Failed to generate SQL query" in result["error"]:
                            st.info(
                                "💡 Try testing the database connection in the sidebar"
                            )
                        elif "Failed to execute SQL query" in result["error"]:
                            st.info(
                                "💡 The generated SQL query failed to execute. "
                                "Please check the SQL query in the results and try again."
                            )

    with col2:
        st.header("📊 Results")

        # Show last query if available
        if st.session_state.last_query:
            st.caption(f"Last query: {st.session_state.last_query}")

        if st.session_state.last_result:
            result = st.session_state.last_result

            # Show SQL query only if it exists
            if result.get("sql_query"):
                with st.expander("🔍 Generated SQL Query"):
                    st.code(result["sql_query"], language="sql")
            else:
                st.warning("⚠️ No SQL query was generated for this request")

            # Show explanation only for successful results
            if result["success"]:
                st.subheader("📈 Analysis")
                st.write(result["explanation"])

                # Show results table
                if not result["results"].empty:
                    st.subheader(f"📋 Data ({result['record_count']} records)")
                    st.dataframe(result["results"], use_container_width=True)

                    # Download option
                    csv = result["results"].to_csv(index=False)
                    st.download_button(
                        label="📥 Download Results",
                        data=csv,
                        file_name=f"fraud_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                    )
            else:
                # Show error details
                st.error(f"❌ {result['error']}")

                # Show different help messages based on error type
                if "Failed to generate SQL query" in result["error"]:
                    st.info(
                        "💡 The AI couldn't understand your query. Try rephrasing or use one of the sample queries."
                    )
                elif "Failed to execute SQL query" in result["error"]:
                    st.info(
                        "💡 The generated SQL query failed to execute. Check the SQL query above and try again."
                    )

    # Footer
    st.markdown("---")
    st.markdown(
        "**🕵️ Fraud Analyst Chatbot** | "
        "Powered by LangChain + OpenAI | "
        "Real-time fraud analysis with natural language queries"
    )


if __name__ == "__main__":
    main()
