# Rinkos duomenys

Kas šeštadienį GitHub nemokamai surenka akcijų ir ETF rodiklius iš Yahoo Finance ir įrašo juos į aplanką `data/`. Claude juos skaito iš `https://raw.githubusercontent.com/<tavo-vardas>/rinkos-duomenys/main/data/`, todėl užklausų limitų nėra.

## Ką surenka

- `santrauka.csv` – apie 530 tikerių (S&P 500, `akcijos.txt`, `etf.txt`): grąža per 1, 3, 6 mėn. ir 1 m., atstumas nuo 100 d. ir 52 sav. aukščiausios kainos.
- `pelnas.csv` – akcijoms, kurios per 1 ir 3 mėn. kilo daugiau už VT (iki 250), ir visoms `akcijos.txt` akcijoms: EPS konsensusas dabar ir prieš 7, 30, 60, 90 d., analitikų skaičius, forward P/E, paskutinių ir kitų rezultatų datos.
- `analitikai.csv` – toms pačioms akcijoms kaip `pelnas.csv`: reitingų skaičius dabar (`strong_buy` … `strong_sell`, `bhs` = Buy/Hold/Sell), vidutinis reitingas dabar ir prieš 3 mėn. (1 – Strong Buy, 5 – Strong Sell; neigiamas `rec_change_3m` – reitingai gerėja), vidutinė, medianinė, aukščiausia ir žemiausia tikslinė kaina, potencialas nuo paskutinio uždarymo, per 30 d. reitingų pakėlimai (`up_30d`), sumažinimai (`down_30d`), naujai pradėję vertinti (`init_30d`), tikslinių kainų pakėlimai (`pt_raise_30d`) ir sumažinimai (`pt_cut_30d`), grynasis pokytis per 30 ir 90 d. (`net_30d`, `net_90d` = pakėlimai − sumažinimai).
- `analitikai_veiksmai.csv` – kiekvienas analitiko veiksmas per 90 d.: data, įmonė, veiksmas (`up` – pakėlė, `down` – sumažino, `init` – pradėjo vertinti, `main`/`reit` – patvirtino), reitingas iš → į, tikslinė kaina iš → į.
- `uzdarymai.csv` – dienos uždarymo kainos per ~13 mėn.
- `meta.json` – kada surinkta ir kokios buvo klaidos (`analysts_ok` – kiek akcijų turi analitikų duomenis, `archive` – archyvo būklė).
- `archyvas/uzdarymai_max.csv.gz` – back testams: visų tikerių (S&P 500, `akcijos.txt`, `etf.txt`, 10 sektorių ETF, SPY, EFA, EEM, taip pat IWM, MDY, DIA, TLT, IEF, SHY, BIL, AGG, GLD, VNQ) koreguotos dienos uždarymo kainos nuo 2000 m. Perkuriamas pirmą kiekvieno mėnesio paleidimą arba kai į sąrašus pridedi naują tikerį; jei Yahoo tą dieną riboja, paliekamas senas ir kitą dieną bandoma vėl. `archyvas/info.json` – kada sudarytas ir nuo kurios dienos turi duomenų kiekvienas tikeris.
- `archyvas/analitikai_istorija.csv.gz` – visa Yahoo analitikų veiksmų istorija visoms akcijoms (kiekvienas reitingo ar tikslinės kainos pakeitimas su data ir įmone) analitikų strategijų testams. Perkuriama kartu su archyvu; `archyvas/analitikai_istorija.json` – santrauka.

## Kaip įsijungti (~10 min., viskas naršyklėje)

1. github.com → **Sign up** – nemokama paskyra.
2. **New repository** → pavadinimas `rinkos-duomenys` → **Public** → pažymėk **Add a README file** → **Create repository**.
3. **Add file → Upload files** → nutempk 4 failus: `surinkti.py`, `akcijos.txt`, `etf.txt`, `README.md` → **Commit changes**.
4. Skiltis **Actions** → nuoroda **set up a workflow yourself** → ištrink redaktoriuje esantį tekstą, įklijuok visą `rinkos-duomenys.yml` turinį → **Commit changes**. Failo pavadinimas (pvz., `main.yml`) nesvarbus.
5. **Settings → Actions → General → Workflow permissions** → **Read and write permissions** → **Save**.
6. **Actions → Rinkos duomenys → Run workflow**. Po maždaug 20–30 min. atsiras aplankas `data/`.
7. Parašyk Claude savo GitHub vartotojo vardą – jis patikrins duomenis ir įrašys adresą į savaitinę užduotį.

## Svarbu

- Kaina – 0 €: viešose repozitorijose standartiniai GitHub Actions paleidimai nemokami.
- yfinance – neoficialus Yahoo Finance įrankis asmeniniam naudojimui. Jei Yahoo kartais apriboja užklausas, `meta.json` bus klaidų, o Claude tą savaitę naudos atsarginius šaltinius.
- Repozitorija vieša, bet joje tik rinkos duomenys ir stebimų tikerių sąrašai – jokių slaptažodžių ar raktų.
- Naujas akcijas ar ETF pridėk į `akcijos.txt` ar `etf.txt` (Europos akcijos – Yahoo formatu, pvz., su `.AS`, `.DE`, `.PA` galūnėmis). `akcijos.txt` akcijoms pelno ir analitikų duomenys renkami kas savaitę, net jei jos nepraeina kainų filtro.
- Analitikų duomenys – Yahoo rinkinys, todėl analitikų skaičius ir tikslinės kainos gali šiek tiek skirtis nuo Google Finance, TipRanks ar MarketBeat.
- Archyvo akcijos – dabartinė S&P 500 sudėtis: iš indekso iškritusių ar bankrutavusių bendrovių jame nėra, todėl akcijų back testai būna per optimistiški. Sektorių ir kitų ETF testams ši problema netaikoma.
- Pelno prognozių (`pelnas.csv`) ir analitikų (`analitikai.csv`) istorijos Yahoo neduoda – ji kaupiasi tik į priekį, kiekvienos dienos versija lieka repozitorijos istorijoje (commit'uose).
- Archyvo failas – apie 10–15 MB, todėl dėl jo repozitorija augs maždaug 0,15 GB per metus. GitHub tai leidžia; jei kada reikėtų mažiau, archyvą galima perkurti kas ketvirtį.
- Jei suplanuoti paleidimai kada nors sustotų, Actions skiltyje juos vėl įjunk.
