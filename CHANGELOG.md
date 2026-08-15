# Changelog

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
