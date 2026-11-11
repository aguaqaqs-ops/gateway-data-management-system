CREATE TABLE device (gid BIGINT NOT NULL, dev_addr BIGINT NOT NULL, description TEXT, PRIMARY KEY (dev_addr));
INSERT INTO device VALUES (65532,65532,'复合信号虚装置'),(7,49,'装置四十九'),(9,51,'装置五十一');
CREATE TABLE device_cfg (id BIGINT PRIMARY KEY, payload TEXT);
INSERT INTO device_cfg VALUES (1,'未改配置'),(2,'旧配置');
CREATE TABLE device_st (gid BIGINT PRIMARY KEY, dev_addr BIGINT, name TEXT);
INSERT INTO device_st VALUES (1,49,'未改测点'),(2,51,'将删除'),(3,99,'孤儿');
