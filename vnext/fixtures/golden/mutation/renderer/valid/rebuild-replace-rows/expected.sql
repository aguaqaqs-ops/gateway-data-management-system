DELETE FROM `orders` WHERE `board`=0 AND `link_no`=0;
DELETE FROM `orders` WHERE `board`=1 AND `link_no`=0;
INSERT INTO `orders` (`board`, `link_no`, `status`) VALUES (0, 0, 9);
