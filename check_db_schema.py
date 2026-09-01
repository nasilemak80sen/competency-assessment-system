import sqlite3
from pathlib import Path

db_path = Path('re_competency.db')
print(f'Checking database at: {db_path}')
print(f'Database exists: {db_path.exists()}')

if db_path.exists():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    print(f'\nTables found: {len(tables)}')
    for table in tables:
        print(f'  {table[0]}')
    
    cursor.execute("PRAGMA table_info(summary_scores)")
    columns = cursor.fetchall()
    
    print('\nSummary Scores table columns:')
    next_grade_cols = []
    for col in columns:
        col_name = col[1]
        if 'next_grade' in col_name.lower():
            next_grade_cols.append(col_name)
            print(f'  {col_name} (FOUND!)')
        elif 'staff_base' in col_name.lower():
            print(f'  {col_name}')
    
    if not next_grade_cols:
        print('  *** NO NEXT_GRADE COLUMNS FOUND! ***')
        print('\n  The database needs to be recreated with the new schema.')
        print('  You can either:')
        print('  1. Delete re_competency.db and re-run the import')
        print('  2. Use SQLite ALTER TABLE to add the columns')
    
    cursor.execute("SELECT COUNT(*) FROM summary_scores WHERE next_grade_base IS NOT NULL")
    count = cursor.fetchone()[0]
    print(f'\nRecords with next_grade_base data: {count}')
    
    conn.close()
