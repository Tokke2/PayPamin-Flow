# PayPamin Flow

Lokal Python-skrivbordsapp för **Windows, macOS och Linux** som läser enskilda Fortnox-fakturor från PDF, skapar betalningspåminnelser som PDF och håller reda på nästa steg. Fakturor och kunduppgifter behandlas lokalt; appen ansluter inte till Fortnox och skickar inte e-post eller Kronofogden-ärenden automatiskt.

- **Skapare och upphovsman:** Rickard Länkvist
- **Copyright:** © 2026 Rickard Länkvist

> **Projektstatus:** tidig prototyp. Avläsning och mallar måste kontrolleras mot riktiga fakturor innan appen används skarpt.

## Funktioner

- Läser svenska och engelska faktura-PDF:er och föreslår kund, fakturanummer, datum, slutbelopp och fakturatext. Beloppsläsningen klarar hela belopp och decimaltal i svenska, europeiska och engelska format samt etiketter som **ATT BETALA**, **Total due**, **Amount due** och **Balance due**, utan att använda moms eller subtotal som slutbelopp. Explicit **Fakturatext/Avser** prioriteras och kan omfatta flera rader; tabellrubriker, numeriska kolumner och summeringsrader rensas konservativt.
- **Valuta per faktura** med SEK som standard och redigerbara ISO-koder, exempelvis EUR, USD, NOK och DKK. Belopp växlas inte mellan valutor.
- **Automatisk bevakning av importmappen** upptäcker nya Fortnox-PDF:er utan API eller integrationslicens. Filer väntas in tills de är färdigskrivna och varje ny faktura granskas innan den sparas. Dubbletter stoppas via fakturanummer, sökväg eller identiskt PDF-innehåll, även om filen döpts om.
- **P1/P2-dialog efter importmappsskanning:** efter manuell eller automatisk behandling av PDF-filer visar en dialog fakturanummer, kund och nivå för fakturor som är redo för P1 eller P2. Betalda, ignorerade, ogranskade och väntande fakturor aviseras inte; ingen påminnelse skapas automatiskt.
- **Återanvändbara kundkontakter:** högerklicka på en faktura och välj **Redigera kund** för kundnamn och flera e-postadresser separerade med komma. Adresslistan sparas i databasen och JSON-journalen och fylls i automatiskt på nästa faktura till samma kund.
- **E-postutkast efter generering:** när P1/P2 har skapats kan ett kundfärdigt, språkanpassat utkast till alla kundens adresser och med dold kopia till `rl@tadega.com` öppnas i systemets valda e-postapp efter förhandsgranskning. Texten skiljer P1 från P2 och innehåller belopp, avgifter, totalsumma och betalningsfrist. När Thunderbird är standardapp i Windows bifogas senaste påminnelse-PDF automatiskt; andra e-postprogram använder `mailto:` och manuell bifogning. Inget mejl skickas automatiskt. Om kunden saknar adresser öppnas ingen e-postapp.
- **Förhandsgranskning och separerad e-poststatus:** innan e-postappen öppnas visas mottagare, fast BCC, ämne, redigerbart meddelande och PDF-sökväg i appen. Ändringar gäller bara det aktuella utkastet; avbryt öppnar inget och sparar ingen utkaststatus. Listan skiljer skapad PDF, öppnat utkast och manuellt bekräftad skickad e-post för P1/P2 utan att blanda ihop datumen.
- PDF-förhandsgranskning med markerbara fältområden och återanvändbara leverantörsmallar. Markerade belopp och fakturatext använder samma tolkning som automatisk import. En beloppsruta med flera oetiketterade eller tvetydiga tal skriver inte över det tidigare värdet; markera i stället en snävare ruta runt etiketten och slutbeloppet.
- Innan **P1** skapas kontrolleras en befintlig original-PDF mot fakturans sparade fakturanummer, kund, datum, belopp, valuta och fakturatext. Sparade fältmallar används vid kontrollen; avvikelser stoppar P1 utan att ändra fakturan eller påminnelsehistoriken. Manuella fakturor utan PDF fungerar som tidigare.
- SVG-logotyp kan kopplas till en leverantörsmall och återanvändas vid export. Ett logotypval i PDF-matchningen sparas även direkt på fakturan och följer med till P1/P2 utan att fältmallen behöver sparas; valet påverkas inte av en senare global logotypändring.
- Manuell granskningsgräns, P1/P2/Kronofogden-steg, justerbara dagar, avgift, betalningsfrist och ränta. **Skapa påminnelse** skapar en aktuell men saknad P1 och kan därefter fortsätta till P2 i samma klick när både P2-intervallet och P1:s sparade betalningsfrist har passerat; inget steg skapas i förtid. **Redigera P1** och **Redigera P2** kan byta logotyp och skriva om den befintliga nivåns PDF med ursprungligt datum, originaldata och oförändrade villkor/historik via interna P1/P2-snapshots; den gamla filen bevaras om skrivningen misslyckas. Om en registrerad P1-PDF saknas återskapas den först med ursprungligt datum och oförändrad historik, varefter en aktuell P2 kan skapas. En skadad eller oläsbar SVG ger ett tydligt fel i stället för att tyst ersättas med textlogotyp.
- Samma nya PayPamin Flow-ikon med faktura och påminnelseklocka i fönster, dialoger, programmenyer, Windows-autostartgenväg och systemfältet – inte Pythons ikon.
- **Stäng eller minimera till systemfältet:** fönstrets stäng- och minimeringsknappar döljer appen medan schemalagda kontroller fortsätter. **Arkiv → Avsluta helt** eller systemfältets **Avsluta helt** stänger appen helt.
- **Lokal säkerhetskopiering och återställning** av inställningar, fakturor, påminnelser och logotyper via Arkiv-menyn.
- **Autostart vid inloggning** på Windows, macOS och Linux. Appen startar då minimerad i systemfältet medan manuell start visar fönstret som vanligt. Funktionen är aktiverad som standard och kan stängas av under **Inställningar**.
- **Svenska och engelska** med direkt språkbyte, sparat språkval och översatta meddelanden, statusar, belopp, datum och påminnelse-PDF:er.
- **Automatiska Python-uppdateringar mot GitHub Releases** två gånger per dygn, med commit- och filjämförelse, SHA-256-verifiering och tyst omstart. Både nyare versioner och verkligt ändrade release-byggen med samma versionsnummer upptäcks. Manuell sökning och installation finns i appen via **Hjälp → Sök efter uppdateringar**.
- PDF sparas lokalt och öppnas i datorns standardprogram. **Öppna exportmapp** i knappraden eller under **Arkiv** öppnar mappen med skapade påminnelser i datorns filhanterare. Fellogg öppnas via **Visa fellogg**.
- **Automatiskt påminnelsearkiv:** vid appstart och därefter regelbundet flyttas igenkända P1/P2-PDF:er vars ursprungliga påminnelsedatum är mer än 7 dagar gammalt från `export/` till `export/arkiv/`. Fakturor och påminnelsehistorik ändras inte, arkiverad P1 kan fortfarande redigeras och befintliga arkivfiler skrivs aldrig över.

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

1. Installera Python från python.org och välj **Add Python to PATH**. Den officiella installationen innehåller Tkinter och `pythonw.exe`.
2. Installera tilläggen enligt ovan.
3. Dubbelklicka på **`start_paypamin_flow.vbs`**. Startaren använder `pythonw.exe` med den gemensamma `paypamin_flow_launcher.py` och öppnar inget konsolfönster. Appen lägger dessutom `CREATE_NO_WINDOW` på hjälpprogram som startas för exempelvis PDF/OCR, så att inga extra konsolfönster öppnas i bakgrunden. Den äldre `paypamin_flow.pyw` finns kvar för kompatibilitet men används inte av Windows startkommando eller autostart.

För felsökning från en redan öppen PowerShell kan `py paypamin_flow.py` användas.

### macOS

1. Installera Python 3.10+ med Tkinter och Python Launcher, till exempel det officiella installationspaketet från python.org.
2. Installera tilläggen enligt ovan.
3. Öppna **`paypamin_flow.pyw`** med Python Launcher. Python Launchers alternativ att köra i Terminal ska vara avstängt. Startaren loggar eventuella startfel och visar ett felmeddelande utan att öppna Terminal.

Autostart och omstart efter uppdatering använder Python direkt via LaunchAgents respektive appens befintliga process och öppnar inte Terminal. En separat `.command`-startare används inte eftersom macOS annars kan öppna Terminal.

### Linux

På Debian/Ubuntu installeras skrivbords- och Python-stöd med:

```sh
sudo apt install python3 python3-pip python3-tk
python3 -m pip install -r requirements.txt
./packaging/install_linux.sh
```

Starta därefter **PayPamin Flow** från programmenyn. Skrivbordsposten har `Terminal=false`. Installationen är per användare och kopierar Python-filerna till `~/.local/share/paypamin-flow` som standard. Du kan också köra `./start_paypamin_flow.sh` eller `python3 paypamin_flow_launcher.py` direkt från appmappen.

På system med externally managed Python kan en virtuell miljö användas. Skapa miljön, installera `requirements.txt` i den och ange dess Python med miljövariabeln `PYTHON` när installationsprogrammet körs.

## Om appen inte startar

Kontrollera först att **Python 3.10 eller senare med Tkinter** är installerat och kör `python -m pip install -r requirements.txt` i appmappen. Den konsolfria startaren skriver import- och startfel till **`~/.paminnelseapp/startup.log`** och försöker visa felet i ett systemmeddelande. För terminalfelsökning kan `python3 paypamin_flow.py` användas på Linux/macOS eller `py paypamin_flow.py` på Windows.

## Systemfält och fullständig avslutning

När du stänger eller minimerar huvudfönstret döljs det i systemfältet. Appen fortsätter då med bland annat schemalagda uppdateringskontroller.

- Klicka på PayPamin Flow-ikonen eller välj **Öppna PayPamin Flow** i systemfältet för att visa fönstret igen.
- Välj **Arkiv → Dölj till systemfältet** för att dölja det utan musens stängknapp.
- Välj **Arkiv → Avsluta helt** eller **Avsluta helt** i systemfältet för att avsluta bakgrundsaktiviteten och stänga appen.

Om skrivbordsmiljön inte har ett fungerande systemfält lämnas fönstret synligt och appen erbjuder ett tydligt val att avsluta i stället för att gömmas oåtkomlig. På Linux kan skrivbordets AppIndicator-/systemfältsstöd behöva aktiveras.

På Windows använder appen en egen app-identitet för aktivitetsfältets PayPamin Flow-ikon. Systemfältsikonen kan placeras under **^ / Dolda ikoner** av Windows; dra den till det synliga fältet om du vill ha den framme hela tiden. Start- och ikonfel loggas i `%USERPROFILE%\.paminnelseapp\app.log`.

## Smart cache-rensning och betalda fakturor

- **Arkiv → Rensa cache nu** kör samma smarta filter som den automatiska rensningen. Automatisk rensning är aktiverad som standard och körs högst en gång per kalenderdygn; den kan stängas av under **Inställningar**.
- Filtret tar endast bort appens egna Python-cachefiler och identifierbara tillfälliga uppdaterings-/backupkataloger som är äldre än 24 timmar. Det följer inte symlänkar och rör aldrig import-PDF:er, fakturadatabasen, inställningar, mallar, logotyper, exporter, loggar eller säkerhetskopior.
- Markera en faktura och välj **Markera som betald** i knappraden eller högerklicksmenyn. Beloppet **Redan betalt** sätts till hela fakturabeloppet och statusen blir **Avslutad**. Betalda fakturor visas under **Visa → Alla** och kan korrigeras via **Redigera faktura** vid behov.
- Om samma faktura ligger kvar i importmappen hoppas den över vid senare import via fakturanummer eller PDF-identitet. Automatisk import hoppar över betalda fakturor tyst; manuella sammanfattningar visar dem separat från vanliga dubbletter. Cache-rensningen tar inte bort PDF:en från importmappen.

## Kundens e-post och P1/P2 i samma klick

1. Markera en faktura, högerklicka och välj **Redigera kund**.
2. Ange en eller flera adresser, till exempel `fornamn@example.com, ekonomi@example.com`. Mellanslag runt kommatecken och dubbletter med olika gemener/versaler hanteras automatiskt. Ogiltiga adresser stoppas med ett felmeddelande.
3. Spara. Adresslistan återanvänds nästa gång en faktura med samma normaliserade kundnamn granskas eller läggs till. Den kan också ändras genom det vanliga fakturaformulärets e-postfält.

När en påminnelse har genererats visas först en **e-postförhandsgranskning i PayPamin Flow** med samtliga sparade kundadresser, **`rl@tadega.com` som fast dold kopia (BCC)**, ämne, redigerbart meddelande och sökvägen till PDF:en. P1 och P2 får varsin färdig svensk eller engelsk kundtext med fakturanummer, förfallodatum, kvarstående belopp, aktuell avgift eller avgifter, totalsumma och betalningsfrist samt signatur från Tadega AB. Tillfälliga ändringar av ämne eller meddelande påverkar inte standardtexten vid nästa utkast. Först när du väljer **Öppna i e-postappen** öppnas ett `mailto:`-utkast i systemets valda e-postapp; **Avbryt** eller stängning av dialogen öppnar inget utkast och sparar ingen utkaststatus. När ett utkast öppnas i efterhand används belopp, avgifter, betalningsfrist och påminnelsedatum från respektive P1/P2-snapshot när en sådan finns. När Thunderbird är standardapp för `mailto:` i Windows skapas ett tillfälligt `.eml`-utkast med `X-Unsent: 1`. Mottagare, fast BCC, redigerat ämne/meddelande och den visade, senaste påminnelse-PDF:en ingår i utkastet, där PDF:en är inbäddad som en riktig MIME-bilaga. Thunderbird 91 eller senare öppnar filen direkt som ett redigerbart utkast utan den separata `-compose attachment=`-tolkningen. Tillfälliga utkast tas bort direkt vid startfel och PayPamin Flows egna utkastfiler äldre än 24 timmar rensas vid senare användning. Windows 11:s aktuella `UserChoice` för `mailto:` prioriteras vid identifieringen, med registrerad användar- och systemstandard som reserv. Programfilen kan hittas via Thunderbirds `App Paths`, registrerade startkommandon, `PATH` och vanliga installationsmappar. Om Thunderbird är standardapp men programfilen inte hittas visas detta uttryckligen och `mailto:` används med manuell bifogning. Tomma eller oläsbara PDF-filer stoppas före processstart, och omedelbara Thunderbird-fel loggas utan att utkaststatus registreras. Andra e-postprogram och plattformar använder vanlig `mailto:`, som inte har enhetligt stöd för bilagor; bifoga då den visade PDF:en manuellt. Oavsett väg granskar och skickar du mejlet själv. Appen skickar aldrig mejl i bakgrunden. Om både P1 och P2 skapas i samma klick öppnas utkastet för den senast skapade nivån.

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

**`~/.paminnelseapp/reminder_journal.json`** uppdateras atomiskt direkt efter att en faktura eller inlärd leverantörsmall sparas, inställningar eller logotypval ändras, en faktura markeras som betald/ignorerad eller tas bort, samt efter varje **lyckad P1/P2-generering**, varje öppnat e-postutkast och varje manuell skickadmarkering. Korrigerade belopp och fakturatext samt inlärda PDF-fält och deras urval behöver därför inte vänta på veckokopian. Journalen innehåller aktuella fakturor, P1/P2:s utkast- och skickaddatum, kundkontakter och deras e-postadresser, inställningar, leverantörslogotypval, PDF-fältmallar och fälturval samt en bestående historik för varje påminnelse med nivå, datum, avgift, villkor, språk, logotypval, PDF-filnamn och fakturans innehåll vid tillfället. Äldre P1/P2-datum utan tidigare journal tas med automatiskt. Ett JSON-skrivfel visas för användaren; den redan sparade databasändringen påverkas inte.

- En automatisk kopia skapas **en gång per ISO-vecka medan appen körs**. Kontrollen görs vid start och därefter en gång i timmen. JSON-kopian sparas som `reminder-journal-ÅÅÅÅ-Wvv.json` under **`~/.paminnelseapp/backups/journal/`**. Samma vecka skapas även `reminder-journal-ÅÅÅÅ-Wvv-files.zip` med hela `import/`- och `export/`-mapparna, inklusive undermappar och tomma kataloger. Om någon del av veckoparet saknas eller är skadat återskapas det utan att vänta till nästa vecka.
- Efter ominstallation väljer du **Arkiv → Importera JSON-journal** och väljer huvudfilen eller en veckokopia. Fakturor, kundkontakter, inställningar, mallar och påminnelsehistorik återställs. Befintliga fakturor slås samman utan dubbletter; lokala fakturaändringar och kundkontakter skrivs inte över, medan saknade kontakter och påminnelsehistorik kompletteras. JSON-importen skriver inte över `import/` eller `export/`; packa upp veckans `-files.zip` manuellt om du även vill återställa filerna.
- JSON-filen innehåller PDF-filnamn men inte själva PDF- eller SVG-filerna. Veckans `-files.zip` innehåller originalfakturor och skapade påminnelse-PDF:er. Använd den manuella ZIP-säkerhetskopian för att även flytta logotypfiler. Påminnelsehistoriken finns även i databasen och följer därför med manuella ZIP-säkerhetskopior.

## Uppdateringar i appen

Appen kontrollerar den senaste stabila GitHub-releasen en kort stund efter start och därefter **var 12:e timme medan appen körs**, även när fönstret ligger i systemfältet. Automatiska uppdateringar är aktiverade som standard och kan stängas av under **Inställningar**.

Vid en nyare version eller ett ändrat officiellt bygge av samma version hämtas samma Python-ZIP för Windows, macOS och Linux. Ett litet release-manifest innehåller full commit, SHA-256 för varje distribuerad fil och ett samlat fil-fingeravtryck. Vid samma versionsnummer jämför appen installerad commit och fil-fingeravtryck med releasen: **om något av dem skiljer sig finns en uppdatering**. Ett nytt numeriskt release-ID med oförändrad commit och identiska filer installerar därför inte om samma innehåll. Äldre installationer som bara har release-ID använder det som kompatibilitetsväg tills de har tagit emot det nya uppdateringsformatet. En lägre version erbjuds inte som nedgradering. Kontrollen går mot GitHubs **latest release**, inte mot `main`.

Kontrollsumman verifieras, arkivets sökvägar och filer valideras och Python-filerna syntaxkontrolleras innan något ersätts. För nya release-manifest måste även det uppackade paketets commit, release-ID och fil-fingeravtryck matcha manifestet. Appen ersätter endast egna program-, start-, dokumentations- och ikonfiler. Databas, `import/`, `export/`, `svg/` och andra användardata ingår inte och lämnas orörda. Installationer med den äldre uppdateraren, som endast jämför versionsnummer, måste installera det första paketet med release-ID-stöd manuellt en gång.

Installationen sker **inuti appen**; du ska inte starta någon separat uppdateringsfil. Därefter startas den uppdaterade Python-appen om utan konsolfönster. Gamla programfiler används som reserv under ersättningen och återställs om installationen eller omstarten misslyckas. Den gamla appen stängs först när den nya processen har bekräftat att gränssnittets händelseloop startat via en engångsbekräftelse med PID och token. Vid timeout eller tidigt avslut stoppas den misslyckade nya processen, filerna rullas tillbaka och den gamla appen lämnas användbar.

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
| Windows | `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\PayPamin Flow.lnk`, med PayPamin Flow-ikon och `pythonw.exe paypamin_flow_launcher.py --minimized` |
| macOS | `~/Library/LaunchAgents/se.paypamin.flow.plist` |
| Linux | `$XDG_CONFIG_HOME/autostart/paypamin-flow.desktop`, normalt `~/.config/autostart/` |

Stäng av eller aktivera via **Inställningar → Starta PayPamin Flow automatiskt när jag loggar in**. Windows-genvägen skapas atomiskt med Windows eget genvägsgränssnitt via dold PowerShell och får explicit appens `.ico`-fil. Den tidigare registerposten under `CurrentVersion\Run` tas bort vid synkronisering så att ingen dubbelstart sker. Autostartkommandot använder **inte `.pyw`**. Om appmappen flyttas, starta appen en gång från den nya platsen så uppdateras sökvägen. Autostart sker efter inloggning och öppnar inget konsolfönster.

## Applikationsikon

Ikonen föreställer ett fakturadokument med textrader, flödespil och en grön **påminnelseklocka**. Den är ritad för att vara tydlig även i små storlekar och används i stället för Pythons ikon. Original och skrivbordsformat ligger i `assets/`:

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

GitHub Actions-workflöen i `.github/workflows/build.yml` kör testerna på Windows, macOS och Linux. Ubuntu-jobbet skapar Python-ZIP, SHA-256-fil och byggmanifest med commit och enskilda filhashar. Vid en release bifogas alla tre filerna för appens uppdateringsfunktion.

## Kostnadsfri Fortnox-import utan API

Appen behöver ingen Fortnox-integrationslicens för PDF-importen:

1. Exportera eller spara en faktura-PDF från Fortnox i appens `import/`-mapp. Knappen **Öppna importmapp** öppnar rätt plats.
2. Appen kontrollerar mappen var femte sekund. En ny eller ändrad PDF måste ha samma storlek och tidsstämpel vid två kontroller, så att appen inte läser en halvfärdig export.
3. Den färdiga PDF:en öppnas automatiskt i den befintliga förhandsgranskningen. Kontrollera och godkänn uppgifterna innan fakturan sparas.
4. En PDF kan innehålla **flera fakturor och flera sidor per faktura**. Appen startar en ny faktura när ett nytt fakturanummer börjar och behåller sidor med samma eller inget nytt fakturanummer som fortsättningssidor. Varje faktura granskas och sparas separat med sitt eget sidintervall. För automatisk delning mellan två fakturor behöver den nya fakturan ha ett läsbart fakturanummer.
5. Dubbletter stoppas per faktura utan extra popup vid automatisk körning. Om bara vissa fakturor i en samlings-PDF sparats kan en ny skanning fortsätta med de återstående. En sammanfattning visas när något importerats eller när ett fel behöver åtgärdas.

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
- Betalstatus hämtas inte via Fortnox. Kontrollera betalningar manuellt före utskick och använd **Markera som betald** när betalningen är verifierad.
- Dagregler, avgifter, ränta och avtalsvillkor måste verifieras för verksamheten.
- Automatisk e-post eller automatisk ansökan till Kronofogden ingår inte.

## Copyright och licens

**Copyright © 2026 Rickard Länkvist. Skapare: Rickard Länkvist.** Se `NOTICE`.

Ingen separat användarlicens är vald. Normalt upphovsrättsskydd gäller, och rätt att återanvända eller distribuera koden ges inte automatiskt.
