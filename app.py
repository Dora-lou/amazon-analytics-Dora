from __future__ import annotations

import io
import os
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode, GridUpdateMode, DataReturnMode
import json


APP_TITLE = "店铺数据分析-Dora"
DATA_DIR = Path("data")
HISTORY_FILE = DATA_DIR / "history.csv"
RULES_FILE = DATA_DIR / "rule_templates.json"
BUDGET_FILE = DATA_DIR / "budget_targets.json"
PARENT_BUDGET_FILE = DATA_DIR / "budget_targets_parent_asin.json"
CHILD_BUDGET_FILE = DATA_DIR / "budget_targets_child_asin.json"
REQUIRED_FIELDS = [
    "date",
    "product_line",
    "parent_asin",
    "child_asin",
    "brand",
    "spend",
    "sales",
    "ad_sales",
    "orders",
    "sessions",
    "impressions",
    "clicks",
]
MAPPING_FIELDS = REQUIRED_FIELDS + ["ad_type", "rating", "reviews", "inventory"]
AD_TYPES = ["SP", "SB", "SBV", "SD", "ST"]
DEFAULT_METRIC_COLUMNS = [
    "impressions",
    "clicks",
    "sales",
    "spend",
    "orders",
    "sessions",
    "ctr",
    "cvr",
    "cpc",
    "acos",
    "acoas",
]


def is_streamlit_cloud() -> bool:
    """
    Streamlit Community Cloud / Cloud Run 环境检测。
    云端文件系统通常是“可写但不持久”，且重启后可能丢失写入文件。
    因此在云端默认用 session_state 存储历史/模板，避免因权限或持久化差异导致崩溃。
    """

    if os.getenv("DORA_FORCE_CLOUD", "").strip().lower() in {"1", "true", "yes"}:
        return True
    return bool(
        os.getenv("STREAMLIT_CLOUD")
        or os.getenv("STREAMLIT_SHARING")
        or os.getenv("STREAMLIT_RUNTIME_ENV", "").strip().lower() == "cloud"
    )


def rerun_app() -> None:
    """兼容不同 Streamlit 版本的 rerun API。"""
    try:
        rerun = getattr(st, "rerun", None)
        if callable(rerun):
            rerun()
            return
        exp = getattr(st, "experimental_rerun", None)
        if callable(exp):
            exp()
            return
    except Exception:
        return


def _budget_record(value: Any) -> dict[str, Any]:
    """
    兼容旧格式：
    - 旧：{"某产品线": 123.0}
    - 新：{"某产品线": {"target": 123.0, "checked": true}}
    """

    if isinstance(value, dict):
        target = float(value.get("target", 0.0) or 0.0)
        checked = bool(value.get("checked", False))
        return {"target": target, "checked": checked}
    try:
        return {"target": float(value or 0.0), "checked": False}
    except Exception:
        return {"target": 0.0, "checked": False}


def load_budget_targets() -> dict[str, dict[str, Any]]:
    if is_streamlit_cloud():
        data = st.session_state.get("_budget_targets", {})
        raw = data if isinstance(data, dict) else {}
        return {str(k): _budget_record(v) for k, v in raw.items()}
    if not BUDGET_FILE.exists():
        return {}
    try:
        with open(BUDGET_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            return {str(k): _budget_record(v) for k, v in raw.items()}
        return {}
    except Exception:
        return {}


def save_budget_targets(targets: dict[str, dict[str, Any]]) -> None:
    if is_streamlit_cloud():
        st.session_state["_budget_targets"] = targets
        return
    DATA_DIR.mkdir(exist_ok=True)
    with open(BUDGET_FILE, "w", encoding="utf-8") as f:
        json.dump(targets, f, ensure_ascii=False, indent=2)


def load_budget_store(file_path: Path, session_key: str) -> dict[str, dict[str, Any]]:
    if is_streamlit_cloud():
        data = st.session_state.get(session_key, {})
        raw = data if isinstance(data, dict) else {}
        return {str(k): _budget_record(v) for k, v in raw.items()}
    if not file_path.exists():
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            return {str(k): _budget_record(v) for k, v in raw.items()}
        return {}
    except Exception:
        return {}


def save_budget_store(file_path: Path, session_key: str, targets: dict[str, dict[str, Any]]) -> None:
    if is_streamlit_cloud():
        st.session_state[session_key] = targets
        return
    DATA_DIR.mkdir(exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(targets, f, ensure_ascii=False, indent=2)


FIELD_CANDIDATES: dict[str, list[str]] = {
    "date": [
        "日期",
        "时间",
        "报告日期",
        "statistic date",
        "date",
        "day",
    ],
    "product_line": [
        "产品线",
        "二级分类",
        "二级类目",
        "分类",
        "品类",
        "category",
        "subcategory",
        "product line",
    ],
    "parent_asin": [
        "父asin",
        "父 asin",
        "parent asin",
        "parentasin",
        "父商品",
    ],
    "child_asin": [
        "子asin",
        "子 asin",
        "asin",
        "child asin",
        "sku",
        "msku",
    ],
    "brand": ["品牌", "brand"],
    "ad_type": [
        "广告类型",
        "广告渠道",
        "广告活动类型",
        "campaign type",
        "ad type",
        "type",
    ],
    "spend": [
        "花费",
        "广告花费",
        "支出",
        "cost",
        "spend",
        "advertising cost",
    ],
    "sales": [
        "销售额",
        "总销售额",
        "销售金额",
        "total sales",
        "sales",
        "ordered product sales",
        "7 day total sales",
        "14 day total sales",
    ],
    "ad_sales": [
        "广告销售额",
        "广告销售",
        "attributed sales",
        "attributed sales 14 day",
        "7 day total sales",
        "14 day total sales",
    ],
    "orders": [
        "订单量",
        "订单数",
        "销量",
        "销售量",
        "units ordered",
        "orders",
        "conversions",
        "purchases",
        "7 day total orders",
        "14 day total orders",
    ],
    "sessions": [
        "session",
        "sessions",
        "session-total",
        "session total",
        "sessions-total",
        "sessions total",
        "session总计",
        "session-total",
        "访问次数",
        "会话",
        "会话数",
        "买家访问次数",
        "total sessions",
    ],
    "impressions": ["曝光", "曝光量", "展示量", "impressions"],
    "clicks": ["点击", "点击量", "clicks"],
    "acos": ["acos", "广告销售成本"],
    "acoas": ["acoas", "tacos", "tacoas", "总acos", "总广告销售成本", "整体广告占比"],
    "ctr": ["ctr", "点击率"],
    "cvr": ["cvr", "转化率", "conversion rate"],
    "rating": ["评分", "星级", "rating", "star rating", "customer reviews"],
    "reviews": ["评论数", "评价数", "review count", "reviews", "ratings count"],
    "inventory": [
        "库存",
        "可售库存",
        "fba库存",
        "available inventory",
        "inventory",
        "afn fulfillable quantity",
    ],
}

DISPLAY_NAMES = {
    "spend": "花费",
    "sales": "销售额",
    "ad_sales": "广告销售额",
    "orders": "订单数",
    "sessions": "Session",
    "impressions": "曝光",
    "clicks": "点击",
    "acos": "ACOS",
    "acoas": "TACoAS",
    "cpc": "CPC",
    "growth_rate": "环比",
    "spend_share": "花费占比",
    "ctr": "CTR",
    "cvr": "CVR",
    "rating": "评分",
    "reviews": "评论数",
    "inventory": "库存",
}


def normalize_text(value: Any) -> str:
    text = str(value).strip().lower()
    text = re.sub(r"[\s_\-()/（）%]+", "", text)
    return text


def candidate_score(column_name: str, candidates: list[str]) -> int:
    normalized_column = normalize_text(column_name)
    best = 0
    for candidate in candidates:
        normalized_candidate = normalize_text(candidate)
        if normalized_column == normalized_candidate:
            best = max(best, 100)
        elif normalized_candidate in normalized_column:
            best = max(best, 80)
        elif normalized_column in normalized_candidate:
            best = max(best, 50)
    return best


def infer_columns(df: pd.DataFrame) -> dict[str, str]:
    mapping: dict[str, str] = {}
    used_columns: set[str] = set()
    for field, candidates in FIELD_CANDIDATES.items():
        scored = [
            (candidate_score(column, candidates), str(column))
            for column in df.columns
            if str(column) not in used_columns and not (field in {"spend", "sales", "ad_sales", "orders"} and is_ad_wide_column(column))
        ]
        scored = [item for item in scored if item[0] > 0]
        if scored:
            _, selected = sorted(scored, reverse=True)[0]
            mapping[field] = selected
            used_columns.add(selected)
    return mapping


def is_ad_wide_column(column: Any) -> bool:
    text = str(column).upper().replace(" ", "")
    return any(ad_type in text for ad_type in AD_TYPES) and any(keyword in text for keyword in ["广告费", "广告销售额", "广告订单"])


def saleable_inventory_columns(df: pd.DataFrame) -> list[str]:
    return [
        str(column)
        for column in df.columns
        if "可售" in str(column) or "fulfillable" in str(column).lower() or "available" in str(column).lower()
    ]


def find_columns_by_keywords(df: pd.DataFrame, keywords: list[str]) -> list[str]:
    matched = []
    for column in df.columns:
        column_text = str(column).strip().lower().replace(" ", "")
        if all(keyword.lower().replace(" ", "") in column_text for keyword in keywords):
            matched.append(str(column))
    return matched


def load_rule_templates() -> dict:
    if is_streamlit_cloud():
        return st.session_state.get("_rule_templates", {})
    DATA_DIR.mkdir(exist_ok=True)
    if not RULES_FILE.exists():
        return {}
    try:
        with open(RULES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_rule_template(name: str, rules: dict) -> None:
    templates = load_rule_templates()
    templates[name] = rules
    if is_streamlit_cloud():
        st.session_state["_rule_templates"] = templates
        return
    DATA_DIR.mkdir(exist_ok=True)
    with open(RULES_FILE, "w", encoding="utf-8") as f:
        json.dump(templates, f, ensure_ascii=False, indent=2)


def ad_wide_columns(df: pd.DataFrame, ad_type: str, metric: str) -> list[str]:
    metric_keywords = {
        "spend": ["广告费"],
        "sales": ["广告销售额"],
        "orders": ["广告订单"],
    }
    aliases = [ad_type]
    if ad_type == "SB":
        aliases = ["SB"]
    columns: list[str] = []
    for alias in aliases:
        for column in find_columns_by_keywords(df, [alias, *metric_keywords[metric]]):
            if ad_type == "SB" and any(other in str(column).upper() for other in ["SBV"]):
                continue
            columns.append(column)
    return list(dict.fromkeys(columns))


def normalize_ad_type(value: Any) -> str:
    text = str(value).lower()
    if "sponsored products" in text or re.search(r"\bsp\b", text):
        return "SP"
    if "sbv" in text:
        return "SBV"
    if "sponsored brands" in text or re.search(r"\bsb\b", text):
        return "SB"
    if "sponsored display" in text or re.search(r"\bsd\b", text):
        return "SD"
    if re.search(r"\bst\b", text):
        return "ST"
    return str(value).strip() if str(value).strip() else "未识别渠道"


def parse_number(series: pd.Series) -> pd.Series:
    text = series.astype(str).str.strip()
    multiplier = text.str.contains("万", na=False).map({True: 10000, False: 1})
    text = (
        text.str.replace(",", "", regex=False)
        .str.replace("$", "", regex=False)
        .str.replace("￥", "", regex=False)
        .str.replace("¥", "", regex=False)
        .str.replace("%", "", regex=False)
        .str.replace("万", "", regex=False)
        .str.replace(r"^\((.*)\)$", r"-\1", regex=True)
    )
    return pd.to_numeric(text, errors="coerce").fillna(0) * multiplier


def parse_percent(series: pd.Series) -> pd.Series:
    raw = series.astype(str)
    values = parse_number(series)
    has_percent = raw.str.contains("%", regex=False, na=False)
    values = values.where(~has_percent, values / 100)
    values = values.where(values <= 1, values / 100)
    return values.fillna(0)


def read_report(uploaded_file: Any) -> pd.DataFrame:
    suffix = Path(uploaded_file.name).suffix.lower()
    if suffix in {".xls", ".xlsx"}:
        sheets = pd.read_excel(uploaded_file, sheet_name=None)
        frames = []
        for sheet_name, sheet_df in sheets.items():
            if sheet_df.empty:
                continue
            sheet_df = sheet_df.copy()
            sheet_df["来源Sheet"] = sheet_name
            frames.append(sheet_df)
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    if suffix == ".txt":
        return pd.read_csv(uploaded_file, sep=None, engine="python")

    return pd.read_csv(uploaded_file, sep=None, engine="python")


def clean_raw_data(df: pd.DataFrame) -> pd.DataFrame:
    cleaned = df.copy()
    cleaned.columns = [str(column).strip() for column in cleaned.columns]
    cleaned = cleaned.dropna(axis=1, how="all").dropna(axis=0, how="all")
    return cleaned


def build_standard_data(df: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    out["date"] = (
        pd.to_datetime(df[mapping["date"]], errors="coerce").dt.date
        if "date" in mapping
        else date.today()
    )

    for field in ["product_line", "parent_asin", "child_asin", "brand", "ad_type"]:
        if field in mapping:
            out[field] = df[mapping[field]].astype(str).str.strip().replace("", pd.NA)
        else:
            out[field] = pd.NA

    out["product_line"] = out["product_line"].fillna("未识别产品线")
    out["parent_asin"] = out["parent_asin"].fillna("未识别父ASIN")
    out["child_asin"] = out["child_asin"].fillna("未识别子ASIN")
    out["brand"] = out["brand"].fillna("未识别品牌")
    out["ad_type"] = out["ad_type"].fillna("未识别渠道")
    out["ad_type"] = out["ad_type"].map(normalize_ad_type)

    for field in ["spend", "sales", "ad_sales", "orders", "sessions", "impressions", "clicks", "reviews"]:
        out[field] = parse_number(df[mapping[field]]) if field in mapping else 0

    for ad_type in AD_TYPES:
        for metric in ["spend", "sales", "orders"]:
            columns = ad_wide_columns(df, ad_type, metric)
            out[f"ad_{ad_type.lower()}_{metric}"] = sum(parse_number(df[column]) for column in columns) if columns else 0

    # detect B2B fields (orders / sales) and summarize
    b2b_order_cols = [col for col in df.columns if "b2b" in str(col).lower() or "wholesale" in str(col).lower() or "businessorder" in str(col).lower()]
    b2b_sales_cols = [col for col in df.columns if "b2b" in str(col).lower() or "wholesale" in str(col).lower() or "businesssales" in str(col).lower()]
    if b2b_order_cols:
        out["b2b_orders"] = sum(parse_number(df[col]) for col in b2b_order_cols)
    else:
        out["b2b_orders"] = 0
    if b2b_sales_cols:
        out["b2b_sales"] = sum(parse_number(df[col]) for col in b2b_sales_cols)
    else:
        out["b2b_sales"] = 0

    saleable_columns = saleable_inventory_columns(df)
    if saleable_columns:
        out["inventory"] = sum(parse_number(df[column]) for column in saleable_columns)
    else:
        out["inventory"] = parse_number(df[mapping["inventory"]]) if "inventory" in mapping else 0

    for field in ["acos", "acoas", "ctr", "cvr", "rating"]:
        out[field] = parse_percent(df[mapping[field]]) if field in mapping and field != "rating" else (
            parse_number(df[mapping[field]]) if field in mapping else 0
        )

    wide_spend = sum(out[f"ad_{ad_type.lower()}_spend"] for ad_type in AD_TYPES)
    wide_sales = sum(out[f"ad_{ad_type.lower()}_sales"] for ad_type in AD_TYPES)
    out["spend"] = out["spend"].where(out["spend"] > 0, wide_spend)
    out["ad_sales"] = out["ad_sales"].where(wide_sales <= 0, wide_sales)
    out["ctr_calc"] = safe_divide(out["clicks"], out["impressions"])
    out["cvr_calc"] = safe_divide(out["orders"], out["sessions"])
    out["cpc_calc"] = safe_divide(out["spend"], out["clicks"])
    out["acos_calc"] = safe_divide(out["spend"], out["ad_sales"])
    out["acoas_calc"] = safe_divide(out["spend"], out["sales"])

    out["ctr"] = out["ctr"].where(out["ctr"] > 0, out["ctr_calc"])
    out["cvr"] = out["cvr_calc"]
    out["acos"] = out["acos"].where(out["acos"] > 0, out["acos_calc"])
    out["acoas"] = out["acoas"].where(out["acoas"] > 0, out["acoas_calc"])
    out["cpc"] = out["cpc_calc"]
    out["source_rows"] = 1
    return out


def safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denominator = denominator.replace(0, pd.NA)
    return (numerator / denominator).fillna(0)


def aggregate_metrics(df: pd.DataFrame, groups: list[str]) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    grouped = df.groupby(groups, dropna=False).agg(
        spend=("spend", "sum"),
        sales=("sales", "sum"),
        ad_sales=("ad_sales", "sum"),
        orders=("orders", "sum"),
        sessions=("sessions", "sum"),
        impressions=("impressions", "sum"),
        clicks=("clicks", "sum"),
        rating=("rating", "mean"),
        reviews=("reviews", "max"),
        inventory=("inventory", "sum"),
        source_rows=("source_rows", "sum"),
    )
    grouped = grouped.reset_index()
    grouped["ctr"] = safe_divide(grouped["clicks"], grouped["impressions"])
    grouped["cvr"] = safe_divide(grouped["orders"], grouped["sessions"])
    grouped["cpc"] = safe_divide(grouped["spend"], grouped["clicks"])
    grouped["acos"] = safe_divide(grouped["spend"], grouped["ad_sales"])
    grouped["acoas"] = safe_divide(grouped["spend"], grouped["sales"])
    grouped["sales_share"] = safe_divide(grouped["sales"], pd.Series(grouped["sales"].sum(), index=grouped.index))
    return grouped


def latest_inventory(df: pd.DataFrame, groups: list[str]) -> pd.DataFrame:
    if df.empty or "inventory" not in df:
        return pd.DataFrame(columns=[*groups, "inventory"])
    latest_date = df["date"].max()
    latest_df = df[df["date"] == latest_date]
    return latest_df.groupby(groups, dropna=False).agg(inventory=("inventory", "sum")).reset_index()


def parent_metrics(df: pd.DataFrame) -> pd.DataFrame:
    parent = aggregate_metrics(df, ["product_line", "parent_asin", "brand"])
    if parent.empty:
        return parent
    latest_stock = latest_inventory(df, ["product_line", "parent_asin", "brand"])
    if not latest_stock.empty:
        parent = parent.drop(columns=["inventory"], errors="ignore").merge(
            latest_stock,
            on=["product_line", "parent_asin", "brand"],
            how="left",
        )
        parent["inventory"] = parent["inventory"].fillna(0)
    sku_list = (
        df.groupby(["product_line", "parent_asin", "brand"], dropna=False)["child_asin"]
        .apply(lambda values: "、".join(sorted(set(str(value) for value in values if str(value) and str(value) != "未识别子ASIN"))[:8]))
        .rename("sku")
        .reset_index()
    )
    return parent.merge(sku_list, on=["product_line", "parent_asin", "brand"], how="left")


def child_metrics(df: pd.DataFrame) -> pd.DataFrame:
    child = aggregate_metrics(df, ["product_line", "parent_asin", "child_asin", "brand"])
    if child.empty:
        return child
    latest_stock = latest_inventory(df, ["product_line", "parent_asin", "child_asin", "brand"])
    if not latest_stock.empty:
        child = child.drop(columns=["inventory"], errors="ignore").merge(
            latest_stock,
            on=["product_line", "parent_asin", "child_asin", "brand"],
            how="left",
        )
        child["inventory"] = child["inventory"].fillna(0)
    child["sku"] = child["child_asin"]
    return child


def ad_wide_summary(df: pd.DataFrame, groups: list[str] | None = None) -> pd.DataFrame:
    groups = groups or []
    rows = []
    source_groups = [((), df)] if not groups else df.groupby(groups, dropna=False)
    for group_values, group_df in source_groups:
        group_values = group_values if isinstance(group_values, tuple) else (group_values,)
        base = dict(zip(groups, group_values))
        for ad_type in AD_TYPES:
            spend = float(group_df[f"ad_{ad_type.lower()}_spend"].sum()) if f"ad_{ad_type.lower()}_spend" in group_df else 0
            sales = float(group_df[f"ad_{ad_type.lower()}_sales"].sum()) if f"ad_{ad_type.lower()}_sales" in group_df else 0
            orders = float(group_df[f"ad_{ad_type.lower()}_orders"].sum()) if f"ad_{ad_type.lower()}_orders" in group_df else 0
            if spend == 0 and sales == 0 and orders == 0:
                continue
            rows.append(
                {
                    **base,
                    "ad_type": ad_type,
                    "spend": spend,
                    "sales": sales,
                    "ad_sales": sales,
                    "orders": orders,
                    "acos": spend / sales if sales > 0 else 0,
                    "acoas": spend / float(group_df["sales"].sum()) if float(group_df["sales"].sum()) > 0 else 0,
                }
            )
    table = pd.DataFrame(rows)
    if table.empty:
        fallback = aggregate_metrics(df, [*groups, "ad_type"])
        return fallback
    table["spend_share"] = safe_divide(table["spend"], pd.Series(table["spend"].sum(), index=table.index))
    table["sales_share"] = safe_divide(table["sales"], pd.Series(table["sales"].sum(), index=table.index))
    return table


def format_metric_table(df: pd.DataFrame) -> pd.DataFrame:
    formatted = df.copy()
    money_cols = ["spend", "sales", "ad_sales", "cpc"]
    count_cols = ["orders", "sessions", "impressions", "clicks", "reviews", "inventory", "source_rows"]
    percent_cols = ["ctr", "cvr", "acos", "acoas", "sales_share", "spend_share", "growth_rate"]

    for column in money_cols:
        if column in formatted:
            formatted[DISPLAY_NAMES.get(column, column)] = formatted.pop(column).round(2)
    for column in count_cols:
        if column in formatted:
            formatted[DISPLAY_NAMES.get(column, column)] = formatted.pop(column).round(0)
    for column in percent_cols:
        if column in formatted:
            formatted[DISPLAY_NAMES.get(column, column)] = (formatted.pop(column) * 100).round(2).astype(str) + "%"
    if "rating" in formatted:
        formatted[DISPLAY_NAMES["rating"]] = formatted.pop("rating").round(2)
    return formatted


def table_download(table: pd.DataFrame, filename: str, label: str = "下载") -> None:
    st.download_button(
        label,
        export_excel({"数据": table}),
        filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )


def selectable_columns(table: pd.DataFrame, key: str, fixed_columns: list[str] | None = None) -> list[str]:
    fixed_columns = fixed_columns or []
    available_metrics = [column for column in DEFAULT_METRIC_COLUMNS if column in table.columns]
    selected = st.multiselect(
        "自定义展示列",
        available_metrics,
        default=available_metrics,
        format_func=lambda column: DISPLAY_NAMES.get(column, column),
        key=f"{key}_columns",
    )
    return [column for column in fixed_columns if column in table.columns] + selected


def add_optional_growth_column(table: pd.DataFrame, key: str) -> pd.DataFrame:
    if "growth_rate" not in table.columns:
        return table
    show_growth = st.checkbox("显示环比", value=True, key=f"{key}_show_growth")
    if not show_growth:
        return table.drop(columns=["growth_rate", "compare_value"], errors="ignore")
    output = table.copy()
    output["销售环比"] = output["growth_rate"].apply(lambda value: f"{'↑' if value >= 0 else '↓'}{abs(value):.1%}")
    return output.drop(columns=["growth_rate", "compare_value"], errors="ignore")


def previous_period(df: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    days = (end - start).days + 1
    previous_end = start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=days - 1)
    return df[(df["date"] >= previous_start) & (df["date"] <= previous_end)]


def add_growth(current: pd.DataFrame, previous: pd.DataFrame, group: str) -> pd.DataFrame:
    if previous.empty or current.empty:
        current["growth_rate"] = 0
        return current
    previous_sales = previous.groupby(group)["sales"].sum().rename("previous_sales")
    merged = current.merge(previous_sales, on=group, how="left")
    merged["growth_rate"] = safe_divide(merged["sales"] - merged["previous_sales"].fillna(0), merged["previous_sales"].fillna(0))
    return merged.drop(columns=["previous_sales"])


def add_metric_growth(current: pd.DataFrame, previous: pd.DataFrame, groups: list[str], metric: str = "sales") -> pd.DataFrame:
    if current.empty:
        return current
    if previous.empty:
        current["growth_rate"] = 0
        current["compare_value"] = 0
        return current
    previous_table = aggregate_metrics(previous, groups)
    compare_cols = groups + [metric]
    merged = current.merge(previous_table[compare_cols].rename(columns={metric: "compare_value"}), on=groups, how="left")
    merged["compare_value"] = merged["compare_value"].fillna(0)
    merged["growth_rate"] = safe_divide(merged[metric] - merged["compare_value"], merged["compare_value"])
    return merged


def attach_metric_changes(
    current: pd.DataFrame,
    previous: pd.DataFrame,
    previous_year: pd.DataFrame | None,
    groups: list[str],
    metrics: list[str],
) -> pd.DataFrame:
    """
    为当前聚合表增加环比和同比列。
    - 环比：当前值 vs 上一周期（previous）
    - 同比：当前值 vs 去年同期（previous_year）
    """
    result = current.copy()
    if previous is not None and not previous.empty:
        prev_agg = aggregate_metrics(previous, groups)
        for metric in metrics:
            if metric not in result.columns or metric not in prev_agg.columns:
                continue
            prev_col = f"{metric}_prev"
            result = result.merge(
                prev_agg[groups + [metric]].rename(columns={metric: prev_col}),
                on=groups,
                how="left",
            )
            result[prev_col] = result[prev_col].fillna(0)
            result[f"{metric}_rb"] = safe_divide(result[metric] - result[prev_col], result[prev_col])
    else:
        for metric in metrics:
            if metric in result.columns:
                result[f"{metric}_rb"] = 0.0

    if previous_year is not None and not previous_year.empty:
        prevy_agg = aggregate_metrics(previous_year, groups)
        for metric in metrics:
            if metric not in result.columns or metric not in prevy_agg.columns:
                continue
            prevy_col = f"{metric}_prevy"
            result = result.merge(
                prevy_agg[groups + [metric]].rename(columns={metric: prevy_col}),
                on=groups,
                how="left",
            )
            result[prevy_col] = result[prevy_col].fillna(0)
            result[f"{metric}_yoy"] = safe_divide(result[metric] - result[prevy_col], result[prevy_col])
    else:
        for metric in metrics:
            if metric in result.columns:
                result[f"{metric}_yoy"] = 0.0

    return result


def add_growth_from_table(current: pd.DataFrame, previous_table: pd.DataFrame, groups: list[str], metric: str = "sales") -> pd.DataFrame:
    if current.empty:
        return current
    if previous_table.empty or metric not in previous_table:
        current["growth_rate"] = 0
        current["compare_value"] = 0
        return current
    compare = previous_table[groups + [metric]].rename(columns={metric: "compare_value"})
    merged = current.merge(compare, on=groups, how="left")
    merged["compare_value"] = merged["compare_value"].fillna(0)
    merged["growth_rate"] = safe_divide(merged[metric] - merged["compare_value"], merged["compare_value"])
    return merged


def metric_summary(df: pd.DataFrame) -> dict[str, float]:
    spend = float(df["spend"].sum()) if not df.empty else 0
    sales = float(df["sales"].sum()) if not df.empty else 0
    ad_sales = float(df["ad_sales"].sum()) if not df.empty else 0
    orders = float(df["orders"].sum()) if not df.empty else 0
    sessions = float(df["sessions"].sum()) if not df.empty and "sessions" in df else 0
    clicks = float(df["clicks"].sum()) if not df.empty else 0
    impressions = float(df["impressions"].sum()) if not df.empty else 0
    return {
        "spend": spend,
        "sales": sales,
        "orders": orders,
        "acos": spend / ad_sales if ad_sales > 0 else 0,
        "acoas": spend / sales if sales > 0 else 0,
        "cvr": orders / sessions if sessions > 0 else 0,
        "ctr": clicks / impressions if impressions > 0 else 0,
    }


def metric_delta(current: float, previous: float) -> tuple[float, float]:
    absolute = current - previous
    percent = absolute / previous if previous else (1 if current > 0 else 0)
    return percent, absolute


def format_value(metric: str, value: float) -> str:
    if metric in {"acos", "acoas", "cvr", "ctr"}:
        return f"{value:.1%}"
    if metric == "orders":
        return f"{value:,.0f}"
    return f"{value:,.2f}"


def render_kpi_card(metric: str, title: str, current: float, previous: float, compare_start: date, compare_end: date) -> None:
    delta_pct, delta_abs = metric_delta(current, previous)
    higher_is_good = metric not in {"acos", "acoas"}
    good = delta_pct >= 0 if higher_is_good else delta_pct <= 0
    color = "#16a34a" if good else "#dc2626"
    arrow = "↑" if delta_pct >= 0 else "↓"
    st.markdown(
        f"""
        <div class="kpi-card" title="本期：{format_value(metric, current)}&#10;环比：{format_value(metric, delta_abs)}  {delta_pct:.2%}&#10;{compare_start} 至 {compare_end}">
          <div class="kpi-title">{title}</div>
          <div class="kpi-value">{format_value(metric, current)}</div>
          <div class="kpi-delta" style="color:{color};">{arrow}{abs(delta_pct):.1%}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def overview_line(line_view: pd.DataFrame) -> str:
    if line_view.empty:
        return "当前筛选范围内无产品线数据。"
    top = line_view.sort_values("sales", ascending=False).iloc[0]
    worst = line_view.sort_values("sales", ascending=True).iloc[0]
    return f"最高销售产品线：{top.get('product_line','-')}（{top.get('sales',0):,.0f}），下降最多：{worst.get('product_line','-')}（{worst.get('sales',0):,.0f}）"


def overview_ad(ad_view: pd.DataFrame, prev_ad_view: pd.DataFrame) -> str:
    if ad_view.empty:
        return "当前筛选范围内无广告数据。"
    # 总花费变化
    cur_spend_total = ad_view["spend"].sum()
    prev_spend_total = prev_ad_view["spend"].sum() if not prev_ad_view.empty else 0
    spend_change = cur_spend_total - prev_spend_total
    spend_pct = safe_divide(pd.Series([spend_change]), pd.Series([prev_spend_total if prev_spend_total else 0])).iloc[0]
    # 总销售变化
    cur_sales_total = ad_view["sales"].sum()
    prev_sales_total = prev_ad_view["sales"].sum() if not prev_ad_view.empty else 0
    sales_change = cur_sales_total - prev_sales_total
    sales_pct = safe_divide(pd.Series([sales_change]), pd.Series([prev_sales_total if prev_sales_total else 0])).iloc[0]

    # 按广告类型看花费变化，找“上涨最快/下降最多”的类型，并给出具体数值
    cur = ad_view.groupby("ad_type", dropna=False)["spend"].sum()
    prev = prev_ad_view.groupby("ad_type", dropna=False)["spend"].sum() if not prev_ad_view.empty else pd.Series(dtype=float)
    changes = []
    for ad in cur.index:
        p = prev.get(ad, 0)
        diff = cur[ad] - p
        pct = diff / p if p else (1 if cur[ad] > 0 else 0)
        changes.append((ad, diff, pct))
    if not changes:
        return f"总花费变化：{spend_change:+,.0f}（{spend_pct:+.1%}），总销售变化：{sales_change:+,.0f}（{sales_pct:+.1%}）。"
    changes_sorted = sorted(changes, key=lambda x: x[2], reverse=True)
    top_gain, gain_diff, gain_pct = changes_sorted[0]
    top_drop, drop_diff, drop_pct = changes_sorted[-1]
    return (
        f"总花费变化：{spend_change:+,.0f}（{spend_pct:+.1%}），总销售变化：{sales_change:+,.0f}（{sales_pct:+.1%}）；"
        f"上涨最快：{top_gain}（花费 {gain_diff:+,.0f}，{gain_pct:+.1%}），"
        f"下降最多：{top_drop}（花费 {drop_diff:+,.0f}，{drop_pct:+.1%}）"
    )


def summarize_product_lines(line_overall: pd.DataFrame) -> str:
    if line_overall.empty:
        return "当前筛选范围内没有产品线数据。"
    metric = "sales_rb" if "sales_rb" in line_overall.columns else "sales"
    best = line_overall.sort_values(metric, ascending=False).iloc[0]
    worst = line_overall.sort_values(metric, ascending=True).iloc[0]
    best_name = best.get("product_line", "-")
    worst_name = worst.get("product_line", "-")
    return (
        f"优先关注：产品线 {worst_name} 销售环比 {best.get('sales_rb',0):+.1%}，"
        f"产品线 {best_name} 销售环比 {worst.get('sales_rb',0):+.1%} 表现最佳，可考虑加大投放。"
    )


def summarize_products(product_view: pd.DataFrame, good_mask: pd.Series, bad_mask: pd.Series) -> str:
    if product_view.empty:
        return "当前筛选范围内没有产品数据。"
    lines = []
    bad_products = product_view[bad_mask]
    if not bad_products.empty:
        focus_bad = bad_products.sort_values(["spend", "acos"], ascending=[False, False]).iloc[0]
        lines.append(
            f"优先优化：产品线 {focus_bad.get('product_line','-')} / 父ASIN {focus_bad.get('parent_asin','-')} "
            f"花费 {focus_bad.get('spend',0):,.0f}，ACOS {focus_bad.get('acos',0):.1%}，CVR {focus_bad.get('cvr',0):.1%}。"
        )
    good_products = product_view[good_mask]
    if not good_products.empty:
        focus_good = good_products.sort_values(["sales", "cvr"], ascending=[False, False]).iloc[0]
        lines.append(
            f"可放量：产品线 {focus_good.get('product_line','-')} / 父ASIN {focus_good.get('parent_asin','-')} "
            f"销售 {focus_good.get('sales',0):,.0f}，ACOS {focus_good.get('acos',0):.1%}，CVR {focus_good.get('cvr',0):.1%}。"
        )
    return " ".join(lines) if lines else "当前没有明显需要优先优化或放量的产品。"


def summarize_inventory(inventory_table: pd.DataFrame) -> str:
    if inventory_table.empty:
        return "当前筛选范围内没有库存数据。"
    # 预计可售天数最少的为缺货风险，最多的为积压
    soon_oos = inventory_table.sort_values("预计可售天数", ascending=True).iloc[0]
    overstock = inventory_table.sort_values("预计可售天数", ascending=False).iloc[0]
    msg_soon = (
        f"缺货风险：产品线 {soon_oos.get('product_line','-')} / 父ASIN {soon_oos.get('parent_asin','-')} "
        f"预计可售 {soon_oos.get('预计可售天数',0)} 天。"
    )
    msg_over = (
        f"库存积压：产品线 {overstock.get('product_line','-')} / 父ASIN {overstock.get('parent_asin','-')} "
        f"库存 {overstock.get('inventory',0):,.0f}，预计可售 {overstock.get('预计可售天数',0)} 天。"
    )
    return msg_soon + " " + msg_over


def summarize_rating(rating_table: pd.DataFrame) -> str:
    if rating_table.empty:
        return "当前筛选范围内没有评分/评论数据。"
    worst = rating_table.sort_values("rating", ascending=True).iloc[0]
    best = rating_table.sort_values("rating", ascending=False).iloc[0]
    msg_bad = (
        f"口碑风险：产品线 {worst.get('product_line','-')} / 父ASIN {worst.get('parent_asin','-')} "
        f"评分 {worst.get('rating',0):.1f}，评论数 {worst.get('reviews',0):,.0f}。"
    )
    msg_good = (
        f"口碑优势：产品线 {best.get('product_line','-')} / 父ASIN {best.get('parent_asin','-')} "
        f"评分 {best.get('rating',0):.1f}，评论数 {best.get('reviews',0):,.0f}。"
    )
    return msg_bad + " " + msg_good


def evaluate_rules(table: pd.DataFrame, rules: list[dict]) -> pd.Series:
    if table.empty or not rules:
        return pd.Series([False] * len(table), index=table.index)
    mask = pd.Series([True] * len(table), index=table.index)
    for rule in rules:
        metric = rule.get("metric")
        op = rule.get("op")
        value = rule.get("value")
        if metric not in table.columns:
            mask &= False
            continue
        # handle percent entered as >1 meaning percent like 15 -> 0.15
        if metric in {"cvr", "acos", "acoas"} and value is not None:
            if value > 1:
                value = float(value) / 100.0
        if op == "<":
            mask &= table[metric] < value
        elif op == "<=":
            mask &= table[metric] <= value
        elif op == ">":
            mask &= table[metric] > value
        elif op == ">=":
            mask &= table[metric] >= value
        else:
            mask &= False
    return mask


def product_tags(row: pd.Series, thresholds: dict[str, float]) -> str:
    tags = []
    if row.get("acos", 0) > thresholds["high_acos"]:
        tags.append("高ACOS")
    if row.get("acoas", 0) > thresholds["high_acoas"]:
        tags.append("高TACoAS")
    if row.get("cvr", 0) < thresholds["low_cvr"] and row.get("clicks", 0) > 0:
        tags.append("低CVR")
    if (
        row.get("acos", 0) < thresholds["high_acos"]
        and row.get("acoas", 0) < thresholds["high_acoas"]
        and row.get("cvr", 0) > thresholds["low_cvr"]
    ):
        tags.append("潜力款")
    return " / ".join(tags) if tags else "正常"


def advertising_diagnosis(df: pd.DataFrame, thresholds: dict[str, float], level: str = "parent") -> pd.DataFrame:
    product = child_metrics(df) if level == "child" else parent_metrics(df)
    if product.empty:
        return product
    rows = []
    for _, row in product.iterrows():
        high_risk = (
            row["acos"] > thresholds["high_acos"]
            and row["acoas"] > thresholds["high_acoas"]
            and row["cvr"] < thresholds["low_cvr"]
            and row["clicks"] > thresholds["click_threshold"]
        )
        scalable = (
            row["acos"] < thresholds["high_acos"]
            and row["acoas"] < thresholds["high_acoas"]
            and row["cvr"] > thresholds["low_cvr"]
            and row["clicks"] < thresholds["click_threshold"]
        )
        if high_risk or scalable:
            item = row.to_dict()
            item["标签"] = "高风险" if high_risk else "可放量"
            item["层级"] = "子ASIN" if level == "child" else "父ASIN"
            item["问题"] = "广告消耗高但转化弱，存在亏损风险" if high_risk else "转化效率好但流量不足"
            item["建议"] = "降低广告花费或优化 Listing" if high_risk else "增加广告预算，扩大曝光和点击"
            rows.append(item)
    return pd.DataFrame(rows)


def render_diagnosis_cards(table: pd.DataFrame, title: str, empty_text: str) -> None:
    st.markdown(f'<div class="mini-title">{title}</div>', unsafe_allow_html=True)
    if table.empty:
        st.info(empty_text)
        return
    for _, row in table.head(12).iterrows():
        card_class = "alert-red" if row["标签"] == "高风险" else "alert-green"
        child_line = f"<div><b>子ASIN / SKU：</b>{row.get('child_asin', row.get('sku', ''))}</div>" if row.get("层级") == "子ASIN" else ""
        st.markdown(
            f"""
            <div class="alert-card {card_class}">
              <span class="tag">{row['标签']}</span><span class="tag">{row.get('层级', '')}</span>
              <div><b>产品线：</b>{row.get('product_line', '')}</div>
              <div><b>父ASIN：</b>{row.get('parent_asin', '')}</div>
              {child_line}
              <div><b>问题：</b>{row['问题']}</div>
              <div><b>建议：</b>{row['建议']}</div>
              <div style="color:#6b7280;margin-top:6px;">ACOS {row['acos']:.1%} · TACoAS {row['acoas']:.1%} · CVR {row['cvr']:.1%} · 点击 {row['clicks']:,.0f}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def apply_module_filters(df: pd.DataFrame, prefix: str, default_start: date, default_end: date) -> pd.DataFrame:
    with st.expander("模块筛选", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            quick_range = st.selectbox(
                "时间快捷选择",
                ["近3天", "近7天", "近14天", "近30天", "近60天", "近90天", "近180天", "近365天", "自定义"],
                index=3,
                key=f"{prefix}_quick",
            )
            # 快捷时间决定默认区间，但“时间范围”始终可以手动调整
            min_d, max_d = df["date"].min(), df["date"].max()
            if quick_range == "自定义":
                default_range = (default_start, default_end)
            else:
                days = int(quick_range.replace("近", "").replace("天", ""))
                end = min(default_end, max_d)
                start = max(min_d, end - timedelta(days=days - 1))
                default_range = (start, end)
            module_range = st.date_input(
                "时间范围",
                value=default_range,
                min_value=min_d,
                max_value=max_d,
                key=f"{prefix}_date",
            )
        with col2:
            lines = sorted(df["product_line"].dropna().unique().tolist())
            selected = st.multiselect("产品线", lines, default=lines, key=f"{prefix}_line")
        with col3:
            brands = sorted(df["brand"].dropna().unique().tolist())
            selected_brands = st.multiselect("品牌", brands, default=brands, key=f"{prefix}_brand")
    start, end = module_range if isinstance(module_range, tuple) and len(module_range) == 2 else (default_start, default_end)
    return df[
        (df["date"] >= start)
        & (df["date"] <= end)
        & (df["product_line"].isin(selected))
        & (df["brand"].isin(selected_brands))
    ].copy()


def inventory_status(row: pd.Series, days: int) -> str:
    daily_sales = row["orders"] / max(days, 1)
    stock_days = row["inventory"] / daily_sales if daily_sales > 0 else 999
    if row["inventory"] <= 0 and row["orders"] > 0:
        return "🔴 紧急"
    if stock_days < 14 or row["inventory"] < row["orders"] * 0.1:
        return "🔴 紧急"
    if stock_days <= 30:
        return "🟡 预警"
    return "🟢 正常"


def product_alerts(df: pd.DataFrame, thresholds: dict[str, float], has_inventory: bool, has_rating: bool) -> pd.DataFrame:
    product = parent_metrics(df)
    if product.empty:
        return product

    alerts = []
    for _, row in product.iterrows():
        reasons = []
        if row["acos"] > thresholds["high_acos"]:
            reasons.append(f"高ACOS {row['acos']:.1%}")
        if row["acoas"] > thresholds["high_acoas"]:
            reasons.append(f"高TACoAS {row['acoas']:.1%}")
        if row["cvr"] < thresholds["low_cvr"] and row["clicks"] > 0:
            reasons.append(f"低CVR {row['cvr']:.1%}")
        if has_rating and 0 < row["rating"] < thresholds["low_rating"]:
            reasons.append(f"低评分 {row['rating']:.1f}")
        if has_inventory and row["inventory"] > 0 and row["orders"] > 0:
            turnover = row["orders"] / row["inventory"]
            if turnover < thresholds["low_turnover"]:
                reasons.append(f"库存积压 周转{turnover:.2f}次/月")
            if row["orders"] >= thresholds["high_sales"] and row["inventory"] < thresholds["low_stock"]:
                reasons.append("缺货风险")
        if reasons:
            item = row.to_dict()
            item["问题诊断"] = "；".join(reasons)
            alerts.append(item)
    return pd.DataFrame(alerts)


def change_alerts(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or df["date"].nunique() < 2:
        return pd.DataFrame()
    daily = aggregate_metrics(df, ["date", "product_line", "parent_asin"])
    daily = daily.sort_values("date")
    alerts = []
    for metric in ["sales", "orders", "cvr", "acos"]:
        daily[f"{metric}_change"] = (
            daily.groupby(["product_line", "parent_asin"], dropna=False)[metric]
            .pct_change()
            .replace([float("inf"), float("-inf")], 0)
            .fillna(0)
        )
        changed = daily[daily[f"{metric}_change"].abs() >= 0.2]
        for _, row in changed.iterrows():
            level = "🔴 严重预警" if abs(row[f"{metric}_change"]) > 0.5 else "🟡 中等预警"
            alerts.append(
                {
                    "日期": row["date"],
                    "产品线": row["product_line"],
                    "父ASIN": row["parent_asin"],
                    "指标": DISPLAY_NAMES.get(metric, metric),
                    "变化幅度": f"{row[f'{metric}_change']:.1%}",
                    "当前值": format_value(metric, row[metric]),
                    "预警级别": level,
                }
            )
    return pd.DataFrame(alerts)


def export_excel(tables: dict[str, pd.DataFrame]) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        wrote_sheet = False
        for name, table in tables.items():
            if table is not None and not table.empty:
                table.to_excel(writer, sheet_name=name[:31], index=False)
                wrote_sheet = True
        if not wrote_sheet:
            pd.DataFrame({"提示": ["当前筛选条件下没有可导出的数据"]}).to_excel(writer, sheet_name="空数据", index=False)
    return output.getvalue()


def export_all_data(all_data: pd.DataFrame, line_table: pd.DataFrame, product_table: pd.DataFrame, ad_table: pd.DataFrame, diagnosis_table: pd.DataFrame, inventory_table: pd.DataFrame, rating_table: pd.DataFrame) -> bytes:
    sheets = {
        "原始标准化数据": all_data,
        "产品线分析": line_table,
        "产品表现": product_table,
        "广告表现": ad_table,
        "广告诊断": diagnosis_table,
        "库存预警": inventory_table,
        "评分预警": rating_table,
    }
    return export_excel(sheets)


def export_pdf(summary: dict[str, Any]) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4)
    font_name = "Helvetica"
    for font_path in [
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
        "/System/Library/Fonts/PingFang.ttc",
    ]:
        if Path(font_path).exists():
            pdfmetrics.registerFont(TTFont("ChineseFont", font_path))
            font_name = "ChineseFont"
            break

    pdf.setFont(font_name, 16)
    pdf.drawString(50, 800, APP_TITLE)
    pdf.setFont(font_name, 11)
    y = 760
    for key, value in summary.items():
        pdf.drawString(50, y, f"{key}: {value}")
        y -= 24
    pdf.showPage()
    pdf.save()
    return output.getvalue()


def load_history() -> pd.DataFrame:
    if is_streamlit_cloud():
        history = st.session_state.get("_history_df")
        return history.copy() if isinstance(history, pd.DataFrame) else pd.DataFrame()
    if not HISTORY_FILE.exists():
        return pd.DataFrame()
    return pd.read_csv(HISTORY_FILE, parse_dates=["date"]).assign(date=lambda frame: frame["date"].dt.date)


def save_history(df: pd.DataFrame) -> None:
    existing = load_history()
    combined = pd.concat([existing, df], ignore_index=True) if not existing.empty else df.copy()
    combined = combined.drop_duplicates()
    if is_streamlit_cloud():
        # 云端：仅在本次会话内保存，避免因写文件失败导致页面断开
        st.session_state["_history_df"] = combined
        return
    DATA_DIR.mkdir(exist_ok=True)
    combined.to_csv(HISTORY_FILE, index=False, encoding="utf-8-sig")


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    st.markdown(
        """
        <style>
        .stApp { background: #f6f7fb; color: #111827; }
        h1, h2, h3 { letter-spacing: -0.02em; }
        .block-container { padding-top: 1.4rem; max-width: 1500px; }
        div[data-testid="stVerticalBlockBorderWrapper"] {
          background: #ffffff;
          border: 1px solid #e5e7eb;
          border-radius: 18px;
          box-shadow: 0 10px 28px rgba(15, 23, 42, 0.06);
          padding: 1.1rem 1.2rem;
        }
        div[data-testid="stDataFrame"] {
          border-radius: 14px;
          overflow: hidden;
          border: 1px solid #edf0f5;
          font-size: 15px;
          background: white;
        }
        div[data-testid="stDataFrame"] [role="row"] { min-height: 44px; }
        div[data-testid="stDataFrame"] [role="columnheader"] {
          background: #f8fafc !important;
          color: #334155 !important;
          font-weight: 800 !important;
        }
        div[data-testid="stDataFrame"] [role="row"]:hover {
          background: #f1f5f9 !important;
        }
        .hero {
          background: linear-gradient(135deg, #111827 0%, #1f2937 55%, #0f766e 100%);
          border-radius: 24px;
          color: white;
          padding: 26px 30px;
          margin-bottom: 18px;
          box-shadow: 0 16px 40px rgba(15, 23, 42, 0.18);
        }
        .hero h1 { margin: 0; color: white; font-size: 34px; }
        .hero p { margin: 8px 0 0; color: #d1d5db; }
        .kpi-card {
          background: #ffffff;
          border: 1px solid #e5e7eb;
          border-radius: 18px;
          padding: 18px;
          min-height: 136px;
          box-shadow: 0 10px 28px rgba(15, 23, 42, 0.06);
        }
        .kpi-title { color: #6b7280; font-size: 13px; font-weight: 600; }
        .kpi-value { color: #111827; font-size: 29px; font-weight: 800; margin-top: 10px; }
        .kpi-delta { font-size: 14px; font-weight: 800; margin-top: 8px; }
        .section-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 2px 0 14px;
          border-bottom: 1px solid #eef2f7;
          margin-bottom: 16px;
        }
        .section-title { font-size: 32px; font-weight: 950; margin-bottom: 4px; color: #0f172a; line-height: 1.15; }
        .mini-title { font-size: 22px; font-weight: 900; color: #0f172a; margin: 10px 0 12px; }
        .section-caption { color: #6b7280; font-size: 13px; margin-bottom: 14px; }
        .module-badge {
          display: inline-flex;
          align-items: center;
          border-radius: 999px;
          background: linear-gradient(135deg, #ecfeff, #eef2ff);
          color: #0e7490;
          border: 1px solid #bae6fd;
          padding: 7px 12px;
          font-size: 13px;
          font-weight: 800;
        }
        /* 模块卡片浅色底：轮流使用柔和的粉/黄/蓝色调 */
        div[data-testid="stVerticalBlockBorderWrapper"]:nth-of-type(3n+1) { background: #fef2f2; }  /* 浅粉红 */
        div[data-testid="stVerticalBlockBorderWrapper"]:nth-of-type(3n+2) { background: #fefce8; }  /* 浅米黄 */
        div[data-testid="stVerticalBlockBorderWrapper"]:nth-of-type(3n+3) { background: #eff6ff; }  /* 浅蓝 */
        .alert-card {
          border-radius: 16px;
          padding: 16px 18px;
          margin-bottom: 12px;
          border: 1px solid #e5e7eb;
          background: #fff;
        }
        .alert-red { border-left: 6px solid #dc2626; background: #fff7f7; }
        .alert-green { border-left: 6px solid #16a34a; background: #f6fff9; }
        .tag {
          display: inline-block;
          border-radius: 999px;
          padding: 4px 10px;
          font-size: 12px;
          font-weight: 700;
          background: #eef2ff;
          color: #3730a3;
          margin-right: 6px;
        }
        .status-green { color: #047857; font-weight: 900; }
        .status-yellow { color: #b45309; font-weight: 900; }
        .status-red { color: #b91c1c; font-weight: 900; }
        .stTabs [data-baseweb="tab-list"] { gap: 16px; }
        .stTabs [data-baseweb="tab"] {
          border-radius: 999px;
          border: 1px solid #e5e7eb;
          padding: 22px 40px;
          font-size: 22px;
          font-weight: 900;
          letter-spacing: 0.8px;
          box-shadow: 0 8px 18px rgba(15,23,42,0.1);
        }
        /* 顶部六个模块 tab 使用淡淡的不同底色（直接作用在 tab 元素本身） */
        .stTabs [data-baseweb="tab-list"] [data-baseweb="tab"]:nth-of-type(1) { background: #fef2f2; } /* 产品线分析：浅粉 */
        .stTabs [data-baseweb="tab-list"] [data-baseweb="tab"]:nth-of-type(2) { background: #fefce8; } /* 产品表现：浅黄 */
        .stTabs [data-baseweb="tab-list"] [data-baseweb="tab"]:nth-of-type(3) { background: #eff6ff; } /* 广告表现：浅蓝 */
        .stTabs [data-baseweb="tab-list"] [data-baseweb="tab"]:nth-of-type(4) { background: #ecfdf5; } /* 库存预警：浅绿 */
        .stTabs [data-baseweb="tab-list"] [data-baseweb="tab"]:nth-of-type(5) { background: #f5f3ff; } /* 评分口碑：浅紫 */
        .stTabs [data-baseweb="tab-list"] [data-baseweb="tab"]:nth-of-type(6) { background: #fff7ed; } /* 导出/字段：浅橙 */
        .summary-card {
          background: #0f172a;
          background: linear-gradient(135deg, #38bdf8 0%, #6366f1 45%, #0f172a 100%);
          border-radius: 20px;
          padding: 18px 20px;
          color: #ecfdf5;
          box-shadow: 0 18px 40px rgba(15,23,42,0.45);
          display: flex;
          flex-direction: column;
          gap: 6px;
        }
        .summary-label {
          font-size: 13px;
          font-weight: 700;
          opacity: 0.9;
        }
        .summary-main {
          font-size: 24px;
          font-weight: 900;
        }
        .summary-sub {
          font-size: 13px;
          color: #d1fae5;
        }
        /* 隐藏右上角反复弹出的“Connection lost”状态提示，避免干扰使用 */
        div[data-testid="stConnectionStatus"] {
          display: none !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""
        <div class="hero">
          <h1>{APP_TITLE}</h1>
          <p>亚马逊运营数据看板：聚焦产品、广告、库存与评分数据，帮助快速发现问题并优化运营决策。</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        st.markdown('<div class="section-title">数据上传</div>', unsafe_allow_html=True)
        st.markdown('<div class="section-caption">支持多文件上传；没有库存、评分等字段时，对应模块会自动跳过。</div>', unsafe_allow_html=True)
        upload_col, history_col = st.columns([4, 1])
        with upload_col:
            files = st.file_uploader(
                "支持 XLS / XLSX / TXT / CSV，可一次上传多个历史报表",
                type=["xls", "xlsx", "txt", "csv"],
                accept_multiple_files=True,
                label_visibility="collapsed",
            )
        with history_col:
            use_history = st.checkbox("合并历史数据", value=True)

    raw_frames: list[pd.DataFrame] = []
    mappings: list[dict[str, str]] = []
    errors: list[str] = []
    # 自动识别字段；尽量“能用多少用多少”，缺失字段的模块自动显示“无数据”
    # 同时提供“字段映射”折叠面板，让你覆盖系统识别结果，重点只展示核心字段
    for idx, uploaded_file in enumerate(files or []):
        try:
            raw = clean_raw_data(read_report(uploaded_file))
            inferred = infer_columns(raw)
            mapping = dict(inferred)
            missing_required = [field for field in REQUIRED_FIELDS if field not in inferred]

            if missing_required:
                st.warning(f"文件 {uploaded_file.name} 未识别到必需字段：{', '.join(missing_required)}。这些字段相关的模块将显示“无数据”。")

            with st.expander(f"字段映射（可选）：{uploaded_file.name}", expanded=bool(missing_required)):
                st.write("系统已根据表头自动识别字段。如需调整，请在下拉框中修改；选择“(不使用)”表示本次分析不使用该字段。")
                mapping_rows = []
                columns_as_str = [str(c) for c in raw.columns]
                # 只优先展示核心字段，避免面板过长
                for field in MAPPING_FIELDS:
                    options = ["(不使用)"] + columns_as_str
                    default_col = inferred.get(field, None)
                    default_index = options.index(default_col) if default_col in options else 0
                    choice = st.selectbox(
                        f"{field}",
                        options,
                        index=default_index,
                        key=f"map_{idx}_{field}",
                    )
                    if choice != "(不使用)":
                        mapping[field] = choice
                    elif field in mapping:
                        mapping.pop(field, None)
                    mapping_rows.append(
                        {
                            "系统字段": field,
                            "自动识别列": inferred.get(field, "（未识别）"),
                            "最终使用列": mapping.get(field, "不使用"),
                        }
                    )
                st.data_editor(pd.DataFrame(mapping_rows), use_container_width=True, hide_index=True, disabled=True)

            std = build_standard_data(raw, mapping)
            raw_frames.append(std)
            mappings.append(mapping)
        except Exception:
            # 只在真正读不出文件时记为失败（例如文件损坏或完全不支持的格式）
            errors.append(uploaded_file.name)

    current_data = pd.concat(raw_frames, ignore_index=True) if raw_frames else pd.DataFrame()
    history_data = load_history() if use_history else pd.DataFrame()
    all_data = pd.concat([history_data, current_data], ignore_index=True) if not current_data.empty or not history_data.empty else pd.DataFrame()

    if errors:
        st.warning(f"{len(errors)} 个文件完全无法读取（可能损坏或格式不支持）：{', '.join(errors)}。其余文件已按可用字段参与分析。")

    if all_data.empty:
        st.info("请先上传 Amazon 报表。建议直接上传你当前的父 ASIN 产品表现报表。")
        return

    all_data["date"] = pd.to_datetime(all_data["date"], errors="coerce").dt.date
    all_data = all_data.dropna(subset=["date"])
    min_date, max_date = all_data["date"].min(), all_data["date"].max()
    data_updated_at = f"{max_date}（数据最新日期）"

    # 全局层面提示：本次分析总体缺少哪些必需字段
    detected_fields: set[str] = set()
    for mapping in mappings:
        detected_fields.update(mapping.keys())
    missing_global = [field for field in REQUIRED_FIELDS if field not in detected_fields]
    if missing_global:
        st.info("本次数据缺少以下关键字段，将导致对应模块显示“无数据”或部分指标为 0： " + ", ".join(missing_global))

    with st.container(border=True):
        st.markdown('<div class="section-title">全局筛选</div>', unsafe_allow_html=True)
        col1, col2, col3, col4, col5 = st.columns([1.1, 1.7, 1.8, 1.8, 1.6])
        with col1:
            quick_range = st.selectbox(
                "快捷时间",
                ["近3天", "近7天", "近14天", "近30天", "近60天", "近90天", "近180天", "近365天", "自定义"],
                index=3,
            )
        # 无论是否选择“自定义”，下面的日期范围都可以手动调整；
        # 快捷时间只是给一个默认区间，方便一键选择。
        with col2:
            if quick_range == "自定义":
                default_range = (min_date, max_date)
            else:
                days = int(quick_range.replace("近", "").replace("天", ""))
                auto_end = max_date
                auto_start = max(min_date, max_date - timedelta(days=days - 1))
                default_range = (auto_start, auto_end)
            selected_range = st.date_input(
                "当前周期",
                value=default_range,
                min_value=min_date,
                max_value=max_date,
            )
        start_date, end_date = (
            selected_range if isinstance(selected_range, tuple) and len(selected_range) == 2 else (min_date, max_date)
        )

        product_lines = sorted(all_data["product_line"].dropna().unique().tolist())
        with col3:
            selected_lines = st.multiselect("产品线", product_lines, default=product_lines)
        brands = sorted(all_data["brand"].dropna().unique().tolist())
        with col4:
            selected_brands = st.multiselect("品牌", brands, default=brands)
        with col5:
            comparison_mode = st.radio("对比周期", ["自动向前等长", "手动选择"], horizontal=False)

        period_days = (end_date - start_date).days + 1
        auto_compare_end = start_date - timedelta(days=1)
        auto_compare_start = auto_compare_end - timedelta(days=period_days - 1)
        if comparison_mode == "手动选择":
            default_compare_start = max(min_date, auto_compare_start)
            default_compare_end = min(max_date, auto_compare_end)
            if default_compare_end < default_compare_start:
                default_compare_start = min_date
                default_compare_end = min_date
            compare_range = st.date_input(
                "手动对比时间",
                value=(default_compare_start, default_compare_end),
                min_value=min_date,
                max_value=max_date,
            )
            compare_start, compare_end = compare_range if isinstance(compare_range, tuple) and len(compare_range) == 2 else (auto_compare_start, auto_compare_end)
        else:
            compare_start, compare_end = auto_compare_start, auto_compare_end
            st.caption(f"当前周期：{start_date} ～ {end_date}；对比周期：{compare_start} ～ {compare_end}")

        with st.expander("预警阈值配置", expanded=False):
            th1, th2, th3, th4, th5, th6 = st.columns(6)
            with th1:
                high_acos = st.slider("ACOS阈值", 0.0, 1.0, 0.35, 0.01)
            with th2:
                high_acoas = st.slider("TACoAS阈值", 0.0, 1.0, 0.30, 0.01)
            with th3:
                low_cvr = st.slider("CVR阈值", 0.0, 0.2, 0.005, 0.001)
            with th4:
                click_threshold = st.number_input("点击阈值", min_value=0, value=100)
            with th5:
                low_rating = st.slider("低评分阈值", 1.0, 5.0, 4.2, 0.1)
            with th6:
                low_stock = st.number_input("缺货库存阈值", min_value=0, value=10)
            high_sales = st.number_input("高销量判断阈值", min_value=0, value=10)

        if not current_data.empty:
            if is_streamlit_cloud():
                st.caption("提示：当前运行在云端（Streamlit Cloud），历史数据/规则模板默认仅在本次会话内保存。")
                if st.button("把本次上传保存为历史数据（本次会话有效）"):
                    save_history(current_data)
                    st.success("已保存到本次会话历史数据（云端重启后可能丢失）。")
            else:
                if st.button("把本次上传保存为历史数据"):
                    save_history(current_data)
                    st.success("已保存到本地历史数据，下次打开可继续用于趋势对比。")

    filtered = all_data[
        (all_data["date"] >= start_date)
        & (all_data["date"] <= end_date)
        & (all_data["product_line"].isin(selected_lines))
        & (all_data["brand"].isin(selected_brands))
    ].copy()

    if filtered.empty:
        st.warning("当前筛选条件下没有数据。")
        return

    has_inventory = filtered["inventory"].sum() > 0
    has_rating = filtered["rating"].sum() > 0 or filtered["reviews"].sum() > 0
    thresholds = {
        "high_acos": high_acos,
        "high_acoas": high_acoas,
        "low_cvr": low_cvr,
        "low_rating": low_rating,
        "low_turnover": 1,
        "low_stock": float(low_stock),
        "high_sales": float(high_sales),
        "click_threshold": float(click_threshold),
    }

    comparison_scope = all_data[
        (all_data["product_line"].isin(selected_lines))
        & (all_data["brand"].isin(selected_brands))
    ]
    previous = comparison_scope[(comparison_scope["date"] >= compare_start) & (comparison_scope["date"] <= compare_end)]
    current_summary = metric_summary(filtered)
    previous_summary = metric_summary(previous)

    # 先计算各模块聚合结果，供摘要和后续模块复用
    line_table = add_metric_growth(aggregate_metrics(filtered, ["product_line", "parent_asin"]), previous, ["product_line", "parent_asin"])
    product_table = parent_metrics(filtered)
    product_table["标签"] = product_table.apply(lambda row: product_tags(row, thresholds), axis=1)
    ad_table = ad_wide_summary(filtered, ["product_line", "parent_asin"])
    alert_table = product_alerts(filtered, thresholds, has_inventory, has_rating)
    diagnosis_table = advertising_diagnosis(filtered, thresholds, "parent")

    st.markdown("### 整体看板")
    st.caption(f"数据更新时间：{data_updated_at}；当前周期：{start_date} 至 {end_date}；对比周期：{compare_start} 至 {compare_end}")

    # 管理层摘要视图：用 3 张卡片快速说明整体情况
    spend_delta_pct, _ = metric_delta(current_summary["spend"], previous_summary["spend"])
    sales_delta_pct, _ = metric_delta(current_summary["sales"], previous_summary["sales"])
    acos_delta_pct, _ = metric_delta(current_summary["acos"], previous_summary["acos"])
    warn_count = len(alert_table)
    diag_count = len(diagnosis_table)
    with st.container():
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(
                f"""
                <div class="summary-card">
                  <div class="summary-label">整体销售</div>
                  <div class="summary-main">{current_summary['sales']:,.0f}</div>
                  <div class="summary-sub">{'↑' if sales_delta_pct >= 0 else '↓'}{abs(sales_delta_pct):.1%} 对比上期</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with c2:
            st.markdown(
                f"""
                <div class="summary-card">
                  <div class="summary-label">广告效率（ACOS / TACoAS）</div>
                  <div class="summary-main">{current_summary['acos']:.1%} / {current_summary['acoas']:.1%}</div>
                  <div class="summary-sub">{'↑' if acos_delta_pct >= 0 else '↓'}{abs(acos_delta_pct):.1%} ACOS 变化，对比上期</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with c3:
            st.markdown(
                f"""
                <div class="summary-card">
                  <div class="summary-label">当前告警</div>
                  <div class="summary-main">{warn_count + diag_count}</div>
                  <div class="summary-sub">产品预警 {warn_count} 个 · 广告诊断 {diag_count} 个</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    kpi_cols = st.columns(7)
    for column, metric, title in zip(
        kpi_cols,
        ["spend", "sales", "orders", "acos", "acoas", "cvr", "ctr"],
        ["花费", "销售额", "订单数", "ACOS", "TACoAS", "CVR", "CTR"],
    ):
        with column:
            render_kpi_card(metric, title, current_summary[metric], previous_summary[metric], compare_start, compare_end)
    # 顶部一键下载全部数据（显眼位置）——放在各表计算后，避免未定义变量引用错误
    dl_col1, dl_col2 = st.columns([9, 1])
    with dl_col2:
        st.download_button(
            "⬇ 一键下载全部数据",
            export_all_data(
                all_data,
                line_table,
                product_table,
                ad_table,
                diagnosis_table,
                parent_metrics(filtered),
                add_metric_growth(parent_metrics(filtered), previous, ["product_line", "parent_asin", "brand"]),
            ),
            "amazon_all_data.xlsx",
        )

    tabs = st.tabs(["产品线分析", "产品表现", "广告表现", "库存预警", "评分口碑", "导出/字段"])

    with tabs[0]:
        module_df = apply_module_filters(filtered, "line", start_date, end_date)
        if module_df.empty:
            st.warning("当前模块筛选下产品线数据为空。")
        else:
            # 以模块时间范围为准计算环比/同比，只针对当前模块选中的产品线/品牌
            module_start, module_end = module_df["date"].min(), module_df["date"].max()
            module_lines = module_df["product_line"].dropna().unique()
            module_scope = comparison_scope[comparison_scope["product_line"].isin(module_lines)]
            module_prev = previous_period(module_scope, module_start, module_end)
            # 去年同期用于同比
            try:
                prev_year_start = module_start - timedelta(days=365)
                prev_year_end = module_end - timedelta(days=365)
                module_prev_year = module_scope[
                    (module_scope["date"] >= prev_year_start) & (module_scope["date"] <= prev_year_end)
                ]
            except Exception:
                module_prev_year = None

            metrics_line = ["sales", "spend", "orders", "ctr", "cvr", "acos", "acoas", "cpc"]

            # 新增：产品线整体汇总表现（不拆父ASIN）
            with st.container(border=True):
                title_col, _ = st.columns([5, 1])
                with title_col:
                    st.markdown('<div class="section-header"><div><div class="module-badge">产品线概览</div><div class="section-title">各产品线整体表现</div></div></div>', unsafe_allow_html=True)
                line_overall_raw = aggregate_metrics(module_df, ["product_line"])
                line_overall = attach_metric_changes(
                    line_overall_raw,
                    module_prev,
                    module_prev_year,
                    ["product_line"],
                    metrics_line,
                )

                # 日预算目标（只在下面大表里编辑）
                budget_targets = load_budget_targets()
                st.caption("提示：你可以在下方大表里直接编辑“日预算目标/已调整”。云端部署时该值默认仅本次会话有效。")
                b1, b2, _b3 = st.columns([1, 1, 6])
                with b1:
                    mark_all = st.button("一键全勾选", key="budget_mark_all")
                with b2:
                    clear_all = st.button("一键清除勾选", key="budget_clear_all")

                if mark_all or clear_all:
                    # 先更新保存，再重跑刷新表格
                    for pl in line_overall["product_line"].astype(str).tolist():
                        record = budget_targets.get(pl, {"target": 0.0, "checked": False})
                        record = _budget_record(record)
                        record["checked"] = True if mark_all else False
                        budget_targets[pl] = record
                    save_budget_targets(budget_targets)
                    rerun_app()

                # 合并到产品线总表：日预算目标 + 日均花费（当前周期）+ 差值（实际-目标）
                module_days = max((module_end - module_start).days + 1, 1)
                line_overall["日预算目标"] = (
                    line_overall["product_line"].astype(str).map(lambda k: budget_targets.get(str(k), {}).get("target", 0.0)).fillna(0.0)
                )
                line_overall["已调整"] = (
                    line_overall["product_line"].astype(str).map(lambda k: bool(budget_targets.get(str(k), {}).get("checked", False))).fillna(False)
                )
                line_overall["日均花费"] = safe_divide(line_overall["spend"], pd.Series(module_days, index=line_overall.index))
                line_overall["差值"] = line_overall["日均花费"] - line_overall["日预算目标"]

                overall_cols = selectable_columns(line_overall, "line_overall", ["product_line", "日预算目标", "已调整", "日均花费", "差值"])
                sorted_overall = line_overall.sort_values("sales", ascending=False)
                st.markdown(f"<div style='margin-bottom:10px;font-weight:700;color:#0f172a'>{summarize_product_lines(line_overall)}</div>", unsafe_allow_html=True)

                mode_label_line = st.radio("数值下方显示（产品线）", ["关闭", "环比", "同比"], horizontal=True, key="line_delta_mode")
                mode_map = {"关闭": "off", "环比": "rb", "同比": "yoy"}
                ratio_mode_line = mode_map[mode_label_line]

                # 列顺序：产品线、日预算目标、日均花费、其余指标
                grid_cols_line = [c for c in overall_cols if c in sorted_overall.columns] + [
                    m for m in metrics_line if m in sorted_overall.columns and m not in overall_cols
                ]
                display_overall = sorted_overall[grid_cols_line].copy()

                def _fmt_val(metric: str, value: Any) -> str:
                    if pd.isna(value):
                        return ""
                    if metric in {"sales", "spend"}:
                        return f"{value:,.2f}"
                    if metric in {"orders"}:
                        return f"{value:,.0f}"
                    if metric in {"ctr", "cvr", "acos", "acoas"}:
                        return f"{value:.2%}"
                    if metric == "cpc":
                        return f"{value:,.2f}"
                    return str(value)

                def _fmt_delta(delta: float) -> str:
                    if pd.isna(delta) or delta == 0:
                        return ""
                    arrow = "↑" if delta >= 0 else "↓"
                    return f"{arrow}{abs(delta)*100:.1f}%"

                for metric in metrics_line:
                    if metric not in display_overall.columns:
                        continue
                    base = sorted_overall[metric]
                    if ratio_mode_line == "rb":
                        delta_series = sorted_overall.get(f"{metric}_rb")
                    elif ratio_mode_line == "yoy":
                        delta_series = sorted_overall.get(f"{metric}_yoy")
                    else:
                        delta_series = None

                    texts: list[str] = []
                    for idx in base.index:
                        v_text = _fmt_val(metric, base.loc[idx])
                        d_text = ""
                        if delta_series is not None:
                            d = delta_series.loc[idx]
                            d_text = _fmt_delta(d)
                        if ratio_mode_line == "off" or not d_text:
                            texts.append(v_text)
                        else:
                            texts.append(f"{v_text} ({d_text})")
                    display_overall[metric] = texts

                # 日均花费显示为金额（不做环比/同比文本拼接）
                if "日均花费" in display_overall.columns:
                    display_overall["日均花费"] = display_overall["日均花费"].apply(lambda v: f"{float(v):,.2f}" if pd.notna(v) else "")

                # 差值：实际（日均花费）-目标（日预算目标），带方向箭头
                if "差值" in display_overall.columns:
                    def _fmt_diff(v: Any) -> str:
                        try:
                            num = float(v)
                        except Exception:
                            return ""
                        if num == 0:
                            return "0.00"
                        arrow = "↑" if num > 0 else "↓"
                        return f"{num:,.2f} {arrow}"

                    display_overall["差值"] = display_overall["差值"].apply(_fmt_diff)

                gb_overall = GridOptionsBuilder.from_dataframe(display_overall)
                gb_overall.configure_default_column(
                    resizable=True,
                    filter=True,
                    sortable=True,
                    wrapText=False,
                    autoHeight=False,
                    editable=False,
                )
                if "日预算目标" in display_overall.columns:
                    gb_overall.configure_column("日预算目标", editable=True, type=["numericColumn"])
                if "已调整" in display_overall.columns:
                    gb_overall.configure_column(
                        "已调整",
                        editable=True,
                        width=110,
                        cellRenderer="agCheckboxCellRenderer",
                        cellEditor="agCheckboxCellEditor",
                    )
                grid_options_overall = gb_overall.build()
                grid_resp = AgGrid(
                    display_overall,
                    gridOptions=grid_options_overall,
                    fit_columns_on_grid_load=True,
                    enable_enterprise_modules=False,
                    theme="balham",
                    update_mode=GridUpdateMode.VALUE_CHANGED,
                    data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
                )

                # 把用户在表格里修改的“日预算目标/已调整”保存下来
                try:
                    updated = grid_resp.get("data")
                except Exception:
                    updated = None
                if updated is not None:
                    if isinstance(updated, pd.DataFrame):
                        updated_df = updated
                    else:
                        updated_df = pd.DataFrame(updated)
                    if not updated_df.empty and "product_line" in updated_df.columns:
                        new_targets: dict[str, dict[str, Any]] = dict(budget_targets)
                        for _, row in updated_df.iterrows():
                            pl = str(row.get("product_line", "")).strip()
                            if not pl:
                                continue
                            target = float(row.get("日预算目标", 0.0) or 0.0) if "日预算目标" in updated_df.columns else 0.0
                            checked = bool(row.get("已调整", False)) if "已调整" in updated_df.columns else False
                            new_targets[pl] = {"target": target, "checked": checked}
                        if new_targets != budget_targets:
                            save_budget_targets(new_targets)
                            budget_targets = new_targets

            with st.container(border=True):
                title_col, action_col = st.columns([5, 1])
                with title_col:
                    st.markdown('<div class="section-header"><div><div class="module-badge">产品线分析</div><div class="section-title">产品线 × 父 ASIN 表现</div></div></div>', unsafe_allow_html=True)
                line_view_raw = aggregate_metrics(module_df, ["product_line", "parent_asin"])
                line_view = attach_metric_changes(
                    line_view_raw,
                    module_prev,
                    module_prev_year,
                    ["product_line", "parent_asin"],
                    metrics_line,
                )
                with action_col:
                    table_download(format_metric_table(line_view), "产品线分析.xlsx", "⬇ 下载")
                st.markdown('<div class="section-caption">默认展示关键字段：销售、花费、订单、CTR/CVR/ACOS/TACoAS 和环比。</div>', unsafe_allow_html=True)
                st.markdown(f"<div style='margin-bottom:10px;font-weight:700;color:#0f172a'>{overview_line(line_view)}</div>", unsafe_allow_html=True)
                selected_cols = selectable_columns(line_view, "line", ["product_line", "parent_asin"])
                sorted_line = line_view.sort_values("sales", ascending=False)
                grid_cols_line_detail = list(dict.fromkeys(selected_cols + metrics_line))
                display_line = sorted_line[grid_cols_line_detail].copy()

                for metric in metrics_line:
                    if metric not in display_line.columns:
                        continue
                    base = sorted_line[metric]
                    if ratio_mode_line == "rb":
                        delta_series = sorted_line.get(f"{metric}_rb")
                    elif ratio_mode_line == "yoy":
                        delta_series = sorted_line.get(f"{metric}_yoy")
                    else:
                        delta_series = None

                    texts: list[str] = []
                    for idx in base.index:
                        v_text = _fmt_val(metric, base.loc[idx])
                        d_text = ""
                        if delta_series is not None:
                            d = delta_series.loc[idx]
                            d_text = _fmt_delta(d)
                        if ratio_mode_line == "off" or not d_text:
                            texts.append(v_text)
                        else:
                            texts.append(f"{v_text} ({d_text})")
                    display_line[metric] = texts

                gb_line = GridOptionsBuilder.from_dataframe(display_line)
                gb_line.configure_default_column(resizable=True, filter=True, sortable=True, wrapText=False, autoHeight=False)
                grid_options_line = gb_line.build()
                AgGrid(
                    display_line,
                    gridOptions=grid_options_line,
                    fit_columns_on_grid_load=True,
                    enable_enterprise_modules=False,
                    theme="balham",
                )
                chart_metric = st.selectbox("趋势指标", ["sales", "spend", "orders", "acos", "acoas", "cvr", "ctr"], format_func=lambda x: DISPLAY_NAMES.get(x, x))
                daily_line = aggregate_metrics(module_df, ["date", "product_line"])
                chart_col1, chart_col2 = st.columns([2, 1])
                with chart_col1:
                    st.plotly_chart(px.line(daily_line, x="date", y=chart_metric, color="product_line", markers=True, title=f"{DISPLAY_NAMES.get(chart_metric, chart_metric)} 趋势"), use_container_width=True)
                with chart_col2:
                    line_pie = aggregate_metrics(module_df, ["product_line"])
                    st.plotly_chart(px.pie(line_pie, names="product_line", values="sales", title="产品线销售占比"), use_container_width=True)

    with tabs[1]:
        module_df = apply_module_filters(filtered, "product", start_date, end_date)
        if module_df.empty:
            st.warning("当前模块筛选下产品数据为空。")
            return
        module_start, module_end = module_df["date"].min(), module_df["date"].max()
        module_days = max((module_end - module_start).days + 1, 1)
        module_lines = module_df["product_line"].dropna().unique()
        module_scope = comparison_scope[comparison_scope["product_line"].isin(module_lines)]
        module_prev = previous_period(module_scope, module_start, module_end)
        # 同比：去年同期
        module_prev_year = None
        try:
            prev_year_start = module_start - timedelta(days=365)
            prev_year_end = module_end - timedelta(days=365)
            module_prev_year = module_scope[
                (module_scope["date"] >= prev_year_start) & (module_scope["date"] <= prev_year_end)
            ]
        except Exception:
            module_prev_year = None
        # 父 ASIN 维度产品表现（主表）
        product_view = parent_metrics(module_df)
        metrics_for_change = ["sales", "spend", "orders", "ctr", "cvr", "acos", "acoas", "cpc"]
        product_view = attach_metric_changes(
            product_view,
            module_prev,
            module_prev_year,
            ["product_line", "parent_asin", "brand"],
            metrics_for_change,
        )
        product_view["标签"] = product_view.apply(lambda row: product_tags(row, thresholds), axis=1)

        # 子 ASIN 维度产品表现（新增表）
        child_view = child_metrics(module_df)
        child_view = attach_metric_changes(
            child_view,
            module_prev,
            module_prev_year,
            ["product_line", "parent_asin", "child_asin", "brand"],
            metrics_for_change,
        )

        # 预算/勾选：父 ASIN（按 product_line+parent_asin+brand 保存）
        parent_store = load_budget_store(PARENT_BUDGET_FILE, "_budget_targets_parent")
        parent_key = (
            product_view["product_line"].astype(str)
            + "||"
            + product_view["parent_asin"].astype(str)
            + "||"
            + product_view["brand"].astype(str)
        )
        product_view["_budget_key"] = parent_key
        product_view["日预算目标"] = product_view["_budget_key"].map(lambda k: float(parent_store.get(str(k), {}).get("target", 0.0))).fillna(0.0)
        product_view["已调整"] = product_view["_budget_key"].map(lambda k: bool(parent_store.get(str(k), {}).get("checked", False))).fillna(False)
        product_view["日均花费"] = safe_divide(product_view["spend"], pd.Series(module_days, index=product_view.index))
        product_view["差值"] = product_view["日均花费"] - product_view["日预算目标"]

        # 预算/勾选：子 ASIN（按 product_line+parent_asin+child_asin+brand 保存）
        child_store = load_budget_store(CHILD_BUDGET_FILE, "_budget_targets_child")
        child_key = (
            child_view["product_line"].astype(str)
            + "||"
            + child_view["parent_asin"].astype(str)
            + "||"
            + child_view["child_asin"].astype(str)
            + "||"
            + child_view["brand"].astype(str)
        )
        child_view["_budget_key"] = child_key
        child_view["日预算目标"] = child_view["_budget_key"].map(lambda k: float(child_store.get(str(k), {}).get("target", 0.0))).fillna(0.0)
        child_view["已调整"] = child_view["_budget_key"].map(lambda k: bool(child_store.get(str(k), {}).get("checked", False))).fillna(False)
        child_view["日均花费"] = safe_divide(child_view["spend"], pd.Series(module_days, index=child_view.index))
        child_view["差值"] = child_view["日均花费"] - child_view["日预算目标"]
        # 自定义规则：用户可定义“表现好/差”规则（最多3条，All 条件 AND）
        with st.expander("自定义表现规则（可选）", expanded=False):
            st.write("你可以动态添加/删除规则，规则间为 AND 关系。支持保存为模板并快速加载。")
            # init session state lists
            if "bad_rules" not in st.session_state:
                st.session_state["bad_rules"] = []
            if "good_rules" not in st.session_state:
                st.session_state["good_rules"] = []

            templates = load_rule_templates()
            template_names = list(templates.keys())
            tcol1, tcol2 = st.columns([3, 1])
            with tcol1:
                temp_name = st.text_input("模板名称（保存/加载）", key="template_name")
            with tcol2:
                if st.button("保存模板"):
                    save_rule_template(temp_name or "template", {"bad": st.session_state["bad_rules"], "good": st.session_state["good_rules"]})
                    st.success("已保存模板")
            if template_names:
                sel = st.selectbox("加载模板", ["(不加载)"] + template_names, key="load_template")
                if sel != "(不加载)":
                    data = templates.get(sel, {})
                    st.session_state["bad_rules"] = data.get("bad", [])
                    st.session_state["good_rules"] = data.get("good", [])

            st.markdown("### 表现差 规则（AND）")
            for idx, rule in enumerate(st.session_state["bad_rules"]):
                c1, c2, c3, c4 = st.columns([2, 1, 1, 0.6])
                with c1:
                    metric = st.selectbox(f"差-指标{idx}", ["sales", "spend", "orders", "sessions", "cvr", "acos", "acoas", "cpc"], index=["sales", "spend", "orders", "sessions", "cvr", "acos", "acoas", "cpc"].index(rule.get("metric", "sales")), key=f"bad_m_{idx}")
                with c2:
                    op = st.selectbox(f"差-操作{idx}", ["<", "<=", ">", ">="], index=["<", "<=", ">", ">="].index(rule.get("op", "<")), key=f"bad_op_{idx}")
                with c3:
                    val = st.number_input(f"差-数值{idx}", value=float(rule.get("value", 0.0)), key=f"bad_v_{idx}")
                with c4:
                    if st.button("删除", key=f"bad_del_{idx}"):
                        st.session_state["bad_rules"].pop(idx)
                        rerun_app()
                st.session_state["bad_rules"][idx] = {"metric": metric, "op": op, "value": val}
            if st.button("新增‘表现差’规则"):
                st.session_state["bad_rules"].append({"metric": "sales", "op": "<", "value": 0.0})

            st.markdown("### 表现好 规则（AND）")
            for idx, rule in enumerate(st.session_state["good_rules"]):
                c1, c2, c3, c4 = st.columns([2, 1, 1, 0.6])
                with c1:
                    metric = st.selectbox(f"好-指标{idx}", ["sales", "spend", "orders", "sessions", "cvr", "acos", "acoas", "cpc"], index=["sales", "spend", "orders", "sessions", "cvr", "acos", "acoas", "cpc"].index(rule.get("metric", "sales")), key=f"good_m_{idx}")
                with c2:
                    op = st.selectbox(f"好-操作{idx}", ["<", "<=", ">", ">="], index=["<", "<=", ">", ">="].index(rule.get("op", "<")), key=f"good_op_{idx}")
                with c3:
                    val = st.number_input(f"好-数值{idx}", value=float(rule.get("value", 0.0)), key=f"good_v_{idx}")
                with c4:
                    if st.button("删除", key=f"good_del_{idx}"):
                        st.session_state["good_rules"].pop(idx)
                        rerun_app()
                st.session_state["good_rules"][idx] = {"metric": metric, "op": op, "value": val}
            if st.button("新增‘表现好’规则"):
                st.session_state["good_rules"].append({"metric": "sales", "op": ">", "value": 0.0})
        # 计算自定义规则匹配（如全部为0则忽略）
        bad_rules_use = st.session_state.get("bad_rules", [])
        good_rules_use = st.session_state.get("good_rules", [])
        bad_mask_custom = evaluate_rules(product_view, [r for r in bad_rules_use if r.get("value") not in (0, None)])
        good_mask_custom = evaluate_rules(product_view, [r for r in good_rules_use if r.get("value") not in (0, None)])
        bad_mask = (
            (product_view["acos"] > thresholds["high_acos"])
            | (product_view["acoas"] > thresholds["high_acoas"])
            | ((product_view["cvr"] < thresholds["low_cvr"]) & (product_view["clicks"] > 0))
        )
        good_mask = product_view["标签"].str.contains("潜力款|正常", regex=True, na=False) & ~bad_mask
        with st.container(border=True):
            title_col, action_col = st.columns([5, 1])
            with title_col:
                st.markdown('<div class="section-header"><div><div class="module-badge">总览</div><div class="section-title">父 ASIN 产品表现</div></div></div>', unsafe_allow_html=True)
            with action_col:
                table_download(format_metric_table(product_view), "产品表现总览.xlsx", "⬇ 下载")
            st.markdown('<div class="section-caption">曝光 → 点击 → Session → 转化，默认只保留核心决策字段。</div>', unsafe_allow_html=True)
            st.markdown(f"<div style='margin-bottom:10px;font-weight:700;color:#0f172a'>{summarize_products(product_view, good_mask, bad_mask)}</div>", unsafe_allow_html=True)
            p1, p2, _p3 = st.columns([1, 1, 6])
            with p1:
                mark_all_parent = st.button("一键全勾选（父ASIN）", key="parent_mark_all")
            with p2:
                clear_all_parent = st.button("一键清除勾选（父ASIN）", key="parent_clear_all")
            if mark_all_parent or clear_all_parent:
                new_parent_store = dict(parent_store)
                for k in product_view["_budget_key"].astype(str).tolist():
                    record = _budget_record(new_parent_store.get(k, {"target": 0.0, "checked": False}))
                    record["checked"] = True if mark_all_parent else False
                    new_parent_store[k] = record
                save_budget_store(PARENT_BUDGET_FILE, "_budget_targets_parent", new_parent_store)
                rerun_app()
            # 排序与列选择
            sort_by = st.selectbox("排序方式", ["sales", "orders", "acos", "acoas", "cvr"], format_func=lambda x: DISPLAY_NAMES.get(x, x))
            ascending = sort_by in {"acos", "acoas"}
            selected_cols = selectable_columns(
                product_view,
                "product_all",
                ["标签", "已调整", "product_line", "parent_asin", "sku", "brand", "日预算目标", "日均花费", "差值"],
            )
            sorted_product = product_view.sort_values(sort_by, ascending=ascending).head(200)

            # 选择显示模式：关闭 / 环比 / 同比
            mode_label = st.radio("数值下方显示", ["关闭", "环比", "同比"], horizontal=True, key="product_delta_mode")
            mode_map = {"关闭": "off", "环比": "rb", "同比": "yoy"}
            ratio_mode = mode_map[mode_label]

            # 为 AgGrid 准备数据：当前值和环比/同比合成一段文本，横向展示（数值后面括号）
            grid_cols = list(dict.fromkeys(selected_cols + metrics_for_change))
            display_df = sorted_product[grid_cols].copy()

            def fmt_value(metric: str, value: Any) -> str:
                if pd.isna(value):
                    return ""
                if metric in {"sales", "spend"}:
                    return f"{value:,.2f}"
                if metric in {"orders", "sessions", "impressions", "clicks"}:
                    return f"{value:,.0f}"
                if metric in {"ctr", "cvr", "acos", "acoas"}:
                    return f"{value:.2%}"
                if metric == "cpc":
                    return f"{value:,.2f}"
                return str(value)

            def fmt_delta(delta: float) -> str:
                if pd.isna(delta) or delta == 0:
                    return ""
                arrow = "↑" if delta >= 0 else "↓"
                return f"{arrow}{abs(delta)*100:.1f}%"

            for metric in metrics_for_change:
                if metric not in display_df.columns:
                    continue
                base = sorted_product[metric]
                if ratio_mode == "rb":
                    delta_series = sorted_product.get(f"{metric}_rb")
                elif ratio_mode == "yoy":
                    delta_series = sorted_product.get(f"{metric}_yoy")
                else:
                    delta_series = None

                texts: list[str] = []
                for idx in base.index:
                    v_text = fmt_value(metric, base.loc[idx])
                    if delta_series is not None:
                        d = delta_series.loc[idx]
                        d_text = fmt_delta(d)
                    else:
                        d_text = ""
                    if ratio_mode == "off" or not d_text:
                        texts.append(v_text)
                    else:
                        # 数值后面括号展示变化（横向），保持一行，便于阅读
                        texts.append(f"{v_text}  ({d_text})")
                display_df[metric] = texts

            # 日均花费：金额显示
            if "日均花费" in display_df.columns:
                display_df["日均花费"] = display_df["日均花费"].apply(lambda v: f"{float(v):,.2f}" if pd.notna(v) else "")

            # 差值：带箭头
            if "差值" in display_df.columns:
                def _fmt_diff_parent(v: Any) -> str:
                    try:
                        num = float(v)
                    except Exception:
                        return ""
                    if num == 0:
                        return "0.00"
                    arrow = "↑" if num > 0 else "↓"
                    return f"{num:,.2f} {arrow}"

                display_df["差值"] = display_df["差值"].apply(_fmt_diff_parent)

            gb = GridOptionsBuilder.from_dataframe(display_df)
            gb.configure_default_column(resizable=True, filter=True, sortable=True, wrapText=False, autoHeight=False, editable=False)
            if "日预算目标" in display_df.columns:
                gb.configure_column("日预算目标", editable=True, type=["numericColumn"])
            if "已调整" in display_df.columns:
                gb.configure_column(
                    "已调整",
                    editable=True,
                    width=120,
                    cellRenderer="agCheckboxCellRenderer",
                    cellEditor="agCheckboxCellEditor",
                )
            grid_options = gb.build()

            resp_parent = AgGrid(
                display_df,
                gridOptions=grid_options,
                fit_columns_on_grid_load=True,
                enable_enterprise_modules=False,
                theme="balham",
                update_mode=GridUpdateMode.VALUE_CHANGED,
                data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
            )
            # 保存表内编辑的预算目标/勾选
            updated = resp_parent.get("data") if isinstance(resp_parent, dict) else None
            if updated is not None:
                upd_df = updated if isinstance(updated, pd.DataFrame) else pd.DataFrame(updated)
                if not upd_df.empty and "_budget_key" in upd_df.columns:
                    new_parent_store = dict(parent_store)
                    for _, row in upd_df.iterrows():
                        k = str(row.get("_budget_key", "")).strip()
                        if not k:
                            continue
                        target = float(row.get("日预算目标", 0.0) or 0.0) if "日预算目标" in upd_df.columns else 0.0
                        checked = bool(row.get("已调整", False)) if "已调整" in upd_df.columns else False
                        new_parent_store[k] = {"target": target, "checked": checked}
                    if new_parent_store != parent_store:
                        save_budget_store(PARENT_BUDGET_FILE, "_budget_targets_parent", new_parent_store)
                        rerun_app()

        # 子 ASIN 产品表现（支持同/环比）
        with st.container(border=True):
            title_col, action_col = st.columns([5, 1])
            with title_col:
                st.markdown('<div class="section-header"><div><div class="module-badge">子 ASIN</div><div class="section-title">子 ASIN 产品表现</div></div></div>', unsafe_allow_html=True)
            with action_col:
                table_download(format_metric_table(child_view), "子ASIN产品表现.xlsx", "⬇ 下载")
            st.markdown(
                '<div class="section-caption">细化到子 ASIN / SKU 维度查看曝光、点击、转化情况，可与父 ASIN 表一起对比。</div>',
                unsafe_allow_html=True,
            )
            c1, c2, _c3 = st.columns([1, 1, 6])
            with c1:
                mark_all_child = st.button("一键全勾选（子ASIN）", key="child_mark_all")
            with c2:
                clear_all_child = st.button("一键清除勾选（子ASIN）", key="child_clear_all")
            if mark_all_child or clear_all_child:
                new_child_store = dict(child_store)
                for k in child_view["_budget_key"].astype(str).tolist():
                    record = _budget_record(new_child_store.get(k, {"target": 0.0, "checked": False}))
                    record["checked"] = True if mark_all_child else False
                    new_child_store[k] = record
                save_budget_store(CHILD_BUDGET_FILE, "_budget_targets_child", new_child_store)
                rerun_app()

            # 排序与列选择
            sort_by_child = st.selectbox(
                "子 ASIN 排序方式",
                ["sales", "orders", "acos", "acoas", "cvr"],
                format_func=lambda x: DISPLAY_NAMES.get(x, x),
                key="child_sort_by",
            )
            ascending_child = sort_by_child in {"acos", "acoas"}
            selected_cols_child = selectable_columns(
                child_view,
                "product_child",
                ["已调整", "product_line", "parent_asin", "child_asin", "brand", "日预算目标", "日均花费", "差值"],
            )
            sorted_child = child_view.sort_values(sort_by_child, ascending=ascending_child).head(300)

            # 子 ASIN 显示模式：关闭 / 环比 / 同比
            mode_label_child = st.radio(
                "子 ASIN 数值下方显示",
                ["关闭", "环比", "同比"],
                horizontal=True,
                key="product_child_delta_mode",
            )
            mode_map_child = {"关闭": "off", "环比": "rb", "同比": "yoy"}
            ratio_mode_child = mode_map_child[mode_label_child]

            grid_cols_child = list(dict.fromkeys(selected_cols_child + metrics_for_change))
            display_child = sorted_child[grid_cols_child].copy()

            def fmt_value_child(metric: str, value: Any) -> str:
                if pd.isna(value):
                    return ""
                if metric in {"sales", "spend"}:
                    return f"{value:,.2f}"
                if metric in {"orders", "sessions", "impressions", "clicks"}:
                    return f"{value:,.0f}"
                if metric in {"ctr", "cvr", "acos", "acoas"}:
                    return f"{value:.2%}"
                if metric == "cpc":
                    return f"{value:,.2f}"
                return str(value)

            def fmt_delta_child(delta: float) -> str:
                if pd.isna(delta) or delta == 0:
                    return ""
                arrow = "↑" if delta >= 0 else "↓"
                return f"{arrow}{abs(delta)*100:.1f}%"

            for metric in metrics_for_change:
                if metric not in display_child.columns:
                    continue
                base = sorted_child[metric]
                if ratio_mode_child == "rb":
                    delta_series = sorted_child.get(f"{metric}_rb")
                elif ratio_mode_child == "yoy":
                    delta_series = sorted_child.get(f"{metric}_yoy")
                else:
                    delta_series = None

                texts: list[str] = []
                for idx in base.index:
                    v_text = fmt_value_child(metric, base.loc[idx])
                    if delta_series is not None:
                        d = delta_series.loc[idx]
                        d_text = fmt_delta_child(d)
                    else:
                        d_text = ""
                    if ratio_mode_child == "off" or not d_text:
                        texts.append(v_text)
                    else:
                        texts.append(f"{v_text}  ({d_text})")
                display_child[metric] = texts

            # 日均花费：金额显示
            if "日均花费" in display_child.columns:
                display_child["日均花费"] = display_child["日均花费"].apply(lambda v: f"{float(v):,.2f}" if pd.notna(v) else "")

            # 差值：带箭头
            if "差值" in display_child.columns:
                def _fmt_diff_child(v: Any) -> str:
                    try:
                        num = float(v)
                    except Exception:
                        return ""
                    if num == 0:
                        return "0.00"
                    arrow = "↑" if num > 0 else "↓"
                    return f"{num:,.2f} {arrow}"

                display_child["差值"] = display_child["差值"].apply(_fmt_diff_child)

            gb_child = GridOptionsBuilder.from_dataframe(display_child)
            gb_child.configure_default_column(
                resizable=True, filter=True, sortable=True, wrapText=False, autoHeight=False, editable=False
            )
            if "日预算目标" in display_child.columns:
                gb_child.configure_column("日预算目标", editable=True, type=["numericColumn"])
            if "已调整" in display_child.columns:
                gb_child.configure_column(
                    "已调整",
                    editable=True,
                    width=120,
                    cellRenderer="agCheckboxCellRenderer",
                    cellEditor="agCheckboxCellEditor",
                )
            grid_options_child = gb_child.build()

            resp_child = AgGrid(
                display_child,
                gridOptions=grid_options_child,
                fit_columns_on_grid_load=True,
                enable_enterprise_modules=False,
                theme="balham",
                update_mode=GridUpdateMode.VALUE_CHANGED,
                data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
            )
            updated = resp_child.get("data") if isinstance(resp_child, dict) else None
            if updated is not None:
                upd_df = updated if isinstance(updated, pd.DataFrame) else pd.DataFrame(updated)
                if not upd_df.empty and "_budget_key" in upd_df.columns:
                    new_child_store = dict(child_store)
                    for _, row in upd_df.iterrows():
                        k = str(row.get("_budget_key", "")).strip()
                        if not k:
                            continue
                        target = float(row.get("日预算目标", 0.0) or 0.0) if "日预算目标" in upd_df.columns else 0.0
                        checked = bool(row.get("已调整", False)) if "已调整" in upd_df.columns else False
                        new_child_store[k] = {"target": target, "checked": checked}
                    if new_child_store != child_store:
                        save_budget_store(CHILD_BUDGET_FILE, "_budget_targets_child", new_child_store)
                        rerun_app()

        good_col, bad_col = st.columns(2)
        with good_col:
            with st.container(border=True):
                title_col, action_col = st.columns([4, 1])
                with title_col:
                    st.markdown('<div class="module-badge">表现好</div><div class="section-title">可继续放量产品</div>', unsafe_allow_html=True)
                mask_good = good_mask_custom if good_mask_custom.any() else good_mask
                good_products = product_view[mask_good].sort_values(["sales", "cvr"], ascending=[False, False]).head(30)
                with action_col:
                    table_download(format_metric_table(good_products), "表现好产品.xlsx", "⬇")
                good_cols = ["标签", "product_line", "parent_asin", "sku", "sales", "orders", "sessions", "cvr", "acos", "acoas", "growth_rate", "compare_value"]
                st.data_editor(format_metric_table(add_optional_growth_column(good_products[[col for col in good_cols if col in good_products.columns]], "good_products")), use_container_width=True, hide_index=True, disabled=True)

        with bad_col:
            with st.container(border=True):
                title_col, action_col = st.columns([4, 1])
                with title_col:
                    st.markdown('<div class="module-badge">表现差</div><div class="section-title">优先优化产品</div>', unsafe_allow_html=True)
                mask_bad = bad_mask_custom if bad_mask_custom.any() else bad_mask
                bad_products = product_view[mask_bad].sort_values(["acoas", "acos"], ascending=False).head(30)
                with action_col:
                    table_download(format_metric_table(bad_products), "表现差产品.xlsx", "⬇")
                bad_cols = ["标签", "product_line", "parent_asin", "sku", "sales", "spend", "clicks", "sessions", "cvr", "acos", "acoas", "growth_rate", "compare_value"]
                st.data_editor(format_metric_table(add_optional_growth_column(bad_products[[col for col in bad_products.columns if col in bad_products.columns]], "bad_products")), use_container_width=True, hide_index=True, disabled=True)

        with st.container(border=True):
            title_col, action_col = st.columns([5, 1])
            with title_col:
                st.markdown('<div class="section-header"><div><div class="module-badge">预警</div><div class="section-title">广告诊断预警</div></div></div>', unsafe_allow_html=True)
            st.markdown('<div class="section-caption">同时从父 ASIN 和子 ASIN 两个维度识别“高风险”和“可放量”，避免父 ASIN 整体好但单个子 ASIN 拖后腿。</div>', unsafe_allow_html=True)
            parent_diag = advertising_diagnosis(module_df, thresholds, "parent")
            child_diag = advertising_diagnosis(module_df, thresholds, "child")
            diag_view = pd.concat([parent_diag, child_diag], ignore_index=True) if not parent_diag.empty or not child_diag.empty else pd.DataFrame()
            with action_col:
                table_download(format_metric_table(diag_view), "产品预警.xlsx", "⬇ 下载")
            parent_high = parent_diag[parent_diag["标签"] == "高风险"] if not parent_diag.empty else pd.DataFrame()
            parent_scale = parent_diag[parent_diag["标签"] == "可放量"] if not parent_diag.empty else pd.DataFrame()
            child_high = child_diag[child_diag["标签"] == "高风险"] if not child_diag.empty else pd.DataFrame()
            child_scale = child_diag[child_diag["标签"] == "可放量"] if not child_diag.empty else pd.DataFrame()

            high_col, scale_col = st.columns(2)
            with high_col:
                render_diagnosis_cards(parent_high, "父 ASIN 高风险", "没有父 ASIN 高风险预警。")
                render_diagnosis_cards(child_high, "子 ASIN 高风险", "没有子 ASIN 高风险预警。")
            with scale_col:
                render_diagnosis_cards(parent_scale, "父 ASIN 可放量", "没有父 ASIN 可放量机会。")
                render_diagnosis_cards(child_scale, "子 ASIN 可放量", "没有子 ASIN 可放量机会。")

    with tabs[2]:
        module_df = apply_module_filters(filtered, "ad", start_date, end_date)
        with st.container(border=True):
            if module_df.empty:
                st.warning("当前模块筛选下广告数据为空。")
                ad_view = pd.DataFrame()
            else:
                module_start, module_end = module_df["date"].min(), module_df["date"].max()
                module_lines = module_df["product_line"].dropna().unique()
                module_scope = comparison_scope[comparison_scope["product_line"].isin(module_lines)]
                module_prev = previous_period(module_scope, module_start, module_end)
                # 去年同期：用于“同比”
                module_prev_year = None
                try:
                    prev_year_start = module_start - timedelta(days=365)
                    prev_year_end = module_end - timedelta(days=365)
                    module_prev_year = module_scope[
                        (module_scope["date"] >= prev_year_start) & (module_scope["date"] <= prev_year_end)
                    ]
                except Exception:
                    module_prev_year = None

                # 产品线 × 广告类型结构（按产品线整体聚合）
                metrics_ad = ["spend", "sales"]
                line_ad_view = ad_wide_summary(module_df, ["product_line"])
                prev_line_ad_view = ad_wide_summary(module_prev, ["product_line"])
                prev_line_year_view = (
                    ad_wide_summary(module_prev_year, ["product_line"])
                    if module_prev_year is not None and not module_prev_year.empty
                    else pd.DataFrame()
                )

                # 计算花费/销售的环比百分比（若上一周期没有数据，则环比显示为 0）
                required_cols_line = {"product_line", "ad_type", *metrics_ad}
                if module_prev.empty or prev_line_ad_view.empty or not required_cols_line.issubset(
                    set(prev_line_ad_view.columns)
                ):
                    for m in metrics_ad:
                        line_ad_view[f"{m}_rb"] = 0.0
                else:
                    prev_key = prev_line_ad_view[["product_line", "ad_type"] + metrics_ad].rename(
                        columns={m: f"{m}_prev" for m in metrics_ad}
                    )
                    line_ad_view = line_ad_view.merge(prev_key, on=["product_line", "ad_type"], how="left")
                    for m in metrics_ad:
                        line_ad_view[f"{m}_prev"] = line_ad_view[f"{m}_prev"].fillna(0)
                        line_ad_view[f"{m}_rb"] = safe_divide(
                            line_ad_view[m] - line_ad_view[f"{m}_prev"], line_ad_view[f"{m}_prev"]
                        )

                # 计算花费/销售的同比百分比（若去年同期没有数据，则同比显示为 0）
                if (
                    module_prev_year is None
                    or module_prev_year.empty
                    or prev_line_year_view.empty
                    or not required_cols_line.issubset(set(prev_line_year_view.columns))
                ):
                    for m in metrics_ad:
                        line_ad_view[f"{m}_yoy"] = 0.0
                else:
                    prev_year_key = prev_line_year_view[["product_line", "ad_type"] + metrics_ad].rename(
                        columns={m: f"{m}_prevy" for m in metrics_ad}
                    )
                    line_ad_view = line_ad_view.merge(prev_year_key, on=["product_line", "ad_type"], how="left")
                    for m in metrics_ad:
                        line_ad_view[f"{m}_prevy"] = line_ad_view[f"{m}_prevy"].fillna(0)
                        line_ad_view[f"{m}_yoy"] = safe_divide(
                            line_ad_view[m] - line_ad_view[f"{m}_prevy"], line_ad_view[f"{m}_prevy"]
                        )

                title_col, _ = st.columns([5, 1])
                with title_col:
                    st.markdown('<div class="section-header"><div><div class="module-badge">产品线广告结构</div><div class="section-title">产品线 × 广告类型结构</div></div></div>', unsafe_allow_html=True)

                # 显示模式：关闭 / 环比 / 同比
                ad_mode_label = st.radio("数值下方显示（广告）", ["关闭", "环比", "同比"], horizontal=True, key="ad_line_delta_mode")
                ad_mode_map = {"关闭": "off", "环比": "rb", "同比": "yoy"}
                ad_ratio_mode = ad_mode_map[ad_mode_label]

                fixed_line_cols = ["product_line", "ad_type"]
                selected_line_cols = selectable_columns(line_ad_view, "ad_line", fixed_line_cols)
                if "spend_share" in line_ad_view and "sales_share" in line_ad_view:
                    selected_line_cols = [*selected_line_cols, *[col for col in ["spend_share", "sales_share"] if col not in selected_line_cols]]

                grid_cols_line_ad = list(dict.fromkeys(selected_line_cols + metrics_ad))
                display_line_ad = line_ad_view[grid_cols_line_ad].sort_values("spend", ascending=False).copy()

                def _fmt_val_ad(metric: str, value: Any) -> str:
                    if pd.isna(value):
                        return ""
                    if metric in {"sales", "spend"}:
                        return f"{value:,.2f}"
                    if metric in {"orders"}:
                        return f"{value:,.0f}"
                    if metric in {"ctr", "cvr", "acos", "acoas"}:
                        return f"{value:.2%}"
                    return str(value)

                def _fmt_delta_ad(delta: float) -> str:
                    if pd.isna(delta) or delta == 0:
                        return ""
                    arrow = "↑" if delta >= 0 else "↓"
                    return f"{arrow}{abs(delta)*100:.1f}%"

                for metric in metrics_ad:
                    if metric not in display_line_ad.columns:
                        continue
                    base = line_ad_view[metric]
                    if ad_ratio_mode == "rb":
                        delta_series = line_ad_view.get(f"{metric}_rb")
                    elif ad_ratio_mode == "yoy":
                        delta_series = line_ad_view.get(f"{metric}_yoy")
                    else:
                        delta_series = None
                    texts: list[str] = []
                    for idx in base.index:
                        v_text = _fmt_val_ad(metric, base.loc[idx])
                        d_text = ""
                        if delta_series is not None:
                            d = delta_series.loc[idx]
                            d_text = _fmt_delta_ad(d)
                        if ad_ratio_mode == "off" or not d_text:
                            texts.append(v_text)
                        else:
                            texts.append(f"{v_text} ({d_text})")
                    display_line_ad[metric] = texts

                gb_line_ad = GridOptionsBuilder.from_dataframe(display_line_ad)
                gb_line_ad.configure_default_column(resizable=True, filter=True, sortable=True, wrapText=False, autoHeight=False)
                grid_options_line_ad = gb_line_ad.build()
                AgGrid(
                    display_line_ad,
                    gridOptions=grid_options_line_ad,
                    fit_columns_on_grid_load=True,
                    enable_enterprise_modules=False,
                    theme="balham",
                )

                # 父ASIN × 广告类型结构
                ad_view = ad_wide_summary(module_df, ["product_line", "parent_asin"])
                prev_ad_view = ad_wide_summary(module_prev, ["product_line", "parent_asin"])
                prev_ad_year_view = (
                    ad_wide_summary(module_prev_year, ["product_line", "parent_asin"])
                    if module_prev_year is not None and not module_prev_year.empty
                    else pd.DataFrame()
                )

                required_cols_parent = {"product_line", "parent_asin", "ad_type", *metrics_ad}
                if module_prev.empty or prev_ad_view.empty or not required_cols_parent.issubset(
                    set(prev_ad_view.columns)
                ):
                    for m in metrics_ad:
                        ad_view[f"{m}_rb"] = 0.0
                else:
                    prev_key_parent = prev_ad_view[["product_line", "parent_asin", "ad_type"] + metrics_ad].rename(
                        columns={m: f"{m}_prev" for m in metrics_ad}
                    )
                    ad_view = ad_view.merge(prev_key_parent, on=["product_line", "parent_asin", "ad_type"], how="left")
                    for m in metrics_ad:
                        ad_view[f"{m}_prev"] = ad_view[f"{m}_prev"].fillna(0)
                        ad_view[f"{m}_rb"] = safe_divide(ad_view[m] - ad_view[f"{m}_prev"], ad_view[f"{m}_prev"])

                # 同比
                if (
                    module_prev_year is None
                    or module_prev_year.empty
                    or prev_ad_year_view.empty
                    or not required_cols_parent.issubset(set(prev_ad_year_view.columns))
                ):
                    for m in metrics_ad:
                        ad_view[f"{m}_yoy"] = 0.0
                else:
                    prev_key_parent_year = prev_ad_year_view[
                        ["product_line", "parent_asin", "ad_type"] + metrics_ad
                    ].rename(columns={m: f"{m}_prevy" for m in metrics_ad})
                    ad_view = ad_view.merge(
                        prev_key_parent_year,
                        on=["product_line", "parent_asin", "ad_type"],
                        how="left",
                    )
                    for m in metrics_ad:
                        ad_view[f"{m}_prevy"] = ad_view[f"{m}_prevy"].fillna(0)
                        ad_view[f"{m}_yoy"] = safe_divide(ad_view[m] - ad_view[f"{m}_prevy"], ad_view[f"{m}_prevy"])

            title_col, action_col = st.columns([5, 1])
            with title_col:
                st.markdown('<div class="section-header"><div><div class="module-badge">广告表现</div><div class="section-title">父 ASIN × 广告类型结构</div></div></div>', unsafe_allow_html=True)
            with action_col:
                table_download(format_metric_table(ad_view), "广告表现.xlsx", "⬇ 下载")
            st.markdown('<div class="section-caption">优先使用 SBV广告费、SP广告费、SB广告费、SD广告费、ST广告费及对应广告销售额/订单量字段计算各广告类型 ACOS。</div>', unsafe_allow_html=True)
            st.markdown(f"<div style='margin-bottom:10px;font-weight:700;color:#0f172a'>{overview_ad(ad_view, prev_ad_view)}</div>", unsafe_allow_html=True)

            # 父 ASIN 表单独提供一个开关，控制是否在数值后面显示环比/同比
            ad_parent_mode_label = st.radio(
                "数值下方显示（父 ASIN 广告）",
                ["关闭", "环比", "同比"],
                horizontal=True,
                key="ad_parent_delta_mode",
            )
            ad_parent_mode_map = {"关闭": "off", "环比": "rb", "同比": "yoy"}
            ad_ratio_mode_parent = ad_parent_mode_map[ad_parent_mode_label]

            fixed_cols = ["product_line", "parent_asin", "ad_type"]
            selected_cols = selectable_columns(ad_view, "ad", fixed_cols)
            if "spend_share" in ad_view and "sales_share" in ad_view:
                selected_cols = [*selected_cols, *[col for col in ["spend_share", "sales_share"] if col not in selected_cols]]
            grid_cols_ad = list(dict.fromkeys(selected_cols + metrics_ad))
            display_ad = ad_view[grid_cols_ad].sort_values("spend", ascending=False).copy()

            for metric in metrics_ad:
                if metric not in display_ad.columns:
                    continue
                base = ad_view[metric]
                if ad_ratio_mode_parent == "rb":
                    delta_series = ad_view.get(f"{metric}_rb")
                elif ad_ratio_mode_parent == "yoy":
                    delta_series = ad_view.get(f"{metric}_yoy")
                else:
                    delta_series = None
                texts: list[str] = []
                for idx in base.index:
                    v_text = _fmt_val_ad(metric, base.loc[idx])
                    d_text = ""
                    if delta_series is not None:
                        d = delta_series.loc[idx]
                        d_text = _fmt_delta_ad(d)
                    if ad_ratio_mode_parent == "off" or not d_text:
                        texts.append(v_text)
                    else:
                        texts.append(f"{v_text} ({d_text})")
                display_ad[metric] = texts

            gb_ad = GridOptionsBuilder.from_dataframe(display_ad)
            gb_ad.configure_default_column(resizable=True, filter=True, sortable=True, wrapText=False, autoHeight=False)
            grid_options_ad = gb_ad.build()
            AgGrid(
                display_ad,
                gridOptions=grid_options_ad,
                fit_columns_on_grid_load=True,
                enable_enterprise_modules=False,
                theme="balham",
            )
            chart1, chart2 = st.columns(2)
            with chart1:
                st.plotly_chart(px.pie(ad_view, names="ad_type", values="spend", title="花费占比"), use_container_width=True)
            with chart2:
                st.plotly_chart(px.pie(ad_view, names="ad_type", values="sales", title="广告销售占比"), use_container_width=True)
            # B2B 占比饼图（优先使用 b2b_sales；若无则使用 b2b_orders）
            b2b_sales = module_df.get("b2b_sales", pd.Series(dtype=float)).sum() if not module_df.empty else 0
            b2b_orders = module_df.get("b2b_orders", pd.Series(dtype=float)).sum() if not module_df.empty else 0
            if b2b_sales > 0:
                other = module_df["sales"].sum() - b2b_sales
                st.plotly_chart(px.pie(pd.DataFrame({"type":["B2B","B2C"], "value":[b2b_sales, max(other,0)]}), names="type", values="value", title="B2B 销售占比"), use_container_width=True)
            elif b2b_orders > 0:
                other = module_df["orders"].sum() - b2b_orders
                st.plotly_chart(px.pie(pd.DataFrame({"type":["B2B","B2C"], "value":[b2b_orders, max(other,0)]}), names="type", values="value", title="B2B 订单占比"), use_container_width=True)
            else:
                st.info("未检测到 B2B 相关字段，无法展示 B2B 占比。")

    with tabs[3]:
        module_df = apply_module_filters(filtered, "inventory", start_date, end_date)
        parent_inventory_table = None  # 供后面“产品线库存状态”图表复用

        # 父 ASIN 维度库存健康度
        with st.container(border=True):
            st.markdown('<div class="section-header"><div><div class="module-badge">库存预警</div><div class="section-title">父 ASIN 库存健康度</div></div></div>', unsafe_allow_html=True)
            if not has_inventory:
                st.info("当前数据没有识别到库存字段，已跳过库存预警模块。系统会自动把表头包含“可售”的字段合并为库存。")
            elif module_df.empty:
                st.warning("当前模块筛选下没有库存数据。")
            else:
                module_start, module_end = module_df["date"].min(), module_df["date"].max()
                module_lines = module_df["product_line"].dropna().unique()
                module_scope = comparison_scope[comparison_scope["product_line"].isin(module_lines)]
                module_prev = previous_period(module_scope, module_start, module_end)
                module_days = max((module_end - module_start).days + 1, 1)
                inventory_table = add_metric_growth(
                    parent_metrics(module_df),
                    module_prev,
                    ["product_line", "parent_asin", "brand"],
                )
                parent_inventory_table = inventory_table
                inventory_table["库存状态"] = inventory_table.apply(lambda row: inventory_status(row, module_days), axis=1)
                inventory_table["预计可售天数"] = inventory_table.apply(
                    lambda row: round(row["inventory"] / (row["orders"] / module_days), 1) if row["orders"] > 0 else 999,
                    axis=1,
                )
                st.markdown(
                    f"<div style='margin-bottom:10px;font-weight:700;color:#0f172a'>{summarize_inventory(inventory_table)}</div>",
                    unsafe_allow_html=True,
                )
                table_download(format_metric_table(inventory_table), "库存预警.xlsx", "⬇ 下载库存表")
                core_cols = [
                    "库存状态",
                    "product_line",
                    "parent_asin",
                    "sku",
                    "brand",
                    "inventory",
                    "orders",
                    "预计可售天数",
                    "growth_rate",
                    "compare_value",
                ]
                st.data_editor(
                    format_metric_table(
                        add_optional_growth_column(
                            inventory_table[[col for col in core_cols if col in inventory_table.columns]].sort_values("预计可售天数"),
                            "inventory",
                        )
                    ),
                    use_container_width=True,
                    hide_index=True,
                    disabled=True,
                )

        # 子 ASIN 维度库存健康度
        with st.container(border=True):
            st.markdown('<div class="section-header"><div><div class="module-badge">库存预警</div><div class="section-title">子 ASIN 库存健康度</div></div></div>', unsafe_allow_html=True)
            if not has_inventory:
                st.info("当前数据没有识别到库存字段，因此无法从子 ASIN 维度分析库存健康度。")
            elif module_df.empty:
                st.warning("当前模块筛选下没有库存数据，无法展示子 ASIN 库存健康度。")
            else:
                module_start, module_end = module_df["date"].min(), module_df["date"].max()
                module_lines = module_df["product_line"].dropna().unique()
                module_scope = comparison_scope[comparison_scope["product_line"].isin(module_lines)]
                module_prev = previous_period(module_scope, module_start, module_end)
                module_days = max((module_end - module_start).days + 1, 1)

                child_inventory_table = add_metric_growth(
                    child_metrics(module_df),
                    module_prev,
                    ["product_line", "parent_asin", "child_asin", "brand"],
                )
                child_inventory_table["库存状态"] = child_inventory_table.apply(
                    lambda row: inventory_status(row, module_days),
                    axis=1,
                )
                child_inventory_table["预计可售天数"] = child_inventory_table.apply(
                    lambda row: round(row["inventory"] / (row["orders"] / module_days), 1) if row["orders"] > 0 else 999,
                    axis=1,
                )
                table_download(
                    format_metric_table(child_inventory_table),
                    "子ASIN库存预警.xlsx",
                    "⬇ 下载子ASIN库存表",
                )
                child_core_cols = [
                    "库存状态",
                    "product_line",
                    "parent_asin",
                    "sku",
                    "brand",
                    "inventory",
                    "orders",
                    "预计可售天数",
                    "growth_rate",
                    "compare_value",
                ]
                st.data_editor(
                    format_metric_table(
                        add_optional_growth_column(
                            child_inventory_table[
                                [col for col in child_core_cols if col in child_inventory_table.columns]
                            ].sort_values("预计可售天数"),
                            "inventory_child",
                        )
                    ),
                    use_container_width=True,
                    hide_index=True,
                    disabled=True,
                )

        # 产品线库存状态图表（放在最下方）
        with st.container(border=True):
            st.markdown('<div class="section-header"><div><div class="module-badge">库存预警</div><div class="section-title">产品线库存状态</div></div></div>', unsafe_allow_html=True)
            if parent_inventory_table is None:
                if not has_inventory:
                    st.info("当前数据没有识别到库存字段，无法展示产品线库存状态。")
                elif module_df.empty:
                    st.warning("当前模块筛选下没有库存数据，无法展示产品线库存状态。")
                else:
                    st.info("暂无可用的库存数据用于绘制产品线库存状态。")
            else:
                st.plotly_chart(
                    px.bar(
                        parent_inventory_table,
                        x="product_line",
                        y="inventory",
                        color="库存状态",
                        title="产品线库存状态",
                    ),
                    use_container_width=True,
                )

    with tabs[4]:
        module_df = apply_module_filters(filtered, "rating", start_date, end_date)
        with st.container(border=True):
            st.markdown('<div class="section-header"><div><div class="module-badge">评分口碑</div><div class="section-title">父 ASIN 评分预警</div></div></div>', unsafe_allow_html=True)
            if not has_rating:
                st.info("当前数据没有识别到评分/评论字段，已跳过评分口碑模块。")
            elif module_df.empty:
                st.warning("当前模块筛选下没有评分数据。")
            else:
                module_start, module_end = module_df["date"].min(), module_df["date"].max()
                module_lines = module_df["product_line"].dropna().unique()
                module_scope = comparison_scope[comparison_scope["product_line"].isin(module_lines)]
                module_prev = previous_period(module_scope, module_start, module_end)
                rating_table = add_metric_growth(parent_metrics(module_df), module_prev, ["product_line", "parent_asin", "brand"])
                rating_table = rating_table[(rating_table["rating"] > 0) | (rating_table["reviews"] > 0)].copy()
                st.markdown(f"<div style='margin-bottom:10px;font-weight:700;color:#0f172a'>{summarize_rating(rating_table)}</div>", unsafe_allow_html=True)
                rating_table["评分状态"] = rating_table["rating"].apply(
                    lambda value: "🔴 严重预警" if 0 < value < 4.0 else ("🟡 中等预警" if 4.0 <= value < 4.2 else "🟢 良好")
                )
                table_download(format_metric_table(rating_table), "评分预警.xlsx", "⬇ 下载评分表")
                core_cols = ["评分状态", "product_line", "parent_asin", "sku", "brand", "rating", "reviews", "sales", "orders", "growth_rate", "compare_value"]
                st.data_editor(format_metric_table(add_optional_growth_column(rating_table[[col for col in core_cols if col in rating_table.columns]].sort_values("rating"), "rating")), use_container_width=True, hide_index=True, disabled=True)
                st.plotly_chart(px.bar(rating_table, x="product_line", y="rating", color="评分状态", title="各产品线评分对比"), use_container_width=True)

    with tabs[5]:
        with st.container(border=True):
            st.markdown('<div class="section-title">导出与字段识别</div>', unsafe_allow_html=True)
            export_tables = {
                "产品线分析": format_metric_table(line_table),
                "产品表现": format_metric_table(product_table),
                "广告表现": format_metric_table(ad_table),
                "产品预警": format_metric_table(alert_table) if not alert_table.empty else pd.DataFrame(),
                "广告诊断": format_metric_table(diagnosis_table) if not diagnosis_table.empty else pd.DataFrame(),
            }
            st.download_button("下载 Excel 分析报告", export_excel(export_tables), "amazon_analysis_report.xlsx")
            st.download_button(
                "下载 PDF 摘要",
                export_pdf(
                    {
                        "时间范围": f"{start_date} 至 {end_date}",
                        "对比周期": f"{compare_start} 至 {compare_end}",
                        "花费": f"{current_summary['spend']:,.2f}",
                        "销售额": f"{current_summary['sales']:,.2f}",
                        "订单数": f"{current_summary['orders']:,.0f}",
                        "广告诊断数": len(diagnosis_table),
                    }
                ),
                "amazon_analysis_summary.pdf",
            )

            if mappings:
                mapping_rows = []
                for index, mapping in enumerate(mappings, start=1):
                    for field, source_column in mapping.items():
                        mapping_rows.append({"文件序号": index, "系统字段": field, "识别到的原始列": source_column})
                st.data_editor(pd.DataFrame(mapping_rows), use_container_width=True, hide_index=True, disabled=True)
            with st.expander("标准化后的前 200 行数据"):
                st.data_editor(filtered.head(200), use_container_width=True, hide_index=True, disabled=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        st.error("页面运行出错，请检查上传文件格式或筛选条件。")
        st.caption(f"错误摘要：{str(exc).splitlines()[0]}")
