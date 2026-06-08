-- ============================================================
-- WORKSHOP INVENTORY & CLEARANCE SYSTEM
-- Migration for Workshop Technician Role
-- ============================================================

-- ────────────────────────────────────────────────────────────
-- CREATE WORKSHOP_INVENTORY TABLE
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS workshop_inventory (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    department_id UUID NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    created_by UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    
    -- Item details
    item_name TEXT NOT NULL,
    category TEXT CHECK (category IN (
        'Power Tools',
        'Hand Tools',
        'Safety Equipment',
        'Measuring Instruments',
        'Electrical Equipment',
        'Machinery',
        'Computer / ICT Equipment',
        'Furniture / Fixtures',
        'Consumables',
        'Other'
    )),
    quantity INTEGER NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    condition TEXT NOT NULL DEFAULT 'good' CHECK (condition IN ('good', 'fair', 'poor', 'damaged')),
    
    -- Identification & Location
    serial_number TEXT,
    location TEXT,
    
    -- Maintenance
    last_serviced DATE,
    
    -- Additional info
    description TEXT,
    notes TEXT,
    
    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_workshop_inventory_dept ON workshop_inventory(department_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_workshop_inventory_category ON workshop_inventory(category);
CREATE INDEX IF NOT EXISTS idx_workshop_inventory_condition ON workshop_inventory(condition);
CREATE INDEX IF NOT EXISTS idx_workshop_inventory_qty_low ON workshop_inventory(quantity) WHERE quantity < 3;

-- Trigger to keep updated_at current
DROP TRIGGER IF EXISTS trg_workshop_inventory_updated_at ON workshop_inventory;
CREATE TRIGGER trg_workshop_inventory_updated_at
    BEFORE UPDATE ON workshop_inventory
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

COMMENT ON TABLE workshop_inventory IS 'Workshop inventory management - tools, equipment, and assets tracked by department';
COMMENT ON COLUMN workshop_inventory.quantity IS 'Current quantity in stock (items with qty < 3 are flagged as low stock)';
COMMENT ON COLUMN workshop_inventory.condition IS 'Physical condition: good, fair, poor, or damaged';
COMMENT ON COLUMN workshop_inventory.last_serviced IS 'Last maintenance/calibration date for the equipment';

-- ────────────────────────────────────────────────────────────
-- ENSURE WORKSHOP_TECHNICIAN ROLE EXISTS IN USER_PROFILES
-- ────────────────────────────────────────────────────────────

-- Update the role CHECK constraint to include workshop_technician
ALTER TABLE user_profiles DROP CONSTRAINT IF EXISTS user_profiles_role_check;
ALTER TABLE user_profiles ADD CONSTRAINT user_profiles_role_check 
    CHECK (role IN (
        'super_admin',
        'dept_admin',
        'trainer',
        'student',
        'employer',
        'examination_officer',
        'industry_mentor',
        'internal_verifier',
        'sports_hod',
        'environment_hod',
        'dean_students',
        'library_hod',
        'finance_officer',
        'registrar',
        'deputy_principal',
        'quality_assurance_officer',
        'liaison_officer',
        'cdacc_verifier',
        'workshop_technician'
    ));

-- ────────────────────────────────────────────────────────────
-- SAMPLE DATA (OPTIONAL - FOR TESTING)
-- ────────────────────────────────────────────────────────────

-- Uncomment to insert sample workshop inventory items
-- INSERT INTO workshop_inventory (department_id, item_name, category, quantity, condition, serial_number, location, description, created_by)
-- SELECT 
--     d.id,
--     'Angle Grinder 4½ inch',
--     'Power Tools',
--     5,
--     'good',
--     'AG-001',
--     'Shelf A3',
--     'Bosch GWS 750 Professional angle grinder for metal cutting and grinding',
--     (SELECT id FROM user_profiles WHERE role = 'workshop_technician' LIMIT 1)
-- FROM departments d
-- WHERE d.code = 'MECH'
-- LIMIT 1;

-- ────────────────────────────────────────────────────────────
-- VERIFICATION QUERIES
-- ────────────────────────────────────────────────────────────

-- Check if workshop_inventory table was created
SELECT 
    'workshop_inventory table created' AS status,
    COUNT(*) AS record_count 
FROM workshop_inventory;

-- List all workshop technicians
SELECT 
    id,
    full_name,
    email,
    staff_no,
    department_id,
    created_at
FROM user_profiles
WHERE role = 'workshop_technician'
ORDER BY created_at DESC;
