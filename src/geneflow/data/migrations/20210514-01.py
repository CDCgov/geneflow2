# migration for adding inclusive functionality to map

from yoyo import step

step("ALTER TABLE step ADD COLUMN map_inclusive TINYINT NOT NULL DEFAULT 0")
