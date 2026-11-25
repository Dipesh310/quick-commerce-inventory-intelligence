-- sql/01_data_cleaning.sql
-- Standardizes raw Zepto inventory data, filters anomalies, and adds unit-economic metrics

CREATE OR REPLACE TABLE clean_inventory AS
WITH base AS (
    SELECT
        ROW_NUMBER() OVER () AS sku_id,
        TRIM(CAST(Category AS VARCHAR)) AS category,
        TRIM(CAST(name AS VARCHAR)) AS product_name,
        ROUND(CAST(mrp AS DOUBLE) / 100.0, 2) AS mrp_inr,
        ROUND(CAST(discountedSellingPrice AS DOUBLE) / 100.0, 2) AS selling_price_inr,
        CAST(discountPercent AS DOUBLE) AS reported_discount_pct,
        CAST(availableQuantity AS INTEGER) AS available_qty,
        CAST(weightInGms AS DOUBLE) AS weight_gms,
        CAST(outOfStock AS BOOLEAN) AS is_out_of_stock,
        CAST(quantity AS INTEGER) AS pack_quantity
    FROM raw_zepto
    WHERE CAST(mrp AS DOUBLE) > 0
      AND CAST(discountedSellingPrice AS DOUBLE) > 0
)
SELECT
    sku_id,
    category,
    product_name,
    mrp_inr,
    selling_price_inr,
    reported_discount_pct,
    ROUND(((mrp_inr - selling_price_inr) / NULLIF(mrp_inr, 0)) * 100.0, 2) AS actual_discount_pct,
    CASE
        WHEN ABS(
            reported_discount_pct - ROUND(((mrp_inr - selling_price_inr) / NULLIF(mrp_inr, 0)) * 100.0, 2)
        ) > 1.0 THEN TRUE
        ELSE FALSE
    END AS has_discount_mismatch,
    available_qty,
    weight_gms,
    is_out_of_stock,
    pack_quantity,
    -- Unit economics & inventory valuation
    ROUND((selling_price_inr / NULLIF(weight_gms, 0)) * 100.0, 2) AS price_per_100g,
    ROUND(selling_price_inr * available_qty, 2) AS est_inventory_value_inr,
    ROUND((mrp_inr - selling_price_inr) * available_qty, 2) AS est_discount_burn_inr,
    CASE
        WHEN weight_gms < 250 THEN 'Low (<250g)'
        WHEN weight_gms <= 1000 THEN 'Medium (250g-1kg)'
        ELSE 'Bulk (>1kg)'
    END AS weight_tier
FROM base;