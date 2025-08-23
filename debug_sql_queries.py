#!/usr/bin/env python3
"""
Debug script to test specific SQL queries that are failing
"""

import mysql.connector

def test_failing_queries():
    """Test the specific queries that are failing."""
    
    print("🧪 Testing Failing SQL Queries")
    print("=" * 50)
    
    # Database connection (same as chatbot)
    db_config = {
        "host": "mysql",
        "user": "root",
        "password": "password",
        "database": "kafka_data",
        "port": 3306,
    }
    
    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor()
        
        # Test the failing queries
        test_queries = [
            ("Average fraud probability", "SELECT AVG(probability) FROM fraud_predictions"),
            ("High probability transactions", "SELECT COUNT(*) FROM fraud_predictions WHERE probability > 0.9"),
            ("Top fraud transactions", "SELECT trans_num, probability FROM fraud_predictions WHERE is_fraud = 1 ORDER BY probability DESC LIMIT 10"),
            ("Probability distribution", "SELECT probability, COUNT(*) FROM fraud_predictions GROUP BY probability ORDER BY probability DESC LIMIT 10"),
            ("Fraud probability stats", "SELECT AVG(probability) as avg_prob, MIN(probability) as min_prob, MAX(probability) as max_prob FROM fraud_predictions WHERE is_fraud = 1"),
        ]
        
        for query_name, sql_query in test_queries:
            print(f"\n🔍 Testing: {query_name}")
            print(f"SQL: {sql_query}")
            
            try:
                cursor.execute(sql_query)
                results = cursor.fetchall()
                
                if results:
                    print(f"✅ Success! Found {len(results)} rows")
                    if len(results) <= 3:
                        for i, row in enumerate(results, 1):
                            print(f"  Row {i}: {row}")
                    else:
                        print(f"  First row: {results[0]}")
                        print(f"  Last row: {results[-1]}")
                else:
                    print("✅ Success! No results found")
                    
            except Exception as e:
                print(f"❌ Failed: {e}")
                print(f"  Error type: {type(e).__name__}")
        
        cursor.close()
        connection.close()
        
    except Exception as e:
        print(f"❌ Database connection failed: {e}")

if __name__ == "__main__":
    test_failing_queries()
