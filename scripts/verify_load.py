from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data_loader import load_master_data
from config import EXCEL_PATH

print('EXCEL_PATH=', EXCEL_PATH)
try:
    df = load_master_data(EXCEL_PATH)
    cols = [c for c in df.columns if 'Custodian' in str(c)]
    print('Custodian columns found:', cols)
    print('Total columns:', len(df.columns))
    print('Sample rows:', df.head(2).to_dict(orient='records'))
except Exception as e:
    print('ERROR', e)
    raise
