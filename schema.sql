-- 오합지졸.io schema.sql v1.3
-- 생성 기준: app/models (SQLAlchemy) — 실제 반영은 Alembic 마이그레이션 사용
-- 변경: task_comment/comment_like, notice 추가
-- MySQL 8 / utf8mb4

CREATE TABLE user (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	login_id VARCHAR(100) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	name VARCHAR(50) NOT NULL, 
	nickname VARCHAR(100) NOT NULL, 
	email VARCHAR(255) NOT NULL, 
	`role` VARCHAR(20) NOT NULL, 
	plan VARCHAR(10) NOT NULL, 
	plan_expires_at DATETIME, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	deleted_at DATETIME, 
	PRIMARY KEY (id), 
	UNIQUE (login_id), 
	UNIQUE (nickname), 
	UNIQUE (email)
);

CREATE TABLE project (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	name VARCHAR(100) NOT NULL, 
	description TEXT, 
	code VARCHAR(20) NOT NULL, 
	priority VARCHAR(10) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	start_date DATE, 
	end_date DATE, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	deleted_at DATETIME, 
	PRIMARY KEY (id), 
	UNIQUE (code)
);

CREATE TABLE project_member (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	project_id BIGINT NOT NULL, 
	user_id BIGINT NOT NULL, 
	`role` VARCHAR(10) NOT NULL, 
	joined_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_project_member UNIQUE (project_id, user_id), 
	FOREIGN KEY(project_id) REFERENCES project (id), 
	FOREIGN KEY(user_id) REFERENCES user (id)
);

CREATE INDEX ix_project_member_project_user ON project_member (project_id, user_id);

CREATE TABLE task (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	project_id BIGINT NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	content TEXT, 
	status VARCHAR(20) NOT NULL, 
	creator_id BIGINT NOT NULL, 
	start_date DATE NOT NULL, 
	end_date DATE NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	deleted_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(project_id) REFERENCES project (id), 
	FOREIGN KEY(creator_id) REFERENCES user (id)
);

CREATE INDEX ix_task_project_deleted ON task (project_id, deleted_at);

CREATE TABLE todo (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	user_id BIGINT NOT NULL, 
	content VARCHAR(200) NOT NULL, 
	status VARCHAR(10) NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	deleted_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES user (id)
);

CREATE TABLE project_todo (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	project_id BIGINT NOT NULL, 
	user_id BIGINT NOT NULL, 
	content VARCHAR(200) NOT NULL, 
	priority VARCHAR(10) NOT NULL, 
	status VARCHAR(10) NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	deleted_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(project_id) REFERENCES project (id), 
	FOREIGN KEY(user_id) REFERENCES user (id)
);

CREATE INDEX ix_project_todo_project_deleted ON project_todo (project_id, deleted_at);

CREATE TABLE doc (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	project_id BIGINT NOT NULL, 
	user_id BIGINT NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	content TEXT, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	deleted_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(project_id) REFERENCES project (id), 
	FOREIGN KEY(user_id) REFERENCES user (id)
);

CREATE TABLE inquiry (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	user_id BIGINT NOT NULL, 
	project_id BIGINT, 
	title VARCHAR(200) NOT NULL, 
	content TEXT NOT NULL, 
	status VARCHAR(10) NOT NULL, 
	file_name VARCHAR(255), 
	stored_name VARCHAR(255), 
	file_size BIGINT, 
	mime_type VARCHAR(100), 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	deleted_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES user (id), 
	FOREIGN KEY(project_id) REFERENCES project (id)
);

CREATE TABLE notice (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	user_id BIGINT NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	body TEXT NOT NULL, 
	category VARCHAR(20) NOT NULL, 
	pinned BOOL NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	deleted_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES user (id)
);

CREATE TABLE task_assignee (
	task_id BIGINT NOT NULL, 
	user_id BIGINT NOT NULL, 
	PRIMARY KEY (task_id, user_id), 
	FOREIGN KEY(task_id) REFERENCES task (id), 
	FOREIGN KEY(user_id) REFERENCES user (id)
);

CREATE TABLE task_comment (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	task_id BIGINT NOT NULL, 
	user_id BIGINT NOT NULL, 
	content VARCHAR(1000) NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	deleted_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(task_id) REFERENCES task (id), 
	FOREIGN KEY(user_id) REFERENCES user (id)
);

CREATE INDEX ix_task_comment_task_deleted ON task_comment (task_id, deleted_at);

CREATE TABLE doc_version (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	doc_id BIGINT NOT NULL, 
	version_no INTEGER NOT NULL, 
	file_name VARCHAR(255) NOT NULL, 
	stored_name VARCHAR(255) NOT NULL, 
	file_size BIGINT NOT NULL, 
	mime_type VARCHAR(100) NOT NULL, 
	uploaded_by BIGINT NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	deleted_at DATETIME, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_doc_version_no UNIQUE (doc_id, version_no), 
	FOREIGN KEY(doc_id) REFERENCES doc (id), 
	FOREIGN KEY(uploaded_by) REFERENCES user (id)
);

CREATE INDEX ix_doc_version_doc_deleted ON doc_version (doc_id, deleted_at);

CREATE TABLE answer (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	question_id BIGINT NOT NULL, 
	user_id BIGINT NOT NULL, 
	content TEXT NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	deleted_at DATETIME, 
	PRIMARY KEY (id), 
	UNIQUE (question_id), 
	FOREIGN KEY(question_id) REFERENCES inquiry (id), 
	FOREIGN KEY(user_id) REFERENCES user (id)
);

CREATE TABLE comment_like (
	comment_id BIGINT NOT NULL, 
	user_id BIGINT NOT NULL, 
	PRIMARY KEY (comment_id, user_id), 
	FOREIGN KEY(comment_id) REFERENCES task_comment (id), 
	FOREIGN KEY(user_id) REFERENCES user (id)
);

