#!/usr/bin/env python3
"""Kas savaitę surenka akcijų ir ETF rodiklius iš Yahoo Finance (per yfinance)
ir įrašo juos į data/ katalogą. Paleidžia GitHub Actions
(.github/workflows/rinkos-duomenys.yml).

Failai:
  data/uzdarymai.csv  koreguotos dienos uždarymo kainos (~13 mėn.), stulpeliai = tikeriai
  data/santrauka.csv  grąža 1, 3, 6 mėn. ir 1 m., atstumas nuo 100 d. ir 52 sav. aukščiausio
  data/pelnas.csv     EPS konsensusas dabar ir prieš 7, 30, 60, 90 d., analitikų skaičius,
                      forward P/E, paskutinių ir kitų rezultatų datos (tik kandidatams)
  data/analitikai.csv analitikų reitingai (Strong Buy … Strong Sell dabar, vidutinis reitingas
                      dabar ir prieš 3 mėn.), tikslinės kainos ir potencialas, reitingų ir
                      tikslinių kainų pakėlimai bei sumažinimai per 30 ir 90 d. (tiems patiems
                      kandidatams kaip pelnas.csv)
  data/analitikai_veiksmai.csv  kiekvienas analitiko veiksmas per 90 d.: data, įmonė,
                      reitingas iš → į, tikslinė kaina iš → į
  data/meta.json      kada sugeneruota, kiek tikerių, klaidos
  data/archyvas/uzdarymai_max.csv.gz  koreguotos dienos uždarymo kainos nuo 2000 m. (back testams);
                      perkuriamas pirmą kiekvieno mėnesio paleidimą
  data/archyvas/info.json  archyvo data, laikotarpis, kiekvieno tikerio pirmoji diena

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
ANALITIKU_D = 30   # langas analitikų pokyčiams (pakėlimams ir sumažinimams) skaičiuoti, d.
VEIKSMU_D = 90     # kiek dienų analitikų veiksmų rašyti į analitikai_veiksmai.csv
ARCHYVO_PRADZIA = "2000-01-01"
SEKTORIAI = ["XLK", "XLV", "XLF", "XLI", "XLC", "XLU", "XLE", "XLY", "XLP", "XLB"]  # ROT visuma
LYGINAMIEJI = ["SPY", "EFA", "EEM"]  # ilgesnė istorija nei VT (VT prekiaujamas nuo 2008 m.)
# Tik archyvui (strategijų testams): mažos ir vidutinės bendrovės, obligacijos, auksas, NT, grynųjų atitikmuo
ARCHYVO_ETF = ["IWM", "MDY", "DIA", "TLT", "IEF", "SHY", "BIL", "AGG", "GLD", "VNQ"]

AN_STULPELIAI = [
    "ticker", "close", "bhs", "n_ratings", "strong_buy", "buy", "hold", "sell", "strong_sell",
    "rec_score_now", "rec_score_3m", "rec_change_3m", "rec_mean", "rec_key", "target_analysts",
    "target_mean", "target_median", "target_high", "target_low",
    "upside_mean_pct", "upside_median_pct",
    "up_30d", "down_30d", "init_30d", "pt_raise_30d", "pt_cut_30d", "net_30d", "net_90d",
    "last_action", "error",
]
AN_SVEIKI = ["n_ratings", "strong_buy", "buy", "hold", "sell", "strong_sell", "target_analysts",
             "up_30d", "down_30d", "init_30d", "pt_raise_30d", "pt_cut_30d", "net_30d", "net_90d"]
VEIKSMU_STULPELIAI = ["ticker", "date", "firm", "action", "from_grade", "to_grade",
                      "pt_action", "pt_prior", "pt_current"]

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


def uzdarymai(tickers: list[str], period: str = "13mo", start: str | None = None,
              klaidu: list[str] | None = None) -> pd.DataFrame:
    """Koreguotos dienos uždarymo kainos: pagal nutylėjimą 13 mėn., su start – nuo tos datos."""
    klaidu = klaidos if klaidu is None else klaidu
    laikas = {"start": start} if start else {"period": period}
    dalys = []
    for i in range(0, len(tickers), 100):
        dalis = tickers[i:i + 100]
        for bandymas in range(3):
            try:
                df = yf.download(dalis, interval="1d", auto_adjust=True,
                                 progress=False, threads=True, **laikas)
                if df is None or df.empty:
                    raise RuntimeError("tuščias atsakymas")
                close = df["Close"]
                if isinstance(close, pd.Series):
                    close = close.to_frame(dalis[0])
                dalys.append(close)
                break
            except Exception as e:
                klaidu.append(f"kainos nuo {dalis[0]} (bandymas {bandymas + 1}): {e}"[:200])
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


def _archyvo_santrauka(info: dict, perkurtas: bool) -> dict:
    out = {k: info.get(k) for k in ("built_utc", "from", "to", "tickers")}
    out["rebuilt"] = perkurtas
    return out


def reikia_archyvo(info_f: Path, tickers: list[str] | None = None) -> bool:
    """Archyvas perkuriamas pirmą kiekvieno mėnesio paleidimą, jei jo dar nėra,
    arba jei į visumą pridėta tikerių, kurių anksčiau neprašyta."""
    if not info_f.exists():
        return True
    try:
        info = json.loads(info_f.read_text(encoding="utf-8"))
    except Exception:
        return True
    if str(info.get("built_utc") or "")[:7] != dt.datetime.now(dt.timezone.utc).strftime("%Y-%m"):
        return True
    if tickers:
        prasyta = set(info.get("requested") or info.get("first_date") or [])
        if set(tickers) - prasyta:
            return True
    return False


def archyvas(tickers: list[str]) -> dict:
    """Ilgas kainų archyvas back testams. Jei parsiųsti nepavyksta, senas archyvas paliekamas
    ir kitą dieną bandoma iš naujo (kol to mėnesio archyvas pavyks)."""
    kat = DATA / "archyvas"
    kat.mkdir(parents=True, exist_ok=True)
    info_f, failas = kat / "info.json", kat / "uzdarymai_max.csv.gz"
    senas: dict = {}
    if info_f.exists():
        try:
            senas = json.loads(info_f.read_text(encoding="utf-8"))
        except Exception:
            senas = {}
    if failas.exists() and not reikia_archyvo(info_f, tickers):
        return _archyvo_santrauka(senas, False)

    klaidu: list[str] = []
    cl = uzdarymai(tickers, start=ARCHYVO_PRADZIA, klaidu=klaidu)
    buvo = int(senas.get("tickers") or 0) if failas.exists() else 0
    if cl.empty or (buvo and len(cl.columns) < 0.8 * buvo):
        out = _archyvo_santrauka(senas, False)
        out["error"] = (f"neperkurtas: gauta {len(cl.columns)} tikerių, buvo {buvo}; "
                        f"{'; '.join(klaidu[:3])}")[:300]
        return out

    cl.to_csv(failas, index_label="date", float_format="%.6g",
              compression={"method": "gzip", "mtime": 0})
    pirmos = {}
    for t in cl.columns:
        d = cl[t].first_valid_index()
        if d is not None:
            pirmos[t] = d.date().isoformat()
    info = {
        "built_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "from": str(cl.index[0].date()),
        "to": str(cl.index[-1].date()),
        "tickers": int(len(cl.columns)),
        "rows": int(len(cl)),
        "prices": "uždarymo kainos, koreguotos dividendais ir skaidymais (yfinance auto_adjust=True) "
                  "archyvo sudarymo dieną; jungiant su uzdarymai.csv jungti grąžas, ne kainų lygius",
        "survivorship": "visuma – dabartinė S&P 500 sudėtis + akcijos.txt + etf.txt + sektorių ETF; "
                        "iš indekso iškritusių ar bankrutavusių bendrovių nėra, todėl akcijų testo "
                        "rezultatai būna per geri",
        "first_date": pirmos,
        "requested": sorted(tickers),
        "errors": klaidu[:50],
    }
    info_f.write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    return _archyvo_santrauka(info, True)


def analitiku_istorija(akcijos: list[str]) -> dict:
    """Visa Yahoo analitikų veiksmų istorija (reitingai ir tikslinės kainos) back testams.
    Perkuriama kartu su kainų archyvu (pirmą mėnesio paleidimą) arba jei failo dar nėra.
    Jei daugiau kaip 20 % tikerių nepavyksta, paliekamas senas failas ir kitą dieną bandoma vėl."""
    kat = DATA / "archyvas"
    kat.mkdir(parents=True, exist_ok=True)
    failas, info_f = kat / "analitikai_istorija.csv.gz", kat / "analitikai_istorija.json"
    senas: dict = {}
    if info_f.exists():
        try:
            senas = json.loads(info_f.read_text(encoding="utf-8"))
        except Exception:
            senas = {}
    santr = lambda i, p: {"built_utc": i.get("built_utc"), "tickers_with_history": i.get("tickers_with_history"),
                          "rows": i.get("rows"), "from": i.get("from"), "rebuilt": p}
    if failas.exists() and not reikia_archyvo(info_f, akcijos):
        return santr(senas, False)

    dalys, nepavyko = [], []
    for t in akcijos:
        ud = None
        for bandymas in range(2):
            try:
                ud = yf.Ticker(t).upgrades_downgrades
                break
            except Exception as e:
                if "no upgrade/downgrade history" in str(e).lower():
                    break                                   # analitikų veiksmų nėra – ne klaida
                if _ribojimas(e) and bandymas == 0:
                    time.sleep(60)
                    continue
                nepavyko.append(t)
                break
        if ud is not None and len(ud):
            df = ud.copy()
            idx = pd.to_datetime(df.index)
            if getattr(idx, "tz", None) is not None:
                idx = idx.tz_convert(None)
            dalys.append(pd.DataFrame({
                "ticker": t, "date": idx.strftime("%Y-%m-%d"),
                "firm": df.get("Firm"), "action": df.get("Action"),
                "from_grade": df.get("FromGrade"), "to_grade": df.get("ToGrade"),
                "pt_action": df.get("priceTargetAction"),
                "pt_prior": pd.to_numeric(df.get("priorPriceTarget"), errors="coerce") if "priorPriceTarget" in df else None,
                "pt_current": pd.to_numeric(df.get("currentPriceTarget"), errors="coerce") if "currentPriceTarget" in df else None,
            }).reset_index(drop=True))
        time.sleep(PAUZE)

    if failas.exists() and len(nepavyko) > 0.2 * max(len(akcijos), 1):
        out = santr(senas, False)
        out["error"] = f"neperkurta: nepavyko {len(nepavyko)} iš {len(akcijos)}"
        return out
    ist = pd.concat(dalys, ignore_index=True) if dalys else pd.DataFrame(columns=VEIKSMU_STULPELIAI)
    ist = ist.reindex(columns=VEIKSMU_STULPELIAI).sort_values(["ticker", "date"], ascending=[True, False])
    ist.to_csv(failas, index=False, compression={"method": "gzip", "mtime": 0})
    info = {
        "built_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "tickers_with_history": int(ist["ticker"].nunique()) if len(ist) else 0,
        "rows": int(len(ist)),
        "from": str(ist["date"].min()) if len(ist) else None,
        "note": "Yahoo upgradeDowngradeHistory: kiekvienas analitiko veiksmas (up, down, init, main, reit) su "
                "data, įmone, reitingu iš → į ir tikslinė kaina iš → į. Visuma – dabartinė S&P 500 sudėtis "
                "+ akcijos.txt (išlikimo šališkumas).",
        "failed": nepavyko[:100],
        "requested": sorted(akcijos),
    }
    info_f.write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    return santr(info, True)


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


def _ribojimas(klaida) -> bool:
    """Ar klaida rodo, kad Yahoo apribojo užklausas."""
    s = str(klaida or "").lower()
    return "rate" in s or "too many" in s


def pelnas_vienam(t: str) -> tuple[dict, "yf.Ticker", dict]:
    """Grąžina pelno eilutę, Ticker objektą ir info – pastarieji pernaudojami analitikams."""
    r: dict = {"ticker": t}
    tk = yf.Ticker(t)
    info: dict = {}
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
    return r, tk, info


def _rec_balas(eil) -> tuple[float | None, int]:
    """Vidutinis reitingas 1–5 kaip Yahoo recommendationMean (1 – Strong Buy, 5 – Strong Sell)."""
    svoriai = ((1, "strongBuy"), (2, "buy"), (3, "hold"), (4, "sell"), (5, "strongSell"))
    kiek = [(w, _sk(eil.get(k)) or 0.0) for w, k in svoriai]
    n = sum(c for _, c in kiek)
    if n <= 0:
        return None, 0
    return sum(w * c for w, c in kiek) / n, int(n)


def _pt_kryptis(eil) -> int:
    """+1 – tikslinė kaina pakelta, −1 – sumažinta, 0 – patvirtinta, paskelbta ar nežinoma."""
    veiksmas = str(eil.get("priceTargetAction") or "").strip().lower()
    if veiksmas.startswith("rais"):
        return 1
    if veiksmas.startswith("lower"):
        return -1
    if veiksmas in ("", "adjusts", "adjust"):   # kryptis neparašyta – lyginam skaičius
        dabar, buvo = _sk(eil.get("currentPriceTarget")), _sk(eil.get("priorPriceTarget"))
        if dabar and buvo:
            return 1 if dabar > buvo else (-1 if dabar < buvo else 0)
    return 0


def analitikai_vienam(t: str, tk, info: dict, close: float | None) -> tuple[dict, list[dict]]:
    """Analitikų reitingai, tikslinės kainos ir jų pokyčiai vienam tikeriui.

    Tikslinės kainos ir vidutinis reitingas imami iš jau gauto info (Yahoo financialData),
    todėl papildomai reikia tik dviejų užklausų: reitingų pasiskirstymo ir veiksmų istorijos.
    """
    a: dict = {"ticker": t}
    probl: list[str] = []
    info = info or {}

    for k, nm in (("targetMeanPrice", "target_mean"), ("targetMedianPrice", "target_median"),
                  ("targetHighPrice", "target_high"), ("targetLowPrice", "target_low"),
                  ("numberOfAnalystOpinions", "target_analysts"), ("recommendationMean", "rec_mean")):
        a[nm] = _sk(info.get(k))
    a["rec_key"] = info.get("recommendationKey")
    kaina = _sk(close) or _sk(info.get("currentPrice"))
    a["close"] = kaina
    for k in ("mean", "median"):
        tg = a.get(f"target_{k}")
        a[f"upside_{k}_pct"] = round((tg / kaina - 1) * 100, 2) if tg and kaina else None

    # Reitingų pasiskirstymas dabar (0m) ir prieš 3 mėn. (-3m)
    try:
        rec = tk.recommendations
        if rec is not None and len(rec) and "period" in rec.columns:
            rec = rec.drop_duplicates("period").set_index("period")
            if "0m" in rec.index:
                e = rec.loc["0m"]
                for k, nm in (("strongBuy", "strong_buy"), ("buy", "buy"), ("hold", "hold"),
                              ("sell", "sell"), ("strongSell", "strong_sell")):
                    a[nm] = int(_sk(e.get(k)) or 0)
                balas, n = _rec_balas(e)
                a["n_ratings"] = n
                a["rec_score_now"] = round(balas, 2) if balas is not None else None
                a["bhs"] = f"{a['strong_buy'] + a['buy']}/{a['hold']}/{a['sell'] + a['strong_sell']}"
                if "-3m" in rec.index:
                    balas3, _ = _rec_balas(rec.loc["-3m"])
                    a["rec_score_3m"] = round(balas3, 2) if balas3 is not None else None
                    if balas is not None and balas3 is not None:
                        a["rec_change_3m"] = round(balas - balas3, 2)   # neigiamas – reitingai gerėja
    except Exception as e:
        probl.append(f"recommendations: {e}")

    # Reitingų ir tikslinių kainų pakėlimai bei sumažinimai
    veiksmai: list[dict] = []
    for k in ("up_30d", "down_30d", "init_30d", "pt_raise_30d", "pt_cut_30d", "net_30d", "net_90d"):
        a[k] = 0
    try:
        ud = tk.upgrades_downgrades
    except Exception as e:
        ud = None
        if "no upgrade/downgrade history" not in str(e).lower():   # tiesiog nėra veiksmų – ne klaida
            probl.append(f"upgrades_downgrades: {e}")
    if ud is not None and len(ud):
        df = ud.copy()
        idx = pd.to_datetime(df.index)
        if getattr(idx, "tz", None) is not None:
            idx = idx.tz_convert(None)
        df.index = idx
        df = df.sort_index(ascending=False)
        dabar = pd.Timestamp.now(tz="UTC").tz_localize(None)
        d90 = df[df.index >= dabar - pd.Timedelta(days=VEIKSMU_D)]
        turi_pt = "priceTargetAction" in df.columns or "currentPriceTarget" in df.columns

        def skaicius(d: pd.DataFrame) -> dict:
            act = d["Action"].astype(str).str.lower() if "Action" in d.columns else pd.Series(dtype=str)
            kr = d.apply(_pt_kryptis, axis=1) if (turi_pt and len(d)) else pd.Series(dtype=int)
            s = {"up": int((act == "up").sum()), "down": int((act == "down").sum()),
                 "init": int((act == "init").sum()),
                 "pt_raise": int((kr > 0).sum()) if turi_pt else None,
                 "pt_cut": int((kr < 0).sum()) if turi_pt else None}
            s["net"] = s["up"] - s["down"] + ((s["pt_raise"] or 0) - (s["pt_cut"] or 0))
            return s

        s30 = skaicius(d90[d90.index >= dabar - pd.Timedelta(days=ANALITIKU_D)])
        s90 = skaicius(d90)
        a.update({"up_30d": s30["up"], "down_30d": s30["down"], "init_30d": s30["init"],
                  "pt_raise_30d": s30["pt_raise"], "pt_cut_30d": s30["pt_cut"],
                  "net_30d": s30["net"], "net_90d": s90["net"]})
        a["last_action"] = df.index[0].date().isoformat()
        for d, eil in d90.iterrows():
            veiksmai.append({
                "ticker": t, "date": d.date().isoformat(), "firm": eil.get("Firm"),
                "action": eil.get("Action"), "from_grade": eil.get("FromGrade"),
                "to_grade": eil.get("ToGrade"), "pt_action": eil.get("priceTargetAction"),
                "pt_prior": _sk(eil.get("priorPriceTarget")),
                "pt_current": _sk(eil.get("currentPriceTarget")),
            })

    if probl:
        a["error"] = "; ".join(probl)[:200]
    return a, veiksmai


def pelnas(tickers: list[str], kainos: dict | None = None
           ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    kainos = kainos or {}
    rows, an_rows, veiksmai = [], [], []
    for t in tickers:
        r, tk, info = pelnas_vienam(t)
        if _ribojimas(r.get("error")):
            time.sleep(60)          # Yahoo apribojo – palaukiam ir bandom dar kartą
            r, tk, info = pelnas_vienam(t)
        a, v = analitikai_vienam(t, tk, info, kainos.get(t))
        if _ribojimas(a.get("error")):
            time.sleep(60)
            a, v = analitikai_vienam(t, yf.Ticker(t), info, kainos.get(t))
        rows.append(r)
        an_rows.append(a)
        veiksmai.extend(v)
        time.sleep(PAUZE)
    an = pd.DataFrame(an_rows, columns=AN_STULPELIAI)
    for c in AN_SVEIKI:
        an[c] = pd.to_numeric(an[c], errors="coerce").astype("Int64")
    return pd.DataFrame(rows), an, pd.DataFrame(veiksmai, columns=VEIKSMU_STULPELIAI)


def main() -> None:
    DATA.mkdir(exist_ok=True)
    akcijos = set(sp500()) | set(skaityti_sarasa("akcijos.txt"))
    etf = set(skaityti_sarasa("etf.txt")) | {BENCH} | set(SEKTORIAI) | set(LYGINAMIEJI)
    visi = sorted(akcijos | etf)
    print(f"Visuma: {len(akcijos)} akcijų, {len(etf)} ETF", flush=True)

    cl = uzdarymai(visi)
    sant = santrauka(cl) if not cl.empty else pd.DataFrame(columns=["ticker"])
    kand = kandidatai(sant, akcijos, skaityti_sarasa("akcijos.txt")) if len(sant) else []
    print(f"Kainos: {len(sant)}; pelno patikrai: {len(kand)}", flush=True)
    kainos = dict(zip(sant["ticker"], sant["close"])) if len(sant) and "close" in sant.columns else {}
    if kand:
        pel, anal, veiks = pelnas(kand, kainos)
    else:
        pel = pd.DataFrame(columns=["ticker"])
        anal = pd.DataFrame(columns=AN_STULPELIAI)
        veiks = pd.DataFrame(columns=VEIKSMU_STULPELIAI)

    if not cl.empty:
        cl.round(4).to_csv(DATA / "uzdarymai.csv", index_label="date")
    sant.to_csv(DATA / "santrauka.csv", index=False)
    pel.to_csv(DATA / "pelnas.csv", index=False)
    anal.to_csv(DATA / "analitikai.csv", index=False)
    veiks.to_csv(DATA / "analitikai_veiksmai.csv", index=False)

    vt = sant[sant["ticker"] == BENCH].to_dict("records") if len(sant) else []
    ok = int(pel["fy0_eps_now"].notna().sum()) if "fy0_eps_now" in pel.columns else 0
    if len(anal):
        turi = (pd.to_numeric(anal["n_ratings"], errors="coerce").fillna(0) > 0) | anal["target_mean"].notna()
        an_ok, an_err = int(turi.sum()), int(anal["error"].notna().sum())
    else:
        an_ok, an_err = 0, 0

    try:   # archyvas – po kasdienių failų, kad jo nesėkmė jų nepaveiktų
        arch = archyvas(sorted(set(visi) | set(ARCHYVO_ETF)))
    except Exception as e:
        arch = {"rebuilt": False, "error": f"{e}"[:300]}
    print(f"Archyvas: {json.dumps(arch, ensure_ascii=False)}", flush=True)
    try:
        istor = analitiku_istorija(sorted(akcijos))
    except Exception as e:
        istor = {"rebuilt": False, "error": f"{e}"[:300]}
    print(f"Analitikų istorija: {json.dumps(istor, ensure_ascii=False)}", flush=True)
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
        "analysts_ok": an_ok,          # tikeriai su analitikų reitingais ar tikslinėmis kainomis
        "analysts_errors": an_err,     # tikeriai, kuriems analitikų duomenų gauti nepavyko
        "analyst_actions_90d": int(len(veiks)),
        "archive": arch,               # data/archyvas/: kainos nuo 2000 m. back testams
        "analyst_history": istor,      # data/archyvas/analitikai_istorija.csv.gz: visi analitikų veiksmai
        "vt": vt[0] if vt else None,
        "errors": klaidos[:100],
    }
    (DATA / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: meta[k] for k in ("generated_utc", "priced", "candidates", "eps_ok",
                                           "analysts_ok")}), flush=True)


if __name__ == "__main__":
    main()
