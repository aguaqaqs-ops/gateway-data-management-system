CREATE TABLE device (gid BIGINT NOT NULL, dev_addr BIGINT PRIMARY KEY, description TEXT);
INSERT INTO device VALUES (65532,65532,'复合信号虚装置'),(7,49,'装置');
CREATE TABLE device_st (gid BIGINT PRIMARY KEY, dev_addr BIGINT, name VARCHAR(32));
CREATE TABLE b1_n1_sg_cfg (id BIGINT PRIMARY KEY, value VARCHAR(32));
CREATE TABLE keyless_demo (value TEXT);
INSERT INTO keyless_demo VALUES ('重复'),('重复'),('重复');
