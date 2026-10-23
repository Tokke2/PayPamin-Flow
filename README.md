# PayPåminn Flow

Lokal Windows-app för att läsa enskilda Fortnox-fakturor från PDF, skapa betalningspåminnelser som PDF och hålla reda på nästa steg. Fakturor och kunduppgifter behandlas lokalt; appen ansluter inte till Fortnox och skickar inte e-post eller Kronofogden-ärenden automatiskt.

> **Projektstatus:** tidig prototyp. Avläsning och mallar måste kontrolleras mot riktiga fakturor innan appen används skarpt.

## Funktioner

- Läser enskilda faktura-PDF:er. Fält som föreslås är kund, fakturanummer, fakturadatum, förfallodatum, beloppet efter **ATT BETALA** och fakturatext.
- Importmapp och knapp för att skanna nya PDF-filer. Varje fil öppnas för granskning innan den sparas; redan importerade filer hoppas över.
- PDF-förhandsgranskning med möjlighet att markera fältområden. Matchningsrutor och leverantörsmallar sparas lokalt; flera exempel används för att robustare placera fälten.
- SVG-logotyp väljs i huvudfönstrets meny. Den kan kopplas till en leverantörsmall och återanvändas för framtida fakturor från samma leverantör.
- Importerade uppgifter måste godkännas innan fakturan kan bli aktuell för påminnelse.
- P1/P2/Kronofogden-granskningssteg, justerbara dagintervall, påminnelseavgift, betalningsfrist och räntesats.
- PDF skapas i `export/` och öppnas automatiskt i datorns standardprogram för PDF.
- Fellogg öppnas via appens **Visa fellogg**-knapp.

## Windows: starta utan konsolfönster

1. Installera Python 3.10 eller senare och se till att **Add Python to PATH** är valt.
2. Hämta eller klona repot.
3. Dubbelklicka på `start_paypaminn_flow.vbs`.

Appen kontrollerar vid start efter nödvändiga Python-paket och kan installera saknade paket från PyPI. Det kräver internet. Du kan också installera dem manuellt:

```powershell
py -m pip install -r requirements.txt
```

För felsökning kan appen startas från PowerShell:

```powershell
py paypaminn_flow.py
```

## Fakturor och logotyper

- Lägg faktura-PDF:er i `import/` och klicka **Skanna importmapp**, eller använd **Lägg till faktura-PDF**.
- Kontrollera de föreslagna värdena. Markera fält i PDF-förhandsgranskningen och spara matchningar som mall om en position blir fel.
- Lägg SVG-logotyper i `svg/`. Välj logotyp i huvudfönstret; matcha den mot leverantörsmallen i PDF-förhandsgranskningen.
- Genererade PDF-filer läggs i `export/`.

OCR för skannade PDF:er kräver även Tesseract OCR med svenska språkdata (`swe`) och Poppler installerat i Windows. Appens Python-tillägg räcker inte ensamma för OCR.

## Lokal lagring och integritet

- Fakturor, matchningsmallar, inställningar och fellogg sparas lokalt i användarprofilen under `.paminnelseapp`.
- PDF-fakturorna i `import/`, exporter i `export/`, SVG-logotyper och lokal databas ska inte checkas in. Se `.gitignore`.
- Felloggen sparar inte hela fakturatexten, men kan innehålla tekniska fel och filvägar. Granska den innan den delas.
- Ta säkerhetskopia av den lokala databasen och mallarna innan uppdatering eller ominstallation.

## Tester

Kör parser-tester med:

```powershell
py -m unittest discover -s tests -v
```

Testerna använder syntetisk fakturatext och innehåller inga riktiga kunduppgifter.

## Begränsningar att känna till

- PDF:er skiljer sig åt; OCR och automatisk avläsning kan misstolka fält. Kontrollera fakturan före godkännande.
- Status för betalning uppdateras inte via Fortnox. Importera eller kontrollera betalningar manuellt innan utskick.
- Dagregler, avgifter, ränta och avtalsvillkor måste verifieras för den enskilda verksamheten.
- Ingen automatisk e-postsändning eller automatisk ansökan till Kronofogden ingår.

## Licens

Ingen licens är vald ännu. Om repot publiceras utan licens gäller normalt upphovsrättsligt skydd: andra får inte automatiskt rätt att återanvända eller distribuera koden. Välj och lägg till en licens innan du bjuder in externa bidrag.
