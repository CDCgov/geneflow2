# migration of v1 to v2 20200529-01

from yoyo import step

# workflow table
step("ALTER TABLE workflow CHANGE repo_uri git TEXT")
step("ALTER TABLE workflow DROP documentation_uri")
step("ALTER TABLE workflow ADD COLUMN apps TEXT")
step("UPDATE workflow SET apps = '{}' WHERE apps is NULL")

# app table
step("ALTER TABLE app CHANGE repo_uri git TEXT")
step("ALTER TABLE app CHANGE definition implementation TEXT")
step("ALTER TABLE app ADD COLUMN pre_exec TEXT")
step("UPDATE app SET pre_exec = '[]' WHERE pre_exec is NULL")
step("ALTER TABLE app ADD COLUMN exec_methods TEXT")
step("UPDATE app SET exec_methods = '[]' WHERE exec_methods is NULL")
step("ALTER TABLE app ADD COLUMN post_exec TEXT")
step("UPDATE app SET post_exec = '[]' WHERE post_exec is NULL")

# step table
step("ALTER TABLE step ADD COLUMN exec_parameters TEXT")
step("UPDATE step SET exec_parameters = '{}' WHERE exec_parameters is NULL")

# job table
step("ALTER TABLE job ADD COLUMN exec_parameters TEXT")
step("UPDATE job SET exec_parameters = '{}' WHERE exec_parameters is NULL")


