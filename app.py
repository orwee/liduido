import requests
import pandas as pd
import numpy as np
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path
from datetime import datetime
import time
import re
import json

getcontext().prec = 60

# ----------------------------
# CONFIG
# ----------------------------
DATA_CSV = r"C:\Users\Administrator\Desktop\Folder2\Data API\data_hyperevm.csv"
OUT_DIR = Path(r"C:\Users\Administrator\Desktop\Folder2\Consultoría\Gliquid")
OUT_DIR.mkdir(parents=True, exist_ok=True)

AMOUNTS = [0.1, 1, 10, 100, 1000, 10000, 100000]  # amounts to simulate (human-readable)
BASE_ROUTE_URL = "https://api.liqd.ag/v2/route"

PAUSE_BETWEEN_REQS = 0.35  # seconds between requests

# Fee defaults and special protocols
DEFAULT_FEE_BPS = Decimal("7.5")  # base default in bps (7.5 bps -> 0.075%)
SPECIAL_PROTOCOLS = {"HyperSwapV2", "LaminarV3", "HybraFinanceV3", "ProjectX"}

# ----------------------------
# UTILITIES
# ----------------------------
def parse_pct_str_to_fraction(s):
    if s is None:
        return None
    try:
        if isinstance(s, (int, float, Decimal)):
            return Decimal(str(s)) / Decimal(100)
        s2 = str(s).strip()
        if s2.endswith("%"):
            s2 = s2[:-1]
        return Decimal(s2) / Decimal(100)
    except Exception:
        return None

def show_prepared_url(method, url, params):
    sess = requests.Session()
    req = requests.Request(method, url, params=params)
    pre = sess.prepare_request(req)
    print(pre.url)
    return pre.url

def normalize_raw_amount(raw_amt, token_addr=None, decimals_map=None):
    if raw_amt is None:
        return None
    try:
        s = str(raw_amt)
        if "." in s:
            return Decimal(s)
        if len(s) > 18:
            val = Decimal(s)
            return val / (Decimal(10) ** 18)
        return Decimal(s)
    except Exception:
        try:
            return Decimal(str(raw_amt))
        except Exception:
            return None

def call_route(tokenIn, tokenOut, amountIn, multiHop=False, slippage=1.0):
    params = {
        "tokenIn": tokenIn,
        "tokenOut": tokenOut,
        "amountIn": str(amountIn),
        "multiHop": str(bool(multiHop)).lower(),
        "slippage": str(slippage),
    }
    # intentionally DO NOT pass excludeDexes
    print("Consultando URL /v2/route:")
    show_prepared_url('GET', BASE_ROUTE_URL, params)
    r = requests.get(BASE_ROUTE_URL, params=params, timeout=30)
    r.raise_for_status()
    return r.json()

# parse hops_summary text into list of (protocol, amount, priceImpact) tuples
def parse_hops_summary(hops_summary_text):
    """
    Expected hop fragment format examples:
      "ProjectX:0x...->0x...@342.5@0.095795%"
      "Gliquid:0x...->0x...@330@0.181505%"
    Splits by " | " between hops. For each hop:
      - protocol is text before first ':'
      - last '@' part is price impact (may include %)
      - second-to-last '@' part is amount (human readable)
    Returns list of dicts: [{"protocol":..., "amount":..., "price_impact":...}, ...]
    """
    if not hops_summary_text or not isinstance(hops_summary_text, str):
        return []
    hops = [h.strip() for h in hops_summary_text.split(" | ") if h.strip()]
    parsed = []
    for hop in hops:
        try:
            # split by '@' from right
            parts = hop.rsplit("@", 2)  # at most 2 splits -> [prefix, amount, price]
            if len(parts) == 3:
                prefix, amount_part, price_part = parts
            elif len(parts) == 2:
                prefix, amount_part = parts
                price_part = ""
            else:
                prefix = parts[0]
                amount_part = ""
                price_part = ""

            # protocol is before first colon
            if ":" in prefix:
                protocol = prefix.split(":", 1)[0].strip()
            else:
                protocol = prefix.strip()

            amount = amount_part.strip()
            price = price_part.strip()
            parsed.append({
                "protocol": protocol if protocol != "" else None,
                "amount": amount if amount != "" else None,
                "price_impact": price if price != "" else None
            })
        except Exception:
            # fallback: store raw hop
            parsed.append({
                "protocol": None,
                "amount": None,
                "price_impact": None
            })
    return parsed

def detect_fee_bps_from_hop(hop_dict):
    """
    Busca en hop_dict claves comunes de fee y devuelve fee en bps (Decimal) si se detecta,
    o None si no se detecta.
    Heurística:
      - claves que contengan 'bps' se consideran basis points directos
      - si aparece un string con '%' se convierte a fraction y luego a bps
      - si aparece valor <= 1 se considera fraction (x -> x*10000 bps)
      - si aparece valor > 1 se considera bps
    """
    if not isinstance(hop_dict, dict):
        return None
    candidates = [
        "feeBps", "feeBps_original", "poolFeeBps", "fee", "feeBpsAdj",
        "protocolFeeBps", "routerFeeBps", "feePercent", "feePct", "fee_amount_bps"
    ]
    for k in candidates:
        if k in hop_dict and hop_dict.get(k) is not None:
            v = hop_dict.get(k)
            # if it's a string with %:
            try:
                if isinstance(v, str) and "%" in v:
                    frac = parse_pct_str_to_fraction(v)  # fraction like 0.00075
                    if frac is not None:
                        return (frac * Decimal(10000)).quantize(Decimal("0.00000001"))
                # numeric values
                vv = Decimal(str(v))
                # heuristics:
                if vv <= Decimal("1"):
                    # likely fraction (e.g., 0.00075) -> convert to bps
                    return (vv * Decimal(10000)).quantize(Decimal("0.00000001"))
                else:
                    # likely bps already or percent expressed as e.g. 7.5
                    # if >10000 it's suspicious but we'll return it
                    return vv.quantize(Decimal("0.00000001"))
            except Exception:
                continue
    return None

# ----------------------------
# MAIN
# ----------------------------
def main():
    print("Leyendo CSV de tokens:", DATA_CSV)
    df_tokens = pd.read_csv(DATA_CSV, dtype=str)

    needed_cols = ["dex", "pair", "tokenaddress", "quotetokenaddress"]
    missing = set(needed_cols) - set(df_tokens.columns)
    if missing:
        raise RuntimeError(f"El CSV no contiene las columnas necesarias: {missing}")

    df_sel = df_tokens[needed_cols].copy()
    df_gliquid = df_sel[df_sel["dex"].astype(str) == "Gliquid"].copy()
    df_gliquid.drop_duplicates(subset=["pair"], inplace=True)
    df_gliquid.reset_index(drop=True, inplace=True)

    print(f"Pares Gliquid encontrados (únicos): {len(df_gliquid)}")

    out_rows = []
    max_hops_seen = 0

    for _, row_pair in df_gliquid.iterrows():
        pair_name = row_pair["pair"]
        tA = row_pair["tokenaddress"]
        tB = row_pair["quotetokenaddress"]

        for inverse_flag, (tokenA, tokenB) in (("NO", (tA, tB)), ("YES", (tB, tA))):
            print(f"\n=== Pair {pair_name} - inverse={inverse_flag} -> {tokenA} / {tokenB} ===")
            for amt in AMOUNTS:
                time.sleep(PAUSE_BETWEEN_REQS)
                try:
                    resp = call_route(tokenA, tokenB, amt, multiHop=False, slippage=1.0)
                except Exception as e:
                    print(f"  -> Error calling route for {pair_name} {tokenA}/{tokenB} amount={amt}: {e}")
                    out_rows.append({
                        "pair": pair_name,
                        "pair_tokenA": tokenA,
                        "pair_tokenB": tokenB,
                        "inverse": inverse_flag,
                        "amount_requested": amt,
                        "route_index": None,
                        "route_amountIn_hr": None,
                        "route_hops_summary": None,
                        "route_hops_data": None,
                        "total_fee_route": None
                    })
                    continue

                # extract routes from response similarly to earlier code, but only need hops summary and amountIn
                routes = []
                # try top-level "routes"
                if isinstance(resp.get("routes"), list) and resp.get("routes"):
                    for idx, r in enumerate(resp.get("routes")):
                        amountIn_raw = r.get("amountIn") or r.get("rawAmountIn") or r.get("amountInRaw")
                        amountIn_hr = normalize_raw_amount(amountIn_raw)
                        hops = r.get("hops") or r.get("swaps") or r.get("steps")
                        hops_summary = None
                        route_hops_data = []
                        if isinstance(hops, list) and hops:
                            hop_texts = []
                            for h in hops:
                                router = h.get("routerName") or str(h.get("routerIndex") or "")
                                t_in = h.get("tokenIn") or ""
                                t_out = h.get("tokenOut") or ""
                                amt_raw = h.get("amountIn") or h.get("rawAmountIn") or h.get("amountInRaw")
                                amt_hr = normalize_raw_amount(amt_raw)
                                pi = h.get("priceImpact") or h.get("impact") or h.get("priceImpactPct") or ""
                                # detect fee in bps if present
                                fee_bps_detected = detect_fee_bps_from_hop(h)
                                # store structured hop data
                                route_hops_data.append({
                                    "protocol": router,
                                    "token_in": t_in,
                                    "token_out": t_out,
                                    "amount_hr": amt_hr if amt_hr is not None else (normalize_raw_amount(amountIn_raw) if amountIn_raw is not None else None),
                                    "price_impact": pi,
                                    "fee_bps_detected": fee_bps_detected
                                })
                                hop_texts.append(f"{router}:{t_in}->{t_out}@{amt_hr or amt_raw}@{pi}")
                            hops_summary = " | ".join(hop_texts)
                        routes.append({
                            "route_index": idx,
                            "route_amountIn_hr": str(amountIn_hr) if amountIn_hr is not None else None,
                            "route_hops_summary": hops_summary,
                            "route_hops_data": route_hops_data
                        })
                else:
                    # fallback to execution.details.hopSwaps
                    execution = resp.get("execution") or {}
                    details = execution.get("details") or {}
                    hopSwaps = details.get("hopSwaps") or []
                    if isinstance(hopSwaps, list) and hopSwaps:
                        hop_texts = []
                        sum_amount_in_hr = Decimal(0)
                        amount_in_seen = None
                        route_hops_data = []
                        for hop in hopSwaps:
                            if isinstance(hop, list):
                                for swap in hop:
                                    router = swap.get("routerName") or str(swap.get("routerIndex") or "")
                                    t_in = swap.get("tokenIn") or ""
                                    t_out = swap.get("tokenOut") or ""
                                    amt_raw = swap.get("amountIn")
                                    amt_hr = normalize_raw_amount(amt_raw)
                                    pi = swap.get("priceImpact") or ""
                                    fee_bps_detected = detect_fee_bps_from_hop(swap)
                                    route_hops_data.append({
                                        "protocol": router,
                                        "token_in": t_in,
                                        "token_out": t_out,
                                        "amount_hr": amt_hr,
                                        "price_impact": pi,
                                        "fee_bps_detected": fee_bps_detected
                                    })
                                    hop_texts.append(f"{router}:{t_in}->{t_out}@{amt_hr or amt_raw}@{pi}")
                                    if amt_hr is not None:
                                        try:
                                            sum_amount_in_hr += Decimal(str(amt_hr))
                                        except Exception:
                                            pass
                                    if amount_in_seen is None and amt_raw is not None:
                                        amount_in_seen = amt_raw
                        hops_summary = " | ".join(hop_texts) if hop_texts else None
                        routes.append({
                            "route_index": 0,
                            "route_amountIn_hr": str(sum_amount_in_hr) if sum_amount_in_hr != 0 else None,
                            "route_hops_summary": hops_summary,
                            "route_hops_data": route_hops_data
                        })
                    else:
                        # final fallback: use top-level amountOut/averagePriceImpact as single route (no hops)
                        amountIn_hr = None
                        routes.append({
                            "route_index": 0,
                            "route_amountIn_hr": None,
                            "route_hops_summary": None,
                            "route_hops_data": []
                        })

                if not routes:
                    out_rows.append({
                        "pair": pair_name,
                        "pair_tokenA": tokenA,
                        "pair_tokenB": tokenB,
                        "inverse": inverse_flag,
                        "amount_requested": amt,
                        "route_index": None,
                        "route_amountIn_hr": None,
                        "route_hops_summary": None,
                        "route_hops_data": None,
                        "total_fee_route": None
                    })
                    continue

                for r in routes:
                    hops_summary = r.get("route_hops_summary")
                    route_hops_data = r.get("route_hops_data") or []
                    # compute fees per hop using detected fee_bps (or default) and SPECIAL_PROTOCOLS rule
                    total_fee_route = Decimal(0)
                    # build fee-aware parsed_hops for later expansion
                    parsed_with_fees = []
                    for hop in route_hops_data:
                        proto = hop.get("protocol") or None
                        amt_hr = hop.get("amount_hr")
                        # ensure Decimal
                        if amt_hr is None:
                            amt_dec = None
                        else:
                            try:
                                amt_dec = Decimal(str(amt_hr))
                            except Exception:
                                amt_dec = None
                        detected_bps = hop.get("fee_bps_detected")
                        fee_bps_used = None
                        if detected_bps is not None:
                            fee_bps_used = Decimal(str(detected_bps))
                        else:
                            fee_bps_used = DEFAULT_FEE_BPS
                        # apply special protocol rule
                        if proto and proto in SPECIAL_PROTOCOLS:
                            fee_bps_used = (fee_bps_used / Decimal("100")).quantize(Decimal("0.00000001"))
                        # fee fraction
                        fee_frac = (fee_bps_used / Decimal("10000"))
                        # fee amount in token units of this hop's input token
                        if amt_dec is not None:
                            fee_amount = (amt_dec * fee_frac).quantize(Decimal("0.000000000000000001"))
                        else:
                            fee_amount = None
                        if fee_amount is not None:
                            total_fee_route += fee_amount
                        parsed_with_fees.append({
                            "protocol": proto,
                            "amount": str(amt_dec) if amt_dec is not None else None,
                            "price_impact": hop.get("price_impact"),
                            "fee_bps_used": str(fee_bps_used),
                            "fee_amount": str(fee_amount) if fee_amount is not None else None
                        })
                    if len(parsed_with_fees) > max_hops_seen:
                        max_hops_seen = len(parsed_with_fees)

                    out_rows.append({
                        "pair": pair_name,
                        "pair_tokenA": tokenA,
                        "pair_tokenB": tokenB,
                        "inverse": inverse_flag,
                        "amount_requested": amt,
                        "route_index": r.get("route_index"),
                        "route_amountIn_hr": r.get("route_amountIn_hr"),
                        "route_hops_summary": hops_summary,
                        "route_hops_data": json.dumps(parsed_with_fees),
                        "total_fee_route": str(total_fee_route) if total_fee_route != 0 else None
                    })

    # build dataframe
    df_out = pd.DataFrame(out_rows)

    # drop columns we no longer want in final CSV (route_amountOut_hr, route_priceImpact, route_priceImpact_frac)
    for col in ["route_amountOut_hr", "route_priceImpact", "route_priceImpact_frac"]:
        if col in df_out.columns:
            df_out.drop(columns=[col], inplace=True)

    # Now expand route_hops_summary into separate protocol_route_i, amount_route_i, price_impact_route_i
    # Prefer using route_hops_data (JSON with fee fields) if present; otherwise fallback to parse_hops_summary
    hops_parsed_list = []
    for idx, row in df_out.iterrows():
        raw_data = row.get("route_hops_data")
        parsed = []
        if raw_data:
            try:
                parsed = json.loads(raw_data)
            except Exception:
                # fallback to textual parsing
                hs = row.get("route_hops_summary")
                parsed_text = parse_hops_summary(hs) if hs else []
                # convert parsed_text into expected structure with empty fee fields
                parsed = []
                for p in parsed_text:
                    parsed.append({
                        "protocol": p.get("protocol"),
                        "amount": p.get("amount"),
                        "price_impact": p.get("price_impact"),
                        "fee_bps_used": None,
                        "fee_amount": None
                    })
        else:
            hs = row.get("route_hops_summary")
            parsed_text = parse_hops_summary(hs) if hs else []
            parsed = []
            for p in parsed_text:
                parsed.append({
                    "protocol": p.get("protocol"),
                    "amount": p.get("amount"),
                    "price_impact": p.get("price_impact"),
                    "fee_bps_used": None,
                    "fee_amount": None
                })
        hops_parsed_list.append(parsed)

    # Determine max hops across all rows
    max_hops = max((len(x) for x in hops_parsed_list), default=0)

    # For each row, create columns protocol_route_k, amount_route_k, price_impact_route_k, fee_bps_route_k, fee_amount_route_k
    expanded_cols = []
    for k in range(1, max_hops + 1):
        pcol = f"protocol_route_{k}"
        acol = f"amount_route_{k}"
        prcol = f"price_impact_route_{k}"
        fbcol = f"fee_bps_route_{k}"
        fa_col = f"fee_amount_route_{k}"
        expanded_cols += [pcol, acol, prcol, fbcol, fa_col]
        df_out[pcol] = None
        df_out[acol] = None
        df_out[prcol] = None
        df_out[fbcol] = None
        df_out[fa_col] = None

    # populate
    for idx, parsed in enumerate(hops_parsed_list):
        for i, hop in enumerate(parsed, start=1):
            pcol = f"protocol_route_{i}"
            acol = f"amount_route_{i}"
            prcol = f"price_impact_route_{i}"
            fbcol = f"fee_bps_route_{i}"
            fa_col = f"fee_amount_route_{i}"
            df_out.at[idx, pcol] = hop.get("protocol")
            df_out.at[idx, acol] = hop.get("amount")
            df_out.at[idx, prcol] = hop.get("price_impact")
            df_out.at[idx, fbcol] = hop.get("fee_bps_used")
            df_out.at[idx, fa_col] = hop.get("fee_amount")

    # drop original route_hops_summary and route_hops_data column
    for col in ["route_hops_summary", "route_hops_data"]:
        if col in df_out.columns:
            df_out.drop(columns=[col], inplace=True)

    # ensure column order
    base_cols = ["pair", "pair_tokenA", "pair_tokenB", "inverse", "amount_requested", "route_index", "route_amountIn_hr"]
    cols = base_cols + expanded_cols + ["total_fee_route"]
    # include any missing expanded cols if max_hops is 0 (then no expanded cols)
    for c in cols:
        if c not in df_out.columns:
            df_out[c] = None
    df_out = df_out[cols]



    print(df_out)


    def decimal_equal(x, y):
        try:
            dx = Decimal(str(x))
            dy = Decimal(str(y))
            return dx == dy
        except (InvalidOperation, TypeError):
            return False

    mask = df_out.apply(lambda row: decimal_equal(row['amount_requested'], row['route_amountIn_hr']), axis=1)


    df_out = df_out[mask].reset_index(drop=True)


    df_out = df_out.drop(columns=["total_fee_route"])

    print(df_out)


    df_out = df_out.drop(columns=[c for c in df_out.columns if c.endswith("_human")])


    def compute_amount_pct_routes(df, drop_helpers=True):
        if 'amount_requested' not in df.columns:
            raise KeyError("No existe la columna 'amount_requested' en el DataFrame.")

        df['amount_requested_num'] = pd.to_numeric(df['amount_requested'], errors='coerce')

        route_cols = sorted([c for c in df.columns if re.match(r'^amount_route_(\d+)$', c)],
                            key=lambda x: int(re.search(r'(\d+)', x).group(1)))

        for col in route_cols:
            m = re.search(r'(\d+)$', col)
            n = m.group(1)
            pct_col = f'amount_pct_route_{n}'

            df[col + '_num'] = pd.to_numeric(df[col], errors='coerce')

            denom = df['amount_requested_num']
            valid_denom = denom.notna() & (denom != 0)

            pct_raw = pd.Series(np.nan, index=df.index, dtype='float64')
            pct_raw[valid_denom] = df.loc[valid_denom, col + '_num'] / denom[valid_denom]

            pct_div18 = pd.Series(np.nan, index=df.index, dtype='float64')
            pct_div18[valid_denom] = (df.loc[valid_denom, col + '_num'] / 1e18) / denom[valid_denom]

            valid1 = pct_raw.between(0, 10, inclusive='both')
            valid2 = pct_div18.between(0, 10, inclusive='both')

            chosen_pct = pd.Series(np.nan, index=df.index, dtype='float64')
            chosen_pct[valid1] = pct_raw[valid1]
            chosen_pct[~valid1 & valid2] = pct_div18[~valid1 & valid2]
            chosen_pct[~valid1 & ~valid2] = pct_raw[~valid1 & ~valid2]  # fallback (puede ser NaN o muy grande)

            df[pct_col] = chosen_pct

        if drop_helpers:
            helpers = ['amount_requested_num'] + [c for c in df.columns if c.endswith('_num') and re.match(r'^amount_route_(\d+)_num$', c)]
            df.drop(columns=helpers, inplace=True, errors='ignore')

        return df

    df_out = compute_amount_pct_routes(df_out, drop_helpers=True)


    """
    mask1 = df_out['price_impact_route_1'].fillna('').astype(str).str.strip() != "0.000000%"
    mask2_exact = df_out['amount_requested'].eq(df_out['route_amountIn_hr'])
    mask_combined = mask1 & mask2_exact
    df_final = df_out[mask_combined]
    """

    # save CSV
    out_file = OUT_DIR / "Simulations_Gliquid.csv"
    df_out.to_csv(out_file, index=False, encoding="utf-8")
    print("\nCSV guardado en:", out_file)
    return df_out, out_file

if __name__ == "__main__":
    df_res, path = main()
    print("\nTERMINADO.")
