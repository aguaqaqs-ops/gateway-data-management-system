CREATE TABLE device (gid INT NOT NULL, dev_addr INT NOT NULL PRIMARY KEY, description VARCHAR(64));
INSERT INTO device VALUES (2, 2, '替换后装置'), (65532, 65532, '复合信号虚装置');
CREATE TABLE device_st (gid INT NOT NULL PRIMARY KEY, name VARCHAR(128) NOT NULL, dev_addr INT NOT NULL);
INSERT INTO device_st VALUES (8, 'Device 65532:复合测点', 65532);
CREATE TABLE version_manager (project_id VARCHAR(32) NOT NULL PRIMARY KEY, build VARCHAR(32), no INT);
INSERT INTO version_manager VALUES ('project-b', 'build-b', 1);
