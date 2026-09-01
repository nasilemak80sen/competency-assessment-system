"""
Update Next Grade data from Excel file into existing database records.
This script ONLY updates the next_grade_* columns without touching other data.
Safe to run multiple times - will skip records not found in Excel.
"""

import pandas as pd
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from config import DATABASE_URL
from models import SummaryScore, Personnel

def _safe(val):
    """Convert NaN and None to None."""
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(val, float):
        return val if val == val else None  # NaN check
    return val

def update_next_grade_from_excel():
    """Read Excel file and update ONLY next_grade columns in database."""
    
    excel_path = Path('RE Fraternity Jul2026_Master.xlsm')
    
    if not excel_path.exists():
        print(f"❌ Excel file not found at {excel_path}")
        return
    
    print(f"📊 Reading Excel file: {excel_path}")
    
    # Read Excel with correct header row
    df = pd.read_excel(excel_path, sheet_name='All', header=2)
    
    # Filter to records with Name
    df = df[df['Name'].notna()].copy()
    print(f"✓ Found {len(df)} records in Excel")
    
    # Create database session
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        updated_count = 0
        skipped_count = 0
        
        for idx, row in df.iterrows():
            name = row.get('Name', '').strip()
            staff_id = row.get('Staff ID', '')
            
            if not name:
                continue
            
            # Try to find personnel by Staff ID first, then by Name
            personnel = None
            
            if staff_id and str(staff_id).strip() not in ('nan', 'None', ''):
                personnel = session.query(Personnel).filter_by(
                    staff_id=str(staff_id).strip()
                ).first()
            
            if not personnel:
                personnel = session.query(Personnel).filter_by(
                    name=name
                ).first()
            
            if not personnel:
                skipped_count += 1
                if idx < 5:  # Only print first few
                    print(f"  ⊗ Skipped: {name} (not found in database)")
                continue
            
            # Find or create summary score for this personnel
            summary = session.query(SummaryScore).filter_by(
                personnel_id=personnel.id
            ).first()
            
            if not summary:
                print(f"  ⊗ No summary scores for {name}, creating...")
                summary = SummaryScore(personnel_id=personnel.id)
                session.add(summary)
            
            # Update ONLY next_grade columns
            summary.next_grade_base = _safe(row.get('Next Grade Base'))
            summary.next_grade_keys = _safe(row.get('Next Grade Keys'))
            summary.next_grade_pacing = _safe(row.get('Next Grade Pacing'))
            summary.next_grade_emerging = _safe(row.get('Next Grade Emerging'))
            summary.next_grade_cti = _safe(row.get('Next Grade CTI'))
            
            updated_count += 1
        
        session.commit()
        
        print(f"\n✅ Update Complete!")
        print(f"   Updated: {updated_count} records")
        print(f"   Skipped: {skipped_count} records (not in database)")
        print(f"\n📌 Next Grade data is now available in the database!")
        
    except Exception as e:
        session.rollback()
        print(f"❌ Error updating database: {e}")
        import traceback
        traceback.print_exc()
    finally:
        session.close()

if __name__ == '__main__':
    update_next_grade_from_excel()
