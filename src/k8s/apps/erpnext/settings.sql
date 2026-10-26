-- Manage only this setting. Leave the rest of Website Settings untouched.
START TRANSACTION;

UPDATE `tabSingles`
SET value = '1'
WHERE doctype = 'Website Settings' AND field = 'disable_signup';

INSERT INTO `tabSingles` (doctype, field, value)
SELECT 'Website Settings', 'disable_signup', '1'
WHERE NOT EXISTS (
    SELECT 1 FROM `tabSingles`
    WHERE doctype = 'Website Settings' AND field = 'disable_signup'
);

COMMIT;
