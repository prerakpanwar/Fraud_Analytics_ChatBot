import csv
import pandas as pd


def debug_csv_counting():
    print("🔍 Debugging CSV counting issue...")

    # Method 1: Using csv.DictReader (like the producer)
    print("\n📊 Method 1: csv.DictReader (like producer)")
    with open("final_transactions.csv", "r") as file:
        reader = csv.DictReader(file)
        csv_count = sum(1 for row in reader)
        print(f"   Count: {csv_count}")

    # Method 2: Using csv.DictReader with empty line check
    print("\n📊 Method 2: csv.DictReader with empty line check")
    with open("final_transactions.csv", "r") as file:
        reader = csv.DictReader(file)
        csv_count_filtered = sum(1 for row in reader if any(row.values()))
        print(f"   Count (filtered): {csv_count_filtered}")

    # Method 3: Using pandas
    print("\n📊 Method 3: pandas")
    df = pd.read_csv("final_transactions.csv")
    pandas_count = len(df)
    print(f"   Count: {pandas_count}")

    # Method 4: Raw line count
    print("\n📊 Method 4: Raw line count")
    with open("final_transactions.csv", "r") as file:
        lines = file.readlines()
        print(f"   Total lines: {len(lines)}")
        print(f"   Non-empty lines: {len([line for line in lines if line.strip()])}")

    # Method 5: Check for duplicates
    print("\n📊 Method 5: Check for duplicates")
    with open("final_transactions.csv", "r") as file:
        reader = csv.DictReader(file)
        rows = list(reader)
        unique_trans_nums = set(
            row.get("trans_num", "") for row in rows if any(row.values())
        )
        print(f"   Total rows: {len(rows)}")
        print(f"   Unique trans_nums: {len(unique_trans_nums)}")

        # Check for duplicate trans_nums
        trans_nums = [row.get("trans_num", "") for row in rows if any(row.values())]
        from collections import Counter

        duplicates = Counter(trans_nums)
        duplicate_count = sum(1 for count in duplicates.values() if count > 1)
        print(f"   Duplicate trans_nums: {duplicate_count}")


if __name__ == "__main__":
    debug_csv_counting()
