# PayPamin Flow

Lokal Python-skrivbordsapp för **Windows, macOS och Linux** som läser Fortnox-fakturor och kundreskontralistor från PDF, skapar betalningspåminnelser som PDF och håller reda på nästa steg. Fakturor och kunduppgifter behandlas lokalt; appen ansluter inte till Fortnox och skickar inte e-post eller Kronofogden-ärenden automatiskt.

- **Skapare och upphovsman:** Rickard Längkvist
- **Copyright:** © 2026 Rickard Längkvist

> **Projektstatus:** tidig prototyp. Avläsning och mallar måste kontrolleras mot riktiga fakturor innan appen används skarpt.

## Funktioner

- Läser svenska och engelska faktura-PDF:er och föreslår kund, fakturanummer, datum, slutbelopp och fakturatext. Beloppsläsningen klarar hela belopp och decimaltal i svenska, europeiska och engelska format samt etiketter som **ATT BETALA**, **Total due**, **Amount due** och **Balance due**, utan att använda moms eller subtotal som slutbelopp. Explicit **Fakturatext/Avser** prioriteras och kan omfatta flera rader; tabellrubriker, numeriska kolumner och summeringsrader rensas konservativt.
- **Valuta per faktura** med SEK som standard och redigerbara ISO-koder, exempelvis EUR, USD, NOK och DKK. Belopp växlas inte mellan valutor.
- **Automatisk bevakning av importmappen** upptäcker nya Fortnox-PDF:er utan API eller integrationslicens. Filer väntas in tills de är färdigskrivna och varje ny faktura granskas innan den sparas. Dubbletter stoppas via fakturanummer, sökväg eller identiskt PDF-innehåll, även om filen döpts om.
- **Kundreskontralista från PDF:** välj en komplett Fortnox-lista via Arkiv-menyn. Efter lyckad kontroll av sidor, fakturaantal och totalsumma körs importen direkt utan en separat Ja/Nej-granskning. Befintliga fakturor som finns i listan får sitt betalbelopp uppdaterat från Belopp/Saldo, och saldo 0 markeras som helt betalt. Fakturor som fanns i en tidigare lista men saknas i en senare importerad komplett SEK-lista markeras också automatiskt som betalda, **även när den nya listan har samma listdatum**, utan att deras poster eller påminnelsehistorik tas bort. Ett äldre listdatum stoppas fortfarande. Första listan bygger historik för frånvaroregeln och betalmarkerar inte app-fakturor enbart för att de saknas där; icke-SEK-listor ändrar inte befintliga raders betalstatus automatiskt. En fredagspåminnelse underlättar veckovis import. En ifylld referens-/fakturatext sparas på nya fakturor och följer med till P1/P2 som **Avser**; tom text lämnas tom och en återimport skriver inte över en befintlig fakturas sparade text.
- **P1/P2-dialog efter importmappsskanning:** efter manuell eller automatisk behandling av PDF-filer visar en dialog fakturanummer, kund och nivå för fakturor som är redo för P1 eller P2. Betalda, ignorerade, ogranskade och väntande fakturor aviseras inte; ingen påminnelse skapas automatiskt.
- **Färgade statusrader:** grön bakgrund betyder att fakturan förfaller i dag eller senare och inte har P1/P2, gul betyder att P1 ska skapas eller finns utan aktuell P2, och röd betyder att P2 ska skapas eller finns. P2 har företräde framför P1. Betalda, ignorerade, ogranskade och förfallna rader som ännu väntar på P1 lämnas utan statusfärg; den skriftliga statuskolumnen finns kvar.
- **Flikbaserade fakturavyer med sökning och sortering:** välj direkt mellan **Aktuella**, **Historik / arkiverade / betalda**, **Alla**, **Ignorerade** och **Kronofogden – granska**. Historikfliken visar helt betalda samt ignorerade/arkiverade poster med deras belopp och P1/P2-/e-posthistorik kvar. Aktiva obetalda fakturor blandas inte in, och inget flyttas eller raderas i databasen när du byter flik. Sök fritt på kund eller fakturanummer och sortera genom att klicka på kolumnrubrikerna; fakturanummer sorteras numeriskt och en andra klickning vänder ordningen. Högerklicksmenyn kan öppna sparad original-PDF samt senaste befintliga påminnelse-PDF, med P2 före P1 även när filen ligger i `export/arkiv/<kund>/` eller det äldre platta `export/arkiv/`.
- **Självlärande som kan granskas:** appen lär sig lokalt av fakturor du har sparat och leverantörsmallar du har bekräftat. Återkommande värden för kundens e-post, logotyp, valuta, fakturatext och leverantörens betalningsfrist samt leverantörens PDF-layout återanvänds nästa gång. Stark och upprepad evidens tillämpas automatiskt; osäkra förslag frågar först. Under **Inställningar → Granska inlärning** ser du allt appen lärt sig och kan glömma enskilda värden eller allt. Inlärningen stannar i den lokala databasen och påverkar aldrig fakturor, påminnelser eller mallar när den glöms.
- **Återanvändbara kundkontakter och kundlogotyper:** högerklicka på en faktura och välj **Redigera kund** för kundnamn och flera e-postadresser separerade med komma. Adresslistan sparas i databasen och JSON-journalen och fylls i automatiskt på nästa faktura till samma normaliserade kundnamn, även vid manuell inmatning utan förifylld dialog. Senaste icke-tomma SVG-logotyp som sparats på kundens faktura återanvänds också på nästa faktura och för äldre fakturor utan eget val. En explicit faktura-/leverantörslogotyp eller medvetet val av **Ingen logotyp** skrivs inte över. Kundens e-post och logotyp ingår i JSON-säkerhetskopior utan att en äldre journal ersätter en senare lokal logotyp.
- **E-postutkast efter generering:** när P1/P2 har skapats kan ett kundfärdigt, språkanpassat utkast till alla kundens adresser och med dold kopia till `rl@tadega.com` öppnas i systemets valda e-postapp efter förhandsgranskning. Texten skiljer P1 från P2 och innehåller belopp, avgifter, totalsumma och betalningsfrist. När Thunderbird är standardapp i Windows bifogas senaste påminnelse-PDF automatiskt; andra e-postprogram använder `mailto:` och manuell bifogning. Inget mejl skickas automatiskt. Om kunden saknar adresser öppnas ingen e-postapp.
- **Förhandsgranskning och separerad e-poststatus:** innan e-postappen öppnas visas mottagare, fast BCC, ämne, redigerbart meddelande och PDF-sökväg i appen. Ändringar gäller bara det aktuella utkastet; avbryt öppnar inget och sparar ingen utkaststatus. Listan skiljer skapad PDF, öppnat utkast och manuellt bekräftad skickad e-post för P1/P2 utan att blanda ihop datumen.
- PDF-förhandsgranskning med markerbara fältområden och återanvändbara leverantörsmallar. Leverantörs-/mallvalet kan matchas mot sparat organisationsnummer, bankgironummer, leverantörsnamn, logotypalias och, vid en PDF med en faktura, logotypens visuella utseende. Markerade belopp och fakturatext använder samma tolkning som automatisk import. En beloppsruta med flera oetiketterade eller tvetydiga tal skriver inte över det tidigare värdet; markera i stället en snävare ruta runt etiketten och slutbeloppet.
- Innan **P1** skapas kontrolleras en befintlig original-PDF mot fakturans sparade fakturanummer, kund, datum, belopp, valuta och fakturatext. Sparade fältmallar används vid kontrollen; avvikelser stoppar P1 utan att ändra fakturan eller påminnelsehistoriken. För en reskontraimporterad faktura erbjuds i stället valet **Använd reskontraunderlag för P1?** om original-PDF:en är oläslig eller avviker. Ett uttryckligt ja använder den sparade reskontraraden för P1 och loggar valet; ett nej skapar ingen P1. Original-PDF och reskontravärden ändras inte av valet. Fakturor utan reskontraunderlag behåller den strikta spärren, och manuella fakturor utan PDF fungerar som tidigare.
- SVG-logotyp kan kopplas till en leverantörsmall och återanvändas vid export. Ett logotypval i PDF-matchningen sparas även direkt på fakturan och följer med till P1/P2 utan att fältmallen behöver sparas; valet påverkas inte av en senare global logotypändring.
- Manuell granskningsgräns, P1/P2/Kronofogden-steg, justerbara dagar, avgift, betalningsfrist och ränta. **Skapa påminnelse** skapar en aktuell men saknad P1 och kan därefter fortsätta till P2 i samma klick när både P2-intervallet och P1:s sparade betalningsfrist har passerat; inget steg skapas i förtid. **Redigera P1** och **Redigera P2** kan byta logotyp och skriva om den befintliga nivåns PDF med ursprungligt datum, originaldata och oförändrade villkor/historik via interna P1/P2-snapshots; den gamla filen bevaras om skrivningen misslyckas. Om en registrerad P1-PDF saknas återskapas den först med ursprungligt datum och oförändrad historik, varefter en aktuell P2 kan skapas. En skadad eller oläsbar SVG ger ett tydligt fel i stället för att tyst ersättas med textlogotyp. Om fakturatext saknas eller bara innehåller blanksteg utelämnas **Avser**-raden helt i nya eller medvetet återskapade P1/P2-PDF:er, utan standardtext eller extra radavstånd; ifylld text visas som tidigare.
- **Tydlig logotyp och textgränssnitt:** fakturadokument med P-märke och turkos bock används som appikon i fönster, dialoger, systemfält, aktivitetsfält, Aktivitetshanterarens appvy, Dock, Linux och Windows-autostartgenväg. Den horisontella PayPamin Flow-logotypen finns i sidhuvud och Om-fönster. Menyer, verktygsknappar, högerklicksmenyer och dialogknappar visar i stället tydlig text utan funktionsikoner på svenska och engelska.
- **Stäng eller minimera till systemfältet:** fönstrets stäng- och minimeringsknappar döljer appen medan schemalagda kontroller fortsätter. Systemfältets högerklicksmeny innehåller **Öppna**, **Uppdatera appen** och **Avsluta helt**. **Arkiv → Avsluta helt** eller systemfältets **Avsluta helt** stänger appen helt.
- **Detaljerad aktivitetslogg:** knappar, menyer, systemfältsåtgärder, filter, fakturaval, uppdateringar och övriga viktiga händelser loggas strukturerat med start, slut/fel, varaktighet, sessions-ID och spårnings-ID. Befintliga detaljposter för PDF, reskontra, e-post, säkerhetskopior och bakgrundsjobb finns kvar i samma tekniska logg.
- **Dagligt loggarkiv och bestående fellogg:** tekniska loggfiler vars senaste skrivning är från gårdagen eller tidigare flyttas till `logs/arkiv/ÅÅÅÅ-MM-DD/`. Olösta fel ligger kvar i den separata `logs/errors.log` även när källoggen roteras eller arkiveras. Först när du uttryckligen väljer **Hjälp → Markera fellogg som åtgärdad** markeras de granskade felen som åtgärdade och en kopia sparas i loggarkivet.
- **Lokal säkerhetskopiering och återställning** av inställningar, fakturor, påminnelser och logotyper via Arkiv-menyn.
- **Alltid minimerad start och autostart:** appen startar i systemfältet vid autostart, manuell start, direktstart och uppdateringsomstart. Öppna fönstret via systemfältet eller genom att starta appen igen; en ny start visar och fokuserar då den befintliga instansen. Autostart vid inloggning finns på Windows, macOS och Linux och är aktiverad som standard. Båda inställningarna kan ändras under **Inställningar**.
- **Svenska och engelska** med direkt språkbyte, sparat språkval och översatta meddelanden, statusar, belopp, datum och påminnelse-PDF:er.
- **Automatiska Python-uppdateringar mot GitHub Releases** två gånger per dygn, med commit- och filjämförelse, SHA-256-verifiering och tyst omstart. Både nyare versioner och verkligt ändrade release-byggen med samma versionsnummer upptäcks. Manuell sökning och installation finns via den tydliga **Uppdatera appen**-knappen, **Hjälp → Uppdatera appen** eller systemfältets högerklicksmeny.
- PDF sparas lokalt och öppnas i datorns standardprogram. **Öppna exportmapp** i knappraden eller under **Arkiv** öppnar mappen med skapade påminnelser i datorns filhanterare. Den samlade felloggen öppnas via **Visa samlad fellogg** eller **Hjälp → Visa samlad fellogg**.
- **Automatiskt påminnelsearkiv i kundmappar:** vid appstart och därefter regelbundet flyttas igenkända P1/P2-PDF:er från och med dagen efter sitt ursprungliga påminnelsedatum från `export/` till `export/arkiv/<kund>/`. Kundmappen bestäms från fakturans sparade P1/P2-data, inte genom att gissa ett delat filnamn; en fil utan entydig kundkoppling lämnas kvar och loggas. Även filer i det tidigare platta `export/arkiv/` flyttas till rätt kundmapp när kopplingen finns. Fakturor och påminnelsehistorik ändras inte, arkiverad P1/P2 kan fortfarande öppnas och redigeras och befintliga arkivfiler skrivs aldrig över.

## Tangentbord och tillgänglighet

- **Tab / Shift+Tab** flyttar fokus i den visuella ordningen. Knappar, fält, flikar, fakturalistan, textytor och PDF-ytan har tydlig fokusmarkering; dialoger har en egen fokusordning.
- **F1** öppnar **Kortkommandon och tillgänglighet**. **F10** eller **Alt+A** öppnar Arkiv-menyn och **Alt+H** öppnar Hjälp-menyn, som sedan används med piltangenter och Enter.
- Huvudgenvägar: **Ctrl/Cmd+F** sök, **Ctrl/Cmd+N** manuell faktura, **Ctrl/Cmd+O** faktura-PDF, **Ctrl/Cmd+E** eller **F2** redigera vald, **F5** skanna importmappen, **Ctrl/Cmd+Enter** öppna original-PDF, **Ctrl+Tab / Ctrl+Shift+Tab** växla fakturaflik och **Shift+F10** öppna vald fakturas meny.
- **Ctrl/Cmd +**, **Ctrl/Cmd −** och **Ctrl/Cmd 0** ökar, minskar eller återställer textstorleken. Samma val finns i **Inställningar → Textstorlek** och i hjälpfönstret. Skalning 80–200 % sparas i den lokala inställningen och JSON-journalen och påverkar menyer, knappar, formulär, flikar, listor och textytor i öppna och nya fönster.
- Dialoger kan ändra storlek och långa formulär har vertikal och vid behov horisontell rullning. När ett fält eller en knapp får fokus rullas den automatiskt fram, så att även Spara/Stäng kan nås vid 200 % text eller på en liten skärm. E-postmeddelandet har egen vertikal rullning.
- **Högkontrast följer operativsystemet.** Windows högkontrast, macOS Öka kontrast och GNOME/GTK:s högkontrastläge eller HighContrast-tema aktiverar en särskild palett för ttk-kontroller, klassiska textytor, PDF-ytor, fokus och menyer. Ändringar upptäcks automatiskt utan omstart; om skrivbordsinställningen inte kan läsas behålls appens vanliga kontrasttestade palett.
- Textstorleken ändrar endast appens gränssnitt. Fakturadata, skapade P1/P2-PDF:er och e-posthistorik ändras inte. Textkontrasten och den skriftliga statusen är bevarade även med färgade fakturarader; funktionsknappar och menyer använder fortsatt text utan funktionsikoner.
- Riktiga Tk-widgets testas automatiskt i CI med display på skrivbordsplattformarna och Xvfb på Ubuntu. En separat [manuell checklista för NVDA, VoiceOver och Orca](ACCESSIBILITY_TESTING.md) används för uppläsning, eftersom automatiska widgettester inte ensamma kan verifiera skärmläsarstöd.

## Python-only – ingen EXE eller native-app

PayPamin Flow distribueras som **Python-källkod**, inte som EXE, macOS-app eller native Linux-binär. Samma releasepaket används på alla tre plattformarna:

- `PayPamin-Flow-Python.zip`
- `PayPamin-Flow-Python.zip.sha256`
- `PayPamin-Flow-Python.manifest.json` – release-commit och SHA-256 för varje distribuerad fil.

Python **3.10 eller senare** och Tkinter krävs. Packa upp ZIP-filen i en mapp där din användare har skrivrättigheter och installera tilläggen:

```sh
python -m pip install -r requirements.txt
```

Använd `py -m pip` i Windows om det är det kommando som pekar på din Python-installation. Appen kan också installera saknade Python-tillägg i bakgrunden utan att öppna ett konsolfönster.

## Starta utan konsolfönster

### Windows

1. Dubbelklicka på **`start_paypamin_flow.vbs`**. Startaren kontrollerar att en startbar Python finns i `PATH`, via Python Install Manager eller på vanliga installationsplatser. Den öppnar inget konsolfönster.
2. Om Python helt saknas installeras managerens aktuella rekommenderade stabila standardversion automatiskt. Vid behov installeras först den officiella Python Install Manager med WinGet. Installationssteget nås inte när en befintlig Python hittats eller när kontrollen har misslyckats och resultatet därför är osäkert.
3. En befintlig Python används alltid oförändrad. Startaren uppdaterar inte Python-runtime och installerar inte en ny version bredvid en befintlig installation.
4. En befintlig Python som hanteras av Python Install Manager, system-Python eller en virtuell miljö används utan att ersättas eller uppdateras externt. Appen skapar ingen parallellinstallation.

Startaren använder `pythonw.exe` när det finns och den gemensamma `paypamin_flow_launcher.py`. Vid enbart `python.exe` håller Windows Script Host processen dold. Appen lägger dessutom `CREATE_NO_WINDOW` på hjälpprogram som startas för exempelvis PDF/OCR. Windows-autostart använder samma VBS-startare och runtime-kontroll; appens autosynk uppdaterar äldre autostartgenvägar. Den äldre `paypamin_flow.pyw` finns kvar för kompatibilitet men används inte av Windows startkommando eller autostart.

För felsökning från en redan öppen PowerShell kan `py paypamin_flow.py` användas.

### macOS

1. Installera Python 3.10+ med Tkinter och Python Launcher, till exempel det officiella installationspaketet från python.org.
2. Installera tilläggen enligt ovan.
3. Öppna **`paypamin_flow.pyw`** med Python Launcher. Python Launchers alternativ att köra i Terminal ska vara avstängt. Startaren loggar eventuella startfel och visar ett felmeddelande utan att öppna Terminal.

Autostart och omstart efter uppdatering använder Python direkt via LaunchAgents respektive appens befintliga process och öppnar inte Terminal. En separat `.command`-startare används inte eftersom macOS annars kan öppna Terminal. PayPamin Flow uppdaterar eller ersätter inte Apples/systemets Python och installerar inte en ny python.org-runtime bredvid en befintlig installation.

### Linux

På Debian/Ubuntu installeras skrivbords- och Python-stöd med:

```sh
sudo apt install python3 python3-pip python3-tk
python3 -m pip install -r requirements.txt
./packaging/install_linux.sh
```

Starta därefter **PayPamin Flow** från programmenyn. Skrivbordsposten har `Terminal=false`. Installationen är per användare och kopierar Python-filerna till `~/.local/share/paypamin-flow` som standard. Du kan också köra `./start_paypamin_flow.sh` eller `python3 paypamin_flow_launcher.py` direkt från appmappen.

På system med externally managed Python kan en virtuell miljö användas. Skapa miljön, installera `requirements.txt` i den och ange dess Python med miljövariabeln `PYTHON` när installationsprogrammet körs. `start_paypamin_flow.sh` kontrollerar den valda tolken respektive `python3`/`python`, men uppdaterar eller ersätter aldrig system-Python och skapar ingen automatisk parallellinstallation.

## Python och valfria tilläggsuppdateringar

- En befintlig Python-runtime uppdateras **inte vid appstart** och ersätts inte av PayPamin Flow. Windows-startaren installerar Python endast om ingen fungerande Python hittas.
- Vid start kontrolleras att nödvändiga Python-tillägg finns. Saknade tillägg kan återställas i bakgrunden utan att befintliga tillägg uppgraderas.
- Välj **Hjälp → Uppdatera Python-tillägg** för att manuellt uppdatera appens tillägg. Appen frågar först och använder den befintliga Python-miljön; ingen egen virtuell miljö eller parallell Python-runtime skapas. Starta om appen efter en lyckad uppdatering.
- Automatiska veckouppdateringar av Python-runtime och tillägg körs inte längre. Ett misslyckat manuellt tilläggsförsök lämnar appen med befintliga tillägg och loggas.
- Den separata funktionen **Uppdatera appen** för PayPamin Flows egna releasefiler är oförändrad.

## Om appen inte startar

Kontrollera först att **Python 3.10 eller senare med Tkinter** är installerat och kör `python -m pip install -r requirements.txt` i appmappen. Den konsolfria startaren skriver import- och startfel till **`~/.paminnelseapp/logs/startup.log`**, uppdaterar även den samlade felloggen och försöker visa felet i ett systemmeddelande. För terminalfelsökning kan `python3 paypamin_flow.py` användas på Linux/macOS eller `py paypamin_flow.py` på Windows.

## Samlad fellogg för snabb felsökning

Välj **Visa samlad fellogg** i knappraden eller **Hjälp → Visa samlad fellogg**. Appen uppdaterar då och öppnar **`~/.paminnelseapp/logs/errors.log`** direkt i systemets textprogram.

- Samlingsfilen hämtar kompletta `ERROR`- och `CRITICAL`-block med stackspår från `logs/app.log` och dess rotationer, startfel från `logs/startup.log` samt fel och rollback-information från `logs/update.log` och andra app-loggar i samma loggkatalog. Vid första start flyttas kända äldre loggar och rotationer från appdatamappens rot till `logs/`; befintliga filer skrivs inte över och namnkonflikter får prefixet `legacy-`.
- Posterna sorteras med nyaste fel först och exakta dubbletter från roterade eller kopierade loggar slås samman. Källfilen och tiden anges för varje fel. **Olösta fel tas inte bort när en källogg roteras, arkiveras eller inte längre finns i den aktiva loggmappen.**
- Vyn byggs om atomiskt vid appstart, en gång i minuten medan appen körs och varje gång den öppnas. Ett misslyckat skrivförsök lämnar den tidigare samlingsfilen orörd. Efter felloggsuppdateringen arkiveras tekniska loggfiler vars senaste skrivning är från gårdagen eller tidigare under **`logs/arkiv/ÅÅÅÅ-MM-DD/`**. Dagens filer lämnas kvar. Arkivfiler skrivs inte över, namnkonflikter får `legacy-`-prefix och symlinks följs inte. Den tekniska loggen roteras vid midnatt och vid 5 MB med unika rotationsnamn, utan att äldre rotationer raderas automatiskt.
- **`errors.log` arkiveras eller rensas inte automatiskt.** När felen är åtgärdade väljer du **Hjälp → Markera fellogg som åtgärdad** och bekräftar. Aktuella fel markeras då som lösta, en kopia sparas under **`logs/arkiv/resolved/ÅÅÅÅ-MM-DD/`** och samma gamla händelse kan inte komma tillbaka från en oförändrad källogg. Ett nytt fel med ny tidpunkt visas som en ny olöst händelse. Avbryts bekräftelsen ändras ingenting.
- Om inga olösta fel finns står det uttryckligen i filen. All diagnostik stannar lokalt; granska filvägar och tekniska uppgifter innan loggen delas.

## Systemfält och fullständig avslutning

När du stänger eller minimerar huvudfönstret döljs det i systemfältet. Appen fortsätter då med bland annat schemalagda uppdateringskontroller.

- Klicka på PayPamin Flow-ikonen eller välj **Öppna PayPamin Flow** i systemfältet för att visa fönstret igen.
- Högerklicka och välj **Uppdatera appen** för att visa fönstret och starta samma manuella uppdateringskontroll som i Hjälp-menyn. Valet visar även **Uppdatering tillgänglig**, **Söker…** eller **Uppdaterar…** när något pågår.
- Välj **Arkiv → Dölj till systemfältet** för att dölja det utan musens stängknapp.
- Välj **Arkiv → Avsluta helt** eller **Avsluta helt** i systemfältet för att avsluta bakgrundsaktiviteten och stänga appen.

Om skrivbordsmiljön inte har ett fungerande systemfält lämnas fönstret synligt och appen erbjuder ett tydligt val att avsluta i stället för att gömmas oåtkomlig. På Linux kan skrivbordets AppIndicator-/systemfältsstöd behöva aktiveras.

På Windows använder appen en egen app-identitet för aktivitetsfältets PayPamin Flow-ikon. Huvudfönstret och alla sekundära fönster får dessutom både stor och liten PayPamin Flow-ikon direkt via det **yttersta Windows-rot- och ägarfönstret**, som aktivitetsfältet, Alt+Tab och Aktivitetshanterarens appvy använder. Ikonen appliceras både under fönsteruppbyggnaden och igen efter att fönstret har mappats; huvudfönstret får den även på nytt när det återställs från systemfältet. Systemfältsikonen kan placeras under **^ / Dolda ikoner** av Windows; dra den till det synliga fältet om du vill ha den framme hela tiden. Start- och ikonfel loggas i `%USERPROFILE%\.paminnelseapp\logs\app.log`.

**Begränsning i Windows:** Aktivitetshanterarens **Detaljer**-flik och vissa bakgrundsprocessvyer kan fortfarande visa Python-ikonen. Windows hämtar då den inbäddade ikonen från `pythonw.exe`, inte från appfönstret. Att ersätta just den processikonen skulle kräva en native EXE med egen ikonresurs, vilket inte ingår i PayPamin Flows Python-only-distribution.

## Starta minimerad

PayPamin Flow startar som standard minimerad i systemfältet. Det gäller vid inloggning, manuell start, direktstart av `paypamin_flow.py`/startaren och när appen startas om efter en uppdatering. Fönstret skapas och appens schemalagda kontroller börjar direkt, men det visas inte förrän du öppnar det.

- Klicka på systemfältsikonen eller välj **Öppna PayPamin Flow**.
- Eller starta appen igen: eninstansskyddet aktiverar den befintliga appen och visar fönstret.
- Stäng av **Starta alltid minimerad i systemfältet** under **Inställningar** om du hellre vill se fönstret vid start. Flaggan `--minimized` används fortfarande av autostart och tvingar minimerad start.
- Om systemfältet inte är tillgängligt lämnas fönstret synligt i stället för att appen göms oåtkomligt.

## En aktiv appinstans

- PayPamin Flow använder en per-användarlåsning på Windows, macOS och Linux. Ett nytt startförsök startar inte en andra appinstans.
- I stället aktiveras den befintliga appen via en lokal, token-skyddad kanal och huvudfönstret visas, lyfts och får fokus även om det ligger dolt i systemfältet.
- Aktiveringskanalen lyssnar endast på `127.0.0.1` med en slumpad port och en hemlig token per instans. Den är inte exponerad mot nätverket och används inte för fakturadata eller extern kommunikation.
- Uppdateringsomstarten överlämnar instansägandet från den gamla till den nya processen efter den vanliga UI-bekräftelsen. Fullständigt avslut frigör låsningen; en kraschad process frigör den via operativsystemet.

## Självlärande

Självlärandet är aktiverat som standard och arbetar helt lokalt. Appen samlar endast in värden som du själv har sparat eller bekräftat:

- **Kund:** e-postadresser som används för påminnelser, senaste logotyp, valuta och fakturatext/**Avser** för samma normaliserade kundnamn.
- **Leverantör:** valuta, betalningsfrist i dagar mellan fakturadatum och förfallodatum samt PDF-layoutens ordval. Layouten sparas när du bekräftar en leverantör i PDF-förhandsgranskningen, och kan identifiera leverantören vid en senare import även om org.nr/bankgiro saknas.
- **Standardvärden:** tomma fält i en ny faktura fylls från tidigare sparade fakturor för samma kund eller leverantör.
- **Påminnelser:** mottagarna som faktiskt användes när ett utkast öppnades sparas per kund och används om kundens kontaktuppgifter saknas. Panelen visar även antalet påminnelser. P1/P2-standardtexterna, tidsfristerna och avgifterna lärs däremot inte in automatiskt: texterna innehåller fakturaspecifika belopp och datum och förblir de fasta men redigerbara standardtexter som du har godkänt.

Trösklarna är konservativa: minst tre eniga observationer krävs för att ett värde ska tillämpas automatiskt, och minst två för att det ska visas som ett förslag. Lika vanliga motstridiga värden tillämpas aldrig. När underlaget är osäkert frågar dialogen innan förslagen används; ett nej gör att samma förslag inte upprepas förrän mer evidens har tillkommit. Automatiskt ifyllda värden visas i dialogrutan och loggas.

Öppna **Inställningar → Granska inlärning** för att se inlärda värden med antal observationer, om de är automatiska eller förslag, samt antal leverantörsmallar, PDF-zoner och påminnelser. **Glöm valt** tar bort ett enskilt värde och **Glöm allt** rensar inlärda värden och leverantörslayouter. Fakturor, kunder, påminnelser och sparade mallar ändras inte. Stäng av **Lär sig av sparade fakturor och leverantörsval** för att stoppa ny inlärning.

Inlärda värden ligger i samma lokala SQLite-databas som fakturorna och följer därför med ZIP-säkerhetskopior och återställning. De skickas aldrig över nätverket och rensas inte av cache-rensningen.

## Smart cache-rensning och betalda fakturor

- **Arkiv → Rensa cache nu** kör samma smarta filter som den automatiska rensningen. Automatisk rensning är aktiverad som standard och körs högst en gång per kalenderdygn samt vid **Avsluta helt**; den kan stängas av under **Inställningar**. Rensning vid avslut körs även om dagens automatiska rensning redan har körts, och ett cachefel hindrar inte appen från att stängas. Att stänga eller minimera fönstret till systemfältet är inte ett fullständigt avslut och utlöser därför ingen rensning.
- Daglig och manuell rensning tar endast bort appens egna Python-cachefiler och identifierbara tillfälliga uppdaterings-/backupkataloger som är äldre än 24 timmar. Vid fullt avslut rensas alla identifierade poster i samma kategorier oavsett ålder. Filtret följer inte symlänkar och rör aldrig import-PDF:er, fakturadatabasen, inställningar, mallar, logotyper, exporter, loggar eller säkerhetskopior.
- Markera en faktura och välj **Markera som betald** i knappraden eller högerklicksmenyn. Beloppet **Redan betalt** sätts till hela fakturabeloppet och statusen blir **Avslutad**. Betalda fakturor finns under **Historik / arkiverade / betalda** och **Alla**. Om markeringen var fel väljer du **Ångra betalmarkering** i knappraden eller högerklicksmenyn och bekräftar. Fakturan återförs då till **Aktuella** med det betalbelopp som fanns före markeringen; en äldre betalmarkering utan sparat föregående belopp återförs med 0 efter en tydlig varning. P1/P2-, e-post- och reskontrahistorik ändras inte. Även en helbetalmarkering från en verifierad reskontraimport kan ångras på samma sätt.
- Om samma faktura ligger kvar i importmappen hoppas den över vid senare import via fakturanummer eller PDF-identitet. Automatisk import hoppar över betalda fakturor tyst; manuella sammanfattningar visar dem separat från vanliga dubbletter. Cache-rensningen tar inte bort PDF:en från importmappen.

## Kundens e-post och P1/P2 i samma klick

1. Markera en faktura, högerklicka och välj **Redigera kund**.
2. Ange en eller flera adresser, till exempel `fornamn@example.com, ekonomi@example.com`. Mellanslag runt kommatecken och dubbletter med olika gemener/versaler hanteras automatiskt. Ogiltiga adresser stoppas med ett felmeddelande.
3. Spara. Adresslistan återanvänds nästa gång en faktura med samma normaliserade kundnamn granskas eller läggs till. Den kan också ändras genom det vanliga fakturaformulärets e-postfält.

När en påminnelse har genererats visas först en **e-postförhandsgranskning i PayPamin Flow** med samtliga sparade kundadresser, **`rl@tadega.com` som fast dold kopia (BCC)**, ämne, redigerbart meddelande och sökvägen till PDF:en. P1 och P2 får varsin färdig svensk eller engelsk kundtext med fakturanummer, förfallodatum, kvarstående belopp, aktuell avgift eller avgifter, totalsumma och betalningsfrist samt signatur från Tadega AB. Ämnesraden innehåller även leverantörsföretagets namn efter påminnelsetexten, till exempel **`Faktura 6471 – betalningspåminnelse - Laxå Glasmästeri`**. P2 behåller prefixet **SV:**/**Re:** före samma ämne. Företagsnamnet hämtas från påminnelsens sparade leverantörssnapshot; om leverantörsfältet är tomt används endast en entydig leverantörskoppling till fakturans logotyp, aldrig kundens namn eller ett gissat filnamn. E-postens standardtext anger uttryckligen att hela beloppet ska vara mottaget senast sista betalningsdag; P2 upplyser om att ärendet kan lämnas vidare utan ytterligare påminnelse. Standardtexterna nämner ingen ränta. Tillfälliga ändringar av ämne eller meddelande påverkar inte standardtexten vid nästa utkast. Först när du väljer **Öppna i e-postappen** öppnas ett `mailto:`-utkast i systemets valda e-postapp; **Avbryt** eller stängning av dialogen öppnar inget utkast och sparar ingen utkaststatus. När ett utkast öppnas i efterhand används belopp, avgifter, betalningsfrist och påminnelsedatum från respektive P1/P2-snapshot när en sådan finns. När Thunderbird är standardapp för `mailto:` i Windows skapas ett tillfälligt `.eml`-utkast med `X-Unsent: 1`. Mottagare, fast BCC, redigerat ämne/meddelande och den visade, senaste påminnelse-PDF:en ingår i utkastet, där PDF:en är inbäddad som en riktig MIME-bilaga. Thunderbird 91 eller senare öppnar filen direkt som ett redigerbart utkast utan den separata `-compose attachment=`-tolkningen. Tillfälliga utkast tas bort direkt vid startfel och PayPamin Flows egna utkastfiler äldre än 24 timmar rensas vid senare användning. Windows 11:s aktuella `UserChoice` för `mailto:` prioriteras vid identifieringen, med registrerad användar- och systemstandard som reserv. Programfilen kan hittas via Thunderbirds `App Paths`, registrerade startkommandon, `PATH` och vanliga installationsmappar. Om Thunderbird är standardapp men programfilen inte hittas visas detta uttryckligen och `mailto:` används med manuell bifogning. Tomma eller oläsbara PDF-filer stoppas före processstart, och omedelbara Thunderbird-fel loggas utan att utkaststatus registreras. Andra e-postprogram och plattformar använder vanlig `mailto:`, som inte har enhetligt stöd för bilagor; bifoga då den visade PDF:en manuellt. Oavsett väg granskar och skickar du mejlet själv. Appen skickar aldrig mejl i bakgrunden. Om både P1 och P2 skapas i samma klick öppnas utkastet för den senast skapade nivån.

**Skapa utkast i efterhand:** om adresserna saknades när påminnelsen genererades, eller har ändrats senare, spara dem först via **Redigera kund**. Högerklicka sedan på fakturan och välj **Skapa e-postutkast**. Samma förhandsgranskning visas innan e-postappen öppnas. Utkastet använder de aktuella kundadresserna och alltid senaste befintliga nivå: P2 om den finns, annars P1. Befintlig eller arkiverad PDF hittas utan att skrivas om, och varken `sent_count` eller påminnelsehistoriken ändras. Om PDF:en saknas uppmanas du att återskapa den via respektive **Redigera P1/P2** innan utkastet öppnas. I Thunderbird på Windows bifogas PDF:en automatiskt; i andra e-postprogram bifogar du den manuellt. Skicka mejlet själv som vanligt.

**PDF, utkast och skickat är olika statusar.** Kolumnen **P2-datum** visar **Skapad** när PDF:en finns; den påstår inte att e-post har skickats. Kolumnen **E-post (senaste)** visar för P2 om den finns, annars P1, om utkastet ännu inte har öppnats, när det öppnades eller när e-posten markerades som skickad. Första lyckade öppningen i e-postappen sparas som utkastdatum. Eftersom appen inte kan kontrollera e-postprogrammet sker skickadmarkering endast manuellt via högerklick → **Markera e-post som skickad** och en uttrycklig bekräftelse. Detaljraden visar e-poststatus för båda befintliga nivåer, och P1:s egna utkast- och skickaddatum behålls när P2 skapas. Dessa fyra statusfält migreras i befintliga databaser och ingår i JSON-journalen samt ZIP-säkerhetskopior utan att ändra `sent_count` eller påminnelsehändelser.

För att underlätta fortsatt konversation behåller P1 och P2 samma grundämne med fakturanumret. P2, och ett utkast för en faktura som redan har en registrerad påminnelse, får prefixet **SV:** eller **Re:**. Detta är en bästa möjliga trådkoppling: ett vanligt `mailto:` kan inte söka i mailboxen, hitta ett befintligt konversations-ID eller garantera att e-postappen grupperar utkastet som ett svar. Om e-postappen inte kopplar utkastet till rätt konversation måste du öppna den befintliga konversationen och fortsätta den manuellt.

**Skapa påminnelse** beter sig så här:

- Saknas P1 och fakturan är redo för P1 skapas den efter samma granskning och bekräftelse som tidigare.
- Saknas P1-PDF:en men P1 redan finns i historiken återskapas filen med ursprungligt datum utan en ny P1-händelse.
- Därefter skapas P2 om både inställningen **Dagar efter P1 till P2** och den betalningsfrist som sparades på P1 tillåter det. Annars stannar flödet efter P1.

**Redigera P1/P2:** markera fakturan och välj **Redigera P1** eller **Redigera P2** i knappraden eller högerklicksmenyn. Välj ny logotyp och skriv om just den nivåns PDF. Ursprungligt påminnelsedatum, originalfaktura, avgift, övriga villkor, språk, `sent_count` och påminnelsehistorik behålls. Nya P1/P2-snapshots sparas i databasen och JSON-journalen. För en äldre P2 utan snapshot fryses värdena vid den första lyckade omskrivningen. En misslyckad skrivning behåller gamla PDF:en och tidigare logotypval. Redigeringen skapar ingen ny påminnelsehändelse och skickar inget e-postutkast.

## Säkerhetskopiering och återställning

Välj **Arkiv → Säkerhetskopiera inställningar och påminnelser** och spara ZIP-filen på en säker plats. Säkerhetskopian innehåller:

- den lokala databasen med inställningar, fakturor, kundkontakter, leverantörsmallar och PDF-fältområden;
- skapade påminnelse-PDF:er från `export/`;
- företagslogotyper från `svg/`;
- ett manifest med format, version, tidsstämpel och SHA-256-kontrollsummor.

Den manuella ZIP-säkerhetskopian innehåller inte importerade originalfakturor i `import/` eller diagnostikloggar. Originalfakturorna ingår i veckans separata filpaket enligt nedan.

Välj **Arkiv → Återställ säkerhetskopia** för att återställa. Arkivets sökvägar, filtyper, kontrollsummor och SQLite-integritet kontrolleras först. Appen skapar alltid en säkerhetskopia av nuvarande data innan något ersätts. Den sparas under `~/.paminnelseapp/backups`. Om ersättningen misslyckas återställs de tidigare filerna automatiskt.

## JSON-journal och automatisk veckokopia

**`~/.paminnelseapp/reminder_journal.json`** uppdateras atomiskt direkt efter att en faktura eller inlärd leverantörsmall sparas, inställningar eller logotypval ändras, en faktura markeras som betald/ignorerad, en betalmarkering ångras eller en rad tas bort, samt efter varje **lyckad P1/P2-generering**, varje öppnat e-postutkast och varje manuell skickadmarkering. Korrigerade belopp och fakturatext samt inlärda PDF-fält och deras urval behöver därför inte vänta på veckokopian. Journalen innehåller aktuella fakturor, P1/P2:s utkast- och skickaddatum, kundkontakter och deras e-postadresser, inställningar, leverantörslogotypval, leverantörsmallarnas organisations- och bankgironummer, PDF-fältmallar och fälturval samt en bestående historik för varje påminnelse med nivå, datum, avgift, villkor, språk, logotypval, PDF-filnamn och fakturans innehåll vid tillfället. Äldre P1/P2-datum utan tidigare journal tas med automatiskt. Ett JSON-skrivfel visas för användaren; den redan sparade databasändringen påverkas inte.

- En automatisk kopia skapas **en gång per ISO-vecka medan appen körs**. Kontrollen görs vid start och därefter en gång i timmen. JSON-kopian sparas som `reminder-journal-ÅÅÅÅ-Wvv.json` under **`~/.paminnelseapp/backups/journal/`**. Samma vecka skapas även `reminder-journal-ÅÅÅÅ-Wvv-files.zip` med hela `import/`- och `export/`-mapparna, inklusive undermappar och tomma kataloger. Om någon del av veckoparet saknas eller är skadat återskapas det utan att vänta till nästa vecka.
- Efter ominstallation väljer du **Arkiv → Importera JSON-journal** och väljer huvudfilen eller en veckokopia. Fakturor, kundkontakter, inställningar, mallar och påminnelsehistorik återställs. Befintliga fakturor slås samman utan dubbletter; lokala fakturaändringar och kundkontakter skrivs inte över, medan saknade kontakter och påminnelsehistorik kompletteras. JSON-importen skriver inte över `import/` eller `export/`; packa upp veckans `-files.zip` manuellt om du även vill återställa filerna.
- JSON-filen innehåller PDF-filnamn men inte själva PDF- eller SVG-filerna. Veckans `-files.zip` innehåller originalfakturor och skapade påminnelse-PDF:er. Använd den manuella ZIP-säkerhetskopian för att även flytta logotypfiler. Påminnelsehistoriken finns även i databasen och följer därför med manuella ZIP-säkerhetskopior.

## Uppdateringar i appen

Appen kontrollerar den senaste stabila GitHub-releasen en kort stund efter start och därefter **var 12:e timme medan appen körs**, även när fönstret ligger i systemfältet. Automatiska uppdateringar är aktiverade som standard och kan stängas av under **Inställningar**.

Vid en nyare version eller ett ändrat officiellt bygge av samma version hämtas samma Python-ZIP för Windows, macOS och Linux. Ett litet release-manifest innehåller full commit, SHA-256 för varje distribuerad fil och ett samlat fil-fingeravtryck. Vid samma versionsnummer jämför appen installerad commit och fil-fingeravtryck med releasen: **om något av dem skiljer sig finns en uppdatering**. Ett nytt numeriskt release-ID med oförändrad commit och identiska filer installerar därför inte om samma innehåll. Äldre installationer som bara har release-ID använder det som kompatibilitetsväg tills de har tagit emot det nya uppdateringsformatet. En lägre version erbjuds inte som nedgradering. Kontrollen går mot GitHubs **latest release**, inte mot `main`.

Kontrollsumman verifieras, arkivets sökvägar och filer valideras och Python-filerna syntaxkontrolleras innan något ersätts. För nya release-manifest måste även det uppackade paketets commit, release-ID och fil-fingeravtryck matcha manifestet. Appen ersätter endast egna program-, start-, dokumentations- och ikonfiler. Databas, `import/`, `export/`, `svg/` och andra användardata ingår inte och lämnas orörda. Installationer med den äldre uppdateraren, som endast jämför versionsnummer, måste installera det första paketet med release-ID-stöd manuellt en gång.

Installationen sker **inuti appen**; du ska inte starta någon separat uppdateringsfil. Därefter startas den uppdaterade Python-appen om utan konsolfönster. Gamla programfiler används som reserv under ersättningen och återställs om installationen eller omstarten misslyckas. Den gamla appen stängs först när den nya processen har bekräftat att gränssnittets händelseloop startat via en engångsbekräftelse med PID och token. Vid timeout eller tidigt avslut stoppas den misslyckade nya processen, filerna rullas tillbaka och den gamla appen lämnas användbar.

Automatisk installation startar först när både Python-ZIP och SHA-256-fil finns i releasen. Om en release fortfarande publiceras väntar appen tyst till nästa kontroll i stället för att göra ett misslyckat installationsförsök. Under installationen visar uppdateringsknappen stegen **Hämtar och verifierar**, **Installerar filer** och **Startar om**.

Manuell kontroll görs med den framhävda knappen **Uppdatera appen**, **Hjälp → Uppdatera appen** eller **Uppdatera appen** i systemfältets högerklicksmeny. Systemfältsvalet visar fönstret först så att dialogen inte öppnas bakom en dold app. När en uppdatering hittats ändras knapp- och menytexten till **Uppdatering tillgänglig** och den sparade dialogen öppnas direkt utan en onödig ny nätverkkontroll. Dialogen visar om ändringen gäller version, commit, filer eller båda, samt installerad och tillgänglig commit. Välj **Installera och starta om**, **Öppna nedladdningssida** eller **Sök igen** för att tvinga en färsk GitHub-kontroll. Om ZIP eller kontrollsumma saknas visas detta och installationsknappen är avaktiverad tills filerna är klara. Officiella byggen visar även sin commit under **Om PayPamin Flow**.

Kontrollen använder GitHubs publika API och skickar inga faktura-, kund- eller inställningsuppgifter. Automatiska nätverks- och installationsfel loggas utan popup och provas igen vid nästa schemalagda kontroll. Appmappen måste vara skrivbar för den aktuella användaren. Tekniska installationsfel loggas i `~/.paminnelseapp/logs/update.log`.

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
| Windows | `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\PayPamin Flow.lnk`, med PayPamin Flow-ikon och `wscript.exe start_paypamin_flow.vbs --minimized`, vilket ger samma runtime-kontroll och konsolfria start som manuell start |
| macOS | `~/Library/LaunchAgents/se.paypamin.flow.plist` |
| Linux | `$XDG_CONFIG_HOME/autostart/paypamin-flow.desktop`, normalt `~/.config/autostart/` |

Stäng av eller aktivera via **Inställningar → Starta PayPamin Flow automatiskt när jag loggar in**. Windows-genvägen skapas atomiskt med Windows eget genvägsgränssnitt via dold PowerShell och får explicit appens `.ico`-fil. Den tidigare registerposten under `CurrentVersion\Run` tas bort vid synkronisering så att ingen dubbelstart sker. Autostartkommandot använder **inte `.pyw`**. Om appmappen flyttas, starta appen en gång från den nya platsen så uppdateras sökvägen. Autostart sker efter inloggning och öppnar inget konsolfönster.

## Logotyp och appikon

Huvudikonen föreställer ett vitt fakturadokument med blått **P-märke** och en grönturkos **bock** på mörkblå bakgrund med en diskret ljus kant. Den är ritad för att vara tydlig även i små storlekar och används i stället för Pythons ikon. Samma motiv används för huvudfönster, sekundära fönster, systemfält, aktivitetsfält, Aktivitetshanterarens appvy, macOS Dock, Linux och Windows-autostartgenväg.

Den horisontella logotypen kombinerar symbolen med PayPamin Flow-ordmärket och används i sidhuvudet och Om-fönstret. Arkiv-/Hjälpmenyer, högerklicksmeny, verktygsrader och dialogknappar använder **endast text**, utan funktionsikoner. Textetiketterna, snabbkommandona och funktionerna är oförändrade.

Original och skrivbordsformat ligger i `assets/`:

- `paypamin_flow.svg` – redigerbart vektororiginal för appikonen.
- `paypamin_logo.svg` och `paypamin_logo.png` – horisontell logotyp.
- `paypamin_flow.png` och storleksvarianter – Tkinter, systemfält och Linux.
- `paypamin_flow.ico` – Windows, flera inbäddade storlekar.
- `paypamin_flow.icns` – macOS-ikonkälla.
- `icons/` – funktionsikoner med normal och `_light`-variant för varje symbol.

Generera om logotyp, raster-/skrivbordsikoner och samtliga funktionsikoner med Pillow installerat:

```sh
python assets/build_icons.py
```

## Skapa Python-releasepaket

Det finns inget PyInstaller- eller native-byggsteg. Skapa det plattformsoberoende paketet och dess kontrollsumma med:

```sh
python packaging/package_release.py --output release-assets
```

GitHub Actions-workflöen i `.github/workflows/build.yml` kör testerna på Windows, macOS och Linux. Ubuntu-jobbet installerar Tkinter och Xvfb, kör de verkliga Tk-testerna på en 1280×900-skärm och skapar Python-ZIP, SHA-256-fil och byggmanifest med commit och enskilda filhashar. Vid en release bifogas alla tre filerna för appens uppdateringsfunktion.

## Kostnadsfri Fortnox-import utan API

Appen behöver ingen Fortnox-integrationslicens för PDF-importen:

1. Exportera eller spara en faktura-PDF från Fortnox i appens `import/`-mapp. Knappen **Öppna importmapp** öppnar rätt plats.
2. Appen kontrollerar mappen var femte sekund. En ny eller ändrad PDF måste ha samma storlek och tidsstämpel vid två kontroller, så att appen inte läser en halvfärdig export.
3. Den färdiga PDF:en öppnas automatiskt i den befintliga förhandsgranskningen. Kontrollera och godkänn uppgifterna innan fakturan sparas.
4. En PDF kan innehålla **flera fakturor och flera sidor per faktura**. Appen startar en ny faktura när ett nytt fakturanummer börjar och behåller sidor med samma eller inget nytt fakturanummer som fortsättningssidor. Varje faktura granskas och sparas separat med sitt eget sidintervall. För automatisk delning mellan två fakturor behöver den nya fakturan ha ett läsbart fakturanummer.
5. Dubbletter stoppas per faktura utan extra popup vid automatisk körning. Om bara vissa fakturor i en samlings-PDF sparats kan en ny skanning fortsätta med de återstående. En sammanfattning visas när något importerats eller när ett fel behöver åtgärdas.

Bevakningen fungerar även när huvudfönstret ligger i systemfältet; fönstret öppnas när en faktura behöver granskas. Stäng av eller aktivera funktionen under **Inställningar → Bevaka importmappen och importera nya PDF:er automatiskt**. **Skanna importmapp** kan alltid användas manuellt, även för en fil som du tidigare avbrutit.

Detta är ingen direkt API-koppling: exporten från Fortnox görs fortfarande manuellt. Appen loggar inte in i Fortnox och skickar inga uppgifter dit.

## Detaljerad aktivitets- och teknisk logg

**Hjälp → Visa teknisk logg** öppnar `~/.paminnelseapp/logs/app.log`. Samma logg innehåller både de tidigare detaljerade domänposterna och strukturerade `Activity`-händelser för knappar, menyer, högerklicksmenyer, systemfält, filter, fakturaval och uppdateringar. Den samlade felloggen ligger i `~/.paminnelseapp/logs/errors.log`, startfel i `logs/startup.log` och uppdateringsloggen i `logs/update.log`. Kända äldre loggar och rotationer flyttas vid start till samma undermapp utan att befintliga loggfiler skrivs över. En åtgärd får start- och slutpost med samma spårnings-ID, varaktighet och returtyp; fel får i stället feltyp, meddelande och traceback. Sessionens ID och tidsstämpel med tidszon ingår i varje händelse. Oväntade Tk-callbackfel fångas också i den konsollfria installationen.

PDF-/reskontraläsning, faktura- och kundändringar, betalavstämning, P1/P2, e-post, importbevakning, autostart, cache, arkivering, JSON-/ZIP-säkerhetskopior och uppdateringarnas hämtning/installation/omstart har dessutom sina mer detaljerade befintliga loggposter. Den generella aktivitetsloggen sparar inte e-postmeddelandens brödtext eller lösenord. Loggfilen roteras vid midnatt och vid 5 MB med unika, icke-destruktiva rotationsnamn; gårdagens och äldre filer flyttas till loggarkivet. **Visa samlad fellogg** är fortfarande den kortare vyn för enbart olösta fel och tracebacks. Loggar kan innehålla kund-, faktura-, belopps- och sökvägsuppgifter och ska granskas innan de delas.

## Kundreskontralista och betalavstämning

Exportera en **komplett, textbaserad kundreskontralista som PDF** från Fortnox och välj **Arkiv → Importera reskontralista**. Välj PDF-filen med alla tryckta sidor kvar. Bilder och skannade listor används inte i detta flöde, eftersom OCR kan misstolka fakturanummer och belopp.

Innan något sparas kontrollerar appen sidnumren, det totala fakturaantalet och att radernas saldo stämmer mot totalsumman för en SEK-lista. En rad som inte kan läsas säkert stoppar importen. Efter lyckad kontroll körs den atomiska databasändringen direkt utan en ytterligare bekräftelse: betalbelopp på befintliga rader som finns i listan uppdateras, tidigare sedda fakturor som saknas betalmarkeras enligt reglerna nedan och JSON-journalen uppdateras.

För felsökning skrivs detaljerade, strukturerade poster till den lokala tekniska loggen före importen. De innehåller PDF:ens filnamn, listdatum, sid- och fakturaantal, förväntad och inläst totalsumma samt varje tolkad fakturarad med kundnummer, kund, fakturanummer, datum, valuta, belopp, saldo och delbetalning. Alla planerade betalavstämningar loggas. Om valideringen misslyckas finns diagnostiken kvar även om ingen import körs; PDF:ens fullständiga råtext dumpas inte. Öppna loggen via **Hjälp → Visa teknisk logg**. **Visa samlad fellogg** är fortfarande avsedd enbart för fel och tracebacks.

Efter varje lyckad import visas ett rullbart **Reskontrakvitto** med listdatum, build-commit och de faktiska databasresultaten. Varje betalmarkering visas med fakturanummer, kund, belopp och orsak – **Saknas i den nya kompletta listan** eller **Saldo 0 i listan** – och delbetalningar visas separat med tidigare och nytt betalbelopp. Om inget betalmarkeras förklaras nollresultatet med räknare för första listan, redan betalda rader, saknad listhistorik, senare listdatum, oförändrade belopp och skyddade belopp/valutor. Knappen **Visa historik / arkiverade / betalda** rensar en gammal sökning och öppnar historikvyn direkt.

Betalregeln är avsiktligt konservativ:

- Den **första** importerade listan bygger historik för frånvaroregeln. En app-faktura som saknas där betalmarkeras inte enbart på grund av frånvaron.
- I varje verifierad SEK-lista uppdateras en befintlig faktura som finns med i listan från dess **Belopp** och **Saldo**. Saldo 0 markerar fakturan som helt betald även om appens historiska fakturabelopp har korrigerats. Delbetalning uppdateras när fakturabeloppen stämmer överens; ett högre tidigare betalbelopp sänks aldrig.
- I en senare importerad komplett lista markeras dessutom en obetald faktura som har tidigare listhistorik men saknas i den nya listan automatiskt som betald. Detta gäller även två olika kompletta exporter med samma listdatum; en lista med äldre datum kan däremot inte ersätta den senaste avstämningen.
- App-fakturor som aldrig funnits i en importerad lista påverkas inte av frånvaroregeln. Ofullständiga, felaktiga eller äldre listor ändrar ingen betalstatus. Samma senaste lista kan importeras igen för att uppdatera befintliga rader efter en programuppdatering.
- Befintliga fakturors kunduppgifter, fakturabelopp, originalkällor, logotyper och P1/P2-/e-posthistorik skrivs inte över. Nya rader får belopp och delbetalning från listans Belopp och Saldo.
- För listor med annan valuta än SEK kontrolleras sidor och fakturaantal, men befintliga rader och frånvarande fakturor ändrar inte betalstatus automatiskt eftersom totalsumman anges i SEK.
- Reskontra-historiken ingår i JSON- och ZIP-säkerhetskopior.

Efter en lyckad reskontraimport återgår huvudlistan automatiskt till fliken **Aktuella**. Fakturor som just betalmarkerats försvinner därmed från arbetslistan i stället för att ligga kvar som avslutade rader. De raderas inte: posten, beloppen och P1/P2-/e-posthistoriken finns kvar och visas direkt under **Historik / arkiverade / betalda**. Fliken **Alla** visar även både aktiva och historiska poster tillsammans.

**Komplettera med originalfaktura:** högerklicka på en reskontraimporterad faktura och välj **Importera originalfaktura till vald**. Välj originalfakturans PDF, granska de avlästa uppgifterna och spara. PDF:en och dess fakturasektion kopplas till den befintliga raden, och kund, datum, fakturatext, leverantörsmall och logotyp kan kompletteras utan en dubblett. Fakturanumret måste matcha; i samlings-PDF:er krävs en entydig sektion. Reskontrans fakturanummer, belopp, valuta och betalda belopp är låsta i kompletteringsdialogen, och P1/P2-/e-posthistorik samt reskontramarkeringar ändras inte. Det fungerar även för betalda och arkiverade poster utan att skapa en ny påminnelse.

En gång per fredag när appfönstret är synligt visas **Veckans reskontralista**, med möjlighet att välja veckans PDF direkt. Påminnelsen kan stängas av under **Inställningar → Påminn om att importera kundreskontralista varje fredag**. Ingen Fortnox-export eller betaländring sker i bakgrunden utan att du väljer en reskontra-PDF; efter ditt val körs import och betalavstämning automatiskt om listan klarar valideringen.

## Fakturor, logotyper och OCR

### Leverantörsmatchning vid PDF-import

- Sparade leverantörsprofiler matchas först mot **explicit etiketterade** organisationsnummer (`Org.nr`, `Organisationsnummer`) och bankgironummer (`Bankgiro`, `BG`). Format med mellanrum eller bindestreck normaliseras; org.nr lagras med tio siffror och bankgiro med sju eller åtta siffror. Oetiketterade tal utan en uttryckligen markerad zon används inte som leverantörsidentitet.
- En enda entydig identitetsträff används. Om organisationsnummer och bankgiro pekar på olika mallar, eller om flera mallar delar samma träff, lämnas leverantörsvalet öppet för granskning. En svagare namn- eller logotypträff får inte avgöra en sådan konflikt.
- I PDF-granskningen kan du välja **Org.nr (leverantör)** eller **Bankgiro (leverantör)** och rita en ruta runt värdet. Zonen sparas i leverantörsmallen och kan vid nästa import läsa numret från samma plats, även utan textetikett i rutan, och identifiera leverantören. Olika leverantörer som matchar i zonerna ger en konflikt, inte en gissning.
- Utan identitetsträff används normaliserat leverantörs-/mallnamn samt logotypalias från **SVG-filnamn och SVG:ns titel-/textmetadata**. Även äldre zonsmallar utan logotyp finns kvar i matchningen och leverantörsvalet.
- Om ingen text- eller zonträff finns kan en PDF med **en faktura** även matchas visuellt: den faktiska bildlogotypen på fakturans PDF-sida jämförs lokalt mot den SVG som redan är kopplad till leverantören direkt i `svg/`. PDF-filens namn eller en separat bildfil på fakturan används inte. Knappen **Matcha bildlogotyp i PDF** i granskningen gör samma kontroll på den aktuella fakturasektionen. Samma SVG används för P1/P2 och som referens, så ingen extra undermapp eller dubblerad logotyp behövs. Storlek och placering får variera. Matchningen kräver tillräckligt många särdrag, geometrisk överensstämmelse och en tydlig vinnare; fel eller tvetydig logotyp lämnas för granskning. Samlings-PDF:er med flera fakturor undantas från automatisk bildgissning så att en logotyp inte kopplas till fel faktura. Bildmotorn är `opencv-python-headless` och installeras med appens Python-tillägg.
- Bevakad importmapp har inget mappgemensamt leverantörsval. Varje PDF matchas självständigt mot samtliga sparade leverantörsprofiler, och logotypen på fakturan kan därför välja rätt leverantör utan att du väljer en i förväg. PDF-filens namn används inte som leverantör när matchningen misslyckas.
- PDF-granskningen har en redigerbar leverantörsrullista samt fält för leverantörens org.nr och bankgiro. Nya förslag fylls bara när respektive uppgift är entydig i de granskade sidorna. **Kontrollera att uppgifterna tillhör leverantören, inte kunden, innan du sparar.** Samma identifierare kan inte sparas på två olika mallar genom granskningsfönstret.
- När du kopplar en befintlig SVG-logotyp i dialogen måste rätt leverantör/mall vara vald eller inskriven. Om ingen automatisk träff finns är fältet tomt tills du väljer; appen stoppar en logotypkoppling utan leverantör i stället för att skapa en mall med PDF-filens namn.
- För tillförlitlig återkommande matchning: välj eller skriv rätt leverantör/mall, kontrollera org.nr/bankgiro och logotyp och välj **Spara leverantörsmall och fortsätt**. Uppgifterna följer med SQLite-databasen, JSON-journalen och vanliga säkerhetskopior. En äldre JSON-journal utan nummerfält raderar inte redan lokalt sparade identifierare.
- **Hjälp → Visa teknisk logg** visar matchningsmetod och vald leverantör samt missar med fil och sida. Loggen skiljer mellan exempelvis saknad OpenCV, oläsbar PDF-sida, saknad/oläsbar logotypreferens, ingen kandidat över tröskeln och tvetydig träff. En miss går vidare till manuell granskning utan att en osäker leverantör gissas.

- Lägg faktura-PDF:er i `import/` för automatisk bevakning, klicka **Skanna importmapp** för en direkt genomsökning, eller använd **Lägg till faktura-PDF**.
- Kontrollera föreslagna värden och godkänn dem innan en påminnelse skapas.
- Lägg egna SVG-logotyper i `svg/`; dessa är företagslogotyper och ska inte förväxlas med appens ikon i `assets/`.
- Genererade PDF-filer läggs i `export/`.

OCR för skannade PDF:er kräver Tesseract med svenska språkdata (`swe`) och Poppler:

- **Windows:** installera Tesseract OCR och Poppler och lägg dem i PATH.
- **macOS:** `brew install tesseract tesseract-lang poppler`.
- **Debian/Ubuntu:** `sudo apt install tesseract-ocr tesseract-ocr-swe poppler-utils`.

## Lokal lagring och integritet

- Databas, mallar och inställningar sparas i användarprofilen under `~/.paminnelseapp`; teknisk logg, samlad fellogg, startfel och uppdateringslogg ligger samlade i undermappen `~/.paminnelseapp/logs/`. Det befintliga katalognamnet behålls så att tidigare data inte försvinner efter namnbytet.
- `import/`, `export/` och `svg/` ligger i den skrivbara Python-appmappen.
- Kundfakturor, exporter, lokala databaser, loggar och företagslogotyper ska inte checkas in. Se `.gitignore`.
- Tekniska loggar och felloggar kan innehålla filnamn, filvägar, tekniska fel samt kund-, faktura- och beloppsuppgifter från reskontraimporten. Granska dem innan de delas.
- Självlärd data (kundstandardvärden, leverantörslayouter och påminnelsemottagare) ligger i samma lokala databas, följer med ZIP-säkerhetskopior och skickas aldrig över nätverket. Den kan granskas och glömmas under **Inställningar → Granska inlärning**.
- Använd appens ZIP-säkerhetskopior regelbundet och före en manuell ominstallation.

## Tester

```sh
python -m unittest discover -s tests -v
```

Parser-, importbevaknings-, autostart-, ikon-, språk-, valuta-, databas-, säkerhetskopierings-, självlärande-, systemfälts-, paket- och uppdateringstester använder syntetiska data och kräver ingen grafisk skrivbordssession. `tests/test_tk_accessibility.py` använder däremot verkliga Tk-fönster och hoppar över sig när Tk eller display saknas. På Debian/Ubuntu kan hela sviten köras grafiskt utan en inloggad skrivbordssession:

```sh
sudo apt-get install python3-tk xvfb xauth
xvfb-run -a -s "-screen 0 1280x900x24" python -m unittest discover -s tests -v
```

Översättningstesterna kontrollerar att nya texter har engelska översättningar och matchande variabler. Tk-testerna kontrollerar verklig fokusflytt, 200 %-layout, scrollad fokusvisning och växling av högkontrastpalett. Följ även [den manuella skärmläsarchecklistan](ACCESSIBILITY_TESTING.md). Testa alltid ändringar mot riktiga, noggrant granskade exempel före skarp användning.

## Begränsningar

- PDF-layout och OCR kan misstolka fält. Kontrollera fakturan före godkännande. Reskontraimporten kräver textbaserad PDF och stoppar vid oläsbara rader eller avvikande kontrollsummor.
- Betalstatus hämtas inte direkt via Fortnox. Den kan avstämmas med bekräftade, kompletta reskontralistor; kontrollera alltid importsammanfattningen och verifiera betalningar före utskick.
- Dagregler, avgifter, ränta och avtalsvillkor måste verifieras för verksamheten.
- Automatisk e-post eller automatisk ansökan till Kronofogden ingår inte.

## Copyright och licens

**Copyright © 2026 Rickard Längkvist. Skapare: Rickard Längkvist.** Se `NOTICE`.

Ingen separat användarlicens är vald. Normalt upphovsrättsskydd gäller, och rätt att återanvända eller distribuera koden ges inte automatiskt.
