from alembic import op

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None

DDL = ['\n'
 'CREATE TABLE IF NOT EXISTS candidates (\n'
 '\tid INTEGER NOT NULL, \n'
 '\tname VARCHAR(200) NOT NULL, \n'
 '\tphone VARCHAR NOT NULL, \n'
 '\temail VARCHAR NOT NULL, \n'
 '\teducation VARCHAR NOT NULL, \n'
 '\tmajor VARCHAR NOT NULL, \n'
 '\tcreated_at VARCHAR NOT NULL, \n'
 '\tPRIMARY KEY (id)\n'
 ')\n'
 '\n',
 '\n'
 'CREATE TABLE IF NOT EXISTS jobs (\n'
 '\tid INTEGER NOT NULL, \n'
 '\tname VARCHAR(200) NOT NULL, \n'
 '\tjd TEXT NOT NULL, \n'
 '\tdescription TEXT NOT NULL, \n'
 '\tstatus VARCHAR NOT NULL, \n'
 '\tcriteria JSON NOT NULL, \n'
 '\tversion INTEGER NOT NULL, \n'
 '\tcreated_at VARCHAR NOT NULL, \n'
 '\tupdated_at VARCHAR NOT NULL, \n'
 '\tPRIMARY KEY (id)\n'
 ')\n'
 '\n',
 '\n'
 'CREATE TABLE IF NOT EXISTS settings (\n'
 '\t"key" VARCHAR NOT NULL, \n'
 '\tvalue TEXT NOT NULL, \n'
 '\tPRIMARY KEY ("key")\n'
 ')\n'
 '\n',
 '\n'
 'CREATE TABLE IF NOT EXISTS tasks (\n'
 '\tid INTEGER NOT NULL, \n'
 '\tkind VARCHAR NOT NULL, \n'
 '\ttarget_id INTEGER NOT NULL, \n'
 '\tstatus VARCHAR NOT NULL, \n'
 '\tpayload JSON NOT NULL, \n'
 '\tresult JSON NOT NULL, \n'
 '\terror TEXT NOT NULL, \n'
 '\tcreated_at VARCHAR NOT NULL, \n'
 '\tupdated_at VARCHAR NOT NULL, \n'
 '\tPRIMARY KEY (id)\n'
 ')\n'
 '\n',
 '\n'
 'CREATE TABLE IF NOT EXISTS users (\n'
 '\tid INTEGER NOT NULL, \n'
 '\tusername VARCHAR(100) NOT NULL, \n'
 '\tpassword_hash TEXT NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tUNIQUE (username)\n'
 ')\n'
 '\n',
 '\n'
 'CREATE TABLE IF NOT EXISTS resumes (\n'
 '\tid INTEGER NOT NULL, \n'
 '\tcandidate_id INTEGER, \n'
 '\tpurpose VARCHAR NOT NULL, \n'
 '\tfilename TEXT NOT NULL, \n'
 '\tpath TEXT NOT NULL, \n'
 '\tsha256 VARCHAR NOT NULL, \n'
 '\tstatus VARCHAR NOT NULL, \n'
 '\tmarkdown TEXT NOT NULL, \n'
 '\trevision INTEGER NOT NULL, \n'
 '\textracted JSON NOT NULL, \n'
 '\terror TEXT NOT NULL, \n'
 '\tcreated_at VARCHAR NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(candidate_id) REFERENCES candidates (id)\n'
 ')\n'
 '\n',
 '\n'
 'CREATE TABLE IF NOT EXISTS task_events (\n'
 '\tid INTEGER NOT NULL, \n'
 '\ttask_id INTEGER NOT NULL, \n'
 '\ttype VARCHAR NOT NULL, \n'
 '\tpayload JSON NOT NULL, \n'
 '\tcreated_at VARCHAR NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(task_id) REFERENCES tasks (id)\n'
 ')\n'
 '\n',
 '\n'
 'CREATE TABLE IF NOT EXISTS evaluations (\n'
 '\tid INTEGER NOT NULL, \n'
 '\tcandidate_id INTEGER NOT NULL, \n'
 '\tresume_id INTEGER NOT NULL, \n'
 '\tjob_id INTEGER NOT NULL, \n'
 '\tstatus VARCHAR NOT NULL, \n'
 '\tsnapshot JSON NOT NULL, \n'
 '\treport JSON NOT NULL, \n'
 '\ttotal_score INTEGER, \n'
 '\tdecision VARCHAR NOT NULL, \n'
 '\tnote TEXT NOT NULL, \n'
 '\terror TEXT NOT NULL, \n'
 '\tmodel VARCHAR NOT NULL, \n'
 '\tresponse_id VARCHAR NOT NULL, \n'
 '\tusage JSON NOT NULL, \n'
 '\tprompt_version VARCHAR NOT NULL, \n'
 '\tschema_version VARCHAR NOT NULL, \n'
 '\tretry_of INTEGER, \n'
 '\tbatch_key VARCHAR NOT NULL, \n'
 '\tcreated_at VARCHAR NOT NULL, \n'
 '\tcompleted_at VARCHAR, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(candidate_id) REFERENCES candidates (id), \n'
 '\tFOREIGN KEY(resume_id) REFERENCES resumes (id), \n'
 '\tFOREIGN KEY(job_id) REFERENCES jobs (id), \n'
 '\tFOREIGN KEY(retry_of) REFERENCES evaluations (id)\n'
 ')\n'
 '\n',
 '\n'
 'CREATE TABLE IF NOT EXISTS recruitments (\n'
 '\tid INTEGER NOT NULL, \n'
 '\tcandidate_id INTEGER NOT NULL, \n'
 '\tjob_id INTEGER NOT NULL, \n'
 '\tbasis_evaluation_id INTEGER NOT NULL, \n'
 '\tstage VARCHAR NOT NULL, \n'
 '\tactive BOOLEAN NOT NULL, \n'
 '\tversion INTEGER NOT NULL, \n'
 '\tpromoted_at VARCHAR NOT NULL, \n'
 '\tupdated_at VARCHAR NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tUNIQUE (candidate_id, job_id), \n'
 '\tFOREIGN KEY(candidate_id) REFERENCES candidates (id), \n'
 '\tFOREIGN KEY(job_id) REFERENCES jobs (id), \n'
 '\tFOREIGN KEY(basis_evaluation_id) REFERENCES evaluations (id)\n'
 ')\n'
 '\n',
 '\n'
 'CREATE TABLE IF NOT EXISTS stage_events (\n'
 '\tid INTEGER NOT NULL, \n'
 '\trecruitment_id INTEGER NOT NULL, \n'
 '\tfrom_stage VARCHAR NOT NULL, \n'
 '\tto_stage VARCHAR NOT NULL, \n'
 '\tvalid BOOLEAN NOT NULL, \n'
 '\tkind VARCHAR NOT NULL, \n'
 '\tnote TEXT NOT NULL, \n'
 '\tcreated_at VARCHAR NOT NULL, \n'
 '\tPRIMARY KEY (id), \n'
 '\tFOREIGN KEY(recruitment_id) REFERENCES recruitments (id)\n'
 ')\n'
 '\n',
 'CREATE INDEX IF NOT EXISTS ix_candidates_email ON candidates (email)',
 'CREATE INDEX IF NOT EXISTS ix_candidates_phone ON candidates (phone)',
 'CREATE INDEX IF NOT EXISTS ix_tasks_status ON tasks (status)',
 'CREATE INDEX IF NOT EXISTS ix_resumes_sha256 ON resumes (sha256)',
 'CREATE INDEX IF NOT EXISTS ix_task_events_task_id ON task_events (task_id)',
 'CREATE INDEX IF NOT EXISTS ix_eval_pair ON evaluations (candidate_id, job_id, status, '
 'completed_at)',
 'CREATE INDEX IF NOT EXISTS ix_evaluations_batch_key ON evaluations (batch_key)',
 'CREATE INDEX IF NOT EXISTS ix_recruitments_stage ON recruitments (stage)',
 'CREATE INDEX IF NOT EXISTS ix_stage_events_recruitment_id ON stage_events (recruitment_id)']

def upgrade():
    for statement in DDL:
        op.execute(statement)

def downgrade():
    op.drop_table('stage_events')
    op.drop_table('recruitments')
    op.drop_table('evaluations')
    op.drop_table('task_events')
    op.drop_table('resumes')
    op.drop_table('users')
    op.drop_table('tasks')
    op.drop_table('settings')
    op.drop_table('jobs')
    op.drop_table('candidates')
