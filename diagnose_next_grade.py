import sqlite3
import pandas as pd
from pathlib import Path

# Check the database schema
db_path = Path("competency_data.db")
if db_path.exists():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if summary_scores table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='summary_scores'")
    if cursor.fetchone():
        # Get column info
        cursor.execute("PRAGMA table_info(summary_scores)")
        columns = cursor.fetchall()
        
        print("Summary Scores table columns:")
        for col in columns:
            col_name = col[1]
            col_type = col[2]
            print(f"  {col_name}: {col_type}")
        
        # Check for next_grade columns
        next_grade_cols = [c for c in columns if 'next_grade' in c[1].lower()]
        print(f"\nNext Grade columns found: {len(next_grade_cols)}")
        for col in next_grade_cols:
            print(f"  {col[1]}")
        
        # Check if there are any records with next_grade data
        print("\nSample record with next_grade data:")
        cursor.execute("""
            SELECT personnel_id, next_grade_base, next_grade_keys, next_grade_pacing, 
                   next_grade_emerging, next_grade_cti
            FROM summary_scores 
            LIMIT 1
        """)
        result = cursor.fetchone()
        if result:
            print(f"  Personnel ID: {result[0]}")
            print(f"  Next Grade Base: {result[1]}")
            print(f"  Next Grade Keys: {result[2]}")
            print(f"  Next Grade Pacing: {result[3]}")
            print(f"  Next Grade Emerging: {result[4]}")
            print(f"  Next Grade CTI: {result[5]}")
        else:
            print("  No records found")
    else:
        print("summary_scores table not found")
    
    conn.close()
else:
    print(f"Database file not found at {db_path}")

# Also check the Excel file for values
print("\n" + "="*60)
print("Checking Excel file for Next Grade values:")
print("="*60)

excel_path = Path("RE Fraternity Jul2026_Master.xlsm")
if excel_path.exists():
    try:
        df = pd.read_excel(excel_path, sheet_name='All', header=2, nrows=5)
        
        next_grade_cols = [col for col in df.columns if 'Next Grade' in str(col)]
        print(f"\nFound {len(next_grade_cols)} Next Grade columns")
        
        for col in next_grade_cols:
            values = df[col].dropna()
            print(f"\n{col}:")
            print(f"  Non-null values: {len(values)}")
            if len(values) > 0:
                print(f"  Sample values: {values.head(3).tolist()}")
    except Exception as e:
        print(f"Error reading Excel: {e}")
else:
    print(f"Excel file not found at {excel_path}")
