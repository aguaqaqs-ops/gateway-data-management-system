CREATE TABLE device (gid BIGINT NOT NULL, dev_addr BIGINT NOT NULL, description TEXT, PRIMARY KEY (dev_addr));
INSERT INTO device VALUES (7,49,'装置四十九');
CREATE TABLE device_st (gid BIGINT PRIMARY KEY, dev_addr BIGINT, name TEXT, detail TEXT, note TEXT);
INSERT INTO device_st VALUES (1,49,'保留点','保留值',NULL),(3,49,'新增点','新增值','备注');
