# PayPamin Flow

Lokal skrivbordsapp för **Windows, macOS och Linux** som läser enskilda Fortnox-fakturor från PDF, skapar betalningspåminnelser som PDF och håller reda på nästa steg. Fakturor och kunduppgifter behandlas lokalt; appen ansluter inte till Fortnox och skickar inte e-post eller Kronofogden-ärenden automatiskt.

- **Skapare och upphovsman:** Rickard Länkvist
- **Copyright:** © 2026 Rickard Länkvist

> **Projektstatus:** tidig prototyp. Avläsning och mallar måste kontrolleras mot riktiga fakturor innan appen används skarpt.

## Funktioner

- Läser enskilda faktura-PDF:er och föreslår kund, fakturanummer, datum, belopp efter **ATT BETALA** och fakturatext.
- **Valuta per faktura** med SEK som standard och redigerbara koder med tre bokstäver, exempelvis EUR, USD, NOK och DKK. Belopp växlas inte mellan valutor.
- Importmapp och knapp för att skanna nya PDF-filer. Varje ny faktura granskas innan den sparas. Dubbletter stoppas via fakturanummer eller identiskt PDF-innehåll, även om filen döpts om, och användaren får ett tydligt meddelande.
- PDF-förhandsgranskning med markerbara fältområden och återanvändbara leverantörsmallar.
- SVG-logotyp kan kopplas till en leverantörsmall och återanvändas vid export.
- Manuell granskningsgräns, P1/P2/Kronofogden-steg, justerbara dagar, avgift, betalningsfrist och ränta.
- Samma egen applikationsikon i fönster, dialoger, Windows-exe, macOS-app och Linux-programmeny.
- **Autostart vid inloggning** på Windows, macOS och Linux. Funktionen är aktiverad som standard och kan stängas av under **Inställningar**.
- **Svenska och engelska** med direkt språkbyte, sparat språkval och översatta meddelanden, statusar, belopp, datum och påminnelse-PDF:er.
- **Automatiska uppdateringar mot GitHub Releases** två gånger per dygn, med verifierade native-paket och tyst omstart. Manuell sökning och nedladdning finns också.
- PDF sparas lokalt och öppnas i datorns standardprogram. Fellogg öppnas via **Visa fellogg**.

## Starta från källkod

Python **3.10 eller senare** och Tkinter krävs. Installera Python-tilläggen med:

```sh
python -m pip install -r requirements.txt
```

Använd `py` i stället för `python` i Windows om det är det kommando som pekar på din Python-installation.

### Windows

1. Installera Python från python.org och välj **Add Python to PATH**. Den officiella installationen innehåller Tkinter.
2. Installera tilläggen enligt ovan.
3. Dubbelklicka på `start_paypamin_flow.vbs` för att starta utan konsolfönster.

För felsökning från PowerShell:

```powershell
py paypamin_flow.py
```

### macOS

1. Installera Python 3.10+ med Tkinter, till exempel det officiella installationspaketet från python.org.
2. Installera tilläggen enligt ovan.
3. Kör `./start_paypamin_flow.command` eller:

```sh
python3 paypamin_flow.py
```

Det native `.app`-paketet från byggsteget nedan startar utan Terminalfönster.

### Linux

På Debian/Ubuntu installeras skrivbords- och Python-stöd med:

```sh
sudo apt install python3 python3-pip python3-tk
python3 -m pip install -r requirements.txt
./start_paypamin_flow.sh
```

På system med externally managed Python kan en virtuell miljö användas:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
./start_paypamin_flow.sh
```

## Språk / Language

Välj **Inställningar → Språk → Svenska / English** och spara. Språkbytet sker direkt utan omstart och sparas i den lokala databasen. Svenska är standard vid första starten.

Språkvalet gäller huvudfönster, filter, statusar, formulär, PDF-förhandsgranskning, felmeddelanden, belopp och datum samt nya påminnelse-PDF:er. Befintliga fakturor, PDF-mallar, logotypval och autostart fungerar med båda språken. Redan skapade PDF-filer ändras inte i efterhand.

## Uppdateringar

Appen kontrollerar den senaste stabila GitHub-releasen en kort stund efter start och därefter **var 12:e timme medan appen är öppen**. Automatiska uppdateringar är aktiverade som standard och kan stängas av under **Inställningar → Sök efter och installera uppdateringar automatiskt två gånger per dygn**.

När en nyare version finns hämtar en native-installation automatiskt rätt paket för Windows, macOS eller Linux. Paketets SHA-256-kontrollsumma verifieras före uppackning. Därefter stängs appen, programmet byts ut och startas igen utan konsolfönster. Den gamla installationen används som reserv under ombytet så att den kan återställas vid fel. Databas, fakturor, inställningar, mallar och företagslogotyper ingår inte i uppdateringen och lämnas orörda.

Knappen **Sök efter uppdateringar** gör en manuell kontroll. Vid en nyare version kan du välja **Installera och starta om** eller **Öppna nedladdningssida**. Körning direkt från källkod skrivs inte över automatiskt; använd release-sidan eller uppdatera källkoden manuellt.

Kontrollen använder GitHubs publika API och skickar inga faktura-, kund- eller inställningsuppgifter. Automatiska nätverks- och installationsfel loggas utan popup och provas igen vid nästa schemalagda kontroll. Installationsmappen måste vara skrivbar för den aktuella användaren. Operativsystemets säkerhetsskydd, kodsigneringskrav eller saknade releasepaket kan kräva manuell installation. Tekniska installationsfel loggas i `update.log` under `~/.paminnelseapp`.

GitHub Actions bygger och bifogar följande filer till nya publicerade releaser:

- `PayPamin-Flow-Windows.zip` och `.sha256`
- `PayPamin-Flow-macOS.zip` och `.sha256`
- `PayPamin-Flow-Linux.tar.gz` och `.sha256`

Säkerhetskopiera den lokala databasen regelbundet och innan en manuell ominstallation.

## Valuta / Currency

Varje faktura har en egen valuta. **SEK** är standard för nya fakturor och för befintliga fakturor när databasen uppdateras. Ange en annan ISO-kod med tre bokstäver, till exempel **EUR**, **USD**, **NOK** eller **DKK**, i granskningsformuläret eller när fakturan läggs till manuellt. Koden normaliseras till versaler.

PDF-importen föreslår valuta när en kod finns vid **ATT BETALA**, efter **Valuta/Currency** eller i ett sparat markerat valutafält. Kontrollera alltid förslaget före godkännande. Fakturabelopp, betalt belopp, kvarstående belopp, påminnelseavgifter och PDF-summor visas i fakturans valuta. Den inställda numeriska påminnelseavgiften används i respektive fakturas valuta.

**Appen gör ingen valutaomräkning.** Att ändra valuta ändrar märkningen, inte de inmatade siffrorna. Svensk visning blir exempelvis `1 234,50 EUR`; engelsk visning blir `EUR 1,234.50`.

## Autostart

Autostart gäller endast den inloggade användaren och kräver inga administratörsrättigheter. Appen synkroniserar valet vid start och när inställningarna sparas.

| System | Mekanism |
| --- | --- |
| Windows | `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\PayPaminFlow` |
| macOS | `~/Library/LaunchAgents/se.paypamin.flow.plist` |
| Linux | `$XDG_CONFIG_HOME/autostart/paypamin-flow.desktop`, normalt `~/.config/autostart/` |

Stäng av eller aktivera via **Inställningar → Starta PayPamin Flow automatiskt när jag loggar in**. Om appmappen eller det byggda programmet flyttas, starta appen en gång från den nya platsen så uppdateras sökvägen. Autostart sker efter inloggning, inte före inloggning vid datorns boot.

## Applikationsikon

Ikonen föreställer ett fakturadokument med **P** och en grön betalningsmarkering. Original och native format ligger i `assets/`:

- `paypamin_flow.svg` – vektororiginal.
- `paypamin_flow.png` och storleksvarianter – Tkinter och Linux.
- `paypamin_flow.ico` – Windows, flera inbäddade storlekar.
- `paypamin_flow.icns` – macOS.

Generera om raster- och native ikoner med Pillow installerat:

```sh
python assets/build_icons.py
```

## Bygg native skrivbordsapp

Bygg på respektive operativsystem; PyInstaller kors kompilerar inte mellan OS:

```sh
python -m pip install -r requirements-build.txt
pyinstaller paypamin_flow.spec --clean --noconfirm
```

Resultat:

- **Windows:** `dist/PayPamin Flow.exe` med appikon, version, produktnamn och copyrightmetadata.
- **macOS:** `dist/PayPamin Flow.app` med ICNS-ikon, bundle-id och copyrightmetadata.
- **Linux:** `dist/paypamin-flow`. Installera programpost och ikon för den aktuella användaren med `./packaging/install_linux.sh`.

GitHub Actions-workflöen i `.github/workflows/build.yml` kör tester och bygger paket för Windows, macOS och Linux. Paketen blir byggartefakter när workflöen körs. När en release publiceras skapar `packaging/package_release.py` plattformspaketen och deras SHA-256-filer, som därefter bifogas releasen för automatiska uppdateringar.

## Fakturor, logotyper och OCR

- Lägg faktura-PDF:er i `import/` och klicka **Skanna importmapp**, eller använd **Lägg till faktura-PDF**.
- Kontrollera föreslagna värden och godkänn dem innan en påminnelse skapas.
- Lägg egna SVG-logotyper i `svg/`; dessa är företagslogotyper och ska inte förväxlas med appens ikon i `assets/`.
- Genererade PDF-filer läggs i `export/`.

OCR för skannade PDF:er kräver Tesseract med svenska språkdata (`swe`) och Poppler:

- **Windows:** installera Tesseract OCR och Poppler och lägg dem i PATH.
- **macOS:** `brew install tesseract tesseract-lang poppler`.
- **Debian/Ubuntu:** `sudo apt install tesseract-ocr tesseract-ocr-swe poppler-utils`.

## Lokal lagring och integritet

- Databas, mallar, inställningar och fellogg sparas i användarprofilen under `~/.paminnelseapp`. Det befintliga katalognamnet behålls så att tidigare data inte försvinner efter namnbytet.
- Vid källkodskörning ligger `import/`, `export/` och `svg/` i projektmappen. I ett fruset/native paket ligger de under `~/.paminnelseapp` så att appen aldrig skriver i en temporär eller skrivskyddad programkatalog.
- Kundfakturor, exporter, lokala databaser, loggar och företagslogotyper ska inte checkas in. Se `.gitignore`.
- Felloggen kan innehålla tekniska fel och filvägar. Granska den innan den delas.
- Säkerhetskopiera databasen och mallarna före uppdatering eller ominstallation.

## Tester

```sh
python -m unittest discover -s tests -v
```

Parser-, autostart-, ikon-, språk-, valuta- och databasmigreringstester använder syntetiska data och kräver ingen grafisk skrivbordssession. Översättningstesterna kontrollerar även att nya texter har engelska översättningar och matchande variabler. Testa alltid ändringar mot riktiga, noggrant granskade exempel före skarp användning.

## Begränsningar

- PDF-layout och OCR kan misstolka fält. Kontrollera fakturan före godkännande.
- Betalstatus uppdateras inte via Fortnox. Kontrollera betalningar manuellt före utskick.
- Dagregler, avgifter, ränta och avtalsvillkor måste verifieras för verksamheten.
- Automatisk e-post eller automatisk ansökan till Kronofogden ingår inte.

## Copyright och licens

**Copyright © 2026 Rickard Länkvist. Skapare: Rickard Länkvist.** Se `NOTICE`.

Ingen separat användarlicens är vald. Normalt upphovsrättsskydd gäller, och rätt att återanvända eller distribuera koden ges inte automatiskt.
