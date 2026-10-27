UPDATE `orders` SET `status`=CASE WHEN `board`=0 AND `link_no`=0 THEN 1 ELSE `status` END WHERE (`board`,`link_no`) IN ((0, 0));
