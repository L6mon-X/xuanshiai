-- =============================================================================
-- 客源线索择偶要求暂存表：后台单选口径列核验（verify）
-- 期望 columns_present = 8，缺列时下方逐一列出。
-- =============================================================================

SET NAMES utf8mb4;

SELECT COUNT(*) AS columns_present
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'customer_lead_preference'
  AND COLUMN_NAME IN (
      'income_range', 'education_requirement', 'marriage_requirement', 'housing_expectation',
      'smoking_expectation', 'drinking_expectation', 'marriage_timeline', 'preferred_occupation'
  );

SELECT COLUMN_NAME, COLUMN_TYPE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'customer_lead_preference'
  AND COLUMN_NAME IN (
      'income_range', 'education_requirement', 'marriage_requirement', 'housing_expectation',
      'smoking_expectation', 'drinking_expectation', 'marriage_timeline', 'preferred_occupation'
  )
ORDER BY COLUMN_NAME;
