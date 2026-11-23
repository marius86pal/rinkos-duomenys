#!/usr/bin/env python3
"""Kas savaitę surenka akcijų ir ETF rodiklius iš Yahoo Finance (per yfinance)
ir įrašo juos į data/ katalogą. Paleidžia GitHub Actions
(.github/workflows/rinkos-duomenys.yml).

Failai:
  data/uzdarymai.csv  koreguotos dienos uždarymo kainos (~13 mėn.), stulpeliai = tikeriai
  data/santrauka.csv  grąža 1, 3, 6 mėn. ir 1 m., atstumas nuo 100 d. ir 52 sav. aukščiausio
  data/pelnas.csv     EPS konsensusas dabar ir prieš 7, 30, 60, 90 d., analitikų skaičius,
                      forward P/E, paskutinių ir kitų rezultatų datos (tik kandidatams)
  data/meta.json      kada sugeneruota, kiek tikerių, klaidos

Visuma: S&P 500 + akcijos.txt (papildomos akcijos, ADR, ES akcijos Yahoo formatu)
        + etf.txt (ETF – tik kainos). VT visada įtraukiamas kaip lyginamasis.
Grąžos skaičiuojamos prekybos dienomis: 1 mėn. = 21, 3 mėn. = 63, 6 mėn. = 126, 1 m. = 252.
"""
from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent   # failas guli repozitorijos šaknyje
DATA = ROOT / "data"
SP500_CSV = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
BENCH = "VT"
TD = {"1m": 21, "3m": 63, "6m": 126, "1y": 252}
MAX_PELNAS = 250   # kiek kandidatų daugiausia tikrinti pelno prognozėms
PAUZE = 1.2        # sekundės tarp tikerių, kad Yahoo neribotų

klaidos: list[str] = []


def skaityti_sarasa(vardas: str) -> list[str]:
    f = ROOT / vardas
    if not f.exists():
        return []
    out = []
    for line in f.read_text(encoding="utf-8").splitlines():
        s = line.split("#", 1)[0].strip()
        if s:
            out.append(s)
    return out


def sp500() -> list[str]:
    try:
        df = pd.read_csv(SP500_CSV)
        return [str(s).strip().replace(".", "-") for s in df["Symbol"]]
    except Exception as e:  # sąrašo nepavyko gauti – tęsiam su papildomais
        klaidos.append(f"S&P 500 sąrašas: {e}")
        return []


def uzdarymai(tickers: list[str]) -> pd.DataFrame:
    dalys = []
    for i in range(0, len(tickers), 100):
        dalis = tickers[i:i + 100]
        for bandymas in range(3):
            try:
                df = yf.download(dalis, period="13mo", interval="1d", auto_adjust=True,
                                 progress=False, threads=True)
                if df is None or df.empty:
                    raise RuntimeError("tuščias atsakymas")
                close = df["Close"]
                if isinstance(close, pd.Series):
                    close = close.to_frame(dalis[0])
                dalys.append(close)
                break
            except Exception as e:
                klaidos.append(f"kainos nuo {dalis[0]} (bandymas {bandymas + 1}): {e}"[:200])
                time.sleep(30 * (bandymas + 1))
        time.sleep(3)
    if not dalys:
        return pd.DataFrame()
    out = pd.concat(dalys, axis=1)
    out = out.loc[:, ~out.columns.duplicated()]
    idx = pd.to_datetime(out.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    out.index = idx
    return out.sort_index().dropna(how="all")


def santrauka(cl: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for t in cl.columns:
        s = cl[t].dropna()
        if len(s) <= TD["3m"]:
            continue
        last = float(s.iloc[-1])
        r = {"ticker": t, "date": s.index[-1].date().isoformat(), "close": round(last, 4)}
        for k, n in TD.items():
            r[f"ret_{k}"] = round((last / float(s.iloc[-1 - n]) - 1) * 100, 2) if len(s) > n else None
        r["from_100d_high"] = round((last / float(s.iloc[-100:].max()) - 1) * 100, 2)
        r["from_52w_high"] = round((last / float(s.iloc[-252:].max()) - 1) * 100, 2)
        rows.append(r)
    return pd.DataFrame(rows)


def kandidatai(sant: pd.DataFrame, akcijos: set[str], stebimi: list[str]) -> list[str]:
    """Akcijos, kurių 1 ir 3 mėn. grąža teigiama ir didesnė už VT, plius stebimos akcijos."""
    s = sant[sant["ticker"].isin(akcijos)]
    vt = sant[sant["ticker"] == BENCH]
    r1 = max(0.0, float(vt["ret_1m"].iloc[0])) if len(vt) else 0.0
    r3 = max(0.0, float(vt["ret_3m"].iloc[0])) if len(vt) else 0.0
    k = s[(s["ret_1m"] > r1) & (s["ret_3m"] > r3)].sort_values("ret_3m", ascending=False)
    out = list(k["ticker"])[:MAX_PELNAS]
    for t in stebimi:
        if t not in out and t in akcijos:
            out.append(t)
    return out


def _sk(v):
    try:
        return None if v is None or pd.isna(v) else float(v)
    except (TypeError, ValueError):
        return None


def pelnas_vienam(t: str) -> dict:
    r: dict = {"ticker": t}
    tk = yf.Ticker(t)
    try:
        tr = tk.eps_trend
        for per, lab in (("0y", "fy0"), ("+1y", "fy1")):
            if tr is not None and per in tr.index:
                for col, nm in (("current", "now"), ("7daysAgo", "7d"), ("30daysAgo", "30d"),
                                ("60daysAgo", "60d"), ("90daysAgo", "90d")):
                    if col in tr.columns:
                        r[f"{lab}_eps_{nm}"] = _sk(tr.at[per, col])
    except Exception as e:
        r["error"] = f"eps_trend: {e}"[:150]
    try:
        ee = tk.earnings_estimate
        if ee is not None and "0y" in ee.index and "numberOfAnalysts" in ee.columns:
            r["fy0_analysts"] = _sk(ee.at["0y", "numberOfAnalysts"])
    except Exception as e:
        r.setdefault("error", f"earnings_estimate: {e}"[:150])
    try:
        info = tk.info or {}
        for k in ("forwardPE", "trailingPE", "currency", "exchange", "sector", "shortName"):
            r[k] = info.get(k)
    except Exception as e:
        r.setdefault("error", f"info: {e}"[:150])
    try:
        ed = tk.get_earnings_dates(limit=8)
        if ed is not None and len(ed):
            ed = ed.sort_index()
            now = pd.Timestamp.now(tz=ed.index.tz) if ed.index.tz is not None else pd.Timestamp.now()
            past, fut = ed[ed.index <= now], ed[ed.index > now]
            if len(past):
                r["last_earnings"] = past.index[-1].date().isoformat()
                row = past.iloc[-1]
                r["last_eps_estimate"] = _sk(row.get("EPS Estimate"))
                r["last_eps_reported"] = _sk(row.get("Reported EPS"))
                r["last_surprise_pct"] = _sk(row.get("Surprise(%)"))
            if len(fut):
                r["next_earnings"] = fut.index[0].date().isoformat()
    except Exception as e:
        r.setdefault("error", f"earnings_dates: {e}"[:150])
    return r


def pelnas(tickers: list[str]) -> pd.DataFrame:
    rows = []
    for t in tickers:
        r = pelnas_vienam(t)
        if "rate" in str(r.get("error", "")).lower() or "too many" in str(r.get("error", "")).lower():
            time.sleep(60)          # Yahoo apribojo – palaukiam ir bandom dar kartą
            r = pelnas_vienam(t)
        rows.append(r)
        time.sleep(PAUZE)
    return pd.DataFrame(rows)


def main() -> None:
    DATA.mkdir(exist_ok=True)
    akcijos = set(sp500()) | set(skaityti_sarasa("akcijos.txt"))
    etf = set(skaityti_sarasa("etf.txt")) | {BENCH}
    visi = sorted(akcijos | etf)
    print(f"Visuma: {len(akcijos)} akcijų, {len(etf)} ETF", flush=True)

    cl = uzdarymai(visi)
    sant = santrauka(cl) if not cl.empty else pd.DataFrame(columns=["ticker"])
    kand = kandidatai(sant, akcijos, skaityti_sarasa("akcijos.txt")) if len(sant) else []
    print(f"Kainos: {len(sant)}; pelno patikrai: {len(kand)}", flush=True)
    pel = pelnas(kand) if kand else pd.DataFrame(columns=["ticker"])

    if not cl.empty:
        cl.round(4).to_csv(DATA / "uzdarymai.csv", index_label="date")
    sant.to_csv(DATA / "santrauka.csv", index=False)
    pel.to_csv(DATA / "pelnas.csv", index=False)

    vt = sant[sant["ticker"] == BENCH].to_dict("records") if len(sant) else []
    ok = int(pel["fy0_eps_now"].notna().sum()) if "fy0_eps_now" in pel.columns else 0
    meta = {
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "last_price_date": str(cl.index[-1].date()) if not cl.empty else None,
        "source": "Yahoo Finance per yfinance",
        "yfinance": yf.__version__,
        "universe_stocks": len(akcijos),
        "universe_etf": len(etf),
        "priced": int(len(sant)),
        "candidates": len(kand),
        "eps_ok": ok,
        "vt": vt[0] if vt else None,
        "errors": klaidos[:100],
    }
    (DATA / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: meta[k] for k in ("generated_utc", "priced", "candidates", "eps_ok")}), flush=True)


if __name__ == "__main__":
    main()
