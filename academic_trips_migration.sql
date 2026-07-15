-- ====================================================================
-- ACADEMIC TRIPS SYSTEM
-- Database Schema for Trip Reports Management
-- ====================================================================

-- Create academic_trips table
CREATE TABLE IF NOT EXISTS academic_trips (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Trip Information (in CAPITAL LETTERS)
    trip_title TEXT NOT NULL,
    destination TEXT NOT NULL,
    trip_date DATE NOT NULL,
    
    -- Academic Details
    class_id UUID NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    department_id UUID NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    term INTEGER NOT NULL CHECK (term IN (1, 2, 3)),
    year INTEGER NOT NULL,
    
    -- Participants
    number_of_trainees INTEGER NOT NULL CHECK (number_of_trainees > 0),
    number_of_trainers INTEGER NOT NULL CHECK (number_of_trainers > 0),
    accompanying_trainers TEXT, -- Comma-separated list of trainer names
    
    -- Report Details
    report_description TEXT,
    objectives TEXT,
    outcomes TEXT,
    
    -- Uploaded By
    uploaded_by UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
    uploader_role TEXT NOT NULL CHECK (uploader_role IN ('trainer', 'trip_coordinator')),
    
    -- Status
    status TEXT NOT NULL DEFAULT 'submitted' 
        CHECK (status IN ('submitted', 'reviewed', 'archived')),
    reviewed_by UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    reviewed_at TIMESTAMPTZ,
    review_notes TEXT,
    
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Create academic_trip_media table for photos/videos
CREATE TABLE IF NOT EXISTS academic_trip_media (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    trip_id UUID NOT NULL REFERENCES academic_trips(id) ON DELETE CASCADE,
    
    -- Media Details
    file_path TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_size BIGINT,
    file_type TEXT NOT NULL CHECK (file_type IN ('photo', 'video')),
    
    -- Optional Metadata
    caption TEXT,
    sequence_order INTEGER DEFAULT 0,
    
    -- Timestamps
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Triggers for updated_at
DROP TRIGGER IF EXISTS trg_academic_trips_updated_at ON academic_trips;
CREATE TRIGGER trg_academic_trips_updated_at
    BEFORE UPDATE ON academic_trips
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_academic_trips_date ON academic_trips(trip_date DESC);
CREATE INDEX IF NOT EXISTS idx_academic_trips_class ON academic_trips(class_id);
CREATE INDEX IF NOT EXISTS idx_academic_trips_dept ON academic_trips(department_id);
CREATE INDEX IF NOT EXISTS idx_academic_trips_year_term ON academic_trips(year DESC, term);
CREATE INDEX IF NOT EXISTS idx_academic_trips_uploader ON academic_trips(uploaded_by);
CREATE INDEX IF NOT EXISTS idx_academic_trip_media_trip ON academic_trip_media(trip_id);

-- Row Level Security (Optional)
ALTER TABLE academic_trips ENABLE ROW LEVEL SECURITY;
ALTER TABLE academic_trip_media ENABLE ROW LEVEL SECURITY;

-- Policy: Trainers and trip coordinators can insert
CREATE POLICY "Trainers can insert trips" ON academic_trips
    FOR INSERT
    WITH CHECK (
        auth.uid() = uploaded_by AND 
        uploader_role IN ('trainer', 'trip_coordinator')
    );

-- Policy: Users can view trips from their department
CREATE POLICY "Users can view department trips" ON academic_trips
    FOR SELECT
    USING (true); -- Will be filtered by application logic

-- Policy: Super admin can view all
-- (Handled by application logic)

-- Policy: Media follows trip permissions
CREATE POLICY "Media follows trip permissions" ON academic_trip_media
    FOR ALL
    USING (
        EXISTS (
            SELECT 1 FROM academic_trips 
            WHERE id = academic_trip_media.trip_id
        )
    );

-- Comments for documentation
COMMENT ON TABLE academic_trips IS 'Stores academic trip reports uploaded by trainers and trip coordinators';
COMMENT ON TABLE academic_trip_media IS 'Stores photos and videos for academic trips';
COMMENT ON COLUMN academic_trips.trip_title IS 'Trip title in CAPITAL LETTERS';
COMMENT ON COLUMN academic_trips.destination IS 'Trip destination/location in CAPITAL LETTERS';
COMMENT ON COLUMN academic_trips.number_of_trainees IS 'Number of students/trainees who attended';
COMMENT ON COLUMN academic_trips.number_of_trainers IS 'Number of trainers who accompanied';
COMMENT ON COLUMN academic_trips.accompanying_trainers IS 'Names of trainers who accompanied the trip';
