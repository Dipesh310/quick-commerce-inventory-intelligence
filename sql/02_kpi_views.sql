-- sql/02_kpi_views.sql
-- Executive KPI views for category performance, weight tiers, and discount bands

-- 1. Category-level KPI scorecard
CREATE OR REPLACE VIEW vw_category_kpis AS
WITH cat_agg AS (
    SELECT
        category,
        COUNT(*) AS total_skus,
        SUM(CASE WHEN NOT is_out_of_stock THEN 1 ELSE 0 END) AS in_stock_skus,
        SUM(CASE WHEN is_out_of_stock THEN 1 ELSE 0 END) AS oos_skus,
        ROUND(AVG(CASE WHEN is_out_of_stock THEN 100.0 ELSE 0.0 END), 2) AS oos_rate_pct,
        ROUND(AVG(mrp_inr), 2) AS avg_mrp_inr,
        ROUND(AVG(selling_price_inr), 2) AS avg_selling_price_inr,
        ROUND(AVG(actual_discount_pct), 2) AS avg_discount_pct,
        ROUND(SUM(est_inventory_value_inr), 2) AS est_inventory_value_inr,
        ROUND(SUM(est_discount_burn_inr), 2) AS est_discount_burn_inr
    FROM clean_inventory
    GROUP BY category
)
SELECT
    *,
    ROUND(
        est_inventory_value_inr * 100.0 / NULLIF(SUM(est_inventory_value_inr) OVER (), 0),
        2
    ) AS inventory_value_share_pct
FROM cat_agg
ORDER BY est_inventory_value_inr DESC;


-- 2. Weight-tier unit economics
CREATE OR REPLACE VIEW vw_weight_tier_summary AS
SELECT
    weight_tier,
    COUNT(*) AS total_skus,
    ROUND(AVG(CASE WHEN is_out_of_stock THEN 100.0 ELSE 0.0 END), 2) AS oos_rate_pct,
    ROUND(AVG(actual_discount_pct), 2) AS avg_discount_pct,
    ROUND(MEDIAN(price_per_100g), 2) AS median_price_per_100g,
    ROUND(SUM(est_inventory_value_inr), 2) AS est_inventory_value_inr
FROM clean_inventory
WHERE weight_gms > 0
GROUP BY weight_tier
ORDER BY est_inventory_value_inr DESC;


-- 3. Discount-band distribution & margin burn
CREATE OR REPLACE VIEW vw_discount_bands AS
SELECT
    CASE
        WHEN actual_discount_pct = 0 THEN '0% (No Discount)'
        WHEN actual_discount_pct <= 10 THEN '1-10%'
        WHEN actual_discount_pct <= 20 THEN '11-20%'
        WHEN actual_discount_pct <= 30 THEN '21-30%'
        ELSE '>30% (Deep Discount)'
    END AS discount_band,
    COUNT(*) AS total_skus,
    ROUND(AVG(CASE WHEN is_out_of_stock THEN 100.0 ELSE 0.0 END), 2) AS oos_rate_pct,
    ROUND(SUM(est_inventory_value_inr), 2) AS est_inventory_value_inr,
    ROUND(SUM(est_discount_burn_inr), 2) AS est_discount_burn_inr
FROM clean_inventory
GROUP BY 1
ORDER BY MIN(actual_discount_pct);