-- sql/03_deep_dives.sql
-- Deep-dive merchandising views: stockout opportunity, pack-size pricing, and discount burn

-- 1. High-MRP out-of-stock SKUs with estimated restock value
CREATE OR REPLACE VIEW vw_high_mrp_oos AS
WITH cat_median_stock AS (
    SELECT
        category,
        CAST(MEDIAN(available_qty) AS INTEGER) AS median_in_stock_qty
    FROM clean_inventory
    WHERE NOT is_out_of_stock AND available_qty > 0
    GROUP BY category
)
SELECT
    c.sku_id,
    c.category,
    c.product_name,
    c.weight_gms,
    c.mrp_inr,
    c.selling_price_inr,
    c.actual_discount_pct,
    m.median_in_stock_qty AS est_restock_qty,
    ROUND(c.selling_price_inr * m.median_in_stock_qty, 2) AS est_restock_value_inr,
    DENSE_RANK() OVER (PARTITION BY c.category ORDER BY c.mrp_inr DESC) AS category_mrp_rank
FROM clean_inventory c
JOIN cat_median_stock m ON c.category = m.category
WHERE c.is_out_of_stock = TRUE
ORDER BY est_restock_value_inr DESC;


-- 2. Pack-size unit-price comparison (same product across multiple weights)
CREATE OR REPLACE VIEW vw_pack_size_value_gaps AS
WITH multi_pack AS (
    SELECT
        product_name,
        category,
        COUNT(DISTINCT weight_gms) AS pack_variants,
        MIN(weight_gms) AS smallest_pack_gms,
        MAX(weight_gms) AS largest_pack_gms,
        ROUND(MIN(price_per_100g), 2) AS best_price_per_100g,
        ROUND(MAX(price_per_100g), 2) AS worst_price_per_100g
    FROM clean_inventory
    WHERE weight_gms > 0
    GROUP BY product_name, category
    HAVING COUNT(DISTINCT weight_gms) > 1
)
SELECT
    *,
    ROUND(
        ((worst_price_per_100g - best_price_per_100g) / NULLIF(best_price_per_100g, 0)) * 100.0,
        2
    ) AS unit_price_spread_pct
FROM multi_pack
ORDER BY unit_price_spread_pct DESC;


-- 3. Top in-stock SKUs by total discount burn
CREATE OR REPLACE VIEW vw_top_discount_burn_skus AS
SELECT
    sku_id,
    category,
    product_name,
    weight_gms,
    mrp_inr,
    selling_price_inr,
    actual_discount_pct,
    available_qty,
    est_inventory_value_inr,
    est_discount_burn_inr
FROM clean_inventory
WHERE NOT is_out_of_stock
  AND est_discount_burn_inr > 0
ORDER BY est_discount_burn_inr DESC;