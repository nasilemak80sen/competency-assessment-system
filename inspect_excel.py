import pandas as pd
import openpyxl

path = r'RE Fraternity Jul2026_Master.xlsm'

# Read with pandas to see the columns
try:
    df = pd.read_excel(path, sheet_name='All', header=2, nrows=1)
    print("All column names:")
    for i, col in enumerate(df.columns):
        print(f"  {i}: {col}")
    
    print("\n\nLooking for Next Grade:")
    for i, col in enumerate(df.columns):
        if 'Next' in str(col) or 'Grade' in str(col):
            print(f"  Col {i}: {col}")
except Exception as e:
    print(f"Error with pandas: {e}")
    import traceback
    traceback.print_exc()
