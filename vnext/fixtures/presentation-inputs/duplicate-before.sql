CREATE TABLE device (id BIGINT PRIMARY KEY, gid BIGINT NOT NULL, dev_addr BIGINT NOT NULL, description TEXT);
INSERT INTO device VALUES (1,7,49,'A'),(2,8,49,'B'),(3,8,50,'C');
CREATE TABLE device_cfg (id BIGINT PRIMARY KEY, gid BIGINT, payload TEXT);
INSERT INTO device_cfg VALUES (1,7,'一'),(2,8,'二'),(3,99,'孤儿');
CREATE TABLE device_st (gid BIGINT PRIMARY KEY, dev_addr BIGINT, name TEXT);
INSERT INTO device_st VALUES (1,49,'点'),(2,99,'孤儿');
