# Manuell tillgänglighetsverifiering

Den här checklistan kompletterar `tests/test_tk_accessibility.py`. De automatiska testerna använder verkliga Tk-fönster och kontrollerar fokus, geometri, scrollning och färger, men de verifierar **inte** vad en skärmläsare läser upp.

Använd en testkopia av appen och testdata. Anteckna operativsystem, Python-/Tk-version, skärmläsare och version, textstorlek samt kontrasttema för varje genomkörning.

## Gemensam genomgång

1. Starta PayPamin Flow utan konsolfönster. Kontrollera att huvudfönstret och dialogerna använder appikonen och att inga nya konsolfönster öppnas.
2. Gå igenom huvudfönstret med **Tab** och **Shift+Tab**. Fokus ska vara synligt, följa den visuella ordningen och aldrig fastna eller hoppa till en dialog bakom huvudfönstret.
3. Öppna **Arkiv** med **F10/Alt+A** och **Hjälp** med **Alt+H**. Använd pilarna och Enter. Öppna hjälpen med **F1**.
4. Kontrollera fakturalistan med piltangenter, **F2**, **Shift+F10** och menyknappen. Ingen faktura ska ändras utan det vanliga uttryckliga valet eller godkännandet.
5. Öka texten till **200 %**. Upprepa kontrollen i Inställningar, Lägg till/Redigera faktura, Redigera kund, Redigera P1/P2, hjälpfönstret och e-postförhandsgranskningen.
6. Gör fönstren mindre. Alla fält och åtgärdsknappar ska kunna nås genom storleksändring eller rullning. Tabbning till ett fält utanför den synliga delen ska rulla fram det.
7. Ändra operativsystemets högkontrastläge medan appen är öppen. Paletten ska växla automatiskt utan omstart och utan att fakturadata eller PDF:er ändras. Stäng av läget och kontrollera att den vanliga paletten kommer tillbaka.
8. Kontrollera att text, fokusramar, markerade rader, inmatningsfält och knappar är läsbara i båda lägena. Status får inte förmedlas enbart med färg.
9. Återställ texten med **Ctrl/Cmd+0**. Stäng alla dialoger och kontrollera att fokus och eventuell modal grab återgår till rätt fönster.

## Windows 11 + NVDA

1. Starta NVDA och sedan appen via `start_paypamin_flow.vbs`.
2. Använd Tab/Shift+Tab och NVDA:s läsning av fokuserat objekt. Kontrollera att knappars och fältens text är begriplig och att vald, avaktiverad och redigerbar status inte missförstås.
3. Kontrollera fakturalistans kolumnrubriker, radvärden och skriftliga statuskolumn. Högerklicksmenyn ska vara användbar utan mus.
4. Upprepa 200 %- och högkontraststegen med Windows **Inställningar → Hjälpmedel → Kontrastteman**.
5. Dokumentera särskilt eventuella fält där Tk bara exponerar widgettyp eller råtext. En automatisk färg- eller fokuskontroll får inte räknas som godkänd NVDA-uppläsning.

## macOS + VoiceOver

1. Starta VoiceOver med **Cmd+F5** och appen via Python Launcher utan Terminal.
2. Använd Tab/Shift+Tab samt VoiceOver-tangenterna för att granska kontroller, menyerna, fakturalistan och dialogerna.
3. Aktivera **Systeminställningar → Hjälpmedel → Bildskärm → Öka kontrast** medan appen är öppen och kontrollera automatisk palettväxling.
4. Upprepa 200 %-testet och kontrollera att scrollade fält och åtgärdsknappar läses upp när de får fokus.

## Linux + Orca

1. Starta Orca på det skrivbord som ska stödjas och appen med samma Python-miljö som vid normal användning.
2. Kontrollera fokus, menyerna, fakturalistan, formulären och dialogisoleringen med Orca aktivt.
3. Aktivera skrivbordets högkontrastläge eller HighContrast-tema. GNOME/GTK detekteras automatiskt; dokumentera resultatet separat för andra skrivbordsmiljöer.
4. Upprepa 200 %- och scrolltesterna. Xvfb-testerna i CI är tekniska Tk-tester och ersätter inte den här Orca-genomkörningen.

## Godkännandekriterier

- Ingen åtgärd blir oåtkomlig vid 200 % text eller mindre fönster.
- Fokus är alltid synligt och dialoger har var sin fokusordning.
- Systemets högkontrastläge aktiveras och avaktiveras utan omstart eller ändrade arbetsdata.
- Skärmläsarens uppläsning är dokumenterad separat från den automatiska CI-statusen.
- P1/P2, e-post, fakturadata, PDF-innehåll, historik och säkerhetskopior beter sig som tidigare.
