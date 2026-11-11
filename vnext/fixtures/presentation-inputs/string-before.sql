CREATE TABLE device (gid BIGINT NOT NULL, dev_addr BIGINT PRIMARY KEY, description TEXT);
INSERT INTO device VALUES (65532,65532,'复合信号虚装置'),(7,49,'整数装置与文本测点不混等');
CREATE TABLE device_cfg (id BIGINT PRIMARY KEY, gid VARCHAR(32), payload TEXT);
INSERT INTO device_cfg VALUES (1,'007','旧');
CREATE TABLE device_st (gid BIGINT PRIMARY KEY, dev_addr VARCHAR(32), name TEXT);
INSERT INTO device_st VALUES (1,'049','旧'),(2,'49','不同文本');
