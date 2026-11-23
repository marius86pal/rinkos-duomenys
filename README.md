# Rinkos duomenys

Kas šeštadienį GitHub nemokamai surenka akcijų ir ETF rodiklius iš Yahoo Finance ir įrašo juos į aplanką `data/`. Claude juos skaito iš `https://raw.githubusercontent.com/<tavo-vardas>/rinkos-duomenys/main/data/`, todėl užklausų limitų nėra.

## Ką surenka

- `santrauka.csv` – apie 530 tikerių (S&P 500, `akcijos.txt`, `etf.txt`): grąža per 1, 3, 6 mėn. ir 1 m., atstumas nuo 100 d. ir 52 sav. aukščiausios kainos.
- `pelnas.csv` – akcijoms, kurios per 1 ir 3 mėn. kilo daugiau už VT (iki 250), ir visoms `akcijos.txt` akcijoms: EPS konsensusas dabar ir prieš 7, 30, 60, 90 d., analitikų skaičius, forward P/E, paskutinių ir kitų rezultatų datos.
- `uzdarymai.csv` – dienos uždarymo kainos per ~13 mėn.
- `meta.json` – kada surinkta ir kokios buvo klaidos.

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
- Naujas akcijas ar ETF pridėk į `akcijos.txt` ar `etf.txt` (Europos akcijos – Yahoo formatu, pvz., su `.AS`, `.DE`, `.PA` galūnėmis).
- Jei suplanuoti paleidimai kada nors sustotų, Actions skiltyje juos vėl įjunk.
