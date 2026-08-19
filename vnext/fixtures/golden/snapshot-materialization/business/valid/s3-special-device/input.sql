CREATE TABLE device (
  gid BIGINT NOT NULL PRIMARY KEY,
  dev_addr INT NOT NULL,
  description VARCHAR(64) NOT NULL
);
INSERT INTO device VALUES (1, 65532, '复合信号虚装置'), (2, 10, 'other');
CREATE TABLE device_st (
  gid BIGINT NOT NULL PRIMARY KEY,
  name VARCHAR(64) NOT NULL,
  dev_addr INT NOT NULL
);
INSERT INTO device_st VALUES (10, 'top', 65532), (11, 'plain', 10), (12, 'unbound', 65532);
