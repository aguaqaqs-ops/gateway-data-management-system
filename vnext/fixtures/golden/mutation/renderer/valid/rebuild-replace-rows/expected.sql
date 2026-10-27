DELETE FROM `orders` WHERE (`board`,`link_no`) IN ((0, 0),(1, 0));
INSERT INTO `orders` (`board`, `link_no`, `status`) VALUES (0, 0, 9);
