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
- **P1/P2 öppnas som ett eget fönster med en arbetslista.** När arbetsflödet når P1 eller P2 – efter en skanning, vid start eller när du själv öppnar det – visas fakturorna som är redo som en lista i stället för en ruta med text: steg, kund, hur många dagar påminnelsen har väntat och kvar att betala, med summa per steg och ett samlat belopp att få in. Listan sorteras på väntetid, eftersom den faktura som varit glömd längst kostar mest, och en nivå vars e-postutkast redan öppnats föreslås inte igen – tjat om arbete som redan påbörjats är värre än tystnad. **Skapa påminnelse** på en rad går in i det vanliga påminnelseflödet med logotypval, avgiftsregler och journal, och **Visa i listan** hoppar till fakturan i huvudtabellen i stället. Fönstret byggs om efter varje skapad påminnelse, så en klar faktura kan inte ligga kvar som "redo". Blandade valutor summeras aldrig ihop. Inget skickas och ingen påminnelse skapas automatiskt.
- **Färgade statusrader:** grön bakgrund betyder att fakturan förfaller i dag eller senare och inte har P1/P2, gul betyder att P1 ska skapas eller finns utan aktuell P2, och röd betyder att P2 ska skapas eller finns. P2 har företräde framför P1. Betalda, ignorerade, ogranskade och förfallna rader som ännu väntar på P1 lämnas utan statusfärg; den skriftliga statuskolumnen finns kvar.
- **Flikbaserade fakturavyer med sökning och sortering:** välj direkt mellan **Aktuella**, **Historik / arkiverade / betalda**, **Alla**, **Ignorerade** och **Kronofogden – granska**. Historikfliken visar helt betalda samt ignorerade/arkiverade poster med deras belopp och P1/P2-/e-posthistorik kvar. Aktiva obetalda fakturor blandas inte in, och inget flyttas eller raderas i databasen när du byter flik. Sökfältet letar i **kund, fakturanummer, belopp, datum, status, e-post, fakturatext och valuta**. Flera ord måste alla finnas men får ligga i olika fält, och ett prefix begränsar ett ord till ett fält: `kund:limoeurope`, `nr:6475`, `belopp:1500`, `datum:2026-11`, `status:granska`, `epost:anna@`, `not:ränta`, `valuta:sek`. Citattecken håller ihop ett namn med mellanslag (`kund:"Acme AB"`), belopp hittas både som `1500`, `1500,00` och `1 500,00`, och datum både som lagrat (`2026-11-01`) och utskrivet (`1 november 2026`). Prefixen fungerar på både svenska och engelska. Under flikarna står hela tiden **Visar X av Y** och vad sökningen gav; om träffarna ligger i en annan flik sägs det uttryckligen i stället för att listan bara blir tom. **Rensa** (eller **Esc** i fältet) tömmer sökningen, och **Sökhjälp** visar samma syntax med exempel. Sortera genom att klicka på kolumnrubrikerna; fakturanummer sorteras numeriskt och en andra klickning vänder ordningen. Högerklicksmenyn kan öppna sparad original-PDF samt senaste befintliga påminnelse-PDF, med P2 före P1 även när filen ligger i `export/arkiv/<kund>/` eller det äldre platta `export/arkiv/`.
- **Självlärande som alltid frågar först:** appen lär sig lokalt av fakturor du har sparat och leverantörsmallar du har bekräftat. Återkommande värden för kundens e-post, logotyp, valuta, fakturatext och leverantörens betalningsfrist samt leverantörens PDF-layout föreslås nästa gång, men appen fyller aldrig i eller väljer något på egen hand. Varje förslag kräver ett uttryckligt ja, oavsett hur mycket underlag som finns. Under **Inställningar → Granska inlärning** ser du allt appen lärt sig och kan glömma enskilda värden eller allt. Inlärningen stannar i den lokala databasen och påverkar aldrig fakturor, påminnelser eller mallar när den glöms.
- **Återanvändbara kundkontakter och kundlogotyper:** högerklicka på en faktura och välj **Redigera kund** för kundnamn och flera e-postadresser separerade med komma. Adresslistan sparas i databasen och JSON-journalen och fylls i automatiskt på nästa faktura till samma normaliserade kundnamn, även vid manuell inmatning utan förifylld dialog. Senaste icke-tomma SVG-logotyp som sparats på kundens faktura återanvänds också på nästa faktura och för äldre fakturor utan eget val. En explicit faktura-/leverantörslogotyp eller medvetet val av **Ingen logotyp** skrivs inte över. Kundens e-post och logotyp ingår i JSON-säkerhetskopior utan att en äldre journal ersätter en senare lokal logotyp.
- **E-postutkast efter generering:** när P1/P2 har skapats kan ett kundfärdigt, språkanpassat utkast till alla kundens adresser och med dold kopia till `rl@tadega.com` öppnas i systemets valda e-postapp efter förhandsgranskning. Texten skiljer P1 från P2 och innehåller belopp, avgifter, totalsumma och betalningsfrist. När Thunderbird är standardapp i Windows bifogas senaste påminnelse-PDF automatiskt; andra e-postprogram använder `mailto:` och manuell bifogning. Inget mejl skickas automatiskt. Om kunden saknar adresser öppnas ingen e-postapp.
- **Förhandsgranskning och separerad e-poststatus:** innan e-postappen öppnas visas mottagare, fast BCC, ämne, redigerbart meddelande och PDF-sökväg i appen. Ändringar gäller bara det aktuella utkastet; avbryt öppnar inget och sparar ingen utkaststatus. Listan skiljer skapad PDF, öppnat utkast och manuellt bekräftad skickad e-post för P1/P2 utan att blanda ihop datumen.
- PDF-förhandsgranskning med markerbara fältområden och återanvändbara leverantörsmallar. Leverantörs-/mallvalet kan matchas mot sparat organisationsnummer, bankgironummer, leverantörsnamn, logotypalias och, vid en PDF med en faktura, logotypens visuella utseende. Markerade belopp och fakturatext använder samma tolkning som automatisk import. En beloppsruta med flera oetiketterade eller tvetydiga tal skriver inte över det tidigare värdet; markera i stället en snävare ruta runt etiketten och slutbeloppet.
- Innan **P1** skapas kontrolleras en befintlig original-PDF mot fakturans sparade fakturanummer, kund, datum, belopp, valuta och fakturatext. Sparade fältmallar används vid kontrollen; avvikelser stoppar P1 utan att ändra fakturan eller påminnelsehistoriken. För en reskontraimporterad faktura erbjuds i stället valet **Använd reskontraunderlag för P1?** om original-PDF:en är oläslig eller avviker. Ett uttryckligt ja använder den sparade reskontraraden för P1 och loggar valet; ett nej skapar ingen P1. Original-PDF och reskontravärden ändras inte av valet. Fakturor utan reskontraunderlag behåller den strikta spärren, och manuella fakturor utan PDF fungerar som tidigare.
- SVG-logotyp kan kopplas till en leverantörsmall och återanvändas. Ett logotypval i PDF-matchningen sparas även direkt på fakturan. Det finns ingen global standardlogotyp: när en påminnelse skapas visas en dialog där du väljer vilken logotyp PDF:en ska tryckas med, och valet sparas med just den påminnelsen.
- Manuell granskningsgräns, P1/P2/Kronofogden-steg, justerbara dagar, avgift och betalningsfrist. **Skapa påminnelse** skapar en aktuell men saknad P1 och kan därefter fortsätta till P2 i samma klick när både P2-intervallet och P1:s sparade betalningsfrist har passerat; inget steg skapas i förtid. **Redigera P1** och **Redigera P2** kan byta logotyp och skriva om den befintliga nivåns PDF med ursprungligt datum, originaldata och oförändrade villkor/historik via interna P1/P2-snapshots; den gamla filen bevaras om skrivningen misslyckas. Om en registrerad P1-PDF saknas återskapas den först med ursprungligt datum och oförändrad historik, varefter en aktuell P2 kan skapas. En skadad eller oläsbar SVG ger ett tydligt fel i stället för att tyst ersättas med textlogotyp. Om fakturatext saknas eller bara innehåller blanksteg utelämnas **Avser**-raden helt i nya eller medvetet återskapade P1/P2-PDF:er, utan standardtext eller extra radavstånd; ifylld text visas som tidigare.
- **Tydlig logotyp och textgränssnitt:** fakturadokument med P-märke och turkos bock används som appikon i fönster, dialoger, systemfält, aktivitetsfält, Aktivitetshanterarens appvy, Dock, Linux och Windows-autostartgenväg. Den horisontella PayPamin Flow-logotypen finns i sidhuvud och Om-fönster. Menyer, verktygsknappar, högerklicksmenyer och dialogknappar visar i stället tydlig text utan funktionsikoner på svenska och engelska.
- **Ljust och mörkt tema, valt under Inställningar.** Appen öppnar i det ljusa temat, precis som förut; **Mörkt** dämpar ljuset i ett mörkt rum och **Följ systemet** byter automatiskt när skrivbordet byter tema. Alla färger kommer från en och samma palett, så ett temabyte målar om alla ytor, fakturatabellens statusfärger, menyer och redan öppna fönster på en gång, utan omstart. Högkontrast går före temat: när skrivbordet begär hög kontrast används alltid den svartvita paletten. Kontrasten är kontrollerad i båda temana – text, dämpad text, fokusmarkering och vald rad ligger alla över 4,5:1.
- **Typografi och ytor.** Ett typsnitt väljs per plattform (Segoe UI, SF Pro Text respektive Inter/Cantarell/Noto Sans/DejaVu Sans) och används för hela gränssnittet i stället för att blanda flera. Rubriker, knappar, fält och tabellhuvuden har en tydlig storlekshierarki, knappar är lugna ytor med hårfin kant, fakturatabellen har högre rad och eget huvudband, och varje fönster har samma bakgrunds-, yt- och kantfärg. Knapparna har tre nivåer: accentfärg för det som avslutar ett steg, lugna sekundärknappar och röd text – inte en röd yta – för **Ta bort vald**, **Ta bort permanent** och **Töm papperskorgen**. Uppdatera-knappen får accentfärg först när det verkligen finns en uppdatering. Ikonregeln står kvar: menyer och knappar visar text, aldrig funktionsikoner.
- **Releasen är källkoden själv, och appen uppdaterar från den.** Det finns inget uppladdat ZIP längre: GitHub skapar ett källkodsarkiv för releasens tagg, så sidans två *Source code*-länkar **är** releasen och kan aldrig peka på något annat. Varje push till arbetsgrenen flyttar taggen till den commiten, vilket gör arkivet till den nyaste koden; `main` används aldrig som källa, eftersom arbetet aldrig mergas. Uppdateringskontrollen läser taggens commit, så samma version med annan commit är en uppdatering och samma commit är det inte – avgjort med en strängjämförelse i stället för en nedladdning. Bara appens egna filer tas ur arkivet: testerna och CI-konfigurationen som ligger i repot skrivs aldrig in i en installation. Installationen stämplar `build_info.py` med commiten den kom ifrån, så nästa kontroll är igen en jämförelse, och releasens beskrivning skrivs om från den commiten medan alla handskrivna meningar runt omkring behålls. Efter varje push läser CI tillbaka resultatet i stället för att lita på sitt eget exit-kod: taggen ska peka på den commit som just testades, sidan ska nämna samma commit, releasen ska sakna uppladdade filer och det arkiv GitHub skapar ska innehålla **exakt** de filerna, jämförda byte för byte mot den utcheckade koden. Stämmer något inte fälls körningen med en tydlig felrad i stället för att lämna en release som beskriver annan kod än den appen hämtar. GitHub kan visa ett par sekunder gammalt arkiv direkt efter att taggen flyttats, så hämtningen görs om några gånger innan kontrollen ger upp.
- **En äldre release kan aldrig installeras över nyare filer.** En innehållsjämförelse säger att två filuppsättningar skiljer sig, aldrig vilken som är nyast. Därför avgör ZIP-filens egen uppladdningstid hos GitHub: har dina installerade filer skrivits efter att releasen publicerades rapporteras releasen som äldre i stället för att erbjudas som uppdatering. Utan den regeln skulle en manuell filkopiering – eller en källkopia – kunna rulla tillbaka appen till förra releasen vid nästa kontroll.
- **Rak, ljus design utan gråtoner.** Rutnätet, flikarna, tabellhuvudet, sökfältet och knapparna ritas platt med hårfin kant i stället för verktygslådans grå gradienter, menylisten tar fönstrets färg i stället för att lämna en vit remsa ovanför logotypen, beloppskolumnerna och deras rubriker är högerställda så siffrorna kan läsas nedåt, och en tunn linje skiljer logotypbandet från arbetet. Text och bild ritas i skärmens egen upplösning: appen begär DPI-medvetenhet genom alla tre Windows-API:erna och loggar om ingen av dem svarar, så fönstret aldrig blir mjukt uppskalat.
- **Fönstret använder skärmens bredd.** Standardfönstret växer med skrivbordets arbetsyta (cirka 86 % av bredden, högst skärmen minus marginal), centreras på skärmen och hamnar aldrig under aktivitetsfältet. Fakturatabellen fördelar överskottsbredden på kund-, status- och e-postkolumnerna, så den slutar där fönstret slutar i stället för mitt på skärmen; sifferkolumnerna behåller sin bredd så beloppen förblir lätta att jämföra. Ett smalt fönster behåller läsbara kolumnbredder och rullar i stället i sidled. Appikonen har dessutom fått en 512 px variant för skarpa aktivitetsfält och Alt-Tab på högupplösta skärmar.
- **Stäng eller minimera till systemfältet:** fönstrets stäng- och minimeringsknappar döljer appen medan schemalagda kontroller fortsätter. I nederkanten finns både **Dölj i systemfältet** och **Avsluta helt** synliga bredvid **Ta bort vald**, så vägen ut är ett val och inte något man måste hitta i en meny. **Avsluta helt** frågar en gång och säger rakt ut att appen även lämnar systemfältet. Systemfältets högerklicksmeny innehåller **Öppna**, **Uppdatera appen** och **Avsluta helt**. **Arkiv → Avsluta helt**, nederkantens **Avsluta helt** eller systemfältets **Avsluta helt** stänger appen helt.
- **Borttagning går att ångra – papperskorgen.** **Ta bort vald**, **Delete** och **Ta bort fakturarad** i högerklicksmenyn flyttar fakturan till papperskorgen i stället för att radera den. Hela raden sparas, inklusive belopp, betalning, fakturatext och P1/P2-historiken, så en återställd faktura är exakt den den var. Direkt efter borttagningen syns en rad med **Ångra** (samma sak som **Ctrl/Cmd+Z**), och den försvinner av sig själv efter en minut – fakturan ligger kvar i papperskorgen även då. **Arkiv → Papperskorg** visar allt som tagits bort, med **Återställ valda**, **Ta bort permanent** och **Töm papperskorgen**. Inget tas bort automatiskt: en faktura ligger kvar tills du själv väljer att ta bort den för gott, och både tömning och permanent borttagning frågar först.
- **CSV-export av listan.** **Arkiv → Exportera listan till CSV** skriver det du ser just nu – öppen flik, sökning och sortering – till en fil som öppnas direkt i Excel eller LibreOffice: semikolon mellan kolumnerna, komma som decimaltecken och UTF-8 med byte-order-mark, så Å, Ä och Ö aldrig blir frågetecken. Belopp, betalt, saldo och påminnelseavgift skrivs som tal utan valutasuffix, statusen står med samma ord som i listan, och ett värde som börjar som en formel (`=`, `+`, `@`) skrivs som text så att ett kundnamn aldrig kan bli en formel. Filnamnet föreslås som `fakturor-ÅÅÅÅ-MM-DD.csv` i exportmappen, och en tom lista säger det i stället för att skapa en tom fil. Inget i databasen ändras av en export.
- **Detaljerad aktivitetslogg:** knappar, menyer, systemfältsåtgärder, filter, fakturaval, uppdateringar och övriga viktiga händelser loggas strukturerat med start, slut/fel, varaktighet, sessions-ID och spårnings-ID i en egen `logs/activity.log`. PDF-, reskontra-, e-post-, säkerhetskopia- och bakgrundsjobbsposter ligger kvar i den tekniska `logs/app.log`. Startfel och uppdateringssteg skrivs också till `app.log`, så en pågående dag har exakt **tre loggfiler**.
- **Dagligt loggarkiv med sju dagars sparning:** vid första posten en ny dag flyttas gårdagens loggar till `logs/arkiv/ÅÅÅÅ-MM-DD/`. Arkiverade dagar, inklusive kopior av åtgärdade fel, raderas automatiskt när de är **äldre än sju dagar**, så loggmappen växer aldrig obegränsat. Dagens tre filer rörs aldrig av rensningen. Olösta fel ligger kvar i `logs/errors.log` även när källoggen roteras eller arkiveras. Först när du uttryckligen väljer **Hjälp → Markera fellogg som åtgärdad** markeras de granskade felen som åtgärdade och en kopia sparas i loggarkivet.
- **Lokal säkerhetskopiering och återställning** av inställningar, fakturor, påminnelser och logotyper via Arkiv-menyn.
- **Alltid minimerad start och autostart:** appen startar i systemfältet vid autostart, manuell start, direktstart och uppdateringsomstart – utan undantag och utan inställning. Öppna fönstret via systemfältet eller genom att starta appen igen; en ny start visar och fokuserar då den befintliga instansen. Autostart vid inloggning finns på Windows, macOS och Linux och är aktiverad som standard och kan ändras under **Inställningar**. Inget konsolfönster öppnas någonstans i kedjan.
- **Svenska och engelska** med direkt språkbyte, sparat språkval och översatta meddelanden, statusar, belopp, datum och påminnelse-PDF:er.
- **Automatiska Python-uppdateringar mot GitHub Releases** två gånger per dygn, med commit- och filjämförelse, SHA-256-verifiering och tyst omstart. Både nyare versioner och verkligt ändrade release-byggen med samma versionsnummer upptäcks. Manuell sökning och installation finns via den tydliga **Uppdatera appen**-knappen, **Hjälp → Uppdatera appen** eller systemfältets högerklicksmeny.
- PDF sparas lokalt och öppnas i datorns standardprogram. **Öppna exportmapp** i knappraden eller under **Arkiv** öppnar mappen med skapade påminnelser i datorns filhanterare. Den samlade felloggen öppnas via **Visa samlad fellogg** eller **Hjälp → Visa samlad fellogg**.
- **Automatiskt påminnelsearkiv i kundmappar:** vid appstart och därefter regelbundet flyttas igenkända P1/P2-PDF:er från och med dagen efter sitt ursprungliga påminnelsedatum från `export/` till `export/arkiv/<kund>/`. Kundmappen bestäms från fakturans sparade P1/P2-data, inte genom att gissa ett delat filnamn; en fil utan entydig kundkoppling lämnas kvar och loggas. Även filer i det tidigare platta `export/arkiv/` flyttas till rätt kundmapp när kopplingen finns. Fakturor och påminnelsehistorik ändras inte, arkiverad P1/P2 kan fortfarande öppnas och redigeras och befintliga arkivfiler skrivs aldrig över.

## Tangentbord och tillgänglighet

- **Tab / Shift+Tab** flyttar fokus i den visuella ordningen. Knappar, fält, flikar, fakturalistan, textytor och PDF-ytan har tydlig fokusmarkering; dialoger har en egen fokusordning.
- **F1** öppnar **Kortkommandon och tillgänglighet**. **F10** eller **Alt+A** öppnar Arkiv-menyn och **Alt+H** öppnar Hjälp-menyn, som sedan används med piltangenter och Enter.
- Huvudgenvägar: **Ctrl/Cmd+F** sök, **Ctrl/Cmd+N** manuell faktura, **Ctrl/Cmd+O** faktura-PDF, **Ctrl/Cmd+E** eller **F2** redigera vald, **F5** skanna importmappen, **Ctrl/Cmd+Enter** öppna original-PDF, **Ctrl+Tab / Ctrl+Shift+Tab** växla fakturaflik och **Shift+F10** öppna vald fakturas meny.
- **Ctrl/Cmd +**, **Ctrl/Cmd −** och **Ctrl/Cmd 0** ökar, minskar eller återställer textstorleken. Samma val finns i **Inställningar → Textstorlek** och i hjälpfönstret. Skalning 80–200 % sparas i den lokala inställningen och JSON-journalen och påverkar menyer, knappar, formulär, flikar, listor och textytor i öppna och nya fönster.
- **Inställningar** anpassar sig hela tiden, inte bara när det öppnas: fälten läggs om mellan en, två och tre kolumner medan fönstret ändras, etiketter och hjälptexter radbryts efter den plats som faktiskt finns och fönstret öppnas i den storlek innehållet behöver. På låga skärmar används tätare avstånd, så rullning behövs bara för det som verkligen inte får plats. Inget göms i flikar eller ihopfällda sektioner, och **Spara inställningar**/**Stäng** ligger kvar i en fast sidfot. Dialoger anpassas till skärmens arbetsyta, så aktivitetsfältet på Windows inte döljer de nedersta fälten, och huvudfönstret öppnas inom den aktuella skärmen.
- Dialoger kan ändra storlek och långa formulär har vertikal och vid behov horisontell rullning. När ett fält eller en knapp får fokus rullas den automatiskt fram, så att även Spara/Stäng kan nås vid 200 % text eller på en liten skärm. E-postmeddelandet har egen vertikal rullning.
- **Högkontrast följer operativsystemet.** Windows högkontrast, macOS Öka kontrast och GNOME/GTK:s högkontrastläge eller HighContrast-tema aktiverar en särskild palett för ttk-kontroller, klassiska textytor, PDF-ytor, fokus och menyer. Ändringar upptäcks automatiskt utan omstart; om skrivbordsinställningen inte kan läsas behålls appens vanliga kontrasttestade palett.
- **Skärpa på skärmar med skalning.** Appen talar om för Windows att den själv ritar i skärmens verkliga upplösning (per-monitor v2, med per-monitor och system-DPI som reserver), i stället för att låta Windows förstora en färdig bild. Textstorleken räknas i punkter som Tk redan skalar från skärmens DPI, medan marginaler, radhöjder, fokusringar, kolumnbredder och fönsterstorlek räknas i pixlar som multipliceras med skalfaktorn en gång. Logotyp och sidhuvudsikon skalas ned en gång från 1024 px-mastern i stället för att töjas av fönsterhanteraren, så text, logotyp och ikoner är skarpa även vid 125, 150, 175 och 200 %.
- Textstorleken ändrar endast appens gränssnitt. Fakturadata, skapade P1/P2-PDF:er och e-posthistorik ändras inte. Textkontrasten och den skriftliga statusen är bevarade även med färgade fakturarader; funktionsknappar och menyer använder fortsatt text utan funktionsikoner.
- Riktiga Tk-widgets testas automatiskt i CI med display på skrivbordsplattformarna och Xvfb på Ubuntu. En separat [manuell checklista för NVDA, VoiceOver och Orca](ACCESSIBILITY_TESTING.md) används för uppläsning, eftersom automatiska widgettester inte ensamma kan verifiera skärmläsarstöd.

## Python-only – ingen EXE eller native-app

PayPamin Flow distribueras som **Python-källkod**, inte som EXE, macOS-app eller native Linux-binär. Samma releasepaket används på alla tre plattformarna:

- `PayPamin-Flow-Python.zip`
- `PayPamin-Flow-Python.zip.sha256`

Releasen innehåller **exakt dessa två filer**. Ett byggmanifest med commit och filhashar skapas fortfarande lokalt av `packaging/package_release.py` när du vill granska ett bygge, men det publiceras inte längre med releasen.

Python **3.10 eller senare** och Tkinter krävs. Packa upp ZIP-filen i en mapp där din användare har skrivrättigheter och installera tilläggen:

```sh
python -m pip install -r requirements.txt
```

Använd `py -m pip` i Windows om det är det kommando som pekar på din Python-installation. Appen kan också installera saknade Python-tillägg i bakgrunden utan att öppna ett konsolfönster.

## Starta utan konsolfönster

Appen har **exakt en startfil per operativsystem**, och den sköter hela starten: den letar upp en användbar Python och startar appen. Frågan om att hämta Python ställs **endast när systemet saknar Python** — finns en fungerande Python startar appen direkt, utan fråga och utan dialog.

| System | Startfil | Hur du startar |
|---|---|---|
| **Windows** | `start_paypamin_flow.vbs` | dubbelklick, inget konsolfönster |
| **macOS** | `start_paypamin_flow.command` | dubbelklick i Finder |
| **Linux** | `start_paypamin_flow.sh` | `./start_paypamin_flow.sh` eller posten i programmenyn |

Alla tre filer finns i release-ZIP:en. Det finns **ingen separat Python-installatör** i paketet och ingen `.bat`-fil: en eventuell Python-installation erbjuds av startfilen själv, bara när den behövs, och aldrig som ett eget skript.

**Så fungerar erbjudandet, likadant på alla tre system:**

1. Startfilen letar först efter en Python som fungerar: `PATH`, kända installationsplatser, Python Install Manager (Windows) och `PAYPAMIN_PYTHON` (macOS/Linux). Kravet är **3.10 eller senare** och att Tkinter finns.
2. **Finns Python startar appen direkt.** Ingen fråga ställs, och ingenting uppdateras, ersätts eller skuggas.
3. **Saknas Python ställs frågan en gång.** Windows installerar då senaste stabila Python för din användare (utan administratörslösenord, via Python Install Manager) om du svarar ja. macOS och Linux öppnar i stället den officiella nedladdningssidan, så att du själv kör installationsprogrammet: de rör aldrig systemets Python och kör aldrig en pakethanterare eller begär administratörsrättigheter.
4. **Svarar du nej kommer frågan inte igen.** Svaret sparas i `~/.paminnelseapp/python-offer.declined`, och startfilen visar då bara en rad med nedladdningsadressen. Radera filen om du vill bli tillfrågad igen. Ett **Avbryt** på Windows räknas inte som nej och sparas inte.
5. Finns Python men **saknar Tkinter** säger startfilen det rakt ut i stället för att föreslå en ny Python-installation, eftersom en ny Python inte skulle lösa problemet.

### Windows

1. Dubbelklicka på **`start_paypamin_flow.vbs`**. Startaren kontrollerar att en startbar Python finns i `PATH`, via Python Install Manager eller på vanliga installationsplatser. Den öppnar inget konsolfönster.
2. Saknas Python helt frågar startaren om senaste stabila Python får installeras för din användare. Svarar du ja installeras vid behov först den officiella Python Install Manager med WinGet och därefter managerens aktuella rekommenderade stabila version. Installationssteget nås inte när en befintlig Python hittats, när frågan avböjts eller när kontrollen har misslyckats och resultatet därför är osäkert.
3. En befintlig Python används alltid oförändrad. Startaren uppdaterar inte Python-runtime och installerar inte en ny version bredvid en befintlig installation.
4. En befintlig Python som hanteras av Python Install Manager, system-Python eller en virtuell miljö används utan att ersättas eller uppdateras externt. Appen skapar ingen parallellinstallation.

Startaren använder `pythonw.exe` när det finns och den gemensamma `paypamin_flow_launcher.py`. Vid enbart `python.exe` håller Windows Script Host processen dold. Appen lägger dessutom `CREATE_NO_WINDOW` på hjälpprogram som startas för exempelvis PDF/OCR. Windows-autostart använder samma VBS-startare och runtime-kontroll; appens autosynk uppdaterar äldre autostartgenvägar. Den äldre `paypamin_flow.pyw` finns kvar för kompatibilitet men används inte av Windows startkommando eller autostart.

För felsökning från en redan öppen PowerShell kan `py paypamin_flow.py` användas.

### macOS

1. Dubbelklicka på **`start_paypamin_flow.command`** i Finder. Finder öppnar filen i Terminal, så startfilen kopplar loss appen direkt, **döljer Terminal-fönstret omedelbart** och stänger det sedan — inget terminalfönster blir kvar bredvid appens fönster.
2. Startfilen letar efter Python 3.10+ med Tkinter i `PATH`, i Homebrew- och python.org-platserna och i `PAYPAMIN_PYTHON`. Apples `/usr/bin/python3` används bara när Command Line Tools redan är installerade, eftersom stubben annars öppnar Apples egen installationsdialog.
3. Saknas Python öppnas nedladdningssidan för senaste Python när du tackar ja. Om du hellre använder Homebrew eller Python Launcher fungerar det också: appen startar med vilken Python som helst som uppfyller kraven.
4. Alternativ start: `python3 paypamin_flow_launcher.py` eller **`paypamin_flow.pyw`** med Python Launcher, med alternativet att köra i Terminal avstängt.

Första gången kan macOS markera den nedladdade ZIP-filen som karantänsatt och vägra starta `.command`-filen. Högerklicka då på filen och välj **Öppna**, eller kör `xattr -dr com.apple.quarantine <mapp>` en gång för uppackade mappen.

Autostart och omstart efter uppdatering använder Python direkt via LaunchAgents respektive appens befintliga process och öppnar inte Terminal. PayPamin Flow uppdaterar eller ersätter inte Apples/systemets Python och installerar inte en ny python.org-runtime bredvid en befintlig installation.

### Linux

På Debian/Ubuntu installeras skrivbords- och Python-stöd med:

```sh
sudo apt install python3 python3-pip python3-tk
python3 -m pip install -r requirements.txt
./packaging/install_linux.sh
```

Starta därefter **PayPamin Flow** från programmenyn. Skrivbordsposten har `Terminal=false`. Installationen är per användare och kopierar Python-filerna till `~/.local/share/paypamin-flow` som standard. Du kan också köra `./start_paypamin_flow.sh` eller `python3 paypamin_flow_launcher.py` direkt från appmappen.

På system med externally managed Python kan en virtuell miljö användas. Skapa miljön, installera `requirements.txt` i den och ange dess Python med miljövariabeln `PYTHON` när installationsprogrammet körs. `start_paypamin_flow.sh` kontrollerar den valda tolken (`PAYPAMIN_PYTHON`), `python3.13` ner till `python3` samt vanliga installationsplatser. Den kräver 3.10 eller senare **och** Tkinter, men uppdaterar eller ersätter aldrig system-Python, kör aldrig en pakethanterare och begär aldrig administratörsrättigheter. Saknas Python öppnas den officiella nedladdningssidan efter ditt ja; på Debian/Ubuntu heter Tkinter-paketet `python3-tk`.

## Python och valfria tilläggsuppdateringar

- En befintlig Python-runtime uppdateras **inte vid appstart** och ersätts inte av PayPamin Flow. Startfilerna erbjuder en ny Python **endast** när ingen fungerande Python hittas, och Windows installerar den bara efter ett uttryckligt ja.
- Vid start kontrolleras att nödvändiga Python-tillägg finns. Saknade tillägg kan återställas i bakgrunden utan att befintliga tillägg uppgraderas.
- Välj **Hjälp → Uppdatera Python-tillägg** för att manuellt uppdatera appens tillägg. Appen frågar först och använder den befintliga Python-miljön; ingen egen virtuell miljö eller parallell Python-runtime skapas. Starta om appen efter en lyckad uppdatering.
- Automatiska veckouppdateringar av Python-runtime och tillägg körs inte längre. Ett misslyckat manuellt tilläggsförsök lämnar appen med befintliga tillägg och loggas.
- Den separata funktionen **Uppdatera appen** för PayPamin Flows egna releasefiler är oförändrad.

## Om appen inte startar

Kontrollera först att **Python 3.10 eller senare med Tkinter** är installerat och kör `python -m pip install -r requirements.txt` i appmappen. Den konsolfria startaren skriver import- och startfel till **`~/.paminnelseapp/logs/app.log`**, uppdaterar även den samlade felloggen och försöker visa felet i ett systemmeddelande. För terminalfelsökning kan `python3 paypamin_flow.py` användas på Linux/macOS eller `py paypamin_flow.py` på Windows.

## Samlad fellogg för snabb felsökning

Välj **Visa samlad fellogg** i knappraden eller **Hjälp → Visa samlad fellogg**. Appen uppdaterar då och öppnar **`~/.paminnelseapp/logs/errors.log`** direkt i systemets textprogram.

- Samlingsfilen hämtar kompletta `ERROR`- och `CRITICAL`-block med stackspår från `logs/app.log` och `logs/activity.log` samt deras rotationer. Startfel och uppdateringssteg skrivs i samma `app.log`, så inga extra sidologgar behövs. Vid första start flyttas kända äldre loggar och rotationer från appdatamappens rot till `logs/`; befintliga filer skrivs inte över och namnkonflikter får prefixet `legacy-`. En äldre `startup.log` eller `update.log` som hittas slås samman in i `app.log` och tas bort, så en dag alltid har tre filer.
- Posterna sorteras med nyaste fel först och exakta dubbletter från roterade eller kopierade loggar slås samman. Källfilen och tiden anges för varje fel. **Olösta fel tas inte bort när en källogg roteras, arkiveras eller inte längre finns i den aktiva loggmappen.**
- Vyn byggs om atomiskt vid appstart, en gång i minuten medan appen körs och varje gång den öppnas. Ett misslyckat skrivförsök lämnar den tidigare samlingsfilen orörd. Efter felloggsuppdateringen arkiveras loggfiler vars senaste skrivning är från gårdagen eller tidigare under **`logs/arkiv/ÅÅÅÅ-MM-DD/`**, och arkivdagar äldre än sju dagar raderas i samma pass. Dagens filer lämnas kvar. Arkivfiler skrivs inte över, namnkonflikter får `legacy-`-prefix och symlinks följs inte. Loggarna roteras vid midnatt och vid 5 MB med unika rotationsnamn.
- **`errors.log` arkiveras eller rensas inte automatiskt.** När felen är åtgärdade väljer du **Hjälp → Markera fellogg som åtgärdad** och bekräftar. Aktuella fel markeras då som lösta, en kopia sparas under **`logs/arkiv/resolved/ÅÅÅÅ-MM-DD/`** och samma gamla händelse kan inte komma tillbaka från en oförändrad källogg. Ett nytt fel med ny tidpunkt visas som en ny olöst händelse. Avbryts bekräftelsen ändras ingenting.
- **Inga fel försvinner längre i tysta undantag.** Gränssnittet fångar hundratals fel som är ofarliga – ett fönster som redan stängts, en temporärfil som redan tagits bort – och de skrevs förut som `except ...: pass`, alltså utan spår. Nu skriver varje sådan plats en rad: förväntad städning (TclError och filfel som redan är borta) som **varning i `app.log`**, allt oväntat som **fel med stackspår** och därmed i `errors.log`. Samma fel på samma plats skrivs en gång och räknas i stället, så en återkommande ritning inte dränker loggen; vid felloggsuppdateringen läggs en summering med antal i `app.log`. En enhetstestning förbjuder nya tysta undantag.
- Om inga olösta fel finns står det uttryckligen i filen. All diagnostik stannar lokalt; granska filvägar och tekniska uppgifter innan loggen delas.

## Systemfält och fullständig avslutning

När du stänger eller minimerar huvudfönstret döljs det i systemfältet. Appen fortsätter då med bland annat schemalagda uppdateringskontroller.

- Klicka på PayPamin Flow-ikonen eller välj **Öppna PayPamin Flow** i systemfältet för att visa fönstret igen.
- Den översta raden i menyn visar arbetsläget direkt, till exempel **PayPamin Flow · 3 väntar P1 · 1 väntar P2**, och samma text visas som verktygstips när du håller musen över ikonen.
- **Skanna importmapp nu** och **Öppna exportmapp** finns i menyn, så de vanligaste åtgärderna nås utan att öppna fönstret.
- Högerklicka och välj **Uppdatera appen** för att visa fönstret och starta samma manuella uppdateringskontroll som i Hjälp-menyn. Valet visar även **Uppdatering tillgänglig**, **Söker…** eller **Uppdaterar…** när något pågår.
- Välj **Dölj i systemfältet** i nederkanten eller **Arkiv → Dölj i systemfältet** för att dölja fönstret utan musens stängknapp.
- Välj **Avsluta helt** i nederkanten, **Arkiv → Avsluta helt** eller **Avsluta helt** i systemfältet för att avsluta bakgrundsaktiviteten och stänga appen. Nederkantens knapp frågar en gång och påminner om att **Dölj i systemfältet** låter appen fortsätta bevaka importmappen.
- Första gången fönstret döljs visas en kort förklaring om att appen fortsätter i systemfältet. Den visas bara en gång.

### Windows, macOS och Linux

| | Minimera | Stäng | Öppna igen | Avsluta helt |
|---|---|---|---|---|
| **Windows** | döljs i systemfältet | döljs i systemfältet | ikonen i systemfältet, eller starta appen igen | systemfältets meny, **Avsluta helt** i nederkanten eller **Arkiv → Avsluta helt** |
| **macOS** | döljs i menyraden | döljs i menyraden | menyradsikonen, Dock-ikonen eller starta appen igen | **Cmd+Q**, menyraden eller **Arkiv → Avsluta helt** |
| **Linux** | döljs i systemfältet | döljs i systemfältet | systemfältets ikon eller starta appen igen | systemfältets meny eller **Arkiv → Avsluta helt** |

På macOS återöppnar ett klick på Dock-ikonen fönstret även när det är dolt, och **Cmd+Q** avslutar appen helt i stället för att bara gömma fönstret.

Om skrivbordsmiljön inte har ett fungerande systemfält lämnas fönstret synligt och appen erbjuder ett tydligt val att avsluta i stället för att gömmas oåtkomlig. Orsaken skrivs till loggen tillsammans med åtgärden:

- **Linux:** systemfältet kräver AppIndicator-stöd (`gir1.2-ayatanaappindicator3-0.1` eller `libappindicator3-1`) och en panel som visar statusikoner. Under Wayland behövs dessutom tillägget AppIndicator/KStatusNotifierItem i skrivbordsmiljön.
- **Windows:** appen måste startas i en vanlig skrivbordssession, inte som tjänst.
- **macOS:** appen kräver en grafisk inloggningssession.

På Windows använder appen en egen app-identitet för aktivitetsfältets PayPamin Flow-ikon. Huvudfönstret och alla sekundära fönster får dessutom både stor och liten PayPamin Flow-ikon direkt via det **yttersta Windows-rot- och ägarfönstret**, som aktivitetsfältet, Alt+Tab och Aktivitetshanterarens appvy använder. Ikonen appliceras både under fönsteruppbyggnaden och igen efter att fönstret har mappats; huvudfönstret får den även på nytt när det återställs från systemfältet. Systemfältsikonen kan placeras under **^ / Dolda ikoner** av Windows; dra den till det synliga fältet om du vill ha den framme hela tiden. Start- och ikonfel loggas i `%USERPROFILE%\.paminnelseapp\logs\app.log`.

**Begränsning i Windows:** Aktivitetshanterarens **Detaljer**-flik och vissa bakgrundsprocessvyer kan fortfarande visa Python-ikonen. Windows hämtar då den inbäddade ikonen från `pythonw.exe`, inte från appfönstret. Att ersätta just den processikonen skulle kräva en native EXE med egen ikonresurs, vilket inte ingår i PayPamin Flows Python-only-distribution.

## Starta minimerad – alltid

PayPamin Flow startar **alltid** minimerad i systemfältet. Det gäller vid inloggning, manuell start, direktstart av `paypamin_flow.py`/startaren och när appen startas om efter en uppdatering. Fönstret skapas och appens schemalagda kontroller börjar direkt, men det visas inte förrän du öppnar det.

- Klicka på systemfältsikonen eller välj **Öppna PayPamin Flow**.
- Eller starta appen igen: eninstansskyddet aktiverar den befintliga appen och visar fönstret.
- Det finns ingen inställning som stänger av det: starten är alltid densamma, så det finns inget läge där fönstret dyker upp av misstag. Flaggan `--minimized`, som autostart skickar, accepteras fortfarande men behövs inte längre.
- Första gången appen startar göms fönstret med en förklaring i systemfältet, så det är tydligt var det hamnade.
- Om systemfältet inte är tillgängligt lämnas fönstret synligt i stället för att appen göms oåtkomligt.

## Inget terminal- eller konsolfönster

Ett svart konsolfönster ska aldrig synas – varken vid start eller medan importmappen skannas. Det gäller på tre nivåer:

- **Vid start:** `start_paypamin_flow.vbs` kör `pythonw.exe` via `wscript.exe`, och startaren startar om sig själv med `pythonw.exe` om den råkat startas med `python.exe`. Startar du `paypamin_flow.py` från en egen terminal döljs inget fönster som du själv äger – konsolen delas då med terminalen och lämnas orörd.
- **Vid skanning:** `console_free.py` lägger `CREATE_NO_WINDOW` på **varje** barnprocess så snart modulen laddas, innan PDF- och OCR-biblioteken hunnit laddas. Det täcker `pdftoppm`, `tesseract`, `pip` och allt annat appen startar, oavsett om det sker via `subprocess.Popen` eller `subprocess.run`. Skanningen av importmappen kan därför aldrig blinka fram en konsol.
- **På macOS och Linux:** Terminal-fönstret som Finder respektive skalet öppnar döljs och stängs direkt av startfilen, som sedan lämnar appen kopplad loss från terminalen. En `.desktop`-post startar med `Terminal=false`.

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

Appen fattar aldrig egna beslut om dina uppgifter. Även efter hundratals eniga observationer är ett inlärt värde endast ett förslag som du måste godkänna varje gång; inget fält fylls i och ingen leverantör väljs utan ditt ja. Minst två eniga observationer krävs för att ett förslag ska visas, och lika vanliga motstridiga värden föreslås aldrig. Ett nej gör att samma förslag inte upprepas förrän mer evidens har tillkommit. Godkända förslag visas i dialogrutan och loggas, och inget sparas förrän du själv sparar fakturan.

Öppna **Inställningar → Granska inlärning** för att se inlärda värden med hur många gånger varje värde har setts, samt antal leverantörsmallar, PDF-zoner och påminnelser. **Glöm valt** tar bort ett enskilt värde och **Glöm allt** rensar inlärda värden och leverantörslayouter. Fakturor, kunder, påminnelser och sparade mallar ändras inte. Stäng av **Lär sig av sparade fakturor och leverantörsval** för att stoppa ny inlärning.

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

När en påminnelse har genererats visas först en **e-postförhandsgranskning i PayPamin Flow** med samtliga sparade kundadresser, **`rl@tadega.com` som fast dold kopia (BCC)**, ämne, redigerbart meddelande och sökvägen till PDF:en. P1 och P2 får varsin färdig svensk eller engelsk kundtext med fakturanummer, förfallodatum, kvarstående belopp, aktuell avgift eller avgifter, totalsumma och betalningsfrist men utan avslutningsfras eller företagssignatur – den lägger ditt e-postkonto till självt, så texten slutar efter sista meningen. Ämnesraden innehåller även leverantörsföretagets namn efter påminnelsetexten, till exempel **`Faktura 6475 – betalningspåminnelse / Limoeurope`**. P2 behåller prefixet **SV:**/**Re:** före samma ämne. Namnet följer **den logotyp som valdes när påminnelsen skapades**: först en sparad leverantörskoppling till filen, annars filnamnet (`Limoeurope.svg` blir `Limoeurope`). Om logotypen inte pekar ut någon leverantör används påminnelsens sparade leverantörssnapshot, och om inte heller det finns lämnas ämnesraden utan tillägg. Kundens namn används aldrig, och ett filnamn som bara säger `logo` eller `logotyp` ger ingen gissning. E-postens standardtext anger uttryckligen att hela beloppet ska vara mottaget senast sista betalningsdag; P2 upplyser om att ärendet kan lämnas vidare utan ytterligare påminnelse. Standardtexterna nämner ingen ränta. Tillfälliga ändringar av ämne eller meddelande påverkar inte standardtexten vid nästa utkast. Först när du väljer **Öppna i e-postappen** öppnas ett `mailto:`-utkast i systemets valda e-postapp; **Avbryt** eller stängning av dialogen öppnar inget utkast och sparar ingen utkaststatus. När ett utkast öppnas i efterhand används belopp, avgifter, betalningsfrist och påminnelsedatum från respektive P1/P2-snapshot när en sådan finns. När Thunderbird är standardapp för `mailto:` i Windows skapas ett tillfälligt `.eml`-utkast med `X-Unsent: 1`. Mottagare, fast BCC, redigerat ämne/meddelande och den visade, senaste påminnelse-PDF:en ingår i utkastet, där PDF:en är inbäddad som en riktig MIME-bilaga. Thunderbird 91 eller senare öppnar filen direkt som ett redigerbart utkast utan den separata `-compose attachment=`-tolkningen. Tillfälliga utkast tas bort direkt vid startfel och PayPamin Flows egna utkastfiler äldre än 24 timmar rensas vid senare användning. Windows 11:s aktuella `UserChoice` för `mailto:` prioriteras vid identifieringen, med registrerad användar- och systemstandard som reserv. Programfilen kan hittas via Thunderbirds `App Paths`, registrerade startkommandon, `PATH` och vanliga installationsmappar. Om Thunderbird är standardapp men programfilen inte hittas visas detta uttryckligen och `mailto:` används med manuell bifogning. Tomma eller oläsbara PDF-filer stoppas före processstart, och omedelbara Thunderbird-fel loggas utan att utkaststatus registreras. Andra e-postprogram och plattformar använder vanlig `mailto:`, som inte har enhetligt stöd för bilagor; bifoga då den visade PDF:en manuellt. Oavsett väg granskar och skickar du mejlet själv. Appen skickar aldrig mejl i bakgrunden. Om både P1 och P2 skapas i samma klick öppnas utkastet för den senast skapade nivån.

**Skapa utkast i efterhand:** om adresserna saknades när påminnelsen genererades, eller har ändrats senare, spara dem först via **Redigera kund**. Högerklicka sedan på fakturan och välj **Skapa e-postutkast**. Samma förhandsgranskning visas innan e-postappen öppnas. Utkastet använder de aktuella kundadresserna och alltid senaste befintliga nivå: P2 om den finns, annars P1. Befintlig eller arkiverad PDF hittas utan att skrivas om, och varken `sent_count` eller påminnelsehistoriken ändras. Om PDF:en saknas uppmanas du att återskapa den via respektive **Redigera P1/P2** innan utkastet öppnas. I Thunderbird på Windows bifogas PDF:en automatiskt; i andra e-postprogram bifogar du den manuellt. Skicka mejlet själv som vanligt.

**PDF, utkast och skickat är olika statusar.** Kolumnen **P2-datum** visar **Skapad** när PDF:en finns; den påstår inte att e-post har skickats. Kolumnen **E-post (senaste)** visar för P2 om den finns, annars P1, om utkastet ännu inte har öppnats, när det öppnades eller när e-posten markerades som skickad. Första lyckade öppningen i e-postappen sparas som utkastdatum. Eftersom appen inte kan kontrollera e-postprogrammet sker skickadmarkering endast manuellt via högerklick → **Markera e-post som skickad** och en uttrycklig bekräftelse. Detaljraden visar e-poststatus för båda befintliga nivåer, och P1:s egna utkast- och skickaddatum behålls när P2 skapas. Dessa fyra statusfält migreras i befintliga databaser och ingår i JSON-journalen samt ZIP-säkerhetskopior utan att ändra `sent_count` eller påminnelsehändelser.

För att underlätta fortsatt konversation behåller P1 och P2 samma grundämne med fakturanumret. P2, och ett utkast för en faktura som redan har en registrerad påminnelse, får prefixet **SV:** eller **Re:**. Detta är en bästa möjliga trådkoppling: ett vanligt `mailto:` kan inte söka i mailboxen, hitta ett befintligt konversations-ID eller garantera att e-postappen grupperar utkastet som ett svar. Om e-postappen inte kopplar utkastet till rätt konversation måste du öppna den befintliga konversationen och fortsätta den manuellt.

**Skapa påminnelse** beter sig så här:

- Först visas dialogen **Skapa P1**/**Skapa P2** med två fält. **Logotyp** är en lista över SVG-filerna i `svg/` där fakturans logotyp, leverantörsmallens logotyp eller kundens sparade logotyp är förvald, så det vanliga fallet är ett klick. **Meddelanderad (frivillig)** är en egen rad som trycks i en markerad ruta på PDF:en, till exempel *"Ring gärna om du vill dela upp betalningen."* – **lämnas fältet tomt tas raden bort helt**, utan rubrik, ram eller tomt utrymme kvar på sidan. Båda valen styr PDF:en och sparas med påminnelsen; **Avbryt** skapar ingenting. Skapas P1 och P2 i samma klick används samma val, och det kan ändras i efterhand via **Redigera P1/P2**. Knapparna **Uppdatera lista** och **Öppna SVG-mapp** finns i dialogen, och samma mapp nås via **Arkiv → Öppna logotypmapp**.
- Saknas P1 och fakturan är redo för P1 skapas den efter samma granskning och bekräftelse som tidigare.
- Saknas P1-PDF:en men P1 redan finns i historiken återskapas filen med ursprungligt datum utan en ny P1-händelse.
- Därefter skapas P2 om både inställningen **Dagar efter P1 till P2** och den betalningsfrist som sparades på P1 tillåter det. Annars stannar flödet efter P1.

**Redigera P1/P2:** markera fakturan och välj **Redigera P1** eller **Redigera P2** i knappraden eller högerklicksmenyn. Välj ny logotyp eller ändra meddelanderaden och skriv om just den nivåns PDF. Fältet är förvalt med den rad påminnelsen skickades med, så en gammal rad kan tas bort eller ersättas; varje nivå har sin egen rad i sin snapshot, så en ändring av P2 rör aldrig vad P1 sade. Ursprungligt påminnelsedatum, originalfaktura, avgift, övriga villkor, språk, `sent_count` och påminnelsehistorik behålls. Nya P1/P2-snapshots sparas i databasen och JSON-journalen. För en äldre P2 utan snapshot fryses värdena vid den första lyckade omskrivningen. En misslyckad skrivning behåller gamla PDF:en och tidigare logotypval. Redigeringen skapar ingen ny påminnelsehändelse och skickar inget e-postutkast.

## Säkerhetskopiering och återställning

Välj **Arkiv → Säkerhetskopiera inställningar och påminnelser** och spara ZIP-filen på en säker plats. Säkerhetskopian innehåller:

- den lokala databasen med inställningar, fakturor, kundkontakter, leverantörsmallar och PDF-fältområden;
- skapade påminnelse-PDF:er från `export/`;
- företagslogotyper från `svg/`;
- ett manifest med format, version, tidsstämpel och SHA-256-kontrollsummor.

Den manuella ZIP-säkerhetskopian innehåller inte importerade originalfakturor i `import/` eller diagnostikloggar. Originalfakturorna ingår i veckans separata filpaket enligt nedan.

Välj **Arkiv → Återställ säkerhetskopia** för att återställa. Arkivets sökvägar, filtyper, kontrollsummor och SQLite-integritet kontrolleras först. Appen skapar alltid en säkerhetskopia av nuvarande data innan något ersätts. Den sparas under `~/.paminnelseapp/backups`. Om ersättningen misslyckas återställs de tidigare filerna automatiskt.

## JSON-journal och automatisk veckokopia

**`~/.paminnelseapp/reminder_journal.json`** uppdateras atomiskt direkt efter att en faktura eller inlärd leverantörsmall sparas, inställningar ändras, en påminnelse får en ny logotyp, en faktura markeras som betald/ignorerad, en betalmarkering ångras eller en rad tas bort, samt efter varje **lyckad P1/P2-generering**, varje öppnat e-postutkast och varje manuell skickadmarkering. Korrigerade belopp och fakturatext samt inlärda PDF-fält och deras urval behöver därför inte vänta på veckokopian. Journalen innehåller aktuella fakturor, P1/P2:s utkast- och skickaddatum, kundkontakter och deras e-postadresser, inställningar, leverantörslogotypval, leverantörsmallarnas organisations- och bankgironummer, PDF-fältmallar och fälturval samt en bestående historik för varje påminnelse med nivå, datum, avgift, villkor, språk, logotypval, PDF-filnamn och fakturans innehåll vid tillfället. Äldre P1/P2-datum utan tidigare journal tas med automatiskt. Ett JSON-skrivfel visas för användaren; den redan sparade databasändringen påverkas inte.

- En automatisk kopia skapas **en gång per ISO-vecka medan appen körs**. Kontrollen görs vid start och därefter en gång i timmen. JSON-kopian sparas som `reminder-journal-ÅÅÅÅ-Wvv.json` under **`~/.paminnelseapp/backups/journal/`**. Samma vecka skapas även `reminder-journal-ÅÅÅÅ-Wvv-files.zip` med hela `import/`- och `export/`-mapparna, inklusive undermappar och tomma kataloger. Om någon del av veckoparet saknas eller är skadat återskapas det utan att vänta till nästa vecka.
- Efter ominstallation väljer du **Arkiv → Importera JSON-journal** och väljer huvudfilen eller en veckokopia. Fakturor, kundkontakter, inställningar, mallar och påminnelsehistorik återställs. Befintliga fakturor slås samman utan dubbletter; lokala fakturaändringar och kundkontakter skrivs inte över, medan saknade kontakter och påminnelsehistorik kompletteras. JSON-importen skriver inte över `import/` eller `export/`; packa upp veckans `-files.zip` manuellt om du även vill återställa filerna.
- JSON-filen innehåller PDF-filnamn men inte själva PDF- eller SVG-filerna. Veckans `-files.zip` innehåller originalfakturor och skapade påminnelse-PDF:er. Använd den manuella ZIP-säkerhetskopian för att även flytta logotypfiler. Påminnelsehistoriken finns även i databasen och följer därför med manuella ZIP-säkerhetskopior.

## Uppdateringar i appen

Appen kontrollerar den senaste stabila GitHub-releasen en kort stund efter start och därefter **var 12:e timme medan appen körs**, även när fönstret ligger i systemfältet. Automatiska uppdateringar är aktiverade som standard och kan stängas av under **Inställningar**.

Vid en nyare version eller ett ändrat officiellt bygge av samma version hämtas samma Python-ZIP för Windows, macOS och Linux. Releasen består av ZIP-filen och dess SHA-256-fil; kontrollsumman verifieras mot filen innan något packas upp. Vid samma versionsnummer jämför appen det numeriska **release-ID:t**: ett nytt publicerat bygge har alltid ett nytt ID och erbjuds därför även när versionsnumret står stilla. Om en release någon gång skulle innehålla ett byggmanifest jämförs i stället installerad commit och fil-fingeravtryck, och då installerar ett nytt release-ID med identiska filer inte om samma innehåll. En lägre version erbjuds inte som nedgradering. Kontrollen går mot GitHubs **latest release**, inte mot `main`.

Kontrollsumman verifieras, arkivets sökvägar och filer valideras och Python-filerna syntaxkontrolleras innan något ersätts. Innehåller releasen ett byggmanifest måste även det uppackade paketets commit, release-ID och fil-fingeravtryck matcha manifestet. Appen ersätter endast egna program-, start-, dokumentations- och ikonfiler. Databas, `import/`, `export/`, `svg/` och andra användardata ingår inte och lämnas orörda. Installationer med den äldre uppdateraren, som endast jämför versionsnummer, måste installera det första paketet med release-ID-stöd manuellt en gång.

Installationen sker **inuti appen**; du ska inte starta någon separat uppdateringsfil. Därefter startas den uppdaterade Python-appen om utan konsolfönster. Gamla programfiler används som reserv under ersättningen och återställs om installationen eller omstarten misslyckas. Den gamla appen stängs först när den nya processen har bekräftat att gränssnittets händelseloop startat via en engångsbekräftelse med PID och token. Vid timeout eller tidigt avslut stoppas den misslyckade nya processen, filerna rullas tillbaka och den gamla appen lämnas användbar.

Automatisk installation startar först när både Python-ZIP och SHA-256-fil finns i releasen. Om en release fortfarande publiceras väntar appen tyst till nästa kontroll i stället för att göra ett misslyckat installationsförsök. En nedladdning som möts av **HTTP 408, 425, 429 eller 5xx** – till exempel 504 medan GitHub fortfarande genererar releasefilen – eller av en timeout/bruten anslutning görs om automatiskt tre gånger med växande paus innan felet rapporteras; permanenta fel som 404, för stort paket eller en osäker adress stoppas direkt. Under installationen visar uppdateringsknappen stegen **Hämtar och verifierar**, **Installerar filer** och **Startar om**.

Manuell kontroll görs med den framhävda knappen **Uppdatera appen**, **Hjälp → Uppdatera appen** eller **Uppdatera appen** i systemfältets högerklicksmeny. Systemfältsvalet visar fönstret först så att dialogen inte öppnas bakom en dold app. När en uppdatering hittats ändras knapp- och menytexten till **Uppdatering tillgänglig** och den sparade dialogen öppnas direkt utan en onödig ny nätverkkontroll. Dialogen visar om ändringen gäller version, commit, filer eller båda, samt installerad och tillgänglig commit. Välj **Installera och starta om**, **Öppna nedladdningssida** eller **Sök igen** för att tvinga en färsk GitHub-kontroll. Om ZIP eller kontrollsumma saknas visas detta och installationsknappen är avaktiverad tills filerna är klara. Officiella byggen visar även sin commit under **Om PayPamin Flow**.

Kontrollen använder GitHubs publika API och skickar inga faktura-, kund- eller inställningsuppgifter. Automatiska nätverks- och installationsfel loggas utan popup och provas igen vid nästa schemalagda kontroll. Appmappen måste vara skrivbar för den aktuella användaren. Tekniska installationsfel loggas i `~/.paminnelseapp/logs/app.log`.

## Språk / Language

Välj **Inställningar → Språk → Svenska / English** och spara. Språkbytet sker direkt utan omstart och sparas i den lokala databasen. Svenska är standard vid första starten.

Språkvalet gäller huvudfönster, menyer, systemfält, filter, statusar, formulär, PDF-förhandsgranskning, felmeddelanden, belopp och datum samt nya påminnelse-PDF:er. Befintliga fakturor, PDF-mallar, logotypval och autostart fungerar med båda språken. Redan skapade PDF-filer ändras inte i efterhand.

## Valuta / Currency

Varje faktura har en egen valuta. **SEK** är standard för nya fakturor och för befintliga fakturor när databasen uppdateras. Ange en annan ISO-kod med tre bokstäver, till exempel **EUR**, **USD**, **NOK** eller **DKK**, i granskningsformuläret eller när fakturan läggs till manuellt.

PDF-importen föreslår valuta när en kod finns vid **ATT BETALA**, efter **Valuta/Currency** eller i ett sparat markerat valutafält. Kontrollera alltid förslaget. Fakturabelopp, betalt belopp, kvarstående belopp, avgifter och PDF-summor visas i fakturans valuta.

**Appen gör ingen valutaomräkning.** Att ändra valuta ändrar märkningen, inte de inmatade siffrorna. Svensk visning blir exempelvis `1 234,50 EUR`; engelsk visning blir `EUR 1,234.50`.

## Kundtyp sparas för nästa faktura

När du skapar eller redigerar en faktura finns **Kundtyp (sparas på kunden)** direkt under kundnamnet. Välj **Privatperson** eller **Företag** (även Myndighet stöds). Valet sparas när fakturan sparas och förväljs nästa gång samma kund anges, även vid PDF-import. Skillnader i stora/små bokstäver och extra mellanslag påverkar inte matchningen. Du kan alltid ändra valet på den nya fakturan; det uppdaterar kundens standard för framtida fakturor utan att ändra tidigare fakturor eller deras påminnelser.

## Påminnelseavgift och förseningsersättning

Appen har **två fasta avgiftsmodeller**, och du väljer mellan dem i **Inställningar → Avgiftsmodell**. Inget belopp skrivs in för hand i någon av dem.

### Tidigare modell: 150 kr per påminnelse (inte förvald)

**150 kr** är en äldre valbar modell som behålls för bakåtkompatibilitet. Den debiteras högst en gång per fordran, inte en gång per brev. Från v0.7.7 är i stället den lagstadgade modellen standard även vid uppdatering av befintliga installationer.

- Mot **företag och myndigheter** är 150 kr lagligt: det ligger under den lagstadgade förseningsersättningen 450 kr enligt 4 a §, och den lägre ersättningen får alltid krävas.
- Mot en **privatperson** gäller 4 § med ett tak på **60 kr**. 6 § gör ett vidare villkor ogiltigt, så 150 kr **kan inte krävas in** av en privatperson. Appen stoppar dig inte — du har uttryckligen valt modellen — men varje påminnelse till en privatperson visar en varning om taket i bekräftelsedialogen, och **den lagstadgade modellen finns ett klick bort** för just de fakturorna.

### Lagstadgad avgift enligt 4 § och 4 a § (förvald)

| Kundtyp på fakturan | Belopp | Vad det är | Krav |
|---|---|---|---|
| **Privatperson** | **60 kr** | påminnelseavgift enligt 4 § | avtal senast när skulden uppstod (2 §) |
| **Företag** | **450 kr** | förseningsersättning enligt 4 a § | inget avtal behövs |
| **Myndighet** | **450 kr** | förseningsersättning enligt 4 a § | inget avtal behövs |

**Beloppen är fasta i båda modellerna.** De kan inte ändras i appen — det finns inga avgiftsfält i **Inställningar**, bara en väljare och en rad som visar det belopp som gäller. Ett avgiftsbelopp som en äldre version har sparat (till exempel 150 kr som *inställning*) läses aldrig och tas bort ur databasen vid start; modellvalet är det enda som sparas.

**Fakturatexten sparas ordagrant, men upprepas aldrig med gamla villkor.** Texten på fakturan (**Avser**) behåller sin ursprungliga lydelse, till exempel *"Avgift per påminnelse: 150:-. Försenad betalning debiteras 23% ränta."* Påminnelsen skriver inte ut den meningen: den anger i stället den valda avgiften med sin grund och det nya räntevillkoret separat. Allt annat i texten följer med — betalningsuppgifter, äganderättsförbehåll och anmärkningsfrist. Bekräftelsedialogen säger till när ett sådant villkor lämnas utanför, och fakturans egen text ändras aldrig.

**Betalningsvillkor från v0.7.7:**

- **Privatkunder:** Vid försenad betalning debiteras påminnelseavgift om 60 kr.
- **Företagskunder:** Vid försenad betalning debiteras lagstadgad förseningsersättning om 450 kr enligt lag (1981:739), 4 a §.
- **Dröjsmålsränta:** 23 % per år vid försenad betalning.

Villkoren visas under **Inställningar → Betalningsvillkor**. Påminnelseavgiften måste vara avtalad senast när skulden uppkom; 23 % är en **avtalsränta**, inte en lagstadgad räntesats. Bekräftelsen före nya påminnelser kräver att du kontrollerar avtalsgrunden. Nya villkor gäller inte äldre fakturor automatiskt. Räntevillkoret skrivs på nya PDF:er med förtydligandet att det bara gäller om avtalat. **Appen beräknar inte upplupen ränta och lägger inte till något räntebelopp i totalsumman.** Räntesatsen sparas i påminnelsens snapshot; äldre påminnelser får inte det nya räntevillkoret när logotypen ändras eller PDF:en återskapas. Ett gammalt redigerbart räntevärde används inte och tas bort vid start.

Två regler styr hela modellen:

- **En avgift per fordran.** P2-brevet upprepar den avgift som redan debiterades med P1 i stället för att lägga på en ny. Tidigare kunde P1 och P2 tillsammans bli 300 kr för samma faktura; det är rättat.
- **Taket gäller i SEK.** Fakturor i annan valuta kontrolleras inte automatiskt, eftersom appen inte räknar om valutor. Dialogen varnar i stället för att gissa en växelkurs.

**Kundtyp och avtal** anges per faktura i granskningsformuläret. I den **lagstadgade modellen** blir påminnelseavgiften automatiskt **0 kr** för **Företag** och **Myndighet** och förseningsersättningen används i stället; 5 § 2 st. tillåter inte båda för samma fordran. I **150-modellen** gäller 150 kr för alla kundtyper, eftersom det är en avtalsgrundad avgift — men bara företag och myndigheter får debiteras det beloppet. För privatpersoner anger du **var rätten till avgiften avtalades** — i avtalet vid köpet, i offerten eller endast på fakturan. Det sista alternativet är oftast för sent, eftersom skulden uppstod innan fakturan skrevs, och dialogen säger det innan något skickas.

**Skydden i praktiken:**

- I den **lagstadgade modellen** **stoppar** ett belopp över taket påminnelsen med en förklaring i stället för att skrivas ut: 6 § gör ett högre villkor ogiltigt. I **150-modellen** varnar appen i stället för att blockera, eftersom modellen är ett medvetet val — men varningen säger rakt ut att beloppet inte kan krävas in av en privatperson, och 4 §-modellen är ett klick bort.
- En databas från en äldre version får en **kundtyp** som standard **Privatperson**. I den lagstadgade modellen är 60 kr då lagligt i alla relationer; i 150-modellen får just de fakturorna varningen om 4 §-taket.
- En påminnelse som redan skickats med ett äldre belopp behåller sitt historiska belopp och sin grund. P1 låser beloppet, P2 upprepar det, och ett byte av modell gäller bara påminnelser som inte skapats än.
- En påminnelse som skapas i 150-modellen skriver **"Avgift per påminnelse enligt avtal, 150 kr."** i stället för en paragraf, eftersom 4 § inte ger stöd för 150 kr. I den lagstadgade modellen står 4 § respektive 4 a § som förut.
- Avgiften är **momsfri** och appen lägger aldrig på någon ränta.

## Autostart

Autostart gäller endast den inloggade användaren och kräver inga administratörsrättigheter. Appen synkroniserar valet vid start och när inställningarna sparas.

| System | Mekanism |
| --- | --- |
| Windows | `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\PayPamin Flow.lnk`, med PayPamin Flow-ikon och `wscript.exe start_paypamin_flow.vbs --minimized`, vilket ger samma runtime-kontroll och konsolfria start som manuell start |
| macOS | `~/Library/LaunchAgents/se.paypamin.flow.plist` |
| Linux | `$XDG_CONFIG_HOME/autostart/paypamin-flow.desktop`, normalt `~/.config/autostart/` |

Stäng av eller aktivera via **Inställningar → Starta PayPamin Flow automatiskt när jag loggar in**. Windows-genvägen skapas atomiskt med Windows eget genvägsgränssnitt via dold PowerShell och får explicit appens `.ico`-fil. Den tidigare registerposten under `CurrentVersion\Run` tas bort vid synkronisering så att ingen dubbelstart sker. Autostartkommandot använder **inte `.pyw`**. Om appmappen flyttas, starta appen en gång från den nya platsen så uppdateras sökvägen. Autostart sker efter inloggning och öppnar inget konsolfönster.

## Logotyp och appikon

Huvudikonen föreställer ett vitt **P-märke** – ett fakturadokument sett från sidan – med en grönturkos **bock** i en vit rundel, på mörkblå bakgrund med ett diagonalt turkost svep i nedre vänstra hörnet. Alla färger är plana – inga tonövergångar – eftersom en gradient blir grumlig i systemfältets 16–32 px. Den är ritad för att vara tydlig även i små storlekar och används i stället för Pythons ikon. Samma motiv används för huvudfönster, sekundära fönster, systemfält, aktivitetsfält, Aktivitetshanterarens appvy, macOS Dock, Linux och Windows-autostartgenväg.

Den horisontella logotypen kombinerar symbolen med PayPamin Flow-ordmärket och används i sidhuvudet och Om-fönstret. Arkiv-/Hjälpmenyer, högerklicksmeny, verktygsrader och dialogknappar använder **endast text**, utan funktionsikoner. Textetiketterna, snabbkommandona och funktionerna är oförändrade.

Original och skrivbordsformat ligger i `assets/`:

- `paypamin_flow.svg` – redigerbart vektororiginal för appikonen.
- `paypamin_flow_small.svg` och `paypamin_flow_tiny.svg` – förenklade original för 24–40 px respektive 16–24 px; den minsta varianten har ingen bock, eftersom den bara blir en grå fläck i 16 px.
- `paypamin_logo.svg` och `paypamin_logo.png` – horisontell logotyp.
- `paypamin_flow.png` och storleksvarianter – Tkinter, systemfält och Linux.
- `paypamin_flow.ico` – Windows, flera inbäddade storlekar.
- `paypamin_flow.icns` – macOS-ikonkälla.
- `icons/` – funktionsikoner med normal och `_light`-variant för varje symbol, ritade i samma mörkblå som märket.

Systemfältet får den storlek operativsystemet faktiskt ritar: den förenklade 32 px-varianten på Windows och 48 px på macOS och Linux menyrad. Varje storlek rastreras från den master som är ritad för den – detaljerad från 40 px, förenklad 24–40 px och minst 16–24 px. Nedskalningen sker med förmultiplicerad alpha, så kanterna behåller ikonens färg i stället för att bli grå.

Tryckfilerna ligger i `assets/print/` och **följer med releasepaketet** – de behöver aldrig laddas ner separat. Öppna mappen direkt från appen med **Arkiv → Öppna tryckfiler**.

- `paypamin_logo_print.svg` och `paypamin_logo_print.pdf` – färgversion, vektor.
- `paypamin_logo_print_mono.svg` och `paypamin_logo_print_mono.pdf` – enfärgsversion för stämpel, gravyr och etikett.
- `paypamin_logo_print*.png` – förhandsvisningar på vit botten.
- `README.txt` – mått, färger, fritt utrymme och rekommendationer till tryckeriet.

PDF:erna är 98 × 23,1 mm inklusive 4 mm fritt utrymme, innehåller bara vektor och har metadata med skapare och copyright. Logotypen är beskuren till konsten (788,33:132), så ingen tom yta följer med till tryckeriet.

Generera om logotyp, raster-/skrivbordsikoner, tryck-PDF:er och samtliga funktionsikoner med Pillow installerat:

```sh
python assets/build_icons.py
```

## Skapa Python-releasepaket

Det finns inget PyInstaller- eller native-byggsteg. Skapa det plattformsoberoende paketet och dess kontrollsumma med:

```sh
python packaging/package_release.py --output release-assets
```

GitHub Actions-workflöen i `.github/workflows/build.yml` kör testerna på Windows, macOS och Linux. Ubuntu-jobbet installerar Tkinter och Xvfb, kör de verkliga Tk-testerna på en 1280×900-skärm och skapar Python-ZIP och SHA-256-fil. Vid en release bifogas **endast dessa två filer** för appens uppdateringsfunktion.

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

**Hjälp → Visa teknisk logg** öppnar `~/.paminnelseapp/logs/app.log` med de detaljerade domänposterna. **Hjälp → Visa aktivitetslogg** öppnar `logs/activity.log` med de strukturerade `Activity`-händelserna för knappar, menyer, högerklicksmenyer, systemfält, filter, fakturaval och uppdateringar. **Hjälp → Öppna loggmappen** visar alla tre filerna och arkivet. Den samlade felloggen ligger i `~/.paminnelseapp/logs/errors.log`; startfel och uppdateringssteg skrivs till `logs/app.log`. Kända äldre loggar och rotationer flyttas vid start till samma undermapp utan att befintliga loggfiler skrivs över. En åtgärd får start- och slutpost med samma spårnings-ID, varaktighet och returtyp; fel får i stället feltyp, meddelande och traceback. Sessionens ID och tidsstämpel med tidszon ingår i varje händelse. Oväntade Tk-callbackfel fångas också i den konsollfria installationen.

PDF-/reskontraläsning, faktura- och kundändringar, betalavstämning, P1/P2, e-post, importbevakning, autostart, cache, arkivering, JSON-/ZIP-säkerhetskopior och uppdateringarnas hämtning/installation/omstart har dessutom sina mer detaljerade befintliga loggposter. Den generella aktivitetsloggen sparar inte e-postmeddelandens brödtext eller lösenord. Loggfilerna roteras vid midnatt och vid 5 MB med unika, icke-destruktiva rotationsnamn; gårdagens och äldre filer flyttas till loggarkivet och tas bort när de är äldre än sju dagar. **Visa samlad fellogg** är fortfarande den kortare vyn för enbart olösta fel och tracebacks. Loggar kan innehålla kund-, faktura-, belopps- och sökvägsuppgifter och ska granskas innan de delas.

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

- Databas, mallar och inställningar sparas i användarprofilen under `~/.paminnelseapp`; dagens tre loggar (`app.log`, `activity.log`, `errors.log`) och det sjudagars långa arkivet ligger i undermappen `~/.paminnelseapp/logs/`. Det befintliga katalognamnet behålls så att tidigare data inte försvinner efter namnbytet.
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

## Stöd PayPamin Flow

**Hjälp → Stöd PayPamin Flow** öppnar en egen donationsdialog med tre kanaler: **Swish** (QR-kod), **PayPal** och **Ko-fi**. Layouten följer appens supportsida: korten för PayPal och Ko-fi är knappar som öppnar respektive sida i webbläsaren, medan **Swish är den enda kanalen med en kod** — ingen QR-kod ritas för PayPal eller Ko-fi, eftersom de inte har någon att skanna. Kortet under kanalerna berättar vad en gåva betalar för (*Underhåll*, *Nya funktioner*, *Oberoende*), med stödjande trygghetsrad (*säker betalning hos betaltjänsten*, *kvitto direkt från betaltjänsten*, *ingen spårning*, *svensk utvecklare*), och att gåvan är helt frivillig. Hela innehållet finns **bara i appen** – det finns ingen separat supportsida och ingen länk till någon: de två knapparna är de enda adresser som kan öppnas. Dialogen är byggd för att vara enkel att lita på:

- **Beloppen är låsta.** Du väljer mellan **25, 50, 100 eller 200 kr**. Det finns inget fält för ett eget belopp, och ett belopp utanför de fyra avvisas i stället för att bli en betalkod.
- **Mottagare och länkar är låsta.** Swishnumret, PayPal-adressen och Ko-fi-adressen ligger som konstanter i `donations.py` — inte i databasen. Det finns ingen inställning och inget fält som kan peka donationen någon annanstans, och en återställd säkerhetskopia kan därför aldrig byta mottagare. Appen kontrollerar varje adress mot den låsta listan innan webbläsaren öppnas; en okänd adress loggas och öppnas inte alls.
- **Swish-koden ritas lokalt.** Koden är en helt vanlig Swish-standardkod (`C<nummer>;<belopp>;;6`) och byggs av appens egen QR-kodare i `qr_code.py`. Ingenting hämtas från nätet, så koden fungerar offline och avslöjar aldrig att appen öppnades. Swish-appens egen skanner läser den direkt, och mask `6` låter dig ändra belopp och meddelande i appen medan mottagaren är låst.
- **Beloppet följer med.** PayPal-knappen öppnar `paypal.me/.../<belopp>SEK`, där du alltid kan ändra summan. Ko-fi tar valfritt belopp och även månadsstöd. Det valda beloppet fyller i både Swish-koden och PayPal-länken och står som *Valt belopp* under knapparna.
- **Kanalernas färger bär aldrig betydelsen.** Swish, PayPal och Ko-fi har var sin knappfärg med vit text som klarar kontrastkravet, och i högkontrastläget byts de mot palettens accentyta. Korten använder samma bakgrunds- och textfärger som resten av appen, så textstorlek och högkontrast gäller även här.
- **Inget låses upp.** Donationer är helt frivilliga och ger inga fler funktioner. Appen fungerar precis likadant utan, och dialogen säger det.

Numret visas också i klartext (`0721-817 177`) med en **Kopiera nummer**-knapp, för den som hellre swishar manuellt. Ingen betalning sker i appen — den visar bara koden och öppnar dina egna sidor. Val av belopp, kopiering och att dialogen öppnas loggas som vanliga aktiviteter (`donation`), aldrig med betaluppgifter.

## Begränsningar

- PDF-layout och OCR kan misstolka fält. Kontrollera fakturan före godkännande. Reskontraimporten kräver textbaserad PDF och stoppar vid oläsbara rader eller avvikande kontrollsummor.
- Betalstatus hämtas inte direkt via Fortnox. Den kan avstämmas med bekräftade, kompletta reskontralistor; kontrollera alltid importsammanfattningen och verifiera betalningar före utskick.
- Dagregler, avgifter och avtalsvillkor måste verifieras för verksamheten. Appen visar ett avtalat räntevillkor om 23 % per år men beräknar inte upplupen ränta.
- Automatisk e-post eller automatisk ansökan till Kronofogden ingår inte.

## Copyright och licens

**Copyright © 2026 Rickard Längkvist, Tadega AB. Skapare: Rickard Längkvist.** Villkoren finns i `LICENSE`, som följer med varje kopia av programmet, och en kort sammanfattning i `NOTICE`.

- **Gratis att använda**, privat och i kommersiell verksamhet. Ingen avgift, prenumeration eller betalvägg, och inga funktioner låses upp av en betalning.
- **Inga ändringar utan tillstånd.** Programmet får inte ändras, anpassas, översättas eller spridas i ändrad form utan skriftligt tillstånd från rättighetsinnehavaren. Att skapa egna logotyper, fakturor och andra datafiler med programmet räknas som vanlig användning.
- **Upphovsrätten tillhör Rickard Längkvist, Tadega AB.** Copyright-, licens- och NOTICE-notisen ska följa med varje kopia.
- **Ingen garanti.** Programmet tillhandahålls i befintligt skick. Kontrollera alltid fakturor, avgifter och påminnelser innan de skickas.
- **Tredjepartsbibliotek** som reportlab, PyMuPDF, Pillow och opencv installeras för sig och har egna licenser, som gäller för dem.
