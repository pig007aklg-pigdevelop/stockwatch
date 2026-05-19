"""akshare 数据源封装 — 接口变更时 try/except，失败返回 None。"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

from app.services.external_call import API_CALL_TIMEOUT, call_with_timeout
from app.services.ticker import to_akshare_symbol

log = logging.getLogger(__name__)

# akshare stock_individual_fund_flow 仅支持 A 股 sh/sz/bj
_A_SHARE_MARKETS = frozenset({"SH", "SZ"})


@dataclass
class HsgtSnapshot:
    hold_ratio: float | None
    hold_change_5d: float | None


@dataclass
class FundFlowSnapshot:
    net_inflow_5d: float | None
    main_net_pct: float | None


@dataclass
class FundamentalSnapshot:
    roe: float | None
    revenue_growth: float | None
    net_margin: float | None
    roe_trend: float | None
    revenue_trend: float | None
    margin_trend: float | None


def _valid_df(df) -> pd.DataFrame | None:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return None
    return df


def _has_columns(df: pd.DataFrame, *cols: str) -> bool:
    return all(c in df.columns for c in cols)


def _pick_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _first_numeric(row: pd.Series | None, candidates: list[str]) -> float | None:
    if row is None or not isinstance(row, pd.Series):
        return None
    for c in candidates:
        if c in row.index:
            try:
                v = float(row[c])
                if pd.notna(v):
                    return v
            except (TypeError, ValueError):
                continue
    return None


def fetch_hsgt_holdings(market: str, symbol: str) -> HsgtSnapshot | None:
    code = to_akshare_symbol(market, symbol)
    if not code:
        return None

    def _api_call():
        import akshare as ak
        return ak.stock_hsgt_individual_em(symbol=code)

    try:
        df = _valid_df(call_with_timeout(_api_call, API_CALL_TIMEOUT))
        if df is None:
            return None
        row = df.iloc[-1]
        ratio_cols = ["持股占比", "持股比例", "占流通股比例"]
        change_cols = ["持股数量变化", "增持数量", "5日增持", "持股变动"]
        hold_ratio = _first_numeric(row, ratio_cols)
        hold_change = _first_numeric(row, change_cols)
        return HsgtSnapshot(hold_ratio=hold_ratio, hold_change_5d=hold_change)
    except Exception as e:
        log.warning("fetch_hsgt_holdings %s: %s", code, e)
        return None


def fetch_fund_flow(market: str, symbol: str) -> FundFlowSnapshot | None:
    """个股资金流 — 仅 A 股；港股不支持，避免 market='hk' KeyError。"""
    code = to_akshare_symbol(market, symbol)
    if not code:
        return None
    mkt_upper = (market or "").upper()
    if mkt_upper == "HK":
        return None
    if mkt_upper not in _A_SHARE_MARKETS:
        return None

    ak_market = "sh" if mkt_upper == "SH" else "sz"

    def _api_call():
        import akshare as ak
        return ak.stock_individual_fund_flow(stock=code, market=ak_market)

    try:
        df = _valid_df(call_with_timeout(_api_call, API_CALL_TIMEOUT))
        if df is None:
            return None
        tail = df.tail(5)
        inflow_cols = ["主力净流入-净额", "主力净流入", "净流入", "净额"]
        pct_cols = ["主力净流入-净占比", "主力净流入占比", "净占比"]
        net_sum = None
        for c in inflow_cols:
            if c in tail.columns:
                net_sum = float(tail[c].astype(float).sum())
                break
        main_pct = None
        if not tail.empty:
            last = tail.iloc[-1]
            main_pct = _first_numeric(last, pct_cols)
        return FundFlowSnapshot(net_inflow_5d=net_sum, main_net_pct=main_pct)
    except Exception as e:
        log.warning("fetch_fund_flow %s: %s", code, e)
        return None


def fetch_financial_abstract(market: str, symbol: str) -> FundamentalSnapshot | None:
    code = to_akshare_symbol(market, symbol)
    if not code:
        return None

    def _api_call():
        import akshare as ak
        return ak.stock_financial_abstract(symbol=code)

    try:
        df = _valid_df(call_with_timeout(_api_call, API_CALL_TIMEOUT))
        if df is None:
            return None
        roe = _extract_metric_trend(df, ["净资产收益率", "ROE", "roe"])
        rev = _extract_metric_trend(df, ["营业总收入同比增长率", "营业收入同比增长", "营收同比"])
        margin = _extract_metric_trend(df, ["销售净利率", "净利率", "净利润率"])
        if not isinstance(roe, dict) or not isinstance(rev, dict) or not isinstance(margin, dict):
            return None
        return FundamentalSnapshot(
            roe=roe.get("latest"),
            revenue_growth=rev.get("latest"),
            net_margin=margin.get("latest"),
            roe_trend=roe.get("trend"),
            revenue_trend=rev.get("trend"),
            margin_trend=margin.get("trend"),
        )
    except Exception as e:
        log.warning("fetch_financial_abstract %s: %s", code, e)
        return None


def _extract_metric_trend(df: pd.DataFrame, names: list[str]) -> dict:
    try:
        if df is None or df.empty:
            return {"latest": None, "trend": None}
        row = None
        for name in names:
            if "指标" in df.columns:
                m = df[df["指标"].astype(str).str.contains(name, na=False)]
                if not m.empty:
                    row = m.iloc[0]
                    break
            for idx in df.index:
                try:
                    if name in str(idx) or name in str(df.loc[idx].values):
                        row = df.loc[idx]
                        break
                except Exception:
                    continue
            if row is not None:
                break
        if row is None or not isinstance(row, pd.Series):
            return {"latest": None, "trend": None}
        nums = []
        for c in df.columns:
            if c in ("指标", "选项", "报告期"):
                continue
            try:
                v = float(row[c])
                if pd.notna(v):
                    nums.append(v)
            except (TypeError, ValueError):
                continue
        nums = nums[:4]
        latest = nums[0] if nums else None
        trend = None
        if len(nums) >= 2:
            trend = float(nums[0] - nums[-1])
        return {"latest": latest, "trend": trend}
    except Exception as e:
        log.warning("_extract_metric_trend: %s", e)
        return {"latest": None, "trend": None}
