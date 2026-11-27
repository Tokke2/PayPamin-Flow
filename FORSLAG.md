# PayPamin Flow — Förslagsbank och spärrlista

> Förslagen är kandidater utifrån praktiska användarbehov, inte verifierade påståenden om konkurrenter eller uppmätt efterfrågan. Listorna har skrivits direkt i chatten. Presenterade förslag sparas här som spärrlista för kommande 10-/25-förslagslistor.

## Senast presenterat i chatten (25 st — v0.7.9-arbetet)

1. **Avtalsbevis för avgift och ränta** — koppla offert/avtal, datum och kontrollsumma till fakturan.
2. **Varning för ändrat betalningskonto** — jämför påminnelsens betalningsuppgifter med originalfakturan.
3. **Diskret skärmläge** — maskera kundnamn och belopp vid skärmdelning.
4. **Mottagarundantag per faktura** — ändra ärendets mottagare utan att ändra kundens standard.
5. **Kontroll av exakt mejlbilaga** — visa bifogad PDF:s filnamn, fakturanummer och kontrollsumma.
6. **Låsning av pågående utskicksärende** — varna vid samtidig behandling i flera appinstanser mot samma databas.
7. **Spårbar avgiftseftergift** — efterskänk avgift helt/delvis med orsak och historik.
8. **Särskilt dödsboläge** — separat mottagarhantering och manuell granskning före åtgärder.
9. **Separat saldo för kapital och avgift** — särskilj obetalda avgifter efter betald huvudfaktura.
10. **Återställ osparat fakturautkast** — återuppta inmatning efter krasch utan en skarp fakturarad.
11. **Skydd mot fel systemdatum** — upptäck stora klockhopp före eskalering.
12. **Bevisrad för tolkade belopp** — visa summeringsrutan/texten som ligger bakom valt belopp.
13. **Versionsjämförelse av ersatta original** — visa skillnader mellan två PDF-versioner av samma faktura.
14. **Studsad e-post som egen status** — registrera leveransproblem och begär adressrättning före nästa utkast.
15. **Öresavvikelsekontroll** — förklara differenser mellan ursprungsbelopp, delbetalningar och saldo.
16. **Beställarreferensstyrd fakturarouting** — föreslå kundavdelning utifrån ordernummer/kostnadsställe.
17. **Tidsbegränsad ersättningskontakt** — reservmottagare under semester med automatisk återgång.
18. **Extra granskningssteg för stora krav** — dokumenterad andragranskning över en beloppsgräns.
19. **Avidentifierat supportpaket** — tekniska uppgifter utan kunddata och dokument.
20. **Diskutrymmesbudget före masskanning** — uppskatta arbetsutrymme och stoppa säkert före full disk.
21. **Utskriftsmanifest** — kontrollista för fakturor, sidor och antal exemplar.
22. **Stortryck för enskilda kunder** — kundspecifik PDF-typografi utan att ändra alla brev.
23. **Karantän för riskabla PDF:er** — avskilj skadade eller resurskrävande dokument med felorsak.
24. **Giltighetstid för leverantörsvillkor** — datumsätt villkor och betalningsuppgifter för historiskt riktiga brev.
25. **Simulera nästa åtgärd** — torrkör brev, betalningsfrist och belopp utan status-/historikändring.

---

## Tidigare presenterad lista (25 st — före v0.7.9)

1. **Lokal SIE-4-bokföringsexport för påminnelseavgifter och kundbetalningar** — Generera färdiga `.se`-verifikationsfiler (SIE 4) direkt på datorn när en faktura slutbetalas inklusive lagstadgad påminnelseavgift (60 kr) eller förseningsersättning (450 kr), så bokföringen i Visma, Fortnox eller Bokio uppdateras utan manuell kontering.
2. **Interaktiv betalningsplan / avbetalningsöverenskommelse (PDF + bevakning)** — Skapa en juridiskt tydlig avbetalningsplan på 2–6 delbetalningar med egna förfallodatum, där PayPamin Flow bevakar varje delbetalning lokalt och pausar P2/Kronofogden så länge kunden följer planen.
3. **Automatisk kontroll av kreditfaktura mot debetfaktura i importmappen** — Upptäck kreditfakturor vid PDF-import, matcha dem mot ursprungsfakturan via fakturanummer eller referens och räkna ned kvarstående belopp automatiskt efter användarens bekräftelse.
4. **Automatisk bankkontonummer- och Bankgiro/PlusGiro-validering vid leverantörs- och mallinställning** — Kontrollera kontrollsiffra på Bankgiro, PlusGiro och IBAN lokalt (MOD-10/MOD-97) så att ett skrivfel aldrig hamnar på utskickade påminnelser.
5. **Kundspecifik kontaktlogg för telefonsamtal och muntliga löften ("Lovade betala fredag")** — Snabbnotering på fakturaraden med datumstyrd snooze-påminnelse som lyfter tillbaka ärendet exakt dagen efter kundens utlovade betaldatum om pengarna uteblivit.
6. **Valutamedveten växelkursnotering vid delbetalning i SEK på EUR/USD-faktura** — Registrera inbetalt SEK-belopp mot utländsk fakturavaluta med dokumenterad avräkningskurs så kvarstående saldo i originalvalutan alltid stämmer på öret.
7. **Samlingspåminnelse (Kontoutdrag för kunder med flera förfallna fakturor)** — Slå ihop 2–15 förfallna fakturor för samma kund till ett överskådligt samlingsbrev med specifikation per faktura och korrekt engångsavgift per enskild fordran.
8. **Lokal ISO 20022 `camt.054` / BgMax-betalfilsavläsning** — Dra in bankens återrapporteringsfil från Bankgirot eller internetbanken direkt i appen för att pricka av betalda fakturor och delbetalningar med exakt betaldatum helt utan API-koppling.
9. **Förhandskontroll av motpartsstatus via lokal Bolagsverket/org.nr-validering (Luhn + bolagsform)** — Identifiera enskild firma kontra aktiebolag, handelsbolag, kommun och privatperson direkt från organisations-/personnummerstrukturen så rätt avgiftsregel (4 § vs 4 a §) föreslås direkt.
10. **Tvist- och invändningsläge med fryst påminnelsetid ("Saklig invändning enligt god inkassosed")** — Ett dedikerat tviststatusläge som låser P2 och Kronofogden-eskaleringsflödet med obligatorisk orsaksnotering så man aldrig bryter mot god inkassosed vid bestridd faktura.
11. **Visuell tidslinje per faktura från fakturadatum till slutbetalning** — En kompakt horisontell händelsetidslinje i detaljpanelen som visar Faktura → Förfallodag → P1 → E-post → Delbetalning → P2 → Betald med exakt antal dagar mellan stegen.
12. **Malltestare ("Torrkör leverantörsmall mot 5 PDF:er")** — Testa en sparad PDF-zonmall mot flera fakturor i en mapp på en gång och se avlästa värden sida vid sida innan fakturorna importeras skarpt.
13. **Säker skrivskyddad granskningsvy för revisor ("Revisorspaket ZIP")** — Exportera ett självständigt, lösenordsskyddat eller checksumme-signerat granskningspaket med CSV-sammanfattning, påminnelse-PDF:er och händelselogg för valt räkenskapsår.
14. **Anpassningsbara e-postsignaturer och avsändarblock per leverantörsmall** — Koppla kontaktperson, telefonnummer och öppettider för fakturafrågor till respektive leverantörsmall så kundmejl alltid visar rätt avsändaruppgifter.
15. **Intelligenta varningar för postnummer/adressavvikelser och ogiltiga mottagare före PDF-utskrift** — Flagga fakturor som saknar postadress eller har ofullständig e-post innan utskrifts- eller utskicksrundan påbörjas.
16. **Fönsterutbrytning för dubbelbildskärm ("Dockningsbar PDF-förhandsgranskning bredvid listan")** — Visa markerad originalfaktura eller påminnelse-PDF live på skärm 2 medan du navigerar med piltangenterna i fakturalistan på skärm 1.
17. **Lokal kassaflödesprognos för kommande 7 / 14 / 30 dagar** — Beräkna förväntat inbetalningsflöde viktat efter kundens historiska betalningsmönster efter P1 respektive P2, helt lokalt utan molnanalys.
18. **Snabbimport från urklipp / skärmklipp för pappersfakturor** — Klistra in en bild eller text direkt från urklipp (`Ctrl+V`) för lokal OCR-tolkning när en faktura kommit via skanner eller mejltext i stället för PDF.
19. **Spårbar makulerings- och kreditlogg för redan utskickad påminnelse ("Återkallelsebrev PDF")** — Generera ett artigt ensidigt återkallelsemeddelande som PDF/e-postutkast om betalning korsat påminnelsen på bankgirot samma dag.
20. **Säkerhetskopieringsverifiering med "Provläs utan att skriva över"** — Granska exakt antal fakturor, kunder, mallar och senaste ändringsdatum inuti en `.zip`-säkerhetskopia innan du bestämmer dig för att återställa den.
21. **Tangentbordsstyrd kommandopalett (`Ctrl+K`)** — Hoppa blixtsnabbt till valfri kund, fakturanummer, vyflik eller åtgärd ("Skapa P1 för 10452", "Öppna papperskorg", "Byt tema") utan att släppa tangentbordet.
22. **Automatisk mapporganisering av färdigbetalda original-PDF:er efter år/månad** — Valbar regel som flyttar eller kopierar slutbetalda faktura-PDF:er till en prydlig lokal ` betalda/2026-11/ `-struktur utan att bryta länken i historikvyn.
23. **Kundkort med historisk betaltidsprofil ("Betalar i snitt +6 dagar efter P1")** — Visa direkt på kundkortet och i detaljraden hur snabbt just den kunden brukar betala efter förfallodag respektive första påminnelse.
24. **Utskriftskö för fönsterkuvert (Svensk C5 H2-standardplacering)** — Valbar kuvertanpassad adressplacering på påminnelse-PDF:en samt sammanslagen utskrifts-PDF för dagens alla brevutskick i ett enda svep.
25. **Hälsokontrollpanel för lokal miljö ("Systemstatus & Självtest")** — En överskådlig dialog i Hjälp-menyn som visar status för SQLite-integritet, diskutrymme, PDF-motor, OCR-språkpaket, loggarkiv och senaste säkerhetskopia på 1 sekund.

---

## Tidigare presenterade / förbrukade förslag (spärrlista — återanvänd ej)

Följande förslag är redan implementerade eller har presenterats i tidigare sessioner och får ej återanvändas i nya listor:
- Implementerade i `v0.7.0` (2026-11-25): Helgdags- och bankdagskalender för förfallodatum och frister (svenska bankdagar) · Tvåspråkig påminnelse-PDF och e-post på kundnivå (svenska / engelska per kund).
- Tidigare session (2026-11-25):
1. Swish-QR på påminnelse-PDF · 2. TonChange-trappa · 3. Betalningsrisk-poäng per kund · 4. Åldersfördelningsrapport (30/60/90) · 5. Räntekalkyl enligt räntelagen · 6. Kvittensläge · 7. Betalningskalender · 8. Batch-läge med tangentbordsflöde · 9. Offline-OCR-fallback · 10. Utökad dubbeldetektering · 11. OCR-nummer-validering · 12. Företagsprofiler · 13. Bevakade mappar per profil · 14. Kolumnprofiler · 15. Färgmarkerad urgenskolumn · 16. E-postutkast-generator · 17. Kronofogden-checklista-generator · 18. Dagboksutdrag för domstol · 19. Smart filnamnskonvention · 20. Statistikpanel · 21. Lokal krypterad databas · 22. Schemalagda säkerhetskopior · 23. Tysta timmar + energisnål schemaläggning · 24. Tillgänglighetsläge · 25. Förstagångs-guide.
