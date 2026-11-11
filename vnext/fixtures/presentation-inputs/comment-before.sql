CREATE TABLE comment_demo (id BIGINT PRIMARY KEY COMMENT '旧列', value TEXT) COMMENT='旧表';
INSERT INTO comment_demo VALUES (1,'相同业务');
