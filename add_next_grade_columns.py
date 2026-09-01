import sqlite3
from pathlib import Path

db_path = Path('re_competency.db')

if db_path.exists():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("Adding next_grade columns to summary_scores table...")
    
    columns_to_add = [
        ('next_grade_base', 'REAL'),
        ('next_grade_keys', 'REAL'),
        ('next_grade_pacing', 'REAL'),
        ('next_grade_emerging', 'REAL'),
        ('next_grade_cti', 'REAL'),
    ]
    
    for col_name, col_type in columns_to_add:
        try:
            cursor.execute(f"ALTER TABLE summary_scores ADD COLUMN {col_name} {col_type}")
            print(f"  ✓ Added {col_name}")
        except sqlite3.OperationalError as e:
            if 'duplicate column' in str(e):
                print(f"  ✓ {col_name} already exists")
            else:
                print(f"  ✗ Error adding {col_name}: {e}")
    
    conn.commit()
    conn.close()
    
    print("\nDatabase schema updated successfully!")
    print("\nNow you need to re-import the Excel data to populate these columns.")
    print("In the Streamlit app, use the Admin panel to re-import the master data.")
else:
    print(f"Database not found at {db_path}")
