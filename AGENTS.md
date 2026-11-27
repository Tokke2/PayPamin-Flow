# AGENTS.md — PayPamin Flow

Detta dokument samlar **alla hårda regler och arkitekturkrav** anpassade specifikt för **PayPamin Flow** (`Tokke2/PayPamin-Flow`). Alla agenter och bidragsgivare måste följa varje punkt nedan utan undantag.

---

## 1. Persistens av nya regler (`regel` / `- hård regel`)

- **Skriv alltid in regler på GitHub**: Så fort användaren skriver `regel` eller `- hård regel` i chatten ska regeln omedelbart läggas till eller uppdateras i denna `AGENTS.md` i repo-roten och pushas till den aktiva branchen på GitHub.

---

## 2. Branch- och Git-disciplin (`- hård regel`)

- **All koduppdatering till standardbranchen – skapa ALDRIG nya brancher (`- hård regel`)**: All koduppdatering ska alltid skrivas till den aktiva standardbranchen i sessionen och inga nya extra brancher får någonsin skapas manuellt. Ta bort övriga/inaktiva brancher på GitHub så att **endast en enda aktiv branch** finns kvar (sätt den aktiva branchen som `default_branch` i GitHub Settings innan en äldre standardbranch tas bort). *(Obs: I Arena Agent Mode är varje chatt-session tekniskt låst till sin tilldelade sessionsbranch `arena/<id>-paypamin-flow`; repots standardbranch är `arena/8f4dd6f8-paypamin-flow`. Vid ny chatt ska standardbranchen och sessionens tilldelade branch kontrolleras innan ändringar görs. Om Arena har tilldelat en annan branch ska konflikten förklaras; byt inte branch eller arbeta mot `main` i smyg.)*
- **Arbeta ALDRIG mot `main` (`- hård regel`)**: Skapa, pusha, bygg eller uppdatera aldrig mot `main` – särskilt inte vid appuppdateringar eller CI-flöden. All kod, alla tester och all release-publicering sker enbart från den aktiva branchen (`arena/*`).
- **Merga ALDRIG (`- hård regel`)**: Kör aldrig `git merge`, `gh pr merge` eller motsvarande sammanslagning.
- **Öppna ALDRIG Pull Requests från `arena/*`**: Arena spårar sessionen via branchen; att öppna eller stänga en temporär PR kan stänga branchen och avbryta sessionen. CI kör hela testmatrisen (`windows-latest`, `macos-latest`, `ubuntu-latest`) direkt vid `push` till `arena/**`.
- **Endast en branch på GitHub**: Standardbranchen ska vara `arena/8f4dd6f8-paypamin-flow`. Ta endast bort andra brancher efter att standardbranchen pekats rätt och deras historik kontrollerats; radera aldrig den aktiva sessionsbranchen. Nya chattar ska läsa dessa regler före arbetet.
- **Byt inte namn på den aktiva branchen**: Sessionens branchnamn är låst.

---

## 3. GitHub Release & appuppdatering via filjämförelse (`- hård regel`)

- **Uppdatera ALLTID GitHub Release vid kodförändring och markera som `Latest` (`- hård regel`)**:
  - Varje kodförändring som pushas ska flytta releasetaggen (`v<APP_VERSION>`) till den nya commiten, uppdatera releasens beskrivning (`packaging/release_description.py`), säkerställa att releasen inte är utkast/förhandsrelease (`draft=false`, `prerelease=false`) och **uttryckligen markera releasen som `Latest` (`make_latest=true`)**.
  - Releasen består av källkodsarkivet vid taggen och det automatiskt byggda `PayPamin-Flow-Python.zip` med SHA-256-fil för äldre installationer. Alla nedladdningar måste komma från samma testade commit. `packaging/verify_release.py` verifierar taggens commit, releasebeskrivningen, att releasen är `Latest`, samt att källkodsarkivet matchar commiten byte för byte.
- **Appen jämför filer vid uppdatering (`- hård regel`)**:
  - Uppdateraren (`update_checker.py`, `update_installer.py`, `update_state.py`) får aldrig lita blint på versionsnumret. För samma version jämförs releaseinnehållet och de faktiska programfilernas SHA-256-kontrollsummor (`evaluate_release`, `compare_package_files`).
  - En äldre release får aldrig skriva över nyare lokala filer (`CONTENT_STALE`).
- **Säker installation, atomisk återställning och radering av backup vid lyckad uppdatering**:
  - Före filbyte kontrolleras skrivbehörighet och paketets integritet (`build_info.py`, versionsstämpel, obligatoriska filer och ikoner).
  - Om installationen eller omstartshandskakningen (`wait_for_update_restart` / `mark_update_ready`) misslyckas återställs samtliga filer och installationsstatus atomiskt (`rollback_update`).
  - **När uppdateringen lyckas raderas backupen och temporära uppdateringsmappar omedelbart** (`cleanup_update` och `cleanup_completed_update_backups`), samtidigt som användardata (`~/.paminnelseapp`, `import/`, `export/`, `svg/`) aldrig rörs.

---

## 4. Daglig automatisk uppdatering, resurser och konsolfri körning

- **Automatisk uppdateringskontroll kl. 00:00 varje dag (`- hård regel`)**: Använd datorns lokala tid. Installera automatiskt endast om en verifierad ny uppdatering finns och automatisk uppdatering är aktiverad. Appen kan inte köras när datorn är avstängd; efter vila eller missad körning görs en enda uppsamlingskontroll när appen åter kan köra. Behåll manuell uppdateringskontroll. Ingen tät nätverkspollning.
- **Minnes- och energihushållning**: Undvik obegränsade bild-/PDF-cacher, återkommande omrendering utan ändringar och parallella dubblettjobb. Frigör dokument, bilder, filhandtag och timerjobb när fönster stängs. Mät och regressionstesta konkreta förbättringar; lova inte omätbara prestandavinster.

### Konsolfri körning & minimerad start (`REQ-K4`)

- ** visa ALDRIG ett terminalfönster**: Varken vid start (`start_paypamin_flow.vbs`, `paypamin_flow_launcher.py`, `paypamin_flow.pyw`), bakgrundskontroll av Python-tillägg (`python_maintenance.py`), PDF-/OCR-skanning (`pytesseract`, `pdf2image`), e-postutkast eller appuppdatering får ett konsol-/terminalfönster blinka förbi (`console_free.py` med `pythonw.exe`, `CREATE_NO_WINDOW` och dold `STARTUPINFO`).
- **Starta alltid minimerad i systemfältet**: Appen döljs direkt vid initiering och startar alltid minimerad i systemfältet (`start_minimized()`), oavsett äldre inställningsvärden.
- **Inga tysta fel (`REQ-K4` / `quiet_faults.report_fault()`)**: `except ...: pass` (eller motsvarande tyst sväljning av undantag) är förbjudet och bevakas av `tests/test_quiet.py`. Alla medvetet fångade icke-kritiska fel ska rapporteras via `quiet_faults.report_fault()` eller loggas uttryckligen.

---

## 5. Logghantering & aktiv fellogg

- **Exakt tre aktiva dagsloggar i `~/.paminnelseapp/logs/`**:
  1. `app.log` — komplett teknisk logg (inklusive start- och uppdateringshändelser).
  2. `activity.log` — strukturerade spårbara användar- och systemhändelser.
  3. `errors.log` — aktiv, samlad fellogg över alla oåtgärdade fel från `app.log` och `activity.log`.
- **Daglig arkivering & 7 dagars gallring**: Gårdagens roterade loggar flyttas automatiskt till `logs/arkiv/YYYY-MM-DD/` och arkiverade loggar raderas automatiskt efter **7 dagar** (`RETENTION_DAYS = 7` i `log_archive.py`).
- **Åtgärdade fel tas bort från aktiv fellogg**: När ett eller samtliga fel markeras som åtgärdade (`resolve_errors` / `resolve_selected_errors` i `error_log.py`) arkiveras de under `logs/arkiv/resolved/YYYY-MM-DD/` och tas bort från den aktiva `errors.log` utan att ändra historiken i `app.log`.

---

## 6. Skärmanpassning, visuell skärpa, varumärke & app-specifik UI-logik

- **Maximal fönsterhöjd och innehållsanpassad bredd vid start**: Huvudfönstret öppnas med skärmens maximala tillgängliga arbetsytehöjd (`monitor_work_area`) och en bredd anpassad efter innehållet (tabellkolumner och verktygsrader) utan att hamna under aktivitetsfältet. Dialogrutor anpassas automatiskt efter sitt innehåll (`ScrollableForm.fit_to_content`) så att onödig scrollning undviks.
- **Knivskarp grafik på alla skärmar och DPI-nivåer**:
  - Windows Per-Monitor DPI Awareness v2 aktiveras innan Tk startas.
  - All nedskalning av logotyp och ikoner sker från högupplösta original i förmultiplicerad `RGBa` (`Image.LANCZOS`) för att eliminera grå kanthalo, med dedikerad ljus och mörk ordmärkesvariant.
  - PDF-förhandsvisningen (`preview_invoice`) renderas i skärmens faktiska upplösning med zoomstöd och exakt rektangelmarkering för fältzoner (inklusive OCR-reserv för skannade fakturor).
  - Alla logotyper och ikoner byggs deterministiskt från rena vektormastrar (`assets/*.svg`, `assets/print/*.svg` utan `<text>`- eller `<filter>`-beroenden, med redigerbara namngivna vektorgrupper för tryck) via `assets/build_icons.py` och verifieras med `assets/verify_branding.py`.
- **Projekt- och rutval**: Återställ ett tidigare rutval i projektskaparen endast i appar där funktionen faktiskt fanns. PayPamin Flow har ingen projektskapare och ska inte få en konstgjord sådan.
- **Anpassa funktioner efter varje app**:
  - **Kolumner**: PayPamin Flow har tabellkolumner (`ttk.Treeview`) – samtliga tabeller ska stödja både sortering (med tydlig riktningsindikator) och flytt/omordning av kolumner (`displaycolumns`, sparat i inställningar för huvudtabellen).
  - **Profiler**: Underflik för profiler i Inställningar läggs *endast* till i appar som faktiskt använder användarprofiler. PayPamin Flow är en enbolags- och kundreskontraapp utan användarprofiler och ska därför inte ha en konstgjord profilflik i Inställningar.

---

## 7. Kvalitet, bakåtkompatibilitet & obligatoriska tester

- **Inga tysta beroende- eller gränssnittsbrott**: Uppgradera aldrig användarens befintliga Python-installation i smyg. Bryt aldrig befintliga modulgränssnitt, SQLite-scheman eller tvåspråkiga översättningsnycklar (`sv`/`en` i `i18n.py`).
- **Obligatorisk verifiering före leverans**: Innan ett arbete betraktas som klart måste:
  1. `python assets/verify_branding.py` passera utan fel.
  2. Hela testsviten (`python -m unittest discover -s tests -v`) passera till 100 %.
  3. GitHub Actions (`desktop` på Windows/macOS/Linux samt `refresh-release-files`) och `Latest`-releasen verifieras mot den pushade commiten.

---

## 8. Förslagsregler i chatten (`- hård regel`)

- **25 nya förslag vid efterfrågan**: Skriv alltid de 25 förslagen direkt i chatten, inte bara i en fil. Förslagen ska vara konkreta och relevanta för användarbehov. Påstå inte att konkurrenter saknar en funktion eller att efterfrågan är verifierad utan belägg.
- **Spärra återbruk**: Läs `FORSLAG.md` före varje förslagslista och för in nya förslag där när de presenteras.
- **10-meddelanderegeln (`- hård regel`)**: Var 10:e meddelande i konversationen ska en ny lista med **10 nya, aldrig tidigare använda förslag** visas direkt i chatten.
