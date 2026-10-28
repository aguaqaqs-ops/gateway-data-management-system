CREATE TABLE semantics (
  `id` INT NOT NULL PRIMARY KEY,
  `decimal_bit` BIT(8) NOT NULL,
  `binary_bit` BIT(8) NOT NULL,
  `string_bytes` BLOB NOT NULL,
  `hex_bytes` BLOB NOT NULL,
  `escaped` VARCHAR(64) NOT NULL,
  `doc` JSON NOT NULL,
  `commented` INT /* ignored type comment */ NULL
);
INSERT INTO semantics VALUES (1, 10, b'1010', _binary 'bytes', _binary x'0001ff', 'keep\% and \_', '{"depth":[1,{"ok":true}]}', 7);
