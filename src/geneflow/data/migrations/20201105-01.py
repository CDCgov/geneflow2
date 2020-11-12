# migration for adding glob functionality to map

from yoyo import step

step("ALTER TABLE step ADD COLUMN map_glob VARCHAR(256) NOT NULL DEFAULT '*'")
