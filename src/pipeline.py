# src/pipeline.py
from pathlib import Path
import duckdb
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_CSV = BASE_DIR / "data" / "raw" / "zepto_v2.csv"
PROCESSED_PARQUET = BASE_DIR / "data" / "processed" / "cleaned_zepto.parquet"
DB_PATH = BASE_DIR / "data" / "processed" / "zepto.duckdb"

SQL_FILES = [
    BASE_DIR / "sql" / "01_data_cleaning.sql",
    BASE_DIR / "sql" / "02_kpi_views.sql",
    BASE_DIR / "sql" / "03_deep_dives.sql",
]


def load_raw_csv(path: Path) -> pd.DataFrame:
    """Load CSV handling Zepto's common windows-1252 encoding quirk."""
    try:
        return pd.read_csv(path, encoding="utf-8")
    except UnicodeDecodeError:
        return pd.read_csv(path, encoding="windows-1252")


def run_pipeline() -> None:
    if not RAW_CSV.exists():
        raise FileNotFoundError(f"Missing dataset at: {RAW_CSV}")

    raw_df = load_raw_csv(RAW_CSV)
    con = duckdb.connect(str(DB_PATH))
    con.register("raw_zepto", raw_df)

    for sql_file in SQL_FILES:
        con.execute(sql_file.read_text(encoding="utf-8"))
        print(f"Executed -> {sql_file.name}")

    con.execute(
        f"COPY clean_inventory TO '{PROCESSED_PARQUET.as_posix()}' (FORMAT PARQUET);"
    )

    print("\n=== Top 5 Categories by Inventory Value ===")
    top_cats = con.execute("""
        SELECT category, total_skus, oos_rate_pct, avg_discount_pct, est_inventory_value_inr
        FROM vw_category_kpis
        LIMIT 5
    """).df()
    print(top_cats.to_string(index=False))

    print("\n=== Top 5 Categories by Stockout Rate ===")
    oos_cats = con.execute("""
        SELECT category, oos_skus, total_skus, oos_rate_pct
        FROM vw_category_kpis
        ORDER BY oos_rate_pct DESC
        LIMIT 5
    """).df()
    print(oos_cats.to_string(index=False))

    restock_opp = con.execute("""
        SELECT COUNT(*) AS oos_skus, ROUND(SUM(est_restock_value_inr), 2) AS total_restock_opp
        FROM vw_high_mrp_oos
    """).fetchone()

    con.close()

    print(
        f"\nEst. Restock Opportunity ({restock_opp[0]} OOS SKUs at category median qty): "
        f"INR {restock_opp[1]:,.2f}\n"
    )


if __name__ == "__main__":
    run_pipeline()