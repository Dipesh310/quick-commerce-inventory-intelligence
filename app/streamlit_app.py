# app/streamlit_app.py
from pathlib import Path
import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(
    page_title="Quick-Commerce Inventory & Discount Intelligence",
    page_icon=":material/inventory_2:",
    layout="wide",
)

BASE_DIR = Path(__file__).resolve().parent.parent
PARQUET_PATH = BASE_DIR / "data" / "processed" / "cleaned_zepto.parquet"


@st.cache_data
def load_data() -> pd.DataFrame:
    if not PARQUET_PATH.exists():
        st.error(
            f"Processed dataset not found at `{PARQUET_PATH}`. "
            "Run `python src/pipeline.py` first."
        )
        st.stop()
    con = duckdb.connect()
    df = con.execute(f"SELECT * FROM read_parquet('{PARQUET_PATH.as_posix()}')").df()
    con.close()
    return df


df = load_data()

# --- Sidebar Filters ---
st.sidebar.header("Filters")

all_categories = sorted(df["category"].unique().tolist())
selected_categories = st.sidebar.multiselect(
    "Product categories",
    options=all_categories,
    default=all_categories,
)

weight_tiers = ["Low (<250g)", "Medium (250g-1kg)", "Bulk (>1kg)"]
selected_tiers = st.sidebar.multiselect(
    "Weight tiers",
    options=weight_tiers,
    default=weight_tiers,
)

exclude_dup_categories = st.sidebar.toggle(
    "Exclude duplicate-scrape categories",
    value=False,
    help=(
        "In the raw Kaggle dataset, 'Paan Corner' mirrors 'Personal Care' and "
        "'Dairy, Bread & Batter' mirrors 'Beverages'. Toggle to view deduplicated totals."
    ),
)

filtered = df[
    df["category"].isin(selected_categories)
    & df["weight_tier"].isin(selected_tiers)
].copy()

if exclude_dup_categories:
    filtered = filtered[~filtered["category"].isin(["Paan Corner", "Dairy, Bread & Batter"])]

if filtered.empty:
    st.warning("No SKUs match the current filter selection.")
    st.stop()

# Precompute category median in-stock quantity for restock sizing
cat_medians = (
    filtered[(~filtered["is_out_of_stock"]) & (filtered["available_qty"] > 0)]
    .groupby("category")["available_qty"]
    .median()
    .round()
    .to_dict()
)

oos_df = filtered[filtered["is_out_of_stock"]].copy()
oos_df["est_restock_qty"] = oos_df["category"].map(cat_medians).fillna(3).astype(int)
oos_df["est_restock_value_inr"] = (
    oos_df["selling_price_inr"] * oos_df["est_restock_qty"]
).round(2)

# --- Header ---
st.title("Quick-Commerce Inventory & Discount Intelligence")
st.caption(
    "Unit economics, stockout risk, and margin simulation built with DuckDB + Streamlit on Zepto catalog data."
)

# --- Top KPI Row ---
total_skus = len(filtered)
oos_count = int(filtered["is_out_of_stock"].sum())
oos_rate = (oos_count / total_skus) * 100
inv_value = filtered["est_inventory_value_inr"].sum()
discount_burn = filtered["est_discount_burn_inr"].sum()
restock_opp = oos_df["est_restock_value_inr"].sum()

k1, k2, k3, k4 = st.columns(4)
k1.metric("Active inventory value", f"₹{inv_value:,.0f}", f"{total_skus:,} SKUs", border=True)
k2.metric("Out-of-stock rate", f"{oos_rate:.2f}%", f"{oos_count:,} OOS SKUs", delta_color="inverse", border=True)
k3.metric("Est. restock opportunity", f"₹{restock_opp:,.0f}", "At category median qty", border=True)
k4.metric("Active discount burn", f"₹{discount_burn:,.0f}", f"Avg {filtered['actual_discount_pct'].mean():.1f}% off", border=True)

if not exclude_dup_categories:
    st.info(
        "**Data audit note:** Raw catalog inspection flagged identical SKU distributions between "
        "**Personal Care / Paan Corner** and **Beverages / Dairy, Bread & Batter**. "
        "Use the sidebar toggle to inspect deduplicated totals."
    )

# --- Tabs ---
tab1, tab2, tab3 = st.tabs(
    ["Executive overview", "Pricing & unit economics", "What-if simulator"]
)

# === TAB 1: EXECUTIVE OVERVIEW ===
with tab1:
    cat_summary = (
        filtered.groupby("category", as_index=False)
        .agg(
            total_skus=("sku_id", "count"),
            oos_skus=("is_out_of_stock", "sum"),
            avg_discount_pct=("actual_discount_pct", "mean"),
            est_inventory_value_inr=("est_inventory_value_inr", "sum"),
            est_discount_burn_inr=("est_discount_burn_inr", "sum"),
        )
    )
    cat_summary["oos_rate_pct"] = (
        (cat_summary["oos_skus"] / cat_summary["total_skus"]) * 100
    ).round(2)

    col_left, col_right = st.columns(2)

    with col_left:
        fig_val = px.bar(
            cat_summary.sort_values("est_inventory_value_inr", ascending=True),
            x="est_inventory_value_inr",
            y="category",
            orientation="h",
            title="Estimated inventory value by category (₹)",
            labels={"est_inventory_value_inr": "Inventory value (₹)", "category": ""},
            color="avg_discount_pct",
            color_continuous_scale="Teal",
        )
        fig_val.update_layout(height=450, coloraxis_colorbar_title="Avg disc %")
        st.plotly_chart(fig_val, width="stretch")

    with col_right:
        fig_oos = px.bar(
            cat_summary.sort_values("oos_rate_pct", ascending=True),
            x="oos_rate_pct",
            y="category",
            orientation="h",
            title="Out-of-stock rate by category (%)",
            labels={"oos_rate_pct": "Stockout rate (%)", "category": ""},
            color="oos_rate_pct",
            color_continuous_scale="Reds",
        )
        fig_oos.update_layout(height=450, coloraxis_showscale=False)
        st.plotly_chart(fig_oos, width="stretch")

    st.subheader("Discount band distribution")
    bands = pd.cut(
        filtered["actual_discount_pct"],
        bins=[-0.01, 0, 10, 20, 30, 100],
        labels=["0% (No discount)", "1–10%", "11–20%", "21–30%", ">30% (Deep)"],
    )
    band_df = (
        filtered.assign(discount_band=bands)
        .groupby("discount_band", observed=False, as_index=False)
        .agg(
            skus=("sku_id", "count"),
            inventory_value=("est_inventory_value_inr", "sum"),
            discount_burn=("est_discount_burn_inr", "sum"),
        )
    )
    st.dataframe(
        band_df.style.format(
            {"skus": "{:,}", "inventory_value": "₹{:,.2f}", "discount_burn": "₹{:,.2f}"}
        ),
        width="stretch",
        hide_index=True,
    )

# === TAB 2: PRICING & UNIT ECONOMICS ===
with tab2:
    st.subheader("MRP vs. actual discount %")
    scatter_df = filtered.assign(
        stock_status=filtered["is_out_of_stock"].map({True: "Out of stock", False: "In stock"})
    )
    fig_scatter = px.scatter(
        scatter_df,
        x="mrp_inr",
        y="actual_discount_pct",
        color="stock_status",
        size="available_qty",
        hover_data=["product_name", "category", "selling_price_inr", "weight_gms"],
        labels={
            "mrp_inr": "MRP (₹)",
            "actual_discount_pct": "Actual discount (%)",
            "stock_status": "Status",
        },
        color_discrete_map={"In stock": "#1f77b4", "Out of stock": "#d62728"},
        opacity=0.7,
    )
    fig_scatter.update_layout(height=440)
    st.plotly_chart(fig_scatter, width="stretch")

    st.subheader("Pack-size unit price gaps (same product, multiple weights)")
    valid_weight = filtered[filtered["weight_gms"] > 0]
    multi_pack = (
        valid_weight.groupby(["product_name", "category"], as_index=False)
        .agg(
            pack_variants=("weight_gms", "nunique"),
            smallest_gms=("weight_gms", "min"),
            largest_gms=("weight_gms", "max"),
            best_price_100g=("price_per_100g", "min"),
            worst_price_100g=("price_per_100g", "max"),
        )
    )
    multi_pack = multi_pack[multi_pack["pack_variants"] > 1].copy()
    multi_pack["unit_price_spread_pct"] = (
        ((multi_pack["worst_price_100g"] - multi_pack["best_price_100g"]) / multi_pack["best_price_100g"])
        * 100
    ).round(1)
    multi_pack = multi_pack.sort_values("unit_price_spread_pct", ascending=False)

    st.dataframe(
        multi_pack.head(25).style.format(
            {
                "smallest_gms": "{:,.0f} g",
                "largest_gms": "{:,.0f} g",
                "best_price_100g": "₹{:,.2f}",
                "worst_price_100g": "₹{:,.2f}",
                "unit_price_spread_pct": "{:,.1f}%",
            }
        ),
        width="stretch",
        hide_index=True,
    )

# === TAB 3: WHAT-IF SIMULATOR ===
with tab3:
    sim_left, sim_right = st.columns(2)

    with sim_left:
        st.subheader("1. Priority restock simulator")
        max_n = max(1, min(100, len(oos_df)))
        top_n = st.slider("Restock top N highest-value OOS SKUs", 1, max_n, min(20, max_n))
        restock_mult = st.slider(
            "Restock depth (multiplier of category median qty)",
            min_value=0.5,
            max_value=3.0,
            value=1.0,
            step=0.5,
        )

        priority_oos = (
            oos_df.sort_values("est_restock_value_inr", ascending=False)
            .head(top_n)
            .copy()
        )
        priority_oos["sim_qty"] = (priority_oos["est_restock_qty"] * restock_mult).round().astype(int)
        priority_oos["sim_value_inr"] = (
            priority_oos["selling_price_inr"] * priority_oos["sim_qty"]
        ).round(2)

        unlocked_val = priority_oos["sim_value_inr"].sum()
        st.metric("Projected inventory value unlocked", f"₹{unlocked_val:,.2f}", f"Top {top_n} OOS SKUs", border=True)

        display_cols = [
            "category",
            "product_name",
            "mrp_inr",
            "selling_price_inr",
            "sim_qty",
            "sim_value_inr",
        ]
        st.dataframe(
            priority_oos[display_cols].style.format(
                {"mrp_inr": "₹{:,.2f}", "selling_price_inr": "₹{:,.2f}", "sim_value_inr": "₹{:,.2f}"}
            ),
            width="stretch",
            hide_index=True,
        )

        csv_bytes = priority_oos[display_cols].to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download restock plan (CSV)",
            data=csv_bytes,
            file_name="priority_restock_plan.csv",
            mime="text/csv",
            width="stretch",
        )

    with sim_right:
        st.subheader("2. Discount cap margin simulator")
        discount_cap = st.slider(
            "Cap maximum discount on in-stock SKUs at (%)",
            min_value=5,
            max_value=40,
            value=15,
            step=1,
        )

        in_stock = filtered[~filtered["is_out_of_stock"]].copy()
        capped_disc = in_stock["actual_discount_pct"].clip(upper=discount_cap)
        new_selling_price = in_stock["mrp_inr"] * (1 - capped_disc / 100.0)
        new_burn = (in_stock["mrp_inr"] - new_selling_price) * in_stock["available_qty"]

        in_stock["burn_saved_inr"] = (in_stock["est_discount_burn_inr"] - new_burn).clip(lower=0).round(2)
        affected = in_stock[in_stock["burn_saved_inr"] > 0].sort_values(
            "burn_saved_inr", ascending=False
        )

        total_saved = affected["burn_saved_inr"].sum()
        st.metric(
            "Projected discount burn saved",
            f"₹{total_saved:,.2f}",
            f"{len(affected):,} SKUs affected",
            border=True,
        )

        st.dataframe(
            affected[
                ["category", "product_name", "actual_discount_pct", "available_qty", "burn_saved_inr"]
            ]
            .head(20)
            .style.format({"actual_discount_pct": "{:.1f}%", "burn_saved_inr": "₹{:,.2f}"}),
            width="stretch",
            hide_index=True,
        )