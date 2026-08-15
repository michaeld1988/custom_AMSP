# Changelog

## 1.2.0 – Assistent

### Neu: optionaler Kalibrierungs-Assistent

Knopf **🧙 Assistent** im Hauptfenster, vier Schritte. Rein optional – alles,
was er macht, geht auch weiterhin über Drop-Zone und Zuordnungs-Dialog.

* **Schritt 1 – Lights**: per Drop oder Ordnerauswahl. Es darf gleich der
  Ordner mit allen Daten sein; erkannte Nächte werden mit Objekt, Filter,
  Belichtungszeit und Frame-Zahl aufgelistet.
* **Schritt 2 – Kalibrierung**: alles, was noch fehlt. Zusätzlich werden
  **Dark-Flats am Dateinamen erkannt** – `darkflat`, `dark_flat`, `dark-flat`,
  `dark.flat`, `dark flat` und dieselben vier mit vertauschten Wörtern.
  Umgestufte Dateien werden aufgelistet, die Regel ist abschaltbar und
  umkehrbar. Nur der Dateiname zählt, nicht der Ordnername.
* **Schritt 3 – Zuordnung pro Nacht**: eine Zeile je Nacht mit Bias, Dark,
  Dark-Flat und Flat. Vorausgefüllt wird immer eine konkrete Quelle statt
  „Auto", damit sichtbar ist, was verwendet wird. Pro Art ein Knopf
  **„… auf alle Nächte"** – der Fall Dark-Bibliothek.
* **Schritt 4 – Prüfung**:
  * Belichtungszeit Dark ↔ Lights, Standardtoleranz **±5 s**
  * Belichtungszeit Dark-Flat ↔ Flats, dieselbe Toleranz
  * Datum Flat ↔ Nacht der Lights, Standardtoleranz **±1 Tag** – ein Flat vom
    15.08. gehört nicht zur Nacht vom 13. auf den 14., ein Flat vom Nachmittag
    des 14. dagegen schon
  * Zeilen, die noch auf „Auto" stehen, werden gemeldet
  * beide Toleranzen einstellbar; Warnungen müssen bestätigt werden, bevor
    „Übernehmen" freigeschaltet wird
* Das Ergebnis fließt in dieselben Zuordnungstabellen wie der Dialog – der
  Assistent ist eine Oberfläche, kein zweiter Codepfad.

### Weitere Änderungen

* Die Vorauswahl für Dark-Flats nimmt den Bias, wenn kein Dark innerhalb der
  Toleranz zur Belichtungszeit der Flats passt. Ein 300-s-Dark ist kein
  Dark-Flat für 3-s-Flats.
* `DropZone` lässt sich beschriften und wird von den Assistenten-Seiten
  wiederverwendet.
* Auswahllisten für Kalibrierungsquellen kommen aus einer gemeinsamen
  Funktion, damit Dialog und Assistent identische Quellen-IDs erzeugen.
* Testsuite auf 86 Tests erweitert; `python3 tests/run_all.py` führt alles aus.

## 1.1.0 – Custom AMSP (Fork von AMSP 1.0.17)

### Neu: manuelle Zuordnung der Kalibrierungs-Frames

* Jede Kalibrierungsquelle bekommt eine stabile ID, die nicht aus dem
  Aufnahmezeitpunkt abgeleitet ist: Rohframe-Gruppen (`subs:…`), fertige
  Master und External-Dateien (`file:…`), synthetischer Bias, „keine".
* Neuer Dialog **🎯 Calibration Assignment**
  * Reiter *Lights*: Bias / Dark / Flat pro Gruppe aus
    Objekt × Nacht × Filter × Belichtungszeit
  * Reiter *Flats*: Bias bzw. Dark-Flat pro Flat-Gruppe
  * „Copy first row to all rows" und „Reset tab to Auto"
  * Voreinstellung jeder Zeile ist *Auto* – ohne Eingriff bleibt das
    bisherige Verhalten unverändert
* Darks lassen sich über alle Nächte poolen (`Dark subs · all nights · 300s`),
  wodurch eine Dark-Bibliothek direkt auswählbar ist.
* Zuordnungen werden in der Konfigurationsdatei gespeichert und überleben
  einen Neustart.
* **Strict-Modus** (Pipeline-Optionen): keinerlei automatische Zuordnung.
  Alles, was auf *Auto* steht, bleibt unkalibriert, statt über das Datum
  geraten zu werden.
* Master, die von einer Zuordnung referenziert werden, werden auch dann
  gebaut, wenn die automatische Bedarfsprüfung sie übersprungen hätte
  (ungenutzter Filter, ungenutzte Belichtungszeit).
* Zugeordnete Master heißen `cal_*.fit` und tauchen dadurch nicht als
  Kandidaten in den automatischen Suchen (`master-bias*`, `master-dark_*`,
  `master-flat-*`) anderer Gruppen auf.
* Gleiche Frames werden nicht zweimal gestackt: eine „all nights"-Quelle aus
  nur einer Nacht verwendet das bereits gebaute Master dieser Nacht.

### Weitere Änderungen

* Kontextmenü: **Mark as Master frame / Mark as Sub frame**. Die
  Master-Erkennung hängt an `STACKCNT > 1`, das viele Programme nicht
  schreiben – ein fertiges Master wäre sonst erneut gestackt worden.
* Kontextmenü: Dateityp-Korrektur gilt jetzt auch für Master. Ein Master-Flat
  mit falschem `IMAGETYP` war sonst nicht als Flat zuordenbar.
* Konfigurationsdatei heißt `custom_amsp.json`, damit Custom AMSP und das
  Original nebeneinander laufen können.
* Testsuite (38 Tests), lauffähig ohne Siril: `sirilpy` wird gestubbt, Qt
  läuft offscreen.

### Bugfixes im übernommenen Code

* Die Option „Save master frames to output/masters/" wurde nie an die Engine
  durchgereicht – `keep_masters` blieb immer auf dem Default `True`, die
  Checkbox war wirkungslos.
* Die Cross-Stack-Ausrichtung protokollierte sich als „Phase 6" von 5.
* Ein beschädigter oder von Hand editierter Eintrag in der Konfigurationsdatei
  konnte das Öffnen des Fensters verhindern; alle Ebenen werden jetzt
  typgeprüft.

---

## Upstream

Die Historie von AMSP bis 1.0.17 steht im Kopf von `Custom_AMSP.py`.
AMSP © 2026 Cyril Richard, GPL-3.0-or-later.
