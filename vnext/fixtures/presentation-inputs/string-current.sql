CREATE TABLE device (gid VARCHAR(32) NOT NULL, dev_addr VARCHAR(32) PRIMARY KEY, description TEXT);
INSERT INTO device VALUES ('007','049','文本装置');
CREATE TABLE device_cfg (id BIGINT PRIMARY KEY, gid VARCHAR(32), payload TEXT);
INSERT INTO device_cfg VALUES (1,'007','新');
CREATE TABLE device_st (gid BIGINT PRIMARY KEY, dev_addr VARCHAR(32), name TEXT);
INSERT INTO device_st VALUES (1,'049','新'),(2,'49','不同文本');
