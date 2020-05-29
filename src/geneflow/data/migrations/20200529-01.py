# migration of v1 to v2 20200529-01

from yoyo import step

# workflow table
step("ALTER TABLE workflow CHANGE repo_uri git TEXT NOT NULL DEFAULT ''")
step("ALTER TABLE workflow DROP documentation_uri")
step("ALTER TABLE workflow ADD COLUMN apps TEXT NOT NULL DEFAULT ''")

# app table
step("ALTER TABLE app CHANGE repo_uri git TEXT NOT NULL DEFAULT ''")
step("ALTER TABLE app CHANGE definition implementation TEXT NOT NULL DEFAULT ''")
step("ALTER TABLE app ADD COLUMN pre_exec TEXT NOT NULL DEFAULT ''")
step("ALTER TABLE app ADD COLUMN exec_methods TEXT NOT NULL DEFAULT ''")
step("ALTER TABLE app ADD COLUMN post_exec TEXT NOT NULL DEFAULT ''")

# step table
step("ALTER TABLE step ADD COLUMN exec_parameters TEXT NOT NULL DEFAULT ''")

# job table
step("ALTER TABLE job ADD COLUMN exec_parameters TEXT NOT NULL DEFAULT ''")


