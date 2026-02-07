#!/usr/bin/env python3
"""
Direct database migration script to add virality and caption fields.
Run with: python app/migrations/apply_migration.py
"""
import os
import sys

# Add the parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable not set")
    sys.exit(1)

engine = create_engine(DATABASE_URL)

migration_sql = """
-- Add new columns to clips table if they don't exist
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='clips' AND column_name='virality_score') THEN
        ALTER TABLE clips ADD COLUMN virality_score INTEGER;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='clips' AND column_name='hook_type') THEN
        ALTER TABLE clips ADD COLUMN hook_type VARCHAR;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='clips' AND column_name='transcript_json') THEN
        ALTER TABLE clips ADD COLUMN transcript_json TEXT;
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='clips' AND column_name='layout_type') THEN
        ALTER TABLE clips ADD COLUMN layout_type VARCHAR DEFAULT 'center_crop';
    END IF;
END $$;
"""

print("Applying migration to add virality fields...")

try:
    with engine.connect() as conn:
        conn.execute(text(migration_sql))
        conn.commit()
    print("✅ Migration applied successfully!")
    print("   - Added virality_score column")
    print("   - Added hook_type column")
    print("   - Added transcript_json column")
    print("   - Added layout_type column")
except Exception as e:
    print(f"❌ Migration failed: {e}")
    sys.exit(1)
