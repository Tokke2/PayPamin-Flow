PayPamin Flow – tryckfiler / print files
========================================

Den här mappen följer med appens releasepaket. Du behöver inte ladda ner
något separat: filerna finns redan i den installerade appen under assets/print/
och kan öppnas direkt från appen via Arkiv → Öppna tryckfiler.

Innehåll
--------
paypamin_logo_print.svg        Vektororiginal, plana färger (redigerbart)
paypamin_logo_print.pdf         Tryckfärdig PDF, vektor, 90 mm bred
paypamin_logo_print.png         Förhandsvisning 2400 px på vit botten

paypamin_logo_print_mono.svg   Enfärgsoriginal (stämpel, gravyr, etikett)
paypamin_logo_print_mono.pdf   Tryckfärdig PDF, en färg
paypamin_logo_print_mono.png   Förhandsvisning 2400 px

Rekommendation till tryckeriet
------------------------------
- Skicka PDF-filen. Den är ren vektor: inga rasterbilder, inga inbäddade
  typsnitt och ingen genomskinlighet.
- PDF:en är 98 x 29,9 mm inklusive 4 mm fritt utrymme runt märket.
  Skala proportionellt; ändra aldrig höjd och bredd separat.
- Minsta bredd för tryck: 25 mm. Under det blir bockens kontur otydlig.
- Fritt utrymme runt logotypen: minst 4 mm på alla sidor.
- Färger (RGB i originalet, konverteras till CMYK av tryckeriet):
    Mörkblå   #0F2F63
    Ljusblå   #1B5AA8
    Turkos    #0B7F79  (bock)
    Vit       #FFFFFF
  Kontrollera alltid en färgproof före större upplagor; turkos kan ligga
  utanför CMYK-gamut och då behöver tryckeriet justera mättnaden.
- Enfärgsversionen används när bara en färg är tillgänglig. Den fungerar
  som svart på vitt och inverterad (vit på mörk botten).

Typografi
---------
Ordmärket är omvandlat till konturer. Typsnittet är Inter, publicerat under
SIL Open Font License 1.1. Licensen kräver ingen medföljande fil när bara
konturerna används. Logotypen får inte sättas om eller ändras.

Skapare och copyright
---------------------
Rickard Längkvist. Copyright © 2026 Rickard Längkvist.

Regenerera filerna
------------------
Från repositoryts rot: python assets/build_icons.py
Vektorn är källan; allt annat rastreras eller exporteras från den.
