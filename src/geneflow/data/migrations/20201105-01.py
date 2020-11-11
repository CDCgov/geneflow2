# migration for adding glob and recursive functionality to map

from yoyo import step

step("ALTER TABLE step ADD COLUMN map_glob VARCHAR(256) NOT NULL DEFAULT '*'")
step("ALTER TABLE step ADD COLUMN map_recursive TINYINT NOT NULL DEFAULT 0")
