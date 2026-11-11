CREATE TABLE device (gid BIGINT NOT NULL, dev_addr BIGINT PRIMARY KEY, description TEXT);
INSERT INTO device VALUES (7,49,'装置');
CREATE TABLE device_st (gid BIGINT PRIMARY KEY, dev_addr BIGINT, name TEXT, before_only TEXT COMMENT '改前列');
CREATE TABLE b1_n1_sg_cfg (id BIGINT PRIMARY KEY, value TEXT);
CREATE TABLE keyless_demo (value TEXT);
INSERT INTO keyless_demo VALUES ('重复');
