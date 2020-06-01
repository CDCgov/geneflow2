# migration of v1 to v2 20200529-01

from yoyo import step

# workflow table
step("ALTER TABLE workflow CHANGE repo_uri git TEXT NOT NULL")
step("ALTER TABLE workflow DROP documentation_uri")
step("ALTER TABLE workflow ADD COLUMN apps TEXT NOT NULL")
step("UPDATE workflow SET apps = '{}' WHERE apps = ''")

# app table
step("ALTER TABLE app CHANGE repo_uri git TEXT NOT NULL")
step("ALTER TABLE app CHANGE definition implementation TEXT NOT NULL")
step("ALTER TABLE app ADD COLUMN pre_exec TEXT NOT NULL")
step("UPDATE app SET pre_exec = '[]' WHERE pre_exec = ''")
step("ALTER TABLE app ADD COLUMN exec_methods TEXT NOT NULL")
step("UPDATE app SET exec_methods = '[]' WHERE exec_methods = ''")
step("ALTER TABLE app ADD COLUMN post_exec TEXT NOT NULL")
step("UPDATE app SET post_exec = '[]' WHERE post_exec = ''")

# step table
step("ALTER TABLE step ADD COLUMN exec_parameters TEXT NOT NULL")
step("UPDATE step SET exec_parameters = '{}' WHERE exec_parameters = ''")

# job table
step("ALTER TABLE job ADD COLUMN exec_parameters TEXT NOT NULL")
step("UPDATE job SET exec_parameters = '{}' WHERE exec_parameters = ''")


