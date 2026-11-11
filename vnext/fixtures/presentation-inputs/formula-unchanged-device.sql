CREATE TABLE device (
  gid INT NOT NULL,
  dev_addr INT NOT NULL,
  description VARCHAR(128),
  PRIMARY KEY (dev_addr)
);
INSERT INTO device VALUES (1, 1, '线路保护装置 A'), (2, 2, '测控装置（升级）'), (3, 3, '直流屏'), (65532, 65532, '复合信号虚装置');
CREATE TABLE device_st (gid INT NOT NULL PRIMARY KEY, name VARCHAR(128) NOT NULL, dev_addr INT NOT NULL);
INSERT INTO device_st VALUES (8, 'Device 65532:复合测点', 65532);
CREATE TABLE keyless_demo (value VARCHAR(64) NULL);
INSERT INTO keyless_demo VALUES ('保留'), ('删除'), ('新增');
CREATE TABLE retired_table (id INT NOT NULL PRIMARY KEY, label VARCHAR(32));
INSERT INTO retired_table VALUES (1, '旧表');
CREATE TABLE schema_demo (id INT NOT NULL PRIMARY KEY, label VARCHAR(32), enabled TINYINT NULL);
INSERT INTO schema_demo VALUES (1, '初始值', 0);
CREATE TABLE b1_n1_iec104_syx_list (gid INT NULL, no INT NOT NULL, value VARCHAR(32) NULL);
INSERT INTO b1_n1_iec104_syx_list VALUES (2, 1, '遥信 B'), (1, 2, '遥信 A'), (NULL, 3, NULL);
CREATE TABLE b1_n1_iec104_yc_list (no INT NOT NULL, value VARCHAR(32) NULL);
INSERT INTO b1_n1_iec104_yc_list VALUES (1, '无稳定 gid');
CREATE TABLE version_manager (project_id VARCHAR(32) NOT NULL PRIMARY KEY, build VARCHAR(32), no INT);
INSERT INTO version_manager VALUES ('project-a', 'build-1', 1);
