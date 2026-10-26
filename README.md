# PayPamin Flow

Lokal Python-skrivbordsapp för **Windows, macOS och Linux** som läser enskilda Fortnox-fakturor från PDF, skapar betalningspåminnelser som PDF och håller reda på nästa steg. Fakturor och kunduppgifter behandlas lokalt; appen ansluter inte till Fortnox och skickar inte e-post eller Kronofogden-ärenden automatiskt.

- **Skapare och upphovsman:** Rickard Länkvist
- **Copyright:** © 2026 Rickard Länkvist

> **Projektstatus:** tidig prototyp. Avläsning och mallar måste kontrolleras mot riktiga fakturor innan appen används skarpt.

## Funktioner

- Läser faktura-PDF:er och föreslår kund, fakturanummer, datum, belopp efter **ATT BETALA** och fakturatext.
- **Valuta per faktura** med SEK som standard och redigerbara ISO-koder, exempelvis EUR, USD, NOK och DKK. Belopp växlas inte mellan valutor.
- **Automatisk bevakning av importmappen** upptäcker nya Fortnox-PDF:er utan API eller integrationslicens. Filer väntas in tills de är färdigskrivna och varje ny faktura granskas innan den sparas. Dubbletter stoppas via fakturanummer, sökväg eller identiskt PDF-innehåll, även om filen döpts om.
- PDF-förhandsgranskning med markerbara fältområden och återanvändbara leverantörsmallar.
- SVG-logotyp kan kopplas till en leverantörsmall och återanvändas vid export.
- Manuell granskningsgräns, P1/P2/Kronofogden-steg, justerbara dagar, avgift, betalningsfrist och ränta.
- Samma PayPamin Flow-ikon i fönster, dialoger, programmenyer och systemfältet.
- **Stäng till systemfältet:** fönstrets stängknapp döljer appen medan schemalagda kontroller fortsätter. **Arkiv → Avsluta helt** eller systemfältets **Avsluta helt** stänger appen helt.
- **Lokal säkerhetskopiering och återställning** av inställningar, fakturor, påminnelser och logotyper via Arkiv-menyn.
- **Autostart vid inloggning** på Windows, macOS och Linux. Funktionen är aktiverad som standard och kan stängas av under **Inställningar**.
- **Svenska och engelska** med direkt språkbyte, sparat språkval och översatta meddelanden, statusar, belopp, datum och påminnelse-PDF:er.
- **Automatiska Python-uppdateringar mot GitHub Releases** två gånger per dygn, med SHA-256-verifiering och tyst omstart. Manuell sökning och installation finns i appen via **Hjälp → Sök efter uppdateringar**.
- PDF sparas lokalt och öppnas i datorns standardprogram. Fellogg öppnas via **Visa fellogg**.

## Python-only – ingen EXE eller native-app

PayPamin Flow distribueras som **Python-källkod**, inte som EXE, macOS-app eller native Linux-binär. Samma releasepaket används på alla tre plattformarna:

- `PayPamin-Flow-Python.zip`
- `PayPamin-Flow-Python.zip.sha256`

Python **3.10 eller senare** och Tkinter krävs. Packa upp ZIP-filen i en mapp där din användare har skrivrättigheter och installera tilläggen:

```sh
python -m pip install -r requirements.txt
```

Använd `py -m pip` i Windows om det är det kommando som pekar på din Python-installation. Appen kan också installera saknade Python-tillägg i bakgrunden utan att öppna ett konsolfönster.

## Starta utan konsolfönster

### Windows

1. Installera Python från python.org och välj **Add Python to PATH**. Den officiella installationen innehåller Tkinter och `pythonw.exe`.
2. Installera tilläggen enligt ovan.
3. Dubbelklicka på **`start_paypamin_flow.vbs`**. Startaren använder `pythonw.exe` och öppnar inget konsolfönster.

För felsökning från en redan öppen PowerShell kan `py paypamin_flow.py` användas.

### macOS

1. Installera Python 3.10+ med Tkinter och Python Launcher, till exempel det officiella installationspaketet från python.org.
2. Installera tilläggen enligt ovan.
3. Öppna **`paypamin_flow.pyw`** med Python Launcher. Python Launchers alternativ att köra i Terminal ska vara avstängt.

Autostart och omstart efter uppdatering använder Python direkt via LaunchAgents respektive appens befintliga process och öppnar inte Terminal. En separat `.command`-startare används inte eftersom macOS annars kan öppna Terminal.

### Linux

På Debian/Ubuntu installeras skrivbords- och Python-stöd med:

```sh
sudo apt install python3 python3-pip python3-tk
python3 -m pip install -r requirements.txt
./packaging/install_linux.sh
```

Starta därefter **PayPamin Flow** från programmenyn. Skrivbordsposten har `Terminal=false`. Installationen är per användare och kopierar Python-filerna till `~/.local/share/paypamin-flow` som standard.

På system med externally managed Python kan en virtuell miljö användas. Skapa miljön, installera `requirements.txt` i den och ange dess Python med miljövariabeln `PYTHON` när installationsprogrammet körs.

## Systemfält och fullständig avslutning

När du stänger huvudfönstret döljs det i systemfältet. Appen fortsätter då med bland annat schemalagda uppdateringskontroller.

- Klicka på PayPamin Flow-ikonen eller välj **Öppna PayPamin Flow** i systemfältet för att visa fönstret igen.
- Välj **Arkiv → Dölj till systemfältet** för att dölja det utan musens stängknapp.
- Välj **Arkiv → Avsluta helt** eller **Avsluta helt** i systemfältet för att avsluta bakgrundsaktiviteten och stänga appen.

Om skrivbordsmiljön inte har ett fungerande systemfält lämnas fönstret synligt och appen erbjuder ett tydligt val att avsluta i stället för att gömmas oåtkomlig. På Linux kan skrivbordets AppIndicator-/systemfältsstöd behöva aktiveras.

## Säkerhetskopiering och återställning

Välj **Arkiv → Säkerhetskopiera inställningar och påminnelser** och spara ZIP-filen på en säker plats. Säkerhetskopian innehåller:

- den lokala databasen med inställningar, fakturor, leverantörsmallar och PDF-fältområden;
- skapade påminnelse-PDF:er från `export/`;
- företagslogotyper från `svg/`;
- ett manifest med format, version, tidsstämpel och SHA-256-kontrollsummor.

Importerade originalfakturor i `import/` och diagnostikloggar ingår inte. Kopiera originalfakturorna separat om de inte finns någon annanstans.

Välj **Arkiv → Återställ säkerhetskopia** för att återställa. Arkivets sökvägar, filtyper, kontrollsummor och SQLite-integritet kontrolleras först. Appen skapar alltid en säkerhetskopia av nuvarande data innan något ersätts. Den sparas under `~/.paminnelseapp/backups`. Om ersättningen misslyckas återställs de tidigare filerna automatiskt.

## Uppdateringar i appen

Appen kontrollerar den senaste stabila GitHub-releasen en kort stund efter start och därefter **var 12:e timme medan appen körs**, även när fönstret ligger i systemfältet. Automatiska uppdateringar är aktiverade som standard och kan stängas av under **Inställningar**.

Vid en nyare version hämtas samma Python-ZIP för Windows, macOS och Linux. Kontrollsumman verifieras, arkivets sökvägar och filer valideras och Python-filerna syntaxkontrolleras innan något ersätts. Appen ersätter endast egna program-, start-, dokumentations- och ikonfiler. Databas, `import/`, `export/`, `svg/` och andra användardata ingår inte och lämnas orörda.

Installationen sker **inuti appen**; du ska inte starta någon separat uppdateringsfil. Därefter startas den uppdaterade Python-appen om utan konsolfönster. Gamla programfiler används som reserv under ersättningen och återställs om installationen eller omstarten misslyckas.

Manuell kontroll görs med knappen **Sök efter uppdateringar** eller **Hjälp → Sök efter uppdateringar**. Vid en nyare version väljer du **Installera och starta om** eller **Öppna nedladdningssida**.

Kontrollen använder GitHubs publika API och skickar inga faktura-, kund- eller inställningsuppgifter. Automatiska nätverks- och installationsfel loggas utan popup och provas igen vid nästa schemalagda kontroll. Appmappen måste vara skrivbar för den aktuella användaren. Tekniska installationsfel loggas i `update.log` under `~/.paminnelseapp`.

## Språk / Language

Välj **Inställningar → Språk → Svenska / English** och spara. Språkbytet sker direkt utan omstart och sparas i den lokala databasen. Svenska är standard vid första starten.

Språkvalet gäller huvudfönster, menyer, systemfält, filter, statusar, formulär, PDF-förhandsgranskning, felmeddelanden, belopp och datum samt nya påminnelse-PDF:er. Befintliga fakturor, PDF-mallar, logotypval och autostart fungerar med båda språken. Redan skapade PDF-filer ändras inte i efterhand.

## Valuta / Currency

Varje faktura har en egen valuta. **SEK** är standard för nya fakturor och för befintliga fakturor när databasen uppdateras. Ange en annan ISO-kod med tre bokstäver, till exempel **EUR**, **USD**, **NOK** eller **DKK**, i granskningsformuläret eller när fakturan läggs till manuellt.

PDF-importen föreslår valuta när en kod finns vid **ATT BETALA**, efter **Valuta/Currency** eller i ett sparat markerat valutafält. Kontrollera alltid förslaget. Fakturabelopp, betalt belopp, kvarstående belopp, avgifter och PDF-summor visas i fakturans valuta.

**Appen gör ingen valutaomräkning.** Att ändra valuta ändrar märkningen, inte de inmatade siffrorna. Svensk visning blir exempelvis `1 234,50 EUR`; engelsk visning blir `EUR 1,234.50`.

## Autostart

Autostart gäller endast den inloggade användaren och kräver inga administratörsrättigheter. Appen synkroniserar valet vid start och när inställningarna sparas.

| System | Mekanism |
| --- | --- |
| Windows | `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\PayPaminFlow` med `pythonw.exe` |
| macOS | `~/Library/LaunchAgents/se.paypamin.flow.plist` |
| Linux | `$XDG_CONFIG_HOME/autostart/paypamin-flow.desktop`, normalt `~/.config/autostart/` |

Stäng av eller aktivera via **Inställningar → Starta PayPamin Flow automatiskt när jag loggar in**. Om appmappen flyttas, starta appen en gång från den nya platsen så uppdateras sökvägen. Autostart sker efter inloggning och öppnar inget konsolfönster.

## Applikationsikon

Ikonen föreställer ett fakturadokument med **P** och en grön betalningsmarkering. Original och skrivbordsformat ligger i `assets/`:

- `paypamin_flow.svg` – vektororiginal.
- `paypamin_flow.png` och storleksvarianter – Tkinter, systemfält och Linux.
- `paypamin_flow.ico` – Windows, flera inbäddade storlekar.
- `paypamin_flow.icns` – macOS-ikonkälla.

Generera om raster- och skrivbordsikoner med Pillow installerat:

```sh
python assets/build_icons.py
```

## Skapa Python-releasepaket

Det finns inget PyInstaller- eller native-byggsteg. Skapa det plattformsoberoende paketet och dess kontrollsumma med:

```sh
python packaging/package_release.py --output release-assets
```

GitHub Actions-workflöen i `.github/workflows/build.yml` kör testerna på Windows, macOS och Linux. Ubuntu-jobbet skapar Python-ZIP och SHA-256-fil. Vid en framtida, uttryckligen beställd release kan samma två filer bifogas releasen för appens uppdateringsfunktion.

## Kostnadsfri Fortnox-import utan API

Appen behöver ingen Fortnox-integrationslicens för PDF-importen:

1. Exportera eller spara en faktura-PDF från Fortnox i appens `import/`-mapp. Knappen **Öppna importmapp** öppnar rätt plats.
2. Appen kontrollerar mappen var femte sekund. En ny eller ändrad PDF måste ha samma storlek och tidsstämpel vid två kontroller, så att appen inte läser en halvfärdig export.
3. Den färdiga PDF:en öppnas automatiskt i den befintliga förhandsgranskningen. Kontrollera och godkänn uppgifterna innan fakturan sparas.
4. Dubbletter stoppas utan extra popup vid automatisk körning. En sammanfattning visas när något importerats eller när ett fel behöver åtgärdas.

Bevakningen fungerar även när huvudfönstret ligger i systemfältet; fönstret öppnas när en faktura behöver granskas. Stäng av eller aktivera funktionen under **Inställningar → Bevaka importmappen och importera nya PDF:er automatiskt**. **Skanna importmapp** kan alltid användas manuellt, även för en fil som du tidigare avbrutit.

Detta är ingen direkt API-koppling: exporten från Fortnox görs fortfarande manuellt. Appen loggar inte in i Fortnox och skickar inga uppgifter dit.

## Fakturor, logotyper och OCR

- Lägg faktura-PDF:er i `import/` för automatisk bevakning, klicka **Skanna importmapp** för en direkt genomsökning, eller använd **Lägg till faktura-PDF**.
- Kontrollera föreslagna värden och godkänn dem innan en påminnelse skapas.
- Lägg egna SVG-logotyper i `svg/`; dessa är företagslogotyper och ska inte förväxlas med appens ikon i `assets/`.
- Genererade PDF-filer läggs i `export/`.

OCR för skannade PDF:er kräver Tesseract med svenska språkdata (`swe`) och Poppler:

- **Windows:** installera Tesseract OCR och Poppler och lägg dem i PATH.
- **macOS:** `brew install tesseract tesseract-lang poppler`.
- **Debian/Ubuntu:** `sudo apt install tesseract-ocr tesseract-ocr-swe poppler-utils`.

## Lokal lagring och integritet

- Databas, mallar, inställningar och fellogg sparas i användarprofilen under `~/.paminnelseapp`. Det befintliga katalognamnet behålls så att tidigare data inte försvinner efter namnbytet.
- `import/`, `export/` och `svg/` ligger i den skrivbara Python-appmappen.
- Kundfakturor, exporter, lokala databaser, loggar och företagslogotyper ska inte checkas in. Se `.gitignore`.
- Felloggen kan innehålla tekniska fel och filvägar. Granska den innan den delas.
- Använd appens ZIP-säkerhetskopior regelbundet och före en manuell ominstallation.

## Tester

```sh
python -m unittest discover -s tests -v
```

Parser-, importbevaknings-, autostart-, ikon-, språk-, valuta-, databas-, säkerhetskopierings-, systemfälts-, paket- och uppdateringstester använder syntetiska data och kräver ingen grafisk skrivbordssession. Översättningstesterna kontrollerar att nya texter har engelska översättningar och matchande variabler. Testa alltid ändringar mot riktiga, noggrant granskade exempel före skarp användning.

## Begränsningar

- PDF-layout och OCR kan misstolka fält. Kontrollera fakturan före godkännande.
- Betalstatus uppdateras inte via Fortnox. Kontrollera betalningar manuellt före utskick.
- Dagregler, avgifter, ränta och avtalsvillkor måste verifieras för verksamheten.
- Automatisk e-post eller automatisk ansökan till Kronofogden ingår inte.

## Copyright och licens

**Copyright © 2026 Rickard Länkvist. Skapare: Rickard Länkvist.** Se `NOTICE`.

Ingen separat användarlicens är vald. Normalt upphovsrättsskydd gäller, och rätt att återanvända eller distribuera koden ges inte automatiskt.
