CREATE TABLE device (gid BIGINT NOT NULL, dev_addr BIGINT NOT NULL, description TEXT, PRIMARY KEY (dev_addr));
INSERT INTO device VALUES (65532,65532,'复合信号虚装置'),(8,50,'装置五十'),(9,51,'装置五十一');
CREATE TABLE device_cfg (id BIGINT PRIMARY KEY, gid BIGINT, page_no INT, option_name TEXT, payload TEXT);
INSERT INTO device_cfg VALUES (1,7,1,'option1','未改配置'),(2,9,1,'option2','新配置'),(3,8,1,'option3','被抑制新增');
CREATE TABLE device_st (gid BIGINT PRIMARY KEY, dev_addr BIGINT, name TEXT);
INSERT INTO device_st VALUES (1,49,'未改测点'),(3,99,'孤儿'),(4,50,'被抑制新增');
