-- Fix course_applications.department_id FK to allow department deletion
-- Drops the existing restrictive FK and recreates it with ON DELETE SET NULL

ALTER TABLE course_applications
    DROP CONSTRAINT IF EXISTS course_applications_department_id_fkey;

ALTER TABLE course_applications
    ADD CONSTRAINT course_applications_department_id_fkey
    FOREIGN KEY (department_id)
    REFERENCES departments(id)
    ON DELETE SET NULL;
